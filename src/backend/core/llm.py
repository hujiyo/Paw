#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""LLM 客户端：统一的 OpenAI 兼容 chat/completions 调用。

只做一件事——把 messages + tools 发出去，把文本增量回调、把 tool_calls
组装好。不做重试、不做降级：出错以 LLMError 抛出，由 agent 层决定怎么展示。
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import aiohttp


class LLMError(Exception):
    """模型调用失败。message 是给用户看的中文描述。"""


@dataclass
class LLMResult:
    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"


class LLMClient:
    def __init__(self, api_url: str, api_key: str, model: str, timeout: float = 60.0):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        stream: bool = True,
        extra_params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> LLMResult:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if extra_params:
            payload.update(extra_params)

        client_timeout = aiohttp.ClientTimeout(total=timeout or self.timeout)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    headers=self._headers(),
                    timeout=client_timeout,
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise LLMError(f"模型接口返回 {response.status}: {body[:300]}")
                    if stream:
                        return await self._read_stream(response, on_delta)
                    return self._read_full(await response.json())
        except (asyncio.TimeoutError, TimeoutError):
            raise LLMError(f"模型请求超时（{timeout or self.timeout} 秒）")
        except aiohttp.ClientError as e:
            raise LLMError(f"模型网络请求失败: {e}")

    @staticmethod
    def _read_full(data: Dict[str, Any]) -> LLMResult:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("模型返回缺少 choices")
        message = choices[0].get("message") or {}
        return LLMResult(
            content=message.get("content"),
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choices[0].get("finish_reason") or "stop",
        )

    @staticmethod
    async def _read_stream(
        response: aiohttp.ClientResponse,
        on_delta: Optional[Callable[[str], None]],
    ) -> LLMResult:
        content_parts: List[str] = []
        tool_calls: Dict[int, Dict[str, Any]] = {}
        finish_reason = "stop"
        first_text = True

        async for raw in response.content:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue

            choice = choices[0]
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}

            text = delta.get("content")
            if text:
                # 首个片段去掉模型自带的前导换行
                if first_text:
                    text = text.lstrip("\n")
                    if not text:
                        continue
                    first_text = False
                content_parts.append(text)
                if on_delta:
                    on_delta(text)

            for tc_delta in delta.get("tool_calls") or []:
                index = tc_delta.get("index", 0)
                slot = tool_calls.setdefault(
                    index,
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tc_delta.get("id"):
                    slot["id"] = tc_delta["id"]
                fn = tc_delta.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]

        # 部分兼容接口不给 id，补齐以维持 tool_call/tool_result 配对
        ordered = []
        for index in sorted(tool_calls):
            slot = tool_calls[index]
            if not slot["id"]:
                slot["id"] = f"call_{index}"
            ordered.append(slot)

        content = "".join(content_parts) if content_parts else None
        return LLMResult(content=content, tool_calls=ordered, finish_reason=finish_reason)
