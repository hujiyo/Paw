"""模型协议适配。

对外只暴露 build_provider：按配置里的 style（必要时按 URL 推断）选一个适配器。
新增协议只需要在这里加一个分支和一个 Provider 子类，业务层不动。
"""

from typing import Any, Dict, Optional

from core.providers.anthropic import AnthropicProvider
from core.providers.base import (
    ChatRequest,
    ChatResult,
    LLMError,
    Provider,
    Usage,
)
from core.providers.openai import AzureProvider, OpenAIProvider

__all__ = [
    "build_provider",
    "detect_style",
    "AnthropicProvider",
    "AzureProvider",
    "OpenAIProvider",
    "ChatRequest",
    "ChatResult",
    "LLMError",
    "Provider",
    "Usage",
]


def detect_style(url: str) -> str:
    lowered = (url or "").lower()
    if "anthropic" in lowered or lowered.rstrip("/").endswith("/messages"):
        return "anthropic"
    if "openai.azure.com" in lowered or "/deployments/" in lowered:
        return "azure"
    return "openai"


def build_provider(
    url: str,
    key: str,
    style: str = "auto",
    extra_body: Optional[Dict[str, Any]] = None,
) -> Provider:
    resolved = (style or "auto").strip().lower()
    if resolved == "auto":
        resolved = detect_style(url)
    if resolved == "anthropic":
        return AnthropicProvider(url, key, extra_body)
    if resolved == "azure":
        return AzureProvider(url, key, extra_body)
    if resolved != "openai":
        raise ValueError(f"未知的接口协议: {style}")
    return OpenAIProvider(url, key, extra_body)
