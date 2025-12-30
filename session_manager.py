#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
会话管理器 - Session Manager

负责保存和恢复完整的对话会话状态，包括：
- ChunkManager 的完整 chunks
- Shell 终端状态
- 工作目录
- 模型配置
- 时间戳和标题
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class SessionSnapshot:
    """会话快照"""
    session_id: str                              # 会话ID
    title: str                                   # 对话标题（从第一条用户消息生成）
    timestamp: str                               # 创建时间
    workspace_dir: str                           # 工作目录
    model: str                                   # 模型名称
    chunks: List[Dict[str, Any]]                 # ChunkManager 的 chunks
    token_count: int                             # token 总数
    message_count: int                           # 消息数量（用户+助手）
    shell_open: bool = False                     # 终端是否打开
    shell_pid: Optional[int] = None              # 终端PID（如果打开）


class SessionManager:
    """
    会话管理器

    保存位置: ~/.paw/sessions/
    文件格式: {session_id}.json
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """初始化

        Args:
            storage_path: 存储目录，默认为 ~/.paw/sessions/
        """
        if storage_path is None:
            home = Path.home()
            self.storage_path = home / ".paw" / "sessions"
        else:
            self.storage_path = Path(storage_path)

        self.storage_path.mkdir(parents=True, exist_ok=True)

        # 索引文件，加速列表查询
        self.index_path = self.storage_path / "index.json"
        self._index = self._load_index()

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        """加载会话索引"""
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_index(self):
        """保存会话索引"""
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SessionManager] 保存索引失败: {e}")

    def _update_index(self, snapshot: SessionSnapshot):
        """更新索引"""
        self._index[snapshot.session_id] = {
            "title": snapshot.title,
            "timestamp": snapshot.timestamp,
            "workspace_dir": snapshot.workspace_dir,
            "model": snapshot.model,
            "message_count": snapshot.message_count,
            "token_count": snapshot.token_count,
            "shell_open": snapshot.shell_open
        }
        self._save_index()

    def _generate_title(self, chunks: List[Dict[str, Any]]) -> str:
        """从 chunks 生成对话标题

        使用第一条用户消息的前30个字符
        """
        for chunk in chunks:
            if chunk.get("type") == "user":
                content = chunk.get("content", "")
                # 去掉换行和多余空格
                content = " ".join(content.split())
                if len(content) > 30:
                    content = content[:30] + "..."
                return content or "新对话"
        return "空对话"

    def _count_messages(self, chunks: List[Dict[str, Any]]) -> int:
        """统计消息数量（用户+助手）"""
        count = 0
        for chunk in chunks:
            if chunk.get("type") in ("user", "assistant"):
                count += 1
        return count

    def save_session(self,
                     chunk_manager,
                     workspace_dir: str,
                     model: str,
                     shell_open: bool = False,
                     shell_pid: Optional[int] = None,
                     session_id: Optional[str] = None) -> SessionSnapshot:
        """保存当前会话

        Args:
            chunk_manager: ChunkManager 实例
            workspace_dir: 工作目录路径
            model: 模型名称
            shell_open: 终端是否打开
            shell_pid: 终端PID
            session_id: 已存在的会话ID（更新现有会话时使用）

        Returns:
            SessionSnapshot 对象
        """
        # 导出 chunks
        chunks_data = chunk_manager.to_json()

        # 生成或使用现有 session_id
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]

        # 生成标题
        title = self._generate_title(chunks_data)

        # 创建快照
        snapshot = SessionSnapshot(
            session_id=session_id,
            title=title,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            workspace_dir=str(workspace_dir),
            model=model,
            chunks=chunks_data,
            token_count=chunk_manager.current_tokens,
            message_count=self._count_messages(chunks_data),
            shell_open=shell_open,
            shell_pid=shell_pid
        )

        # 保存到文件
        session_file = self.storage_path / f"{session_id}.json"
        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": snapshot.session_id,
                    "title": snapshot.title,
                    "timestamp": snapshot.timestamp,
                    "workspace_dir": snapshot.workspace_dir,
                    "model": snapshot.model,
                    "chunks": snapshot.chunks,
                    "token_count": snapshot.token_count,
                    "message_count": snapshot.message_count,
                    "shell_open": snapshot.shell_open,
                    "shell_pid": snapshot.shell_pid
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SessionManager] 保存会话失败: {e}")
            return snapshot

        # 更新索引
        self._update_index(snapshot)

        return snapshot

    def load_session(self, session_id: str) -> Optional[SessionSnapshot]:
        """加载会话

        Args:
            session_id: 会话ID

        Returns:
            SessionSnapshot 对象，如果不存在则返回 None
        """
        session_file = self.storage_path / f"{session_id}.json"

        if not session_file.exists():
            return None

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            return SessionSnapshot(
                session_id=data["session_id"],
                title=data["title"],
                timestamp=data["timestamp"],
                workspace_dir=data["workspace_dir"],
                model=data["model"],
                chunks=data["chunks"],
                token_count=data.get("token_count", 0),
                message_count=data.get("message_count", 0),
                shell_open=data.get("shell_open", False),
                shell_pid=data.get("shell_pid")
            )
        except Exception as e:
            print(f"[SessionManager] 加载会话失败: {e}")
            return None

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出会话列表

        Args:
            limit: 最多返回数量

        Returns:
            按时间倒序的会话列表
        """
        # 从索引读取
        sessions = []
        for session_id, info in self._index.items():
            sessions.append({
                "session_id": session_id,
                **info
            })

        # 按时间倒序排序
        sessions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return sessions[:limit]

    def delete_session(self, session_id: str) -> bool:
        """删除会话

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        session_file = self.storage_path / f"{session_id}.json"

        # 删除文件
        if session_file.exists():
            try:
                session_file.unlink()
            except Exception:
                pass

        # 从索引移除
        if session_id in self._index:
            del self._index[session_id]
            self._save_index()
            return True

        return False

    def get_session_path(self) -> Path:
        """获取存储路径"""
        return self.storage_path
