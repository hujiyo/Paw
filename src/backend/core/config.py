#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""应用配置：单一配置源。

配置文件位置由环境变量 PAW_CONFIG_DIR 决定（Electron 传入 userData 目录）。
未设置时回退到 ~/.paw，保证后端可独立运行。

密钥只存在于配置文件，不进入仓库。仓库内不再提供 config.yaml。
"""

import os
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

CONFIG_FILE_NAME = "config.yaml"


@dataclass
class IdentityConfig:
    name: str = "Paw"
    username: str = "hujiyo"
    honey: str = "老公"


@dataclass
class ApiConfig:
    key: str = ""
    url: str = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
    model: Optional[str] = None


@dataclass
class MemoryConfig:
    enabled: bool = False
    embedding_url: str = "http://localhost:1234/v1/embeddings"
    embedding_key: str = ""
    embedding_model: str = "text-embedding-qwen3-embedding-0.6b"


@dataclass
class RecallConfig:
    enabled: bool = True
    threshold: float = 0.36


@dataclass
class TerminalConfig:
    shell: str = "powershell"
    encoding: str = "utf-8"
    buffer_size: int = 24


@dataclass
class WebConfig:
    search_engine: str = "duckduckgo"
    max_results: int = 5
    page_size: int = 8192
    use_jina_reader: bool = True
    custom_search_api: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceConfig:
    """默认工作目录。空字符串表示用户主目录。"""

    home_dir: str = ""


@dataclass
class ContextConfig:
    """上下文预算配置。

    max_tokens 是整个请求（system + 历史 + 工具 schema）共享的预算上限。
    keep_recent_turns 是压缩时无条件保留的最近轮次数量。
    """

    max_tokens: int = 64000
    keep_recent_turns: int = 4


@dataclass
class AppConfig:
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    recall: RecallConfig = field(default_factory=RecallConfig)
    terminal: TerminalConfig = field(default_factory=TerminalConfig)
    web: WebConfig = field(default_factory=WebConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    theme: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def config_dir() -> Path:
    raw = os.getenv("PAW_CONFIG_DIR")
    path = Path(raw) if raw else Path.home() / ".paw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    raw = os.getenv("PAW_DATA_DIR")
    path = Path(raw) if raw else Path.home() / ".paw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


def _merge_dataclass(cls, raw: Any):
    """把 dict 合并进 dataclass，忽略未知字段，保持向后兼容。"""
    if not isinstance(raw, dict):
        return cls()
    default = cls()
    kwargs = {}
    for name in default.__dataclass_fields__:
        if name in raw:
            kwargs[name] = raw[name]
    return cls(**kwargs)


def _legacy_config_path() -> Optional[Path]:
    """旧版本把 config.yaml 放在 backend 源码目录。"""
    candidate = Path(__file__).resolve().parent.parent / "config.yaml"
    return candidate if candidate.exists() else None


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        legacy = _legacy_config_path()
        if legacy is not None:
            shutil.copyfile(legacy, path)
    raw: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[Config] 读取失败 {path}: {e}")
            raw = {}

    return AppConfig(
        identity=_merge_dataclass(IdentityConfig, raw.get("identity")),
        api=_merge_dataclass(ApiConfig, raw.get("api")),
        memory=_merge_dataclass(MemoryConfig, raw.get("memory")),
        recall=_merge_dataclass(RecallConfig, raw.get("recall")),
        terminal=_merge_dataclass(TerminalConfig, raw.get("terminal")),
        web=_merge_dataclass(WebConfig, raw.get("web")),
        # 兼容旧配置：system.chunk_size / system.home_dir
        context=_merge_dataclass(ContextConfig, raw.get("context") or {
            "max_tokens": (raw.get("system") or {}).get("chunk_size", 64000)
        }),
        workspace=_merge_dataclass(WorkspaceConfig, raw.get("workspace") or {
            "home_dir": (raw.get("system") or {}).get("home_dir", "")
        }),
        theme=raw.get("theme") or {},
    )


def save_config(config: AppConfig) -> None:
    path = config_path()
    payload = config.to_dict()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def public_config(config: AppConfig) -> Dict[str, Any]:
    """返回给前端的配置原样返回。

    这是本机回环接口，只有本机进程能访问；如果把 key 打码，设置界面保存时
    会把打码值写回去，导致密钥被破坏。
    """
    return config.to_dict()
