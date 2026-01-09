#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web UI系统 - 重构版
负责启动Web服务并与前端进行WebSocket通信，精确复刻终端UI的交互逻辑。
"""

from typing import List, Dict, Any
import asyncio
import uuid
import yaml
import json
import aiohttp
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import Request
import uvicorn

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
        self.is_webui = True  # 标识为 WebUI 模式
        self._stop_callback = None  # 停止回调函数
        self._setup_routes()

    def set_stop_callback(self, callback):
        """设置停止回调函数，用于立即响应 /stop 命令"""
        self._stop_callback = callback

    def _setup_routes(self):
        # 挂载静态文件
        self.app.mount("/static", StaticFiles(directory="static"), name="static")

        @self.app.get("/", response_class=HTMLResponse)
        async def get_index():
            try:
                with open("templates/index.html", "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read())
            except FileNotFoundError:
                return HTMLResponse(content="Error: index.html not found.", status_code=500)

        @self.app.get("/api/config")
        async def get_config():
            """获取当前配置"""
            config_path = Path(__file__).parent / "config.yaml"
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f) or {}
                    return JSONResponse(content={"success": True, "config": config})
                except Exception as e:
                    return JSONResponse(content={"success": False, "error": str(e)})
            return JSONResponse(content={"success": False, "error": "配置文件不存在"})

        @self.app.post("/api/config")
        async def save_config(request: Request):
            """保存配置"""
            try:
                data = await request.json()
                config = data.get("config", {})
                config_path = Path(__file__).parent / "config.yaml"

                # 读取现有配置以保留注释（使用ruamel.yaml会更理想，但这里用标准yaml）
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f) or {}

                # 合并配置
                existing_config.update(config)

                # 保存配置
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(existing_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

                return JSONResponse(content={"success": True, "message": "配置已保存，请重启应用生效"})
            except Exception as e:
                return JSONResponse(content={"success": False, "error": str(e)})

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

                    # /stop 命令需要立即处理，不放入队列
                    if data.strip() == '/stop':
                        if self._stop_callback:
                            self._stop_callback()
                        # 不放入队列，直接返回
                        continue

                    # 尝试解析为 JSON 处理控制命令
                    try:
                        msg = json.loads(data)
                        if isinstance(msg, dict) and msg.get('type') == 'fetch_models':
                            await self._handle_fetch_models(websocket, msg)
                            continue
                    except (json.JSONDecodeError, ValueError):
                        pass  # 不是 JSON，继续作为普通消息处理

                    # 控制类输入（模型选择等）优先路由到 control_queue
                    if getattr(self, "_expect", None):
                        # 模型选择阶段，忽略命令（以/开头的输入）
                        if data.strip().startswith('/'):
                            # 命令放回 chat_queue 处理，不当作模型名
                            await self.chat_queue.put(data)
                            # 保持 _expect 不变，继续等待模型选择
                        else:
                            await self.control_queue.put(data)
                            self._expect = None
                    else:
                        await self.chat_queue.put(data)
            except WebSocketDisconnect:
                print("INFO:     WebSocket connection closed.")
                self.websocket = None

    async def _handle_fetch_models(self, websocket: WebSocket, msg: Dict):
        """处理获取模型列表的请求"""
        request_id = msg.get('request_id')
        api_key = msg.get('api_key', '')
        api_url = msg.get('api_url', '')

        try:
            models = await self._fetch_models_from_api(api_key, api_url)
            await websocket.send_json({
                "event": "models_fetched",
                "data": {
                    "request_id": request_id,
                    "models": models
                }
            })
        except Exception as e:
            await websocket.send_json({
                "event": "models_fetched",
                "data": {
                    "request_id": request_id,
                    "models": [],
                    "error": str(e)
                }
            })

    async def _fetch_models_from_api(self, api_key: str, api_url: str) -> List[str]:
        """从 API 获取可用模型列表"""
        try:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # 提取 base URL（去掉 /chat/completions）
            base_url = api_url.replace("/chat/completions", "")
            # 智谱 AI 的模型列表端点
            if "bigmodel.cn" in base_url:
                models_url = f"{base_url.replace('/v4', '')}/v4/models"
            else:
                models_url = f"{base_url.replace('/v1', '')}/v1/models"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    models_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 智谱AI返回格式: {"data": [{"id": "model_name"}, ...]}
                        models = [m["id"] for m in data.get("data", [])]
                        return models
                    else:
                        error_text = await response.text()
                        raise Exception(f"API 返回错误 ({response.status}): {error_text[:100]}")
        except Exception as e:
            raise Exception(f"获取模型失败: {str(e)}")

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

    def turn_end(self):
        """整个对话轮次结束，可以接受新的用户输入"""
        asyncio.create_task(self.send_message("turn_end", {}))

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
        # 不再显示消息，状态栏已经显示模型信息
        pass

    # --- 空操作方法，保持接口兼容性 ---
    def clear_screen(self): pass
    def show_status_bar(self, model: str = None, start_time=None):
        from datetime import datetime
        runtime_str = ""
        if start_time:
            runtime = datetime.now() - start_time
            runtime_str = str(runtime).split('.')[0]

        status_data = {
            "time": runtime_str,
            "model": model,
            "mode": ""
        }
        asyncio.create_task(self.send_message("status_update", status_data))
    def mark_conversation_start(self): pass
    def refresh_conversation_history(self, *args, **kwargs): pass
    def enter_alternate_screen(self): pass
    def leave_alternate_screen(self): pass
    def get_model_choice(self, prompt: str) -> str: pass # 同步方法在WebUI中无意义
    def show_command_help(self, help_text: str): self.print_dim(help_text)

    # --- 对话编辑器方法 ---
    def show_editor(self, chunks: list):
        """显示对话编辑器

        Args:
            chunks: [(real_index, chunk), ...] 可编辑的语块列表
        """
        from chunk_system import ChunkType

        # 转换为前端需要的格式
        chunks_data = []
        for real_idx, chunk in chunks:
            chunks_data.append({
                'index': real_idx,
                'type': chunk.chunk_type.value,
                'content': chunk.content,
                'tokens': chunk.tokens
            })

        asyncio.create_task(self.send_message("show_editor", {"chunks": chunks_data}))

    def show_editor_result(self, success: bool, message: str = "", error: str = ""):
        """发送编辑器操作结果"""
        asyncio.create_task(self.send_message("editor_result", {
            "success": success,
            "message": message,
            "error": error
        }))

    # --- 记忆管理方法 ---
    def show_memory(self, conversations: list):
        """显示记忆管理界面

        Args:
            conversations: 记忆列表
        """
        asyncio.create_task(self.send_message("show_memory", {"conversations": conversations}))

    def show_memory_result(self, success: bool, conversations: list = None, message: str = "", error: str = ""):
        """发送记忆操作结果"""
        data = {"success": success}
        if conversations is not None:
            data["conversations"] = conversations
        if message:
            data["message"] = message
        if error:
            data["error"] = error
        asyncio.create_task(self.send_message("memory_result", data))

    # --- 兼容Shell UI的接口 ---
    async def show_chunk_editor(self, chunks: list, current_index: int = 0):
        """显示对话编辑器（兼容Shell UI接口）

        对于Web UI，发送事件到前端后直接返回，由前端通过WebSocket发送操作结果
        """
        if not chunks:
            self.print_dim("没有可编辑的对话内容")
            return ('quit', -1, None)

        self.show_editor(chunks)

        # 等待用户操作结果
        while True:
            response = await self.chat_queue.get()
            if response.startswith('EDIT:'):
                parts = response.split(':', 2)
                if len(parts) == 3:
                    idx = int(parts[1])
                    new_content = parts[2]
                    return ('edit', idx, new_content)
            elif response.startswith('DELETE:'):
                idx = int(response.split(':')[1])
                return ('delete', idx, None)
            elif response.startswith('ROLLBACK:'):
                idx = int(response.split(':')[1])
                return ('delete_from', idx, None)
            elif response == 'QUIT':
                return ('quit', -1, None)

    async def show_memory_editor(self, conversations: list, current_index: int = 0):
        """显示记忆管理界面（兼容Shell UI接口）

        对于Web UI，发送事件到前端后直接返回，由前端通过WebSocket发送操作结果
        """
        if not conversations:
            self.print_dim("没有记忆记录")
            return ('quit', None, None)

        self.show_memory(conversations)

        # 等待用户操作结果
        while True:
            response = await self.chat_queue.get()
            if response.startswith('MEMORY_DELETE:'):
                doc_id = response.split(':', 1)[1]
                return ('delete', doc_id, None)
            elif response.startswith('MEMORY_SEARCH:'):
                keyword = response.split(':', 1)[1]
                return ('search', None, keyword)
            elif response == 'MEMORY_CLEAN':
                return ('clean_duplicates', None, None)
            elif response == 'QUIT':
                return ('quit', None, None)

    def show_edit_result(self, action: str, success: bool, detail: str = ""):
        """显示编辑结果"""
        if success:
            self.print_success(f"✓ {action}成功 {detail}")
        else:
            self.print_error(f"✗ 操作失败 {detail}")
        self.show_editor_result(success, detail if success else "", detail if not success else "")

    # --- 会话管理方法 ---
    def send_session_list(self, sessions: list, current_id: str = None):
        """发送会话列表"""
        asyncio.create_task(self.send_message("session_list", {
            "sessions": sessions,
            "current_id": current_id
        }))

    def send_session_load(self, chunks: list):
        """发送加载会话的完整内容"""
        asyncio.create_task(self.send_message("session_load", {
            "chunks": chunks
        }))

    def send_session_loaded(self, session_id: str, title: str):
        """发送会话加载成功通知"""
        asyncio.create_task(self.send_message("session_loaded", {
            "session_id": session_id,
            "title": title
        }))

    def send_tool_details(self, tool_id: str, args: dict, result: str, duration: str = None):
        """发送工具详情"""
        asyncio.create_task(self.send_message("tool_details", {
            "tool_id": tool_id,
            "details": {
                "args": args,
                "result": result,
                "duration": duration
            }
        }))
