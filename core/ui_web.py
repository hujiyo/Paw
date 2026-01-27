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
    
    重要：所有消息发送通过有序队列处理，确保前端按正确顺序接收消息。
    """
    def __init__(self, host="*********", port=8081):
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
        
        # === 有序消息队列系统 ===
        # 解决 asyncio.create_task() fire-and-forget 导致的消息乱序问题
        self._msg_queue: asyncio.Queue = None  # 延迟初始化（需要在事件循环中创建）
        self._msg_sender_task: asyncio.Task = None  # 消息发送协程
        self._loop: asyncio.AbstractEventLoop = None  # 事件循环引用
        
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

        @self.app.post("/api/calibrate-threshold")
        async def calibrate_threshold(request: Request):
            """校准记忆意图判断阈值"""
            try:
                data = await request.json()
                embedding_url = data.get('embedding_url', '')
                embedding_model = data.get('embedding_model', '')
                
                if not embedding_url or not embedding_model:
                    return JSONResponse(content={"success": False, "error": "请先配置 Embedding URL 和模型"})
                
                # 导入并调用校准函数
                from calibrate_threshold import calibrate_api
                
                result = await asyncio.to_thread(
                    calibrate_api, 
                    embedding_url, 
                    embedding_model
                )
                
                return JSONResponse(content=result)
                
            except Exception as e:
                return JSONResponse(content={"success": False, "error": str(e)})

        @self.app.post("/api/browse-folder")
        async def browse_folder(request: Request):
            """Mock 文件夹选择接口 (仅 Web 模式使用，Electron 模式使用 IPC)"""
            # 目前 Web 端无法直接调用系统对话框，这里只是返回一个 mock 结果
            # 或者可以返回主目录作为默认值
            return JSONResponse(content={"success": True, "path": str(Path.home())})

        @self.app.post("/api/fs/list")
        async def list_files(request: Request):
            """列出指定目录下的文件"""
            try:
                data = await request.json()
                path_str = data.get("path") or "."
                
                # 安全检查：防止访问系统敏感目录（简单示例，实际需更严谨）
                # 这里假设用户有权访问任何目录，因为是本地工具
                
                p = Path(path_str).resolve()
                if not p.exists():
                    return JSONResponse(content={"success": False, "error": "Path does not exist"})
                
                items = []
                try:
                    for item in p.iterdir():
                        try:
                            stats = item.stat()
                            items.append({
                                "name": item.name,
                                "path": str(item),
                                "is_dir": item.is_dir(),
                                "size": stats.st_size if not item.is_dir() else 0,
                                "mtime": stats.st_mtime
                            })
                        except Exception:
                            continue
                except PermissionError:
                     return JSONResponse(content={"success": False, "error": "Permission denied"})

                # 排序：目录在前，然后按文件名
                items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
                
                return JSONResponse(content={
                    "success": True, 
                    "items": items,
                    "current_path": str(p),
                    "parent_path": str(p.parent)
                })
            except Exception as e:
                return JSONResponse(content={"success": False, "error": str(e)})

        # 轮次数据获取接口（供前端对话链视图使用）
        # 注意：需要 paw 实例注入 chunk_manager，通过 set_chunk_manager 方法
        self._chunk_manager_ref = None

        @self.app.get("/api/turns")
        async def get_turns():
            """获取对话轮次列表（供前端渲染对话链）"""
            if self._chunk_manager_ref is None:
                return JSONResponse(content={"success": False, "error": "ChunkManager not initialized"})
            
            try:
                turns = self._chunk_manager_ref.get_turns()
                # 转换为前端需要的格式
                result = []
                for idx, turn in enumerate(turns):
                    turn_data = {
                        'index': idx,
                        'role': turn['role'],
                        'start_idx': turn['start_idx'],
                        'end_idx': turn['end_idx'],
                        'preview': self._get_turn_preview(turn),
                        'tool_count': sum(1 for c in turn['chunks'] 
                                         if hasattr(c, 'metadata') and c.metadata.get('tool_calls')),
                        'parts': self._get_turn_parts(turn)
                    }
                    result.append(turn_data)
                return JSONResponse(content={"success": True, "turns": result})
            except Exception as e:
                return JSONResponse(content={"success": False, "error": str(e)})

        @self.app.post("/api/fs/content")
        async def get_file_content(request: Request):
            """获取文件内容"""
            try:
                data = await request.json()
                path_str = data.get("path")
                if not path_str:
                     return JSONResponse(content={"success": False, "error": "No path provided"})
                
                p = Path(path_str).resolve()
                if not p.exists() or not p.is_file():
                    return JSONResponse(content={"success": False, "error": "File not found"})
                
                # 限制文件大小，防止浏览器崩溃
                if p.stat().st_size > 1024 * 1024: # 1MB
                    return JSONResponse(content={"success": False, "error": "File too large to preview (>1MB)"})
                
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    return JSONResponse(content={"success": True, "content": content})
                except Exception as e:
                    return JSONResponse(content={"success": False, "error": str(e)})
            except Exception as e:
                return JSONResponse(content={"success": False, "error": str(e)})

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.websocket = websocket
            self.ws_ready.set()
            
            # 初始化消息队列（必须在事件循环中）
            self._ensure_msg_queue()
            
            # 连接建立后，立刻把积压消息发送给前端
            # 这些是在队列初始化前缓存的消息，需要按顺序发送
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
                        if isinstance(msg, dict):
                            msg_type = msg.get('type')
                            if msg_type == 'fetch_models':
                                await self._handle_fetch_models(websocket, msg)
                                continue
                            elif msg_type == 'create_new_chat':
                                # 路由到 chat_queue，由 paw.py 处理
                                await self.chat_queue.put(data)
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
        """从 API 获取可用模型列表 (通用实现)"""
        try:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # 智能判断 API 类型并构建 models URL
            # 1. 智谱 AI
            if "bigmodel.cn" in api_url:
                base_url = api_url.split("/v4/")[0]
                models_url = f"{base_url}/v4/models"
            # 2. Ollama 
            elif "11434" in api_url or "/api/" in api_url:
                # Ollama Embedding: .../api/embeddings -> .../api/tags
                # Ollama Chat: .../api/chat -> .../api/tags
                if "/api/embeddings" in api_url:
                    models_url = api_url.replace("/api/embeddings", "/api/tags")
                elif "/api/chat" in api_url:
                    models_url = api_url.replace("/api/chat", "/api/tags")
                elif "/v1/" in api_url: # Ollama 兼容接口
                    models_url = api_url.split("/v1/")[0] + "/api/tags"
                else:
                    # 尝试直接访问 /api/tags (假设 api_url 是 base url)
                    base_url = api_url.rstrip("/")
                    models_url = f"{base_url}/api/tags"
            # 3. OpenAI 兼容接口 (v1)
            elif "/v1/" in api_url:
                # .../v1/chat/completions -> .../v1/models
                # .../v1/embeddings -> .../v1/models
                base_url = api_url.split("/v1/")[0]
                models_url = f"{base_url}/v1/models"
            else:
                # 默认尝试追加 /models
                models_url = f"{api_url.rstrip('/')}/models"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    models_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 解析不同格式的响应
                        # Ollama: {"models": [{"name": "llama3:latest", ...}]}
                        if "models" in data and isinstance(data["models"], list):
                            return [m["name"] for m in data["models"]]
                        
                        # OpenAI / 智谱: {"data": [{"id": "gpt-4", ...}]}
                        if "data" in data and isinstance(data["data"], list):
                            return [m["id"] for m in data.get("data", [])]
                            
                        # 简单的列表: ["model1", "model2"]
                        if isinstance(data, list):
                            return data
                            
                        raise Exception(f"未知的响应格式: {str(data)[:100]}")
                    else:
                        error_text = await response.text()
                        raise Exception(f"API 返回错误 ({response.status}): {error_text[:100]}")
        except Exception as e:
            # 记录错误但不崩溃
            print(f"获取模型列表失败 ({models_url if 'models_url' in locals() else api_url}): {e}")
            raise Exception(f"获取模型失败: {str(e)}")

    # === 消息队列核心方法 ===
    
    def _ensure_msg_queue(self):
        """确保消息队列已初始化（必须在事件循环中调用）"""
        if self._msg_queue is None:
            try:
                self._loop = asyncio.get_running_loop()
                self._msg_queue = asyncio.Queue()
                # 启动消息发送协程
                self._msg_sender_task = asyncio.create_task(self._msg_sender_loop())
            except RuntimeError:
                # 没有运行中的事件循环，稍后再初始化
                pass
    
    async def _msg_sender_loop(self):
        """消息发送协程：按顺序从队列取出消息并发送
        
        这是解决消息乱序问题的核心：
        - 所有消息都进入同一个队列
        - 单一协程按 FIFO 顺序发送
        - 确保 stream_start 一定在 stream_chunk 之前到达前端
        """
        while True:
            try:
                payload = await self._msg_queue.get()
                
                # 等待 WebSocket 就绪
                if not self.websocket:
                    # WebSocket 未连接，缓存消息
                    self._pending.append(payload)
                    self._msg_queue.task_done()
                    continue
                
                try:
                    await self.websocket.send_json(payload)
                except Exception as e:
                    print(f"ERROR:    Failed to send WebSocket message: {e}")
                finally:
                    self._msg_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"ERROR:    Message sender loop error: {e}")
    
    def queue_message(self, event: str, data: Any):
        """将消息放入有序队列（同步方法，可从任何地方调用）
        
        这是所有 UI 方法应该使用的发送方式，替代原来的 asyncio.create_task()。
        消息会按调用顺序被发送到前端。
        """
        payload = {"event": event, "data": data}
        
        # 确保队列已初始化
        self._ensure_msg_queue()
        
        if self._msg_queue is None:
            # 事件循环未启动，先缓存
            self._pending.append(payload)
            return
        
        try:
            # 使用 put_nowait 避免阻塞（队列无大小限制）
            self._msg_queue.put_nowait(payload)
        except Exception:
            # 降级：直接缓存
            self._pending.append(payload)
    
    async def send_message(self, event: str, data: Any):
        """异步发送消息（直接发送，用于需要立即确认的场景）"""
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
    # 重构说明：所有方法改用 queue_message() 替代 asyncio.create_task(send_message())
    # 确保消息按调用顺序发送到前端，解决流式输出乱序问题

    def print_welcome(self):
        self.queue_message("welcome", {})

    def print_goodbye(self):
        self.queue_message("goodbye", {})

    def print_assistant(self, text: str, end: str = '', flush: bool = False):
        """流式输出助手消息
        
        消息发送顺序保证：
        1. assistant_stream_start (首次调用时)
        2. assistant_stream_chunk (每次调用时)
        通过有序队列确保前端按正确顺序接收
        """
        if not hasattr(self, '_current_stream_id'):
            self._current_stream_id = str(uuid.uuid4())
            self.queue_message("assistant_stream_start", {"id": self._current_stream_id})
        self.queue_message("assistant_stream_chunk", {"id": self._current_stream_id, "text": text})

    def assistant_stream_end(self):
        """结束流式输出"""
        if hasattr(self, '_current_stream_id'):
            self.queue_message("assistant_stream_end", {"id": self._current_stream_id})
            del self._current_stream_id

    def turn_end(self):
        """整个对话轮次结束，可以接受新的用户输入"""
        self.queue_message("turn_end", {})

    def show_tool_start(self, tool_call_id: str, tool_name: str, args_str: str, raw_request: dict = None):
        """显示工具调用开始
        
        Args:
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            args_str: 参数字符串（显示用）
            raw_request: 原始请求数据（包含完整的工具调用信息）
        """
        self.queue_message("tool_start", {
            "id": tool_call_id,
            "name": tool_name,
            "args": args_str,
            "raw_request": raw_request
        })

    def show_tool_result(self, tool_call_id: str, tool_name: str, display: dict, success: bool = True, raw_response: dict = None):
        """显示工具调用结果
        
        Args:
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            display: 显示信息
            success: 是否成功
            raw_response: 原始响应数据（包含完整的工具执行结果）
        """
        self.queue_message("tool_result", {
            "id": tool_call_id,
            "name": tool_name,
            "display": display,
            "success": success,
            "raw_response": raw_response
        })

    async def get_user_input(self, prompt: str = None) -> str:
        if prompt:
            # 普通输入走聊天通道
            await self.send_message("request_input", {"prompt": prompt})
        return await self.chat_queue.get()

    def print_dim(self, text: str, **kwargs):
        self.queue_message("system_message", {"text": text, "type": "dim"})

    def print_system(self, text: str, **kwargs):
        self.queue_message("system_message", {"text": text, "type": "system"})

    def print_error(self, text: str):
        self.queue_message("system_message", {"text": text, "type": "error"})

    def print_success(self, text: str):
        self.queue_message("system_message", {"text": text, "type": "success"})

    def show_model_list(self, models: List[str]):
        self.queue_message("show_model_selection", {"models": models})

    async def get_model_choice_async(self, prompt: str) -> str:
        # 标记下一条输入为模型选择，路由到 control_queue
        self._expect = "model_choice"
        await self.send_message("request_input", {"prompt": prompt, "type": "model_choice"})
        return await self.control_queue.get()

    def show_model_input_prompt(self):
        self.queue_message("request_input", {"prompt": "无法自动获取模型列表，请输入模型名称:", "type": "model_input"})

    def show_model_selected(self, model: str):
        # 不再显示消息，状态栏已经显示模型信息
        pass

    # --- 空操作方法，保持接口兼容性 ---
    def clear_screen(self): pass
    def show_status_bar(self, **kwargs):
        """更新状态栏
        
        支持任意字段，常用字段:
            model: 模型名称
            tokens: 当前上下文 token 数
        
        示例:
            show_status_bar(model='gpt-4', tokens=12500)
        """
        # 过滤掉空值
        status_data = {k: v for k, v in kwargs.items() if v is not None and v != ''}
        self.queue_message("status_update", status_data)
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

        self.queue_message("show_editor", {"chunks": chunks_data})

    def show_editor_result(self, success: bool, message: str = "", error: str = ""):
        """发送编辑器操作结果"""
        self.queue_message("editor_result", {
            "success": success,
            "message": message,
            "error": error
        })

    # --- 记忆管理方法 ---
    def show_memory(self, conversations: list):
        """显示记忆管理界面

        Args:
            conversations: 记忆列表
        """
        self.queue_message("show_memory", {"conversations": conversations})

    def show_memory_result(self, success: bool, conversations: list = None, message: str = "", error: str = ""):
        """发送记忆操作结果"""
        data = {"success": success}
        if conversations is not None:
            data["conversations"] = conversations
        if message:
            data["message"] = message
        if error:
            data["error"] = error
        self.queue_message("memory_result", data)

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
        self.queue_message("session_list", {
            "sessions": sessions,
            "current_id": current_id
        })

    def send_session_load(self, chunks: list):
        """发送加载会话的完整内容"""
        self.queue_message("session_load", {
            "chunks": chunks
        })

    def send_session_loaded(self, session_id: str, title: str):
        """发送会话加载成功通知"""
        self.queue_message("session_loaded", {
            "session_id": session_id,
            "title": title
        })

    def send_tool_details(self, tool_id: str, args: dict, result: str, duration: str = None):
        """发送工具详情"""
        self.queue_message("tool_details", {
            "tool_id": tool_id,
            "details": {
                "args": args,
                "result": result,
                "duration": duration
            }
        })

    def send_terminal_output(self, content: str, is_open: bool = True):
        """发送终端输出到工作区
        
        Args:
            content: 终端输出内容
            is_open: 终端是否已打开
        """
        self.queue_message("terminal_output", {
            "content": content,
            "is_open": is_open
        })

    # --- 轮次管理方法 ---
    def set_chunk_manager(self, chunk_manager):
        """注入 ChunkManager 引用（由 Paw 调用）
        
        Args:
            chunk_manager: ChunkManager 实例
        """
        self._chunk_manager_ref = chunk_manager

    def _get_turn_preview(self, turn: dict) -> str:
        """获取轮次预览文本
        
        Args:
            turn: 轮次数据 (from ChunkManager.get_turns())
            
        Returns:
            预览文本（最多50字符）
        """
        from chunk_system import ChunkType
        
        for chunk in turn['chunks']:
            if chunk.chunk_type in (ChunkType.USER, ChunkType.ASSISTANT):
                content = chunk.content or ''
                # 移除换行，截断
                preview = content.replace('\n', ' ').strip()
                if len(preview) > 50:
                    preview = preview[:47] + '...'
                return preview
        
        # 如果只有工具调用，显示工具数量
        tool_count = sum(1 for c in turn['chunks'] 
                        if hasattr(c, 'metadata') and c.metadata.get('tool_calls'))
        if tool_count > 0:
            return f'{tool_count} 个工具调用'
        return ''

    def _get_turn_parts(self, turn: dict) -> list:
        """获取轮次的详细部分(用于展开视图)
        
        Args:
            turn: 轮次数据
            
        Returns:
            parts 列表,每个元素 {type: 'text'|'tool', ...}
            按照 chunks 在对话中的实际顺序返回，保留"文本-工具-文本-工具"的交错关系
        """
        from chunk_system import ChunkType
        
        parts = []
        # 按 chunks 顺序遍历，保留时间顺序
        for chunk in turn['chunks']:
            # 处理 ASSISTANT chunk
            if chunk.chunk_type == ChunkType.ASSISTANT:
                # 1. 先添加文本（如果有）
                if chunk.content:
                    parts.append({
                        'type': 'text',
                        'text': chunk.content[:100] + ('...' if len(chunk.content) > 100 else '')
                    })
                
                # 2. 再添加工具调用（如果有）
                if hasattr(chunk, 'metadata') and chunk.metadata.get('tool_calls'):
                    for tc in chunk.metadata['tool_calls']:
                        func = tc.get('function', {})
                        parts.append({
                            'type': 'tool',
                            'id': tc.get('id', ''),
                            'name': func.get('name', 'unknown')
                        })
            
            # 处理 USER chunk（虽然通常不会出现在 assistant 轮次，但保留兼容性）
            elif chunk.chunk_type == ChunkType.USER:
                if chunk.content:
                    parts.append({
                        'type': 'text',
                        'text': chunk.content[:100] + ('...' if len(chunk.content) > 100 else '')
                    })
        
        return parts

    def notify_turns_updated(self):
        """通知前端轮次已更新（触发对话链刷新）"""
        self.queue_message("turns_updated", {})

    def send_todos_updated(self, todos: list):
        """推送 Todo 列表更新到前端
        
        Args:
            todos: 完整的 todo 列表，每项包含 id, title, details, status
        """
        self.queue_message("todos_updated", {
            "todos": todos
        })
