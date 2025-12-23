#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web UI系统 - 重构版
负责启动Web服务并与前端进行WebSocket通信，精确复刻终端UI的交互逻辑。
"""

import asyncio
import json
import webbrowser
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from typing import List, Dict, Any

class WebUI:
    """
    Web UI, 替代终端UI, 通过WebSocket与前端交互。
    此版本实现了与ui.py的接口对齐，并使用ID追踪工具调用状态。
    """
    def __init__(self, host="127.0.0.1", port=8080):
        self.host = host
        self.port = port
        self.app = FastAPI()
        self.websocket: WebSocket = None
        self.chat_queue = asyncio.Queue()
        self.control_queue = asyncio.Queue()
        self._expect = None  # 控制输入预期类型（如 'model_choice'）
        self.ws_ready = asyncio.Event()
        self._pending: List[Dict[str, Any]] = []
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/", response_class=HTMLResponse)
        async def get_index():
            try:
                with open("templates/index.html", "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read())
            except FileNotFoundError:
                return HTMLResponse(content="Error: index.html not found.", status_code=500)

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.websocket = websocket
            self.ws_ready.set()
            # 连接建立后，立刻把积压消息发送给前端
            if self._pending:
                for payload in self._pending:
                    try:
                        await websocket.send_json(payload)
                    except Exception:
                        pass
                self._pending.clear()
            print("INFO:     WebSocket connection established.")
            try:
                while True:
                    data = await websocket.receive_text()
                    # 控制类输入（模型选择等）优先路由到 control_queue
                    if getattr(self, "_expect", None):
                        await self.control_queue.put(data)
                        self._expect = None
                    else:
                        await self.chat_queue.put(data)
            except WebSocketDisconnect:
                print("INFO:     WebSocket connection closed.")
                self.websocket = None

    async def send_message(self, event: str, data: Any):
        payload = {"event": event, "data": data}
        # 若 WebSocket 尚未就绪，先缓存，等连接后统一发送
        if not self.websocket:
            self._pending.append(payload)
            return
        try:
            await self.websocket.send_json(payload)
        except Exception as e:
            print(f"ERROR:    Failed to send WebSocket message: {e}")

    def run_server(self):
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        server = uvicorn.Server(config)
        print(f"INFO:     Starting Web UI on http://{self.host}:{self.port}")
        webbrowser.open(f"http://{self.host}:{self.port}")
        # uvicorn.run is blocking, so we need to run it in a separate thread
        # or use server.serve() which is async.
        return server.serve()

    # --- UI 兼容方法 --- (与 ui.py 对齐)

    def print_welcome(self):
        asyncio.create_task(self.send_message("welcome", {}))

    def print_goodbye(self):
        asyncio.create_task(self.send_message("goodbye", {}))

    def print_assistant(self, text: str, end: str = '', flush: bool = False):
        # 统一的流式输出：仅首次发送 start，之后持续发送 chunk
        if not hasattr(self, '_current_stream_id'):
            self._current_stream_id = str(uuid.uuid4())
            asyncio.create_task(self.send_message("assistant_stream_start", {"id": self._current_stream_id}))
        asyncio.create_task(self.send_message("assistant_stream_chunk", {"id": self._current_stream_id, "text": text}))
        # 不在这里结束，等待外部显式结束（_call_llm_with_tools 会调用 assistant_stream_end）

    def assistant_stream_end(self):
        if hasattr(self, '_current_stream_id'):
            asyncio.create_task(self.send_message("assistant_stream_end", {"id": self._current_stream_id}))
            del self._current_stream_id

    def show_tool_start(self, tool_call_id: str, tool_name: str, args_str: str):
        asyncio.create_task(self.send_message("tool_start", {
            "id": tool_call_id,
            "name": tool_name,
            "args": args_str
        }))

    def show_tool_result(self, tool_call_id: str, tool_name: str, display: dict, success: bool = True):
        asyncio.create_task(self.send_message("tool_result", {
            "id": tool_call_id,
            "name": tool_name,
            "display": display,
            "success": success
        }))

    async def get_user_input(self, prompt: str = None) -> str:
        if prompt:
            # 普通输入走聊天通道
            await self.send_message("request_input", {"prompt": prompt})
        return await self.chat_queue.get()

    def print_dim(self, text: str, **kwargs):
        asyncio.create_task(self.send_message("system_message", {"text": text, "type": "dim"}))

    def print_system(self, text: str, **kwargs):
        asyncio.create_task(self.send_message("system_message", {"text": text, "type": "system"}))

    def print_error(self, text: str):
        asyncio.create_task(self.send_message("system_message", {"text": text, "type": "error"}))

    def print_success(self, text: str):
        asyncio.create_task(self.send_message("system_message", {"text": text, "type": "success"}))

    def show_model_list(self, models: List[str]):
        asyncio.create_task(self.send_message("show_model_selection", {"models": models}))

    async def get_model_choice_async(self, prompt: str) -> str:
        # 标记下一条输入为模型选择，路由到 control_queue
        self._expect = "model_choice"
        await self.send_message("request_input", {"prompt": prompt, "type": "model_choice"})
        return await self.control_queue.get()

    def show_model_input_prompt(self):
        asyncio.create_task(self.send_message("request_input", {"prompt": "无法自动获取模型列表，请输入模型名称:", "type": "model_input"}))

    def show_model_selected(self, model: str):
        asyncio.create_task(self.send_message("system_message", {"text": f"已切换到模型: {model}", "type": "system"}))

    # --- 空操作方法，保持接口兼容性 ---
    def clear_screen(self): pass
    def show_status_bar(self, model: str = None, autostatus: dict = None, start_time=None):
        from datetime import datetime
        runtime_str = ""
        if start_time:
            runtime = datetime.now() - start_time
            runtime_str = str(runtime).split('.')[0]

        mode = ""
        if autostatus and isinstance(autostatus, dict):
            mode = autostatus.get('execution_mode', 'unknown')

        status_data = {
            "time": runtime_str,
            "model": model,
            "mode": mode
        }
        asyncio.create_task(self.send_message("status_update", status_data))
    def mark_conversation_start(self): pass
    def refresh_conversation_history(self, *args, **kwargs): pass
    def enter_alternate_screen(self): pass
    def leave_alternate_screen(self): pass
    def get_model_choice(self, prompt: str) -> str: pass # 同步方法在WebUI中无意义
    def show_command_help(self, help_text: str): self.print_dim(help_text)
