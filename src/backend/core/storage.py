#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""会话持久化：SQLite。

写入是增量且节流的：内容变化时只标记脏，由后台协程按固定间隔落盘，
避免流式输出期间每来一个 token 就同步重写整个会话文件。
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from core.session import Session


class SessionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._dirty: Optional[Session] = None
        self._last_flush = 0.0
        self._flush_interval = 2.0

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    is_manual_title INTEGER NOT NULL DEFAULT 0,
                    workspace_dir TEXT NOT NULL,
                    model TEXT,
                    mode TEXT NOT NULL DEFAULT 'default',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC)"
            )

    # ---------- 读 ----------

    def load(self, session_id: str) -> Optional[Session]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return Session.from_dict(json.loads(row["payload"]))

    def list_sessions(self, limit: int = 50) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, title, workspace_dir, model, mode,
                       message_count, turn_count, updated_at
                FROM sessions ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "title": row["title"],
                "timestamp": row["updated_at"].replace("T", " ")[:19],
                "workspace_dir": row["workspace_dir"],
                "model": row["model"],
                "mode": row["mode"],
                "message_count": row["message_count"],
                "turn_count": row["turn_count"],
            }
            for row in rows
        ]

    def exists(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return row is not None

    # ---------- 写 ----------

    def save(self, session: Session) -> None:
        payload = json.dumps(session.to_dict(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, title, is_manual_title, workspace_dir, model,
                    mode, message_count, turn_count, updated_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    title = excluded.title,
                    is_manual_title = excluded.is_manual_title,
                    workspace_dir = excluded.workspace_dir,
                    model = excluded.model,
                    mode = excluded.mode,
                    message_count = excluded.message_count,
                    turn_count = excluded.turn_count,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    session.session_id,
                    session.title,
                    int(session.is_manual_title),
                    session.workspace_dir,
                    session.model,
                    session.mode,
                    len(session.messages),
                    session.count_turns(),
                    session.updated_at,
                    payload,
                ),
            )

    def delete(self, session_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            return cursor.rowcount > 0

    # ---------- 节流 ----------

    def mark_dirty(self, session: Session) -> None:
        """标记需要保存，真正落盘交给 flush_if_due。"""
        self._dirty = session

    def flush_if_due(self, force: bool = False) -> bool:
        if self._dirty is None:
            return False
        now = time.monotonic()
        if not force and now - self._last_flush < self._flush_interval:
            return False
        session = self._dirty
        self._dirty = None
        self.save(session)
        self._last_flush = now
        return True

    def flush(self) -> bool:
        return self.flush_if_due(force=True)

    async def run_flusher(self, stop_event: asyncio.Event) -> None:
        """后台落盘协程：有脏数据时按间隔写入。"""
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._flush_interval)
            except asyncio.TimeoutError:
                pass
            self.flush_if_due()
        self.flush()
