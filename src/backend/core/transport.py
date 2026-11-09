#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HTTP + WebSocket 传输层。

这里只负责搬运：把前端消息交给应用层，把应用层事件交给前端。
不含业务判断，也不持有会话状态。

事件通过一个有序队列发送，保证 stream_start 一定先于 stream_chunk 到达。
"""

import asyncio
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core import events as ev


class Transport:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.app = FastAPI()
        self._ws: Optional[WebSocket] = None
        self._queue: Optional[asyncio.Queue] = None
        self._sender: Optional[asyncio.Task] = None
        self._pending: List[Dict[str, Any]] = []
        self._input_queue: Optional[asyncio.Queue] = None
        self._control_queue: Optional[asyncio.Queue] = None
        self._expect_control: Optional[str] = None
        # 会话令牌：只有页面自身能读写本服务，阻止其它本机网页调用
        self._token = secrets.token_urlsafe(32)
        self._on_message: Optional[Callable[[str], None]] = None
        self._on_stop: Optional[Callable[[], None]] = None
        self._on_connect: Optional[Callable[[], None]] = None
        self._on_disconnect: Optional[Callable[[], None]] = None
        self._setup_routes()

    # ---------- 事件 ----------

    def emit(self, event: str, data: Dict[str, Any]) -> None:
        payload = {"event": event, "data": data}
        if self._queue is None:
            self._pending.append(payload)
            return
        self._queue.put_nowait(payload)

    def _ensure_queue(self) -> None:
        if self._queue is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._queue = asyncio.Queue()
        self._input_queue = asyncio.Queue()
        self._control_queue = asyncio.Queue()
        self._sender = loop.create_task(self._sender_loop())

    async def _sender_loop(self) -> None:
        assert self._queue is not None
        while True:
            payload = await self._queue.get()
            ws = self._ws
            if ws is None:
                self._pending.append(payload)
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                # 连接已坏，转存待发，等待重连后补发
                self._pending.append(payload)
                self._ws = None
            finally:
                self._queue.task_done()

    async def _flush_pending(self) -> None:
        ws = self._ws
        if ws is None:
            return
        while self._pending:
            payload = self._pending.pop(0)
            try:
                await ws.send_json(payload)
            except Exception:
                self._pending.insert(0, payload)
                return

    # ---------- 输入 ----------

    async def get_input(self) -> str:
        self._ensure_queue()
        return await self._input_queue.get()

    async def request_control(self, prompt: str, kind: str) -> str:
        """请求一次控制类输入（如模型选择），期间普通输入仍走主队列。"""
        self._ensure_queue()
        self._expect_control = kind
        self.emit(ev.REQUEST_INPUT, {"prompt": prompt, "type": kind})
        value = await self._control_queue.get()
        self._expect_control = None
        return value

    # ---------- 路由 ----------

    def _setup_routes(self) -> None:
        renderer_dir = os.getenv("PAW_RENDERER_DIR")
        static_dir = os.getenv("PAW_STATIC_DIR")
        if not renderer_dir or not Path(renderer_dir).exists():
            raise RuntimeError(f"JS 目录不存在或未设置: PAW_RENDERER_DIR={renderer_dir}")
        if not static_dir or not Path(static_dir).exists():
            raise RuntimeError(f"静态资源目录不存在或未设置: PAW_STATIC_DIR={static_dir}")

        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")
        self.app.mount("/js", StaticFiles(directory=renderer_dir), name="js")

        @self.app.get("/", response_class=HTMLResponse)
        async def index() -> HTMLResponse:
            template = Path(__file__).resolve().parent.parent.parent.parent / "resources" / "templates" / "index.html"
            if not template.exists():
                return HTMLResponse("Error: index.html not found.", status_code=500)
            # 注入本次进程的令牌；页面之外的第三方来源拿不到它
            html = template.read_text(encoding="utf-8").replace(
                "{{PAW_TOKEN}}", self._token
            )
            return HTMLResponse(html)

        def token_ok(value: Optional[str]) -> bool:
            return bool(value) and hmac.compare_digest(value, self._token)

        @self.app.middleware("http")
        async def guard(request, call_next):
            # 页面与静态资源可匿名取；接口和写操作必须带令牌
            path = request.url.path
            if path in ("/",) or path.startswith("/static/") or path.startswith("/js/"):
                return await call_next(request)
            if not token_ok(request.headers.get("X-Paw-Token")):
                return JSONResponse({"success": False, "error": "unauthorized"}, status_code=403)
            return await call_next(request)

        @self.app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket) -> None:
            if not token_ok(ws.query_params.get("token")):
                await ws.close(code=4401)
                return
            await ws.accept()
            # 单客户端：新连接顶替旧连接
            self._ws = ws
            self._ensure_queue()
            await self._flush_pending()
            if self._on_connect:
                self._on_connect()
            try:
                while True:
                    text = await ws.receive_text()
                    self._route_input(text)
            except WebSocketDisconnect:
                # 只清理自己这条连接：旧连接在新连接建立之后才断开时，
                # 不能把新连接一并清掉，否则事件会一直堆在待发队列里
                if self._ws is ws:
                    self._ws = None
                    if self._on_disconnect:
                        self._on_disconnect()

    def _route_input(self, text: str) -> None:
        stripped = text.strip()

        # 停止是最高优先级，不进队列
        if stripped == "/stop":
            if self._on_stop:
                self._on_stop()
            return

        # JSON 控制消息：只认识约定过的类型，其它一律丢弃并提示
        if stripped.startswith("{"):
            try:
                msg = json.loads(stripped)
            except json.JSONDecodeError:
                msg = None
            if not isinstance(msg, dict):
                self.emit(ev.SHOW_ERROR, {"text": "无法解析的控制消息"})
                return
            kind = msg.get("type")
            if kind in ("fetch_models", "create_new_chat", "set_mode"):
                if self._on_message:
                    self._on_message(stripped)
            else:
                # 未知 JSON 不进入对话，避免污染上下文
                self.emit(ev.SHOW_ERROR, {"text": f"未知的控制消息类型: {kind}"})
            return

        # 模型选择期间，非命令输入优先进入控制队列
        if self._expect_control:
            if stripped.startswith("/"):
                if self._input_queue is not None:
                    self._input_queue.put_nowait(text)
            elif self._control_queue is not None:
                self._control_queue.put_nowait(text)
            return

        if self._input_queue is not None:
            self._input_queue.put_nowait(text)

    def set_handlers(
        self,
        on_message: Callable[[str], None],
        on_stop: Callable[[], None],
        on_connect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_message = on_message
        self._on_stop = on_stop
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect

    async def serve(self) -> None:
        import uvicorn
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()
