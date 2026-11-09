#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模型客户端：业务层唯一入口。

它自己不解析任何报文，只做三件事：
    - 持有当前配置与模型名（配置变更时由应用层重建）
    - 把请求参数与厂商私有字段组装成 ChatRequest
    - 把真实用量回灌给 token 计数器，供上下文预算使用

协议差异全部由 core/providers 消化。出错一律抛出 LLMError，
kind 标明类别，调用方据此决定是压缩还是报错。
"""

from typing import Any, Callable, Dict, List, Optional

from core.providers import build_provider
from core.providers.base import (
    ChatRequest,
    ChatResult,
    LLMError,
    Provider,
    Usage,
)
from core.tokens import DEFAULT_COUNTER, count_json, count_messages_raw

__all__ = ["LLMClient", "LLMError", "ChatResult", "Usage"]


class LLMClient:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        *,
        style: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        extra_body: Optional[Dict[str, Any]] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider: Provider = build_provider(
            api_url, api_key, style, extra_body
        )

    def reconfigure(
        self,
        api_url: str,
        api_key: str,
        model: str,
        *,
        style: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = build_provider(
            api_url, api_key, style, extra_body
        )

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        on_reasoning: Optional[Callable[[str], None]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: Optional[bool] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> ChatResult:
        request = ChatRequest(
            messages=messages,
            tools=tools if self.provider.supports_tools else None,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
            stream=self.provider.supports_stream if stream is None else stream,
            extra_body=dict(extra_body or {}),
        )
        result = await self.provider.chat(
            model or self.model,
            request,
            on_delta or (lambda _text: None),
            on_reasoning or (lambda _text: None),
        )
        self._record_usage(messages, request.tools, result.usage)
        return result

    async def list_models(self, model: str = "") -> List[str]:
        return await self.provider.list_models(model or self.model)

    @staticmethod
    def _record_usage(
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        usage: Usage,
    ) -> None:
        """用服务端真实 token 数校准估算比例。

        prompt_tokens 包含工具 schema，而消息本身不含；校准前必须先把
        工具占用的部分减掉，否则每次都会把系数往大推。
        只在服务端确实报告了用量时校准；没报告的厂商维持启发式值。
        """
        prompt_tokens = usage.prompt_tokens
        if prompt_tokens <= 0 or not messages:
            return
        tools_raw = count_json(tools) if tools else 0
        raw_total = count_messages_raw(messages)
        if raw_total <= 0:
            return
        # 工具部分的分母也是估算值，按同一比例扣除
        if tools_raw > 0:
            raw_total += tools_raw
        DEFAULT_COUNTER.calibrate(raw_total, prompt_tokens)
