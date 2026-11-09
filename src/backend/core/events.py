#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""后端 → 前端的事件定义。

事件名是前后端契约：任何一端改名都必须同时改另一端。集中在这里
避免出现"后端发了、前端没人听"的幽灵事件。
"""

from dataclasses import dataclass
from typing import Any, Dict, Protocol


class EventSink(Protocol):
    """事件接收方。传输层（WebSocket）实现这个接口。

    emit 必须是同步且非阻塞的，保证调用顺序即发送顺序。
    """

    def emit(self, event: str, data: Dict[str, Any]) -> None: ...


# --- 流式回复 ---
ASSISTANT_STREAM_START = "assistant_stream_start"
ASSISTANT_STREAM_CHUNK = "assistant_stream_chunk"
ASSISTANT_STREAM_END = "assistant_stream_end"

# --- 工具 ---
TOOL_START = "tool_start"
TOOL_RESULT = "tool_result"

# --- 轮次 ---
TURN_END = "turn_end"

# --- 状态 ---
STATUS_UPDATE = "status_update"
SYSTEM_MESSAGE = "system_message"
SHOW_ERROR = "show_error"

# --- 会话 ---
SESSION_LIST = "session_list"
SESSION_LOAD = "session_load"
SESSION_LOADED = "session_loaded"
NEW_CHAT = "new_chat"

# --- 记忆 ---
SHOW_MEMORY = "show_memory"
MEMORY_RESULT = "memory_result"

# --- 其它视图 ---
TERMINAL_OUTPUT = "terminal_output"
TODOS_UPDATED = "todos_updated"
MODE_CHANGED = "mode_changed"

# --- 交互请求 ---
SHOW_MODEL_SELECTION = "show_model_selection"
REQUEST_INPUT = "request_input"
MODELS_FETCHED = "models_fetched"


@dataclass
class NullSink:
    """不发送任何事件的实现，用于测试或纯后端运行。"""

    def emit(self, event: str, data: Dict[str, Any]) -> None:
        return None
