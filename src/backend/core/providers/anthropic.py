#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Anthropic Messages API 适配。

与 OpenAI 的差异集中在四处，全部在这里消化，业务层拿到的仍然是
ChatRequest / ChatResult：

    1. system 提示词是顶层字段，不是 messages 里的一条。
    2. 工具调用是 content block（tool_use / tool_result），不是独立字段。
    3. 鉴权是 x-api-key + anthropic-version，不是 Bearer。
    4. 流式事件是具名事件，文本与工具参数各自一套 delta。
"""

import json
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from core.providers.base import (
    ChatRequest,
    ChatResult,
    LLMError,
    Provider,
    Usage,
    base_url,
    fetch_model_list,
)

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    name = "anthropic"
    supports_reasoning = True

    def __init__(self, url: str, key: str, extra_body: Optional[Dict[str, Any]] = None):
        super().__init__(url, key, extra_body)
        if not self.url:
            self.url = "https://api.anthropic.com/v1/messages"
        # 没有字段可以让 Anthropic 返回 stream 用量以外的额外统计
        self.supports_usage = True

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
        if self.key:
            headers["x-api-key"] = self.key
        return headers

    # ---------- 请求翻译 ----------

    def build_payload(self, model: str, request: ChatRequest) -> Dict[str, Any]:
        system_parts: List[str] = []
        messages: List[Dict[str, Any]] = []

        for message in request.messages:
            role = message.get("role")
            if role == "system":
                text = message.get("content")
                if isinstance(text, str) and text:
                    system_parts.append(text)
                continue
            converted = self._convert_message(message)
            if converted is None:
                continue
            # Anthropic 要求 user/assistant 交替；连续同角色的块合并为一条
            if messages and messages[-1]["role"] == converted["role"]:
                messages[-1]["content"].extend(converted["content"])
            else:
                messages.append(converted)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            # Anthropic 的温度范围是 0~1，超出会被拒绝
            "temperature": min(max(request.temperature, 0.0), 1.0),
            "stream": request.stream,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.tools and self.supports_tools:
            payload["tools"] = [
                {
                    "name": tool["function"]["name"],
                    "description": tool["function"].get("description", ""),
                    "input_schema": tool["function"].get("parameters") or {
                        "type": "object", "properties": {}
                    },
                }
                for tool in request.tools
            ]
        payload.update(request.extra_body)
        payload.update(self.extra_body)
        return payload

    @staticmethod
    def _convert_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        role = message.get("role")
        if role == "tool":
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": message.get("tool_call_id") or "",
                    "content": message.get("content") or "",
                }],
            }
        if role == "assistant":
            blocks: List[Dict[str, Any]] = []
            text = message.get("content")
            if isinstance(text, str) and text:
                blocks.append({"type": "text", "text": text})
            for tool_call in message.get("tool_calls") or []:
                fn = tool_call.get("function") or {}
                raw_args = fn.get("arguments") or "{}"
                if isinstance(raw_args, str):
                    try:
                        parsed = json.loads(raw_args) if raw_args.strip() else {}
                    except json.JSONDecodeError:
                        parsed = {}
                else:
                    parsed = raw_args
                blocks.append({
                    "type": "tool_use",
                    "id": tool_call.get("id") or "",
                    "name": fn.get("name") or "",
                    "input": parsed if isinstance(parsed, dict) else {},
                })
            if not blocks:
                return None
            return {"role": "assistant", "content": blocks}
        if role == "user":
            text = message.get("content")
            if not isinstance(text, str) or not text:
                return None
            return {"role": "user", "content": [{"type": "text", "text": text}]}
        return None

    # ---------- 响应翻译 ----------

    async def chat(
        self,
        model: str,
        request: ChatRequest,
        on_delta: Callable[[str], None],
        on_reasoning: Callable[[str], None],
    ) -> ChatResult:
        payload = self.build_payload(model, request)
        session, response = await self._post(
            _messages_endpoint(self.url), self._headers(), payload, timeout=180
        )
        try:
            if request.stream:
                return await self._read_stream(response, on_delta, on_reasoning)
            return self._read_full(await response.json())
        finally:
            response.release()
            await session.close()

    async def _read_stream(
        self,
        response,
        on_delta: Callable[[str], None],
        on_reasoning: Callable[[str], None],
    ) -> ChatResult:
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        # block index -> 正在拼装的工具调用
        pending_tools: Dict[int, Dict[str, Any]] = {}
        finish_reason = "stop"
        usage = Usage()

        async for event in self._sse_events(response):
            kind = event.get("type")
            if kind == "message_start":
                usage = _merge_usage(usage, event.get("message", {}).get("usage"))
            elif kind == "content_block_start":
                block = event.get("content_block") or {}
                index = event.get("index", 0)
                if block.get("type") == "tool_use":
                    pending_tools[index] = {
                        "id": block.get("id") or "",
                        "type": "function",
                        "function": {
                            "name": block.get("name") or "",
                            "arguments": _json_text(block.get("input")),
                        },
                    }
            elif kind == "content_block_delta":
                index = event.get("index", 0)
                delta = event.get("delta") or {}
                delta_type = delta.get("type")
                if delta_type == "text_delta":
                    text = delta.get("text") or ""
                    if text:
                        content_parts.append(text)
                        if on_delta:
                            on_delta(text)
                elif delta_type == "thinking_delta":
                    thought = delta.get("thinking") or ""
                    if thought:
                        reasoning_parts.append(thought)
                        if on_reasoning:
                            on_reasoning(thought)
                elif delta_type == "input_json_delta":
                    slot = pending_tools.get(index)
                    if slot is not None:
                        slot["function"]["arguments"] += delta.get("partial_json") or ""
            elif kind == "content_block_stop":
                index = event.get("index", 0)
                slot = pending_tools.pop(index, None)
                if slot is not None:
                    # 流式过程中 arguments 初始为空字符串，结束时统一成对象
                    if not slot["function"]["arguments"].strip():
                        slot["function"]["arguments"] = "{}"
                    tool_calls.append(slot)
            elif kind == "message_delta":
                delta = event.get("delta") or {}
                finish_reason = _map_stop_reason(delta.get("stop_reason")) or finish_reason
                usage = _merge_usage(usage, event.get("usage"))
            elif kind == "error":
                error = event.get("error") or {}
                raise LLMError(
                    f"模型返回错误: {error.get('message') or error.get('type')}",
                    kind="upstream",
                )

        content = "".join(content_parts) if content_parts else None
        reasoning = "".join(reasoning_parts) if reasoning_parts else None
        return ChatResult(
            content=content,
            reasoning=reasoning,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    @staticmethod
    def _read_full(data: Dict[str, Any]) -> ChatResult:
        blocks = data.get("content") or []
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for block in blocks:
            block_type = block.get("type")
            if block_type == "text":
                content_parts.append(block.get("text") or "")
            elif block_type == "thinking":
                reasoning_parts.append(block.get("thinking") or "")
            elif block_type == "tool_use":
                tool_calls.append({
                    "id": block.get("id") or "",
                    "type": "function",
                    "function": {
                        "name": block.get("name") or "",
                        "arguments": _json_text(block.get("input")),
                    },
                })
        return ChatResult(
            content="".join(content_parts) or None,
            reasoning="".join(reasoning_parts) or None,
            tool_calls=tool_calls,
            finish_reason=_map_stop_reason(data.get("stop_reason")) or "stop",
            usage=_merge_usage(Usage(), data.get("usage")),
        )

    async def _sse_events(self, response):
        """Anthropic 的 SSE 带具名事件，事件名在 event: 行里。"""
        event_name = ""
        data_lines: List[str] = []
        async for raw in response.content:
            line = raw.decode("utf-8", errors="ignore").rstrip("\r\n")
            if not line:
                if data_lines:
                    payload = _json_or_none("\n".join(data_lines))
                    if payload is not None:
                        if event_name and "type" not in payload:
                            payload["type"] = event_name
                        yield payload
                event_name = ""
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            payload = _json_or_none("\n".join(data_lines))
            if payload is not None:
                if event_name and "type" not in payload:
                    payload["type"] = event_name
                yield payload

    # ---------- 模型列表 ----------

    async def list_models(self, model: str = "") -> List[str]:
        return await fetch_model_list(self._base_url(), self._headers())


def _messages_endpoint(url: str) -> str:
    """把用户填的地址补全成 /v1/messages。

    只填域名或 /v1 时直接 POST 会得到 404，与 OpenAI 适配器同理。
    """
    parts = urlsplit(url or "")
    path = parts.path.rstrip("/")
    if path.endswith("/messages"):
        return url
    return base_url(url) + "/v1/messages"


def _json_or_none(text: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _json_text(value: Any) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value or "{}"
    return json.dumps(value, ensure_ascii=False)


def _map_stop_reason(reason: Optional[str]) -> Optional[str]:
    """Anthropic 的停止原因映射到 OpenAI 词汇，业务层只需认一套。"""
    return {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
        "refusal": "content_filter",
    }.get(reason or "", reason)


def _merge_usage(usage: Usage, raw: Any) -> Usage:
    if not isinstance(raw, dict):
        return usage
    if raw.get("input_tokens"):
        usage.prompt_tokens = int(raw["input_tokens"])
    if raw.get("output_tokens"):
        usage.completion_tokens = int(raw["output_tokens"])
    return usage
