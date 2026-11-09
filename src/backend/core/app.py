#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""应用层：把传输、内核、命令、REST 路由装配在一起。

职责边界：
- 解析用户输入（命令 vs 普通消息）
- 管理当前会话与模型/模式
- 把 REST 查询转成前端需要的结构
- 不持有对话逻辑本身（那在 AgentKernel）
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from core import events as ev
from core.agent import AgentKernel
from core.catalog import build_registry
from core.config import (
    AppConfig, WorkspaceConfig, load_config, save_config, public_config,
)
from core.context import ContextBudget
from core.llm import LLMClient
from core.prompts import SystemPromptBuilder
from core.session import Message, Session
from core.storage import SessionStore
from core.transport import Transport

from prompts import UIPrompts


class PawApp:
    def __init__(self, host: str, port: int, workspace_dir: str, transport: Transport):
        self.transport = transport
        self.config: AppConfig = load_config()
        self.workspace_dir = workspace_dir

        from tools import BaseTools, WebTools

        self.tools = BaseTools(sandbox_dir=workspace_dir, config=self.config.to_dict())
        self.web_tools = WebTools(
            config=self.config.web.__dict__,
            api_url=self.config.api.url,
            model_getter=lambda: self.model,
            api_key=self.config.api.key,
        )

        self.registry = build_registry(self.tools, self.web_tools)
        self.registry.shell_snapshot = lambda: (
            self.tools.async_shell.get_screen_snapshot()
            if self.tools.async_shell.is_shell_open()
            else ""
        )

        self.model: str = self.config.api.model or ""
        self.llm = LLMClient(self.config.api.url, self.config.api.key, self.model or "default")

        self.prompt_builder = SystemPromptBuilder(self.config, self.tools)
        self.store = SessionStore(self._sessions_db_path())
        self.budget = ContextBudget(
            max_tokens=self.config.context.max_tokens,
            keep_recent_turns=self.config.context.keep_recent_turns,
        )
        self.kernel = AgentKernel(
            sink=self.transport,
            llm=self.llm,
            registry=self.registry,
            store=self.store,
            budget=self.budget,
            system_prompt_builder=self.prompt_builder,
        )
        self.memory_manager = None
        self._pending_memory_save = None
        self._stop_event = asyncio.Event()
        self._input_task: Optional[asyncio.Task] = None

        self._mount_routes()

    # ---------- 路径 ----------

    @staticmethod
    def _sessions_db_path() -> Path:
        import os
        base = Path(os.getenv("PAW_DATA_DIR") or (Path.home() / ".paw"))
        base.mkdir(parents=True, exist_ok=True)
        return base / "paw.db"

    # ---------- 启动 ----------

    def _on_connect(self) -> None:
        """前端重连后补发当前状态，避免界面空白。"""
        self._sync_sessions()
        self._status()
        session = self.kernel.session
        if session is not None:
            self.transport.emit(ev.SESSION_LOAD, {
                "chunks": session.to_chunks(),
                "mode": session.mode,
            })

    def _on_disconnect(self) -> None:
        self.store.flush()

    async def start(self) -> None:
        self.transport.set_handlers(
            on_message=self._handle_raw_message,
            on_stop=self.kernel.set_stop,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
        )

        self._sync_sessions()
        self._status()

        if self.config.memory.enabled:
            asyncio.create_task(self._init_memory())

        asyncio.create_task(self._terminal_publisher())
        asyncio.create_task(self.store.run_flusher(self._stop_event))

        # 模型选择可能需要用户交互，放到会话同步之后，不阻塞服务启动
        if not self.model:
            self.model = await self._select_model()
            self.llm.model = self.model
            self._status()

        self._input_task = asyncio.create_task(self._input_loop())

    async def _input_loop(self) -> None:
        while not self._stop_event.is_set():
            user_input = await self.transport.get_input()
            if user_input.lower() in ("exit", "quit", "bye"):
                self.store.flush()
                self._stop_event.set()
                return
            if not user_input.strip():
                continue
            await self._dispatch(user_input)

    async def _dispatch(self, raw: str) -> None:
        json_msg = self._try_json(raw)
        if json_msg is not None:
            kind = json_msg.get("type")
            if kind == "create_new_chat":
                self._create_new_chat(json_msg)
                return
            if kind == "set_mode":
                await self._set_mode(str(json_msg.get("mode", "default")))
                return

        if raw.startswith("MEMORY_DELETE:"):
            await self._memory_delete(raw.split(":", 1)[1])
            return
        if raw.startswith("MEMORY_SEARCH:"):
            await self._show_memory(raw.split(":", 1)[1])
            return
        if raw == "MEMORY_CLEAN":
            await self._memory_clean()
            return
        if raw == "QUIT":
            return

        if raw.startswith("/"):
            await self._handle_command(raw)
            return

        await self._run_turn(raw)

    # ---------- 一轮对话 ----------

    async def _run_turn(self, text: str) -> None:
        try:
            self.kernel.ensure_session(
                workspace_dir=str(self.workspace_dir),
                model=self.model,
                mode=self._mode(),
            )
            await self._recall_before_turn(text)
            await self.kernel.run_turn(text)
        except Exception as e:
            self.transport.emit(ev.SHOW_ERROR, {"text": f"处理消息失败: {e}"})
        finally:
            self._persist_memory()
            self.transport.emit(ev.TURN_END, {})
            self._status()

    async def _recall_before_turn(self, text: str) -> None:
        """按需唤醒记忆。记忆系统未启用时不做任何事。"""
        if self.memory_manager is None:
            return
        session = self.kernel.session
        try:
            recalled = await self.memory_manager.recall_async(text, n_results=3, min_score=0.4)
            if recalled:
                self.kernel.pending_context = self.memory_manager.get_recalled_prompt()
        except Exception as e:
            self.transport.emit(ev.SYSTEM_MESSAGE, {"text": f"[记忆] 检索失败: {e}", "type": "dim"})
        if session is not None and not text.startswith("[系统"):
            self._pending_memory_save = (text, session)

    # ---------- 命令 ----------

    async def _handle_command(self, raw: str) -> None:
        cmd = raw.strip()

        if cmd == "/clear":
            if self.kernel.session:
                self.kernel.session.messages.clear()
                self.store.mark_dirty(self.kernel.session)
                self.store.flush()
            self.transport.emit(ev.SESSION_LOAD, {"chunks": [], "mode": self._mode()})
            return

        if cmd == "/sessions":
            self._sync_sessions()
            return

        if cmd.startswith("/load "):
            await self._load_session(cmd.split(" ", 1)[1].strip())
            return

        if cmd.startswith("/delete-session "):
            self._delete_session(cmd.split(" ", 1)[1].strip())
            return

        if cmd == "/new":
            self._create_new_chat({})
            return

        if cmd == "/model":
            new_model = await self._select_model()
            self.model = new_model
            self.llm.model = new_model
            if self.kernel.session:
                self.kernel.session.model = new_model
                self.store.mark_dirty(self.kernel.session)
            self._status()
            return

        if cmd.startswith("/mode"):
            parts = cmd.split(None, 1)
            if len(parts) > 1:
                await self._set_mode(parts[1].strip().lower())
            return

        if cmd == "/memory":
            await self._show_memory()
            return

        if cmd == "/memory edit":
            await self._show_memory()
            return

        if cmd == "/reload-session":
            self._reload_current_session()
            return

        if cmd.startswith("/delete-message "):
            await self._delete_message(cmd.split(" ", 1)[1].strip())
            return

        if cmd.startswith("/retry "):
            await self._retry(cmd.split(" ", 1)[1].strip())
            return

        if cmd.startswith("/continue "):
            await self._continue(cmd.split(" ", 1)[1].strip())
            return

        self.transport.emit(ev.SYSTEM_MESSAGE, {
            "text": UIPrompts.get_command_help(),
            "type": "dim",
        })

    # ---------- 会话操作 ----------

    def _ensure_session(self) -> Session:
        if self.kernel.session is None:
            return self.kernel.create_session(
                workspace_dir=str(self.workspace_dir),
                model=self.model,
                mode=self._mode(),
            )
        return self.kernel.session

    def _create_new_chat(self, msg: Dict[str, Any]) -> None:
        workspace = msg.get("workspace_dir") or str(self.workspace_dir)
        if workspace == "~":
            workspace = str(Path.home())
        workspace = str(Path(workspace).expanduser().resolve())

        self.workspace_dir = workspace
        self.tools.sandbox_dir = Path(workspace)

        session = self.kernel.create_session(
            workspace_dir=workspace,
            model=msg.get("model") or self.model,
            mode=self._mode(),
            title=(msg.get("title") or "").strip(),
            system_prompt=(msg.get("system_prompt") or "").strip(),
        )
        self._sync_sessions()
        self.transport.emit(ev.NEW_CHAT, {"session_id": session.session_id})
        self._status()

    def _load_session(self, session_id: str) -> None:
        session = self.kernel.load_session(session_id)
        if session is None:
            self.transport.emit(ev.SHOW_ERROR, {"text": f"会话 {session_id} 不存在"})
            return
        if session.workspace_dir:
            self.workspace_dir = session.workspace_dir
            self.tools.sandbox_dir = Path(session.workspace_dir)
        if session.model:
            self.model = session.model
            self.llm.model = session.model
        self.transport.emit(ev.SESSION_LOAD, {
            "chunks": session.to_chunks(),
            "mode": session.mode,
        })
        self.transport.emit(ev.SESSION_LOADED, {
            "session_id": session.session_id,
            "title": session.title,
        })
        self._sync_sessions()
        self._status()

    def _reload_current_session(self) -> None:
        session = self.kernel.session
        if session is None:
            return
        self.transport.emit(ev.SESSION_LOAD, {
            "chunks": session.to_chunks(),
            "mode": session.mode,
        })
        self._sync_sessions()

    def _delete_session(self, session_id: str) -> None:
        if self.kernel.session and session_id == self.kernel.session.session_id:
            self.transport.emit(ev.SHOW_ERROR, {"text": "无法删除当前会话"})
            return
        if not self.store.delete(session_id):
            self.transport.emit(ev.SHOW_ERROR, {"text": f"删除会话失败: {session_id}"})
            return
        self._sync_sessions()

    def _sync_sessions(self) -> None:
        self.transport.emit(ev.SESSION_LIST, {
            "sessions": self.store.list_sessions(limit=50),
            "current_id": self.kernel.session.session_id if self.kernel.session else None,
        })

    # ---------- 消息编辑 ----------

    async def _delete_message(self, payload: str) -> None:
        """payload 是 `<turn_index> <role>`。

        前端能精确算出被点击的消息属于第几个用户轮次；后端按轮次定位，
        不依赖任何临时 DOM id，因此删除的就是用户点中的那一条。
        role=user 只删该用户消息；role=assistant 删除该轮的整个回复
        （含工具调用与结果），保持工具配对完整。
        """
        parts = payload.split()
        if len(parts) < 2:
            self.transport.emit(ev.SHOW_ERROR, {"text": "删除请求缺少参数"})
            return
        try:
            turn_index = int(parts[0])
        except ValueError:
            self.transport.emit(ev.SHOW_ERROR, {"text": f"无法识别的轮次: {parts[0]}"})
            return
        role = parts[1]

        session = self.kernel.session
        if session is None:
            return
        user_indices = [i for i, m in enumerate(session.messages) if m.role == "user"]
        if turn_index < 0 or turn_index >= len(user_indices):
            self.transport.emit(ev.SHOW_ERROR, {"text": "该轮次已不存在，请刷新会话"})
            return

        user_pos = user_indices[turn_index]
        if role == "user":
            del session.messages[user_pos]
        else:
            start = user_pos
            for i in range(user_pos + 1, len(session.messages)):
                if session.messages[i].role == "assistant":
                    start = i
                    break
            else:
                self.transport.emit(ev.SYSTEM_MESSAGE, {"text": "[该轮还没有回复可删除]", "type": "dim"})
                return
            end = len(session.messages)
            for i in range(start + 1, len(session.messages)):
                if session.messages[i].role == "user":
                    end = i
                    break
            del session.messages[start:end]

        self.store.mark_dirty(session)
        self.store.flush()
        self._sync_sessions()
        self.transport.emit(ev.SESSION_LOAD, {"chunks": session.to_chunks(), "mode": session.mode})

    async def _retry(self, payload: str) -> None:
        """重试第 N 个用户轮次：删掉该轮回复，用同样的用户输入重新生成。"""
        session = self.kernel.session
        if session is None:
            return
        try:
            turn_index = int(payload.split()[0])
        except (ValueError, IndexError):
            self.transport.emit(ev.SHOW_ERROR, {"text": "重试请求缺少轮次"})
            return
        user_indices = [i for i, m in enumerate(session.messages) if m.role == "user"]
        if turn_index < 0 or turn_index >= len(user_indices):
            self.transport.emit(ev.SHOW_ERROR, {"text": "该轮次已不存在，请刷新会话"})
            return

        user_pos = user_indices[turn_index]
        text = session.messages[user_pos].content
        end = len(session.messages)
        for i in range(user_pos + 1, len(session.messages)):
            if session.messages[i].role == "user":
                end = i
                break
        del session.messages[user_pos:end]
        self.store.mark_dirty(session)
        self.transport.emit(ev.SESSION_LOAD, {"chunks": session.to_chunks(), "mode": session.mode})
        await self._run_turn(text)

    async def _continue(self, payload: str) -> None:
        session = self.kernel.session
        if session is None:
            return
        session.add_user("[系统提示: 请继续你之前的回复，不要重复已说过的内容]")
        self.store.mark_dirty(session)
        await self._run_turn("")

    # ---------- 记忆视图 ----------

    async def _show_memory(self, keyword: str = "") -> None:
        if self.memory_manager is None:
            self.transport.emit(ev.SYSTEM_MESSAGE, {
                "text": "[记忆] 未启用。请在设置中打开记忆系统并配置 Embedding 服务。",
                "type": "dim",
            })
            return
        store = self.memory_manager.conversation_store
        try:
            if keyword:
                conversations = await store.search(query=keyword, n_results=50, min_score=0.2)
            else:
                conversations = await asyncio.to_thread(store.list_all, limit=100)
        except Exception as e:
            self.transport.emit(ev.SHOW_ERROR, {"text": f"读取记忆失败: {e}"})
            return

        # 统一成前端需要的结构（id + metadata）
        payload = []
        for item in conversations:
            meta = dict(item.get("metadata") or {})
            document = item.get("document") or ""
            # 记忆库只把问答存成 document 文本，这里拆回前端要的两段
            for line in document.splitlines():
                if line.startswith("用户: "):
                    meta.setdefault("user_message", line[len("用户: "):])
                elif line.startswith("AI: "):
                    meta.setdefault("assistant_message", line[len("AI: "):])
            meta.setdefault("timestamp", item.get("timestamp", ""))
            meta.setdefault("project", item.get("project", ""))
            payload.append({"id": item.get("id", ""), "metadata": meta})
        self.transport.emit(ev.SHOW_MEMORY, {"conversations": payload})

    async def _memory_delete(self, doc_id: str) -> None:
        if self.memory_manager is None:
            return
        try:
            ok = await asyncio.to_thread(
                self.memory_manager.conversation_store.delete, doc_id
            )
        except Exception as e:
            self.transport.emit(ev.MEMORY_RESULT, {"success": False, "error": str(e)})
            return
        self.transport.emit(ev.MEMORY_RESULT, {
            "success": ok,
            "message": "已删除" if ok else "删除失败",
        })
        await self._show_memory()

    async def _memory_clean(self) -> None:
        if self.memory_manager is None:
            return
        store = self.memory_manager.conversation_store
        try:
            groups = await asyncio.to_thread(store.find_duplicates, threshold=0.9)
            to_delete = [doc_id for group in groups for doc_id in group[1:]]
            removed = await asyncio.to_thread(store.delete_batch, to_delete) if to_delete else 0
        except Exception as e:
            self.transport.emit(ev.MEMORY_RESULT, {"success": False, "error": str(e)})
            return
        self.transport.emit(ev.MEMORY_RESULT, {
            "success": True,
            "message": f"已清理 {removed} 条重复记忆",
        })
        await self._show_memory()

    # ---------- 模型 / 模式 ----------

    async def _set_mode(self, mode: str) -> None:
        from prompts import SystemPrompts
        if mode not in SystemPrompts.list_modes():
            self.transport.emit(ev.SYSTEM_MESSAGE, {
                "text": f"[Mode] 未知模式 '{mode}'，可用: {', '.join(SystemPrompts.list_modes())}",
                "type": "dim",
            })
            return
        session = self._ensure_session()
        session.mode = mode
        self.store.mark_dirty(session)
        self.transport.emit(ev.MODE_CHANGED, {"mode": mode, "success": True})

    def _mode(self) -> str:
        return self.kernel.session.mode if self.kernel.session else "default"

    async def _select_model(self) -> str:
        while True:
            models = await self._fetch_models()
            if models:
                self.transport.emit(ev.SHOW_MODEL_SELECTION, {"models": models})
            chosen = (await self.transport.request_control(
                "请选择模型或输入模型名", "model_choice"
            ) or "").strip()
            if chosen.startswith("/"):
                self.transport.emit(ev.SYSTEM_MESSAGE, {
                    "text": "请先选择模型后再使用命令。",
                    "type": "error",
                })
                continue
            if chosen and (not models or chosen in models):
                return chosen
            if models:
                self.transport.emit(ev.SYSTEM_MESSAGE, {
                    "text": f"模型不存在: {chosen}",
                    "type": "error",
                })

    async def _fetch_models(self) -> List[str]:
        import aiohttp
        url = self.config.api.url
        if "bigmodel.cn" in url:
            base = url.split("/v4/")[0]
            models_url = f"{base}/v4/models"
        elif "/v1/" in url:
            models_url = url.split("/v1/")[0] + "/v1/models"
        else:
            models_url = url.rstrip("/") + "/models"

        headers = {}
        if self.config.api.key:
            headers["Authorization"] = f"Bearer {self.config.api.key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    models_url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    if isinstance(data, list):
                        return data
                    if "models" in data:
                        return [m["name"] for m in data["models"]]
                    if "data" in data:
                        return [m["id"] for m in data["data"]]
                    return []
        except Exception:
            return []

    # ---------- 输入分发 ----------

    def _handle_raw_message(self, text: str) -> None:
        """传输层已把普通文本放进输入队列，这里只处理结构化 JSON。"""
        stripped = text.strip()
        if not stripped.startswith("{"):
            return
        try:
            msg = json.loads(stripped)
        except json.JSONDecodeError:
            return
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")
        if kind == "fetch_models":
            asyncio.create_task(self._handle_fetch_models(msg))
        elif kind == "create_new_chat":
            asyncio.create_task(self._dispatch(stripped))
        elif kind == "set_mode":
            asyncio.create_task(self._dispatch(stripped))

    async def _handle_fetch_models(self, msg: Dict[str, Any]) -> None:
        models = await self._fetch_models()
        self.transport.emit(ev.MODELS_FETCHED, {
            "request_id": msg.get("request_id"),
            "models": models,
        })

    def _try_json(self, raw: str) -> Optional[Dict[str, Any]]:
        if not raw.strip().startswith("{"):
            return None
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return msg if isinstance(msg, dict) else None

    # ---------- 状态 ----------

    def _status(self) -> None:
        session = self.kernel.session
        tokens = sum(m.estimate_tokens() for m in session.messages) if session else 0
        self.transport.emit(ev.STATUS_UPDATE, {
            "workspace": str(self.workspace_dir),
            "model": self.model,
            "tokens": tokens,
        })

    async def _terminal_publisher(self) -> None:
        last = ""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(0.5)
                if self.tools.async_shell.is_shell_open():
                    snapshot = self.tools.async_shell.get_screen_snapshot() or ""
                    if snapshot != last:
                        last = snapshot
                        self.transport.emit(ev.TERMINAL_OUTPUT, {"content": snapshot, "is_open": True})
                elif last != "__closed__":
                    last = "__closed__"
                    self.transport.emit(ev.TERMINAL_OUTPUT, {"content": "Paw 未打开终端", "is_open": False})
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.transport.emit(ev.SYSTEM_MESSAGE, {"text": f"[终端推送失败] {e}", "type": "dim"})
                return

    # ---------- 记忆 ----------

    async def _init_memory(self) -> None:
        try:
            from memory import MemoryManager
            cfg = self.config.memory
            self.memory_manager = await asyncio.to_thread(
                MemoryManager,
                project_path=self.workspace_dir,
                embedding_url=cfg.embedding_url,
                embedding_key=cfg.embedding_key,
                embedding_model=cfg.embedding_model,
                recall=self.config.recall,
            )
            from core.catalog import register_memory_tools
            register_memory_tools(self.registry, self.memory_manager)
            self.prompt_builder.memory_manager = self.memory_manager
            self.transport.emit(ev.SYSTEM_MESSAGE, {"text": "[记忆] 系统已就绪", "type": "dim"})
        except Exception as e:
            self.transport.emit(ev.SYSTEM_MESSAGE, {
                "text": f"[记忆] 初始化失败: {e}",
                "type": "error",
            })

    # ---------- REST ----------

    def _mount_routes(self) -> None:
        app = self.transport.app

        @app.get("/api/config")
        async def get_config() -> JSONResponse:
            return JSONResponse({"success": True, "config": public_config(self.config)})

        @app.post("/api/config")
        async def put_config(request: Request) -> JSONResponse:
            payload = await request.json()
            incoming = payload.get("config") or {}
            merged = self.config.to_dict()
            _deep_update(merged, incoming)
            self.config = AppConfig(**_from_dict(merged))
            save_config(self.config)
            self._rebuild_clients()
            return JSONResponse({"success": True, "message": "配置已保存并已生效"})

        @app.get("/api/modes")
        async def modes() -> JSONResponse:
            from prompts import SystemPrompts
            return JSONResponse({"modes": SystemPrompts.list_modes_with_meta()})

        @app.get("/api/turns")
        async def turns() -> JSONResponse:
            session = self.kernel.session
            if session is None:
                return JSONResponse({"success": True, "turns": []})
            return JSONResponse({"success": True, "turns": session.to_detailed()})

        @app.get("/api/turns/detailed")
        async def turns_detailed() -> JSONResponse:
            session = self.kernel.session
            if session is None:
                return JSONResponse({"success": True, "turns": []})
            return JSONResponse({"success": True, "turns": session.to_detailed()})

        @app.post("/api/turn/edit-chunk")
        async def edit_chunk(request: Request) -> JSONResponse:
            data = await request.json()
            session = self.kernel.session
            if session is None:
                return JSONResponse({"success": False, "error": "没有活动会话"})
            index = data.get("chunk_index")
            ok = self._edit_chunk(session, index, data.get("content", ""))
            if ok:
                self.store.mark_dirty(session)
                self.store.flush()
            return JSONResponse({"success": ok})

        @app.post("/api/turn/delete")
        async def delete_turn(request: Request) -> JSONResponse:
            data = await request.json()
            session = self.kernel.session
            if session is None:
                return JSONResponse({"success": False, "error": "没有活动会话"})
            ok = self._delete_turn(session, data.get("turn_index"))
            if ok:
                self.store.mark_dirty(session)
                self.store.flush()
                self._sync_sessions()
            return JSONResponse({"success": ok})

        @app.post("/api/turn/insert")
        async def insert_turn(request: Request) -> JSONResponse:
            data = await request.json()
            session = self.kernel.session
            if session is None:
                return JSONResponse({"success": False, "error": "没有活动会话"})
            ok = self._insert_turn(session, data.get("position"), data.get("role"), data.get("content", ""))
            if ok:
                self.store.mark_dirty(session)
                self.store.flush()
            return JSONResponse({"success": ok})

        @app.post("/api/turn/add-tool-call")
        async def add_tool_call(request: Request) -> JSONResponse:
            data = await request.json()
            session = self.kernel.session
            if session is None:
                return JSONResponse({"success": False, "error": "没有活动会话"})
            tool_call_id = self._add_tool_call(session, data)
            if tool_call_id:
                self.store.mark_dirty(session)
                self.store.flush()
            return JSONResponse({"success": bool(tool_call_id), "tool_call_id": tool_call_id})

        @app.post("/api/turn/remove-tool-call")
        async def remove_tool_call(request: Request) -> JSONResponse:
            data = await request.json()
            session = self.kernel.session
            if session is None:
                return JSONResponse({"success": False, "error": "没有活动会话"})
            ok = self._remove_tool_call(session, data.get("tool_call_id"))
            if ok:
                self.store.mark_dirty(session)
                self.store.flush()
            return JSONResponse({"success": ok})

        @app.post("/api/fs/list")
        async def fs_list(request: Request) -> JSONResponse:
            data = await request.json()
            path_str = data.get("path") or str(self.workspace_dir)
            p = Path(path_str).expanduser()
            if not p.exists():
                return JSONResponse({"success": False, "error": "路径不存在"})
            items = []
            try:
                for item in p.iterdir():
                    try:
                        stat = item.stat()
                        items.append({
                            "name": item.name,
                            "path": str(item),
                            "is_dir": item.is_dir(),
                            "size": stat.st_size if not item.is_dir() else 0,
                            "mtime": stat.st_mtime,
                        })
                    except OSError:
                        continue
            except PermissionError:
                return JSONResponse({"success": False, "error": "无访问权限"})
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            return JSONResponse({
                "success": True,
                "items": items,
                "current_path": str(p),
                "parent_path": str(p.parent),
            })

        @app.post("/api/fs/content")
        async def fs_content(request: Request) -> JSONResponse:
            data = await request.json()
            path_str = data.get("path")
            if not path_str:
                return JSONResponse({"success": False, "error": "缺少路径"})
            p = Path(path_str)
            if not p.is_file():
                return JSONResponse({"success": False, "error": "文件不存在"})
            if p.stat().st_size > 1024 * 1024:
                return JSONResponse({"success": False, "error": "文件超过 1MB，无法预览"})
            return JSONResponse({"success": True, "content": p.read_text(encoding="utf-8", errors="replace")})

        @app.post("/api/fs/save")
        async def fs_save(request: Request) -> JSONResponse:
            data = await request.json()
            path_str = data.get("path")
            if not path_str:
                return JSONResponse({"success": False, "error": "缺少路径"})
            p = Path(path_str)
            if not p.parent.exists():
                return JSONResponse({"success": False, "error": "父目录不存在"})
            p.write_text(data.get("content", ""), encoding="utf-8")
            return JSONResponse({"success": True})

        @app.post("/api/calibrate-threshold")
        async def calibrate(request: Request) -> JSONResponse:
            data = await request.json()
            url = data.get("embedding_url") or self.config.memory.embedding_url
            model = data.get("embedding_model") or self.config.memory.embedding_model
            if not url or not model:
                return JSONResponse({"success": False, "error": "请先配置 Embedding URL 和模型"})
            from lib.calibrate_threshold import calibrate_api
            result = await asyncio.to_thread(calibrate_api, url, model)
            return JSONResponse(result)

        @app.get("/api/skills/search")
        async def skills_search(q: str = "", category: str = "", page: int = 1, repo: str = "") -> JSONResponse:
            from lib.skill_marketplace import SkillMarketplace
            marketplace = SkillMarketplace()
            result = await asyncio.to_thread(
                marketplace.search_skills, query=q, category=category, page=page, repo=repo
            )
            return JSONResponse(result)

        @app.post("/api/skills/install")
        async def skills_install(request: Request) -> JSONResponse:
            from lib.skill_marketplace import SkillMarketplace
            data = await request.json()
            marketplace = SkillMarketplace()
            result = await asyncio.to_thread(
                marketplace.download_skill,
                skill_id=data.get("skill_id"),
                skill_name=data.get("skill_name"),
                repo_url=data.get("repo_url"),
            )
            return JSONResponse(result)

        @app.get("/api/skills/installed")
        async def skills_installed() -> JSONResponse:
            from lib.skill_marketplace import SkillMarketplace
            marketplace = SkillMarketplace()
            return JSONResponse(await asyncio.to_thread(marketplace.list_installed_skills))

        @app.delete("/api/skills/{skill_name}")
        async def skills_uninstall(skill_name: str) -> JSONResponse:
            from lib.skill_marketplace import SkillMarketplace
            marketplace = SkillMarketplace()
            return JSONResponse(await asyncio.to_thread(marketplace.uninstall_skill, skill_name=skill_name))

    # ---------- 编辑器操作 ----------

    @staticmethod
    def _chunk_to_message_index(session: Session, chunk_index: int) -> Optional[int]:
        """chunks 下标 → messages 下标（两者的投影一一对应）。"""
        chunks = session.to_chunks()
        if chunk_index < 0 or chunk_index >= len(chunks):
            return None
        offset = 0
        for message_index, message in enumerate(session.messages):
            if message.role == "assistant":
                produced = (1 if message.content else 0) + len(message.tool_calls or [])
            elif message.role in ("user", "tool"):
                produced = 1
            else:
                produced = 0
            if offset <= chunk_index < offset + produced:
                # 必须用枚举下标：按值查找在多条内容相同的消息上会指错
                return message_index
            offset += produced
        return None

    def _edit_chunk(self, session: Session, chunk_index: Any, content: str) -> bool:
        if not isinstance(chunk_index, int):
            return False
        idx = self._chunk_to_message_index(session, chunk_index)
        if idx is None:
            return False
        message = session.messages[idx]
        if message.role not in ("user", "assistant"):
            return False
        message.content = content
        return True

    def _delete_turn(self, session: Session, turn_index: Any) -> bool:
        if not isinstance(turn_index, int):
            return False
        turns = session.to_detailed()
        if turn_index < 0 or turn_index >= len(turns):
            return False
        turn = turns[turn_index]
        start_chunk, end_chunk = turn["start_idx"], turn["end_idx"]
        start_msg = self._chunk_to_message_index(session, start_chunk)
        end_msg = self._chunk_to_message_index(session, end_chunk)
        if start_msg is None or end_msg is None:
            return False
        del session.messages[start_msg:end_msg + 1]
        return True

    def _insert_turn(self, session: Session, position: Any, role: Any, content: str) -> bool:
        if role not in ("user", "assistant") or not isinstance(position, int):
            return False
        turns = session.to_detailed()
        if position >= len(turns):
            insert_at = len(session.messages)
        else:
            insert_at = self._chunk_to_message_index(session, turns[position]["start_idx"])
            if insert_at is None:
                insert_at = len(session.messages)
        session.messages.insert(insert_at, Message(role, content))
        return True

    def _add_tool_call(self, session: Session, data: Dict[str, Any]) -> Optional[str]:
        turn_index = data.get("turn_index")
        name = (data.get("tool_name") or "").strip()
        if not isinstance(turn_index, int) or not name:
            return None
        turns = session.to_detailed()
        if turn_index < 0 or turn_index >= len(turns):
            return None
        start_msg = self._chunk_to_message_index(session, turns[turn_index]["start_idx"])
        end_msg = self._chunk_to_message_index(session, turns[turn_index]["end_idx"])
        if start_msg is None or end_msg is None:
            return None
        # 工具调用只能挂在本轮次之内的 assistant 消息上，不能跨轮
        assistant_idx = None
        for i in range(start_msg, end_msg + 1):
            if session.messages[i].role == "assistant":
                assistant_idx = i
        if assistant_idx is None:
            return None
        tool_call_id = f"manual_{uuid_hex()}"
        arguments = data.get("arguments") or "{}"
        result_text = data.get("result")

        message = session.messages[assistant_idx]
        if message.tool_calls is None:
            message.tool_calls = []
        message.tool_calls.append({
            "id": tool_call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        })
        if result_text:
            # 结果必须紧跟调用之后，否则 OpenAI 协议不合法
            session.insert_tool_result_after(assistant_idx, tool_call_id, name, result_text, True)
        return tool_call_id

    def _remove_tool_call(self, session: Session, tool_call_id: Any) -> bool:
        if not isinstance(tool_call_id, str) or not tool_call_id:
            return False
        removed = False
        for message in session.messages:
            if message.role == "assistant" and message.tool_calls:
                keep = [tc for tc in message.tool_calls if tc.get("id") != tool_call_id]
                if len(keep) != len(message.tool_calls):
                    message.tool_calls = keep or None
                    removed = True
        session.messages = [
            m for m in session.messages
            if not (m.role == "tool" and m.tool_call_id == tool_call_id)
        ]
        return removed

    def _persist_memory(self) -> None:
        pending = getattr(self, "_pending_memory_save", None)
        if not pending:
            return
        self._pending_memory_save = None
        user_text, session = pending
        if not session.messages:
            return
        last_assistant = None
        for message in reversed(session.messages):
            if message.role == "assistant":
                last_assistant = message.content
                break
        if not last_assistant:
            return
        try:
            self.memory_manager.save_conversation(user_text, last_assistant)
        except Exception as e:
            self.transport.emit(ev.SYSTEM_MESSAGE, {"text": f"[记忆] 保存失败: {e}", "type": "dim"})

    def _rebuild_clients(self) -> None:
        self.llm = LLMClient(self.config.api.url, self.config.api.key, self.model or "default")
        self.kernel.llm = self.llm
        self.budget.max_tokens = self.config.context.max_tokens
        self.prompt_builder.config = self.config


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


def _deep_update(target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _from_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    from core.config import (
        ApiConfig, ContextConfig, IdentityConfig, MemoryConfig, RecallConfig,
        TerminalConfig, WebConfig,
    )
    return {
        "identity": IdentityConfig(**data.get("identity", {})),
        "api": ApiConfig(**{k: v for k, v in data.get("api", {}).items() if k in ApiConfig.__dataclass_fields__}),
        "memory": MemoryConfig(**{k: v for k, v in data.get("memory", {}).items() if k in MemoryConfig.__dataclass_fields__}),
        "recall": RecallConfig(**{k: v for k, v in data.get("recall", {}).items() if k in RecallConfig.__dataclass_fields__}),
        "terminal": TerminalConfig(**{k: v for k, v in data.get("terminal", {}).items() if k in TerminalConfig.__dataclass_fields__}),
        "web": WebConfig(**{k: v for k, v in data.get("web", {}).items() if k in WebConfig.__dataclass_fields__}),
        "context": ContextConfig(**{k: v for k, v in data.get("context", {}).items() if k in ContextConfig.__dataclass_fields__}),
        "workspace": WorkspaceConfig(**{
            k: v for k, v in data.get("workspace", {}).items()
            if k in WorkspaceConfig.__dataclass_fields__
        }),
        "theme": data.get("theme") or {},
    }
