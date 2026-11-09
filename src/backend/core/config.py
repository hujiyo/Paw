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
    """模型接入配置。

    style 决定用哪个协议适配器：openai / anthropic / azure；
    auto 时按 url 推断。temperature 与 max_tokens 是请求默认值，
    推理类模型经常需要把它们调高，因此不再写死在代码里。
    """

    key: str = ""
    url: str = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
    model: Optional[str] = None
    style: str = "auto"
    temperature: float = 0.7
    max_tokens: int = 8192
    # 厂商私有字段，原样并入请求体（例如 thinking、enable_search）
    extra_body: Dict[str, Any] = field(default_factory=dict)


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
    # 是否把模型返回的思维链展示给用户
    show_reasoning: bool = True


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


def typed_dataclass(cls, raw: Any):
    """按字段声明类型转换配置值。

    配置既可能来自手写 YAML，也可能来自前端表单（全部字符串）。不在这里
    统一转换，坏值会一路走到业务代码，在那里才以奇怪的异常形式炸开。
    """
    if not isinstance(raw, dict):
        return cls()
    default = cls()
    kwargs = {}
    for name, declared in default.__dataclass_fields__.items():
        if name not in raw:
            continue
        kwargs[name] = _coerce_value(cls.__name__, name, declared.type, raw[name])
    return cls(**kwargs)


def _coerce_value(class_name: str, field_name: str, type_hint: Any, value: Any) -> Any:
    hint = type_hint if isinstance(type_hint, str) else getattr(type_hint, "__name__", "")
    if value is None:
        return None
    try:
        if hint == "int":
            if isinstance(value, bool):
                raise TypeError("布尔值不能当整数")
            return int(value)
        if hint == "float":
            return float(value)
        if hint == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if hint == "str":
            return str(value)
        if hint.startswith("Optional"):
            return value
        if hint.startswith("Dict") or hint == "dict":
            if not isinstance(value, dict):
                raise TypeError("应为字典")
            return dict(value)
        return value
    except (TypeError, ValueError):
        raise ValueError(f"配置项 {class_name}.{field_name} 的类型不合法: {value!r}")


def _legacy_config_path() -> Optional[Path]:
    """旧版本把 config.yaml 放在 backend 源码目录。"""
    candidate = Path(__file__).resolve().parent.parent / "config.yaml"
    return candidate if candidate.exists() else None


def load_config() -> AppConfig:
    """从磁盘读取配置。坏值在这里就报出来，不带进运行时。"""
    path = config_path()
    if not path.exists():
        legacy = _legacy_config_path()
        if legacy is not None:
            shutil.copyfile(legacy, path)
    raw: Dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    try:
        return build_config(raw)
    except ValueError as e:
        raise ValueError(f"配置文件 {path} 有误: {e}")


def build_config(raw: Dict[str, Any]) -> AppConfig:
    """由原始 dict 构造配置，任何非法类型都会抛 ValueError。"""
    legacy_system = raw.get("system") or {}
    context_raw = raw.get("context")
    if not context_raw:
        context_raw = {"max_tokens": legacy_system.get("chunk_size", 64000)}
    workspace_raw = raw.get("workspace")
    if not workspace_raw:
        workspace_raw = {"home_dir": legacy_system.get("home_dir", "")}
    return AppConfig(
        identity=typed_dataclass(IdentityConfig, raw.get("identity")),
        api=typed_dataclass(ApiConfig, raw.get("api")),
        memory=typed_dataclass(MemoryConfig, raw.get("memory")),
        recall=typed_dataclass(RecallConfig, raw.get("recall")),
        terminal=typed_dataclass(TerminalConfig, raw.get("terminal")),
        web=typed_dataclass(WebConfig, raw.get("web")),
        context=typed_dataclass(ContextConfig, context_raw),
        workspace=typed_dataclass(WorkspaceConfig, workspace_raw),
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
