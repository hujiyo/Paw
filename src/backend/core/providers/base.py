#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模型适配层的公共部分。

这里定义业务层看到的唯一形状（ChatRequest / ChatResult），以及所有
协议都要用到的：SSE 解析、HTTP 重试、错误分类。适配器只负责
"把统一形状翻译成某个厂商的报文，再把回包翻译回来"。

错误分类的约定：
    LLMError.kind = "auth" | "rate_limit" | "context_overflow" | "network"
                    | "upstream" | "bad_request"
业务层按 kind 决定是重试、压缩上下文还是直接报给用户，不再靠字符串匹配。
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import aiohttp


class LLMError(Exception):
    def __init__(self, message: str, kind: str = "upstream", status: int = 0):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status = status

    def __str__(self) -> str:
        return self.message


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass
class ChatRequest:
    messages: List[Dict[str, Any]]
    tools: Optional[List[Dict[str, Any]]] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = True
    # 附加在请求顶层或 body 里的厂商私有字段，由配置提供
    extra_body: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResult:
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Usage = field(default_factory=Usage)

    @property
    def truncated(self) -> bool:
        """输出被上限截断。工具调用被截断时同样是 True。"""
        return self.finish_reason in ("length", "max_tokens", "MAX_TOKENS")


DeltaCallback = Callable[[str], None]


class Provider:
    """协议适配器基类。

    capabilities 决定请求里能放什么字段：不支持 tools 的模型不该收到
    工具定义，不支持流式的模型不该收到 stream=true。
    """

    name = "base"
    supports_tools = True
    supports_stream = True
    supports_reasoning = False
    supports_usage = True
    # 输出上限的字段名，各厂商不同
    max_tokens_field = "max_tokens"
    supports_parallel_tools = True

    def __init__(self, url: str, key: str, extra_body: Optional[Dict[str, Any]] = None):
        self.url = url or ""
        self.key = key or ""
        self.extra_body = dict(extra_body or {})

    # ---------- 子类实现 ----------

    async def chat(
        self,
        model: str,
        request: ChatRequest,
        on_delta: DeltaCallback,
        on_reasoning: DeltaCallback,
    ) -> ChatResult:
        raise NotImplementedError

    async def list_models(self, model: str = "") -> List[str]:
        raise NotImplementedError

    # ---------- 公共工具 ----------

    def _base_url(self) -> str:
        return base_url(self.url)

    async def _post(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
        retries: int = 2,
    ) -> Tuple[aiohttp.ClientSession, aiohttp.ClientResponse]:
        """发请求并处理瞬时错误，返回 (会话, 响应)。

        会话由调用方关闭：响应体还没读完就关会话会让流式解析拿到空内容。
        429 与 5xx 视为瞬时，按 Retry-After 或指数退避重试有限次数；
        其余 4xx 一次就抛出——重试不会让它变好。
        """
        last_error: Optional[LLMError] = None
        for attempt in range(retries + 1):
            session = aiohttp.ClientSession()
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            try:
                response = await session.post(
                    url, json=payload, headers=headers, timeout=client_timeout
                )
            except (asyncio.TimeoutError, TimeoutError):
                await session.close()
                last_error = LLMError(f"模型请求超时（{timeout} 秒）", kind="network")
                if attempt >= retries:
                    raise last_error
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            except aiohttp.ClientError as e:
                await session.close()
                last_error = LLMError(f"模型网络请求失败: {e}", kind="network")
                if attempt >= retries:
                    raise last_error
                await asyncio.sleep(1.5 * (attempt + 1))
                continue

            if response.status == 200:
                return session, response

            body = await response.text()
            kind, delay = classify_status(response.status, body, response.headers)
            error = LLMError(
                describe_status(response.status, body),
                kind=kind,
                status=response.status,
            )
            response.release()
            await session.close()
            last_error = error
            # 上下文超长与鉴权问题重试无意义
            if kind in ("context_overflow", "auth", "bad_request"):
                raise error
            if attempt < retries:
                await asyncio.sleep(delay)
                continue
            raise error
        if last_error is not None:
            raise last_error
        raise LLMError("模型请求失败", kind="upstream")

    @staticmethod
    async def _sse_frames(response: aiohttp.ClientResponse) -> AsyncIterator[Dict[str, Any]]:
        """按 SSE 规范切分事件。

        规范允许一个事件由多行 data: 组成，遇到空行才结束；直接在行上
        解析会让这类服务端（例如部分网关）返回的内容解析失败。
        """
        buffer: List[str] = []
        async for raw in response.content:
            line = raw.decode("utf-8", errors="ignore")
            if line in ("\r\n", "\n"):
                if buffer:
                    payload = "\n".join(buffer)
                    buffer = []
                    event = _parse_sse_payload(payload)
                    if event is not None:
                        yield event
                continue
            stripped = line.rstrip("\r\n")
            if stripped.startswith("data:"):
                buffer.append(stripped[5:].lstrip())
            elif stripped.startswith(":") or not stripped:
                continue
            # 其它字段（event:, id:, retry:）对本项目无意义
        if buffer:
            event = _parse_sse_payload("\n".join(buffer))
            if event is not None:
                yield event


def _parse_sse_payload(payload: str) -> Optional[Dict[str, Any]]:
    text = payload.strip()
    if not text or text == "[DONE]":
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_model_ids(data: Any) -> List[str]:
    """从 /models 返回体里取模型名。

    各家形状不一：字符串数组、对象数组、{data: [...]}、{models: [...]}。
    """
    if isinstance(data, list):
        if all(isinstance(item, str) for item in data):
            return list(data)
        return [
            item.get("id") or item.get("name") or ""
            for item in data if isinstance(item, dict)
        ]
    if not isinstance(data, dict):
        return []
    for key in ("data", "models"):
        items = data.get(key)
        if isinstance(items, list):
            return [
                item.get("id") or item.get("name") or ""
                for item in items if isinstance(item, dict)
            ]
    return []


async def fetch_model_list(base: str, headers: Dict[str, str]) -> List[str]:
    """从服务根地址取模型列表。

    用户可能只填了域名，模型列表通常在 /v1/models，因此 404 时再试一次；
    鉴权失败换地址也没用，直接抛出。
    """
    candidates = [f"{base}/models"]
    if "/v1" not in base:
        candidates.append(f"{base}/v1/models")
    last: Optional[LLMError] = None
    for url in candidates:
        try:
            return await fetch_models(url, headers)
        except LLMError as e:
            last = e
            if e.status != 404:
                raise
    assert last is not None
    raise LLMError(
        f"获取模型列表失败：{'、'.join(candidates)} 均不可用（{last.message}）",
        kind=last.kind,
        status=last.status,
    )


async def fetch_models(url: str, headers: Dict[str, str]) -> List[str]:
    """请求模型列表。失败抛出 LLMError，不返回空列表掩盖问题。"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                body = await response.text()
                if response.status != 200:
                    raise LLMError(
                        describe_status(response.status, body),
                        kind=classify_status(response.status, body)[0],
                        status=response.status,
                    )
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    raise LLMError("模型列表不是合法 JSON", kind="upstream")
    except (asyncio.TimeoutError, TimeoutError):
        raise LLMError("获取模型列表超时", kind="network")
    except aiohttp.ClientError as e:
        raise LLMError(f"获取模型列表失败: {e}", kind="network")

    ids = [item for item in extract_model_ids(data) if item]
    if not ids:
        raise LLMError("接口没有返回可用的模型列表", kind="upstream")
    return ids


def base_url(url: str) -> str:
    """从完整的 chat 端点反推出服务根地址。

    用户填的可能是 .../chat/completions、.../v1、甚至只填域名，
    这三种都要能推导出同一个 /models 地址。
    """
    parts = urlsplit(url or "")
    path = parts.path.rstrip("/")
    for suffix in ("/chat/completions", "/messages", "/completions"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


def chat_endpoint(url: str) -> str:
    """把用户填的地址补全成完整的 chat 端点。

    设置页只校验"地址能连通"，用户很可能只填到服务根地址或 /v1；
    直接把这些地址当端点 POST 会得到一个 nginx 404。完整端点原样返回。

    带版本段的服务（.../v1、.../paas/v4）只在末尾补 /chat/completions；
    裸域名才补 /v1/chat/completions，因为版本段属于厂商自己的路由。
    """
    parts = urlsplit(url or "")
    path = parts.path.rstrip("/")
    endpoint_suffixes = ("/chat/completions", "/completions", "/messages")
    if any(path.endswith(suffix) for suffix in endpoint_suffixes):
        return url
    # .../deployments/{name} 是 Azure 式路径，无法推断模型段
    if re.search(r"/deployments/", path):
        return url
    base = base_url(url)
    if re.search(r"/v\d", urlsplit(base).path):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


CONTEXT_OVERFLOW_HINTS = (
    "context length",
    "context_length",
    "maximum context",
    "too many tokens",
    "context window",
    "reduce the length",
    "prompt is too long",
    "input is too long",
    "上下文",
)


def classify_status(status: int, body: str, headers: Any = None):
    """把 HTTP 状态与响应体归类，返回 (kind, 建议等待秒数)。"""
    lowered = (body or "").lower()
    if any(hint in lowered for hint in CONTEXT_OVERFLOW_HINTS):
        return "context_overflow", 0
    if status == 401 or status == 403:
        return "auth", 0
    if status == 429:
        return "rate_limit", _retry_after(headers)
    if status >= 500:
        return "upstream", 2.0
    if status == 400:
        return "bad_request", 0
    return "upstream", 0


def _retry_after(headers: Any) -> float:
    if headers is None:
        return 2.0
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    try:
        return min(max(float(value), 0.5), 30.0)
    except (TypeError, ValueError):
        return 2.0


def describe_status(status: int, body: str) -> str:
    """把厂商的英文错误翻译成用户能看懂的一句话，并保留原始信息。"""
    snippet = (body or "").strip().replace("\n", " ")[:200]
    prefix = {
        400: "请求被拒绝",
        401: "鉴权失败，请检查 API Key",
        403: "没有访问权限",
        404: "接口地址不存在，请检查 API 地址",
        413: "请求体过大",
        429: "请求过于频繁（触发限流）",
        500: "模型服务内部错误",
        502: "模型服务网关错误",
        503: "模型服务暂时不可用",
        504: "模型服务超时",
    }.get(status)
    if prefix is None:
        prefix = "模型接口返回错误" if status >= 500 else "请求失败"
    return f"{prefix}（{status}）: {snippet}" if snippet else f"{prefix}（{status}）"
