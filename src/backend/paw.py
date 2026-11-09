#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Paw 后端入口。

启动顺序：解析参数 → 建立传输层 → 建立应用层 → 并发运行服务与输入循环。
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Windows 控制台 UTF-8 兼容
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Paw - 桌面 AI Agent 后端")
    parser.add_argument("workspace", nargs="?", default=None, help="工作目录（默认取配置 workspace.home_dir，否则用户主目录）")
    parser.add_argument("--host", "-H", default="127.0.0.1")
    parser.add_argument("--port", "-p", type=int, default=8081)
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    from core.config import load_config

    if args.workspace:
        workspace_dir = args.workspace
    else:
        configured_home = load_config().workspace.home_dir
        workspace_dir = configured_home or str(Path.home())

    from core.app import PawApp
    from core.transport import Transport

    transport = Transport(host=args.host, port=args.port)
    app = PawApp(host=args.host, port=args.port, workspace_dir=workspace_dir, transport=transport)

    # 先开始监听，再进入需要前端交互的初始化（例如模型选择）。
    # 否则在没有配置模型时，前端连不上、选择请求永远等不到。
    server_task = asyncio.create_task(transport.serve())
    await app.start()
    try:
        await server_task
    finally:
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
