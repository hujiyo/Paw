#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OpenAI 兼容协议适配（含 Azure OpenAI）。

这是当前事实标准：智谱、DeepSeek、通义、Kimi、MiniMax、豆包、SiliconFlow、
OpenRouter、Ollama /v1、LM Studio、vLLM 都照抄这份报文。
"""

import json
from typing import Any, Callable, Dict, List, Optional

import aiohttp

from core.providers.base import (
    ChatRequest,
    ChatResult,
    LLMError,
    Provider,
    Usage,
    describe_status,
    fetch_models,
)


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, url: str, key: str, extra_body: Optional[Dict[str, Any]] = None):
        super().__init__(url, key, extra_body)
        self.supports_reasoning = True

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def build_payload(self, model: str, request: ChatRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
            self.max_tokens_field: request.max_tokens,
            "stream": request.stream,
        }
        if request.stream:
            # 让服务端在最后一个 chunk 带上真实用量；不支持的厂商会忽略
            payload["stream_options"] = {"include_usage": True}
        if request.tools and self.supports_tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"
        payload.update(request.extra_body)
        payload.update(self.extra_body)
        return payload

    async def chat(
        self,
        model: str,
        request: ChatRequest,
        on_delta: Callable[[str], None],
        on_reasoning: Callable[[str], None],
    ) -> ChatResult:
        payload = self.build_payload(model, request)
        session, response = await self._post(self.url, self._headers(), payload, timeout=180)
        try:
            content_type = response.headers.get("Content-Type", "")
            if request.stream and "text/event-stream" in content_type:
                return await self._read_stream(response, on_delta, on_reasoning)
            # 服务端忽略 stream=true 直接返回整体 JSON 时按非流式处理，
            # 否则用户会看到一条空回复
            return self._read_full(await response.json())
        finally:
            response.release()
            await session.close()

    # ---------- 解析 ----------

    async def _read_stream(
        self,
        response: aiohttp.ClientResponse,
        on_delta: Callable[[str], None],
        on_reasoning: Callable[[str], None],
    ) -> ChatResult:
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls: Dict[int, Dict[str, Any]] = {}
        finish_reason = "stop"
        usage = Usage()
        first_text = True

        async for chunk in self._sse_frames(response):
            if chunk.get("usage"):
                usage = _parse_usage(chunk["usage"])
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}

            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                reasoning_parts.append(reasoning)
                if on_reasoning:
                    on_reasoning(reasoning)

            text = delta.get("content")
            if isinstance(text, str) and text:
                if first_text:
                    # 部分模型首个片段自带前导换行
                    text = text.lstrip("\n")
                    if not text:
                        continue
                    first_text = False
                content_parts.append(text)
                if on_delta:
                    on_delta(text)
            elif isinstance(text, list):
                # 少数实现返回分段数组
                for piece in text:
                    if isinstance(piece, dict) and piece.get("type") == "text":
                        value = piece.get("text") or ""
                        if value:
                            content_parts.append(value)
                            if on_delta:
                                on_delta(value)

            for tc_delta in delta.get("tool_calls") or []:
                index = tc_delta.get("index", 0)
                slot = tool_calls.setdefault(
                    index,
                    {"id": "", "type": "function",
                     "function": {"name": "", "arguments": ""}},
                )
                if tc_delta.get("id"):
                    slot["id"] = tc_delta["id"]
                fn = tc_delta.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                raw_args = fn.get("arguments")
                if isinstance(raw_args, str):
                    slot["function"]["arguments"] += raw_args
                elif isinstance(raw_args, dict):
                    # 个别网关把 arguments 直接给出对象，统一成字符串，
                    # 避免下游解析时类型不一致
                    slot["function"]["arguments"] = json.dumps(
                        raw_args, ensure_ascii=False
                    )

        ordered = []
        for index in sorted(tool_calls):
            slot = tool_calls[index]
            if not slot["id"]:
                slot["id"] = f"call_{index}"
            ordered.append(slot)

        content = "".join(content_parts) if content_parts else None
        reasoning = "".join(reasoning_parts) if reasoning_parts else None
        return ChatResult(
            content=content,
            reasoning=reasoning,
            tool_calls=ordered,
            finish_reason=finish_reason,
            usage=usage,
        )

    @staticmethod
    def _read_full(data: Dict[str, Any]) -> ChatResult:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("模型返回缺少 choices", kind="upstream")
        message = choices[0].get("message") or {}
        return ChatResult(
            content=message.get("content"),
            reasoning=message.get("reasoning_content") or message.get("reasoning"),
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choices[0].get("finish_reason") or "stop",
            usage=_parse_usage(data.get("usage") or {}),
        )

    # ---------- 模型列表 ----------

    async def list_models(self, model: str = "") -> List[str]:
        candidates = [f"{self._base_url()}/models"]
        # 用户只填了域名或地址不带版本段时，模型列表通常在 /v1/models
        if "/v1" not in self._base_url():
            candidates.append(f"{self._base_url()}/v1/models")
        last: Optional[LLMError] = None
        for url in candidates:
            try:
                return await fetch_models(url, self._headers())
            except LLMError as e:
                last = e
                # 只有"地址不存在"才换下一个候选；鉴权失败换地址也没用
                if e.status != 404:
                    raise
        assert last is not None
        raise LLMError(
            f"获取模型列表失败：{'、'.join(candidates)} 均不可用（{last.message}）",
            kind=last.kind,
            status=last.status,
        )


class AzureProvider(OpenAIProvider):
    """Azure OpenAI：/openai/deployments/{deployment}/chat/completions。

    鉴权用 api-key 头，并且必须带 api-version 查询参数。deployment 名就是
    "模型名"，因此请求体里的 model 字段不参与路由。
    """

    name = "azure"

    def __init__(self, url: str, key: str, extra_body: Optional[Dict[str, Any]] = None):
        super().__init__(url, key, extra_body)
        self.api_version = "2024-10-21"

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["api-key"] = self.key
        return headers

    def build_payload(self, model: str, request: ChatRequest) -> Dict[str, Any]:
        payload = super().build_payload(model, request)
        # Azure 不支持 stream_options，会直接 400
        payload.pop("stream_options", None)
        return payload

    def _request_url(self) -> str:
        if "api-version=" in self.url:
            return self.url
        joiner = "&" if "?" in self.url else "?"
        return f"{self.url}{joiner}api-version={self.api_version}"

    async def chat(
        self,
        model: str,
        request: ChatRequest,
        on_delta: Callable[[str], None],
        on_reasoning: Callable[[str], None],
    ) -> ChatResult:
        payload = self.build_payload(model, request)
        session, response = await self._post(
            self._request_url(), self._headers(), payload, timeout=180
        )
        try:
            content_type = response.headers.get("Content-Type", "")
            if request.stream and "text/event-stream" in content_type:
                return await self._read_stream(response, on_delta, on_reasoning)
            return self._read_full(await response.json())
        finally:
            response.release()
            await session.close()

    async def list_models(self, model: str = "") -> List[str]:
        # Azure 的模型列表是"部署列表"，需要管理面权限，普通 key 取不到。
        # 返回空列表让上层提示用户手动填写 deployment 名。
        return []


def _parse_usage(raw: Dict[str, Any]) -> Usage:
    if not isinstance(raw, dict):
        return Usage()
    details = raw.get("completion_tokens_details") or {}
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        reasoning_tokens=int(details.get("reasoning_tokens") or 0),
    )
