#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""会话状态。

内部模型是标准的 OpenAI 消息流（user / assistant / tool），因为这是模型
真正消费的东西。对外通过 to_chunks() 投影成前端渲染需要的块结构。

两者是同一份数据的不同视图，不存在第二份真相。
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    role: str                      # user | assistant | tool | system
    content: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    # 模型输出的思维链。只用于展示，不参与后续请求。
    reasoning: Optional[str] = None
    # 展示用附加信息（不参与模型请求）
    display: Optional[Dict[str, Any]] = None
    success: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_llm(self) -> Dict[str, Any]:
        if self.role == "assistant":
            msg: Dict[str, Any] = {
                "role": "assistant",
                "content": self.content or None,
            }
            if self.tool_calls:
                msg["tool_calls"] = self.tool_calls
            return msg
        if self.role == "tool":
            msg = {
                "role": "tool",
                "content": self.content,
                "tool_call_id": self.tool_call_id or "",
            }
            if self.name:
                msg["name"] = self.name
            return msg
        return {"role": self.role, "content": self.content}

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "success": self.success,
        }
        if self.tool_calls:
            data["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.name:
            data["name"] = self.name
        if self.reasoning:
            data["reasoning"] = self.reasoning
        if self.display:
            data["display"] = self.display
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", "") or "",
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
            reasoning=data.get("reasoning"),
            display=data.get("display"),
            success=data.get("success", True),
            timestamp=data.get("timestamp") or datetime.now().isoformat(),
        )

    def estimate_tokens(self) -> int:
        from core.tokens import count_json, count_text

        chars = count_text(self.content)
        if self.tool_calls:
            chars += count_json(self.tool_calls)
        # 思维链不进入请求，不占预算
        return max(1, chars)


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = "新对话"
    is_manual_title: bool = False
    workspace_dir: str = ""
    model: Optional[str] = None
    mode: str = "default"
    messages: List[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # 被压缩掉的轮次数，用于在 UI 中显式告知用户
    compacted_turns: int = 0
    # 用户在新建对话时自定义的系统提示词，为空则用默认构建器
    custom_system_prompt: str = ""

    # ---------- 追加 ----------

    def add_user(self, text: str) -> Message:
        msg = Message("user", text)
        self.messages.append(msg)
        self.touch()
        return msg

    def add_assistant(
        self,
        text: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        reasoning: Optional[str] = None,
    ) -> Message:
        msg = Message("assistant", text or "", tool_calls=tool_calls, reasoning=reasoning)
        self.messages.append(msg)
        self.touch()
        return msg

    def add_tool_call(self, tool_call: Dict[str, Any]) -> Message:
        """把一次工具调用挂到最近一条 assistant 消息上。

        OpenAI 协议要求 tool_calls 属于 assistant 消息，不能独立成条。
        """
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                if msg.tool_calls is None:
                    msg.tool_calls = []
                msg.tool_calls.append(tool_call)
                self.touch()
                return msg
        # 没有 assistant 消息时补一条空 assistant，保持协议合法
        return self.add_assistant("", [tool_call])

    def insert_tool_result_after(
        self,
        after_index: int,
        tool_call_id: str,
        name: str,
        output: str,
        success: bool = True,
    ) -> Message:
        """把工具结果插到指定消息之后，保证紧跟其 tool_call。"""
        message = Message(
            "tool",
            output,
            tool_call_id=tool_call_id,
            name=name,
            success=success,
        )
        self.messages.insert(after_index + 1, message)
        self.touch()
        return message

    def add_tool_result(
        self,
        tool_call_id: str,
        name: str,
        output: str,
        success: bool,
        display: Optional[Dict[str, Any]] = None,
        max_call_pairs: int = 0,
    ) -> Message:
        msg = Message(
            "tool",
            output,
            tool_call_id=tool_call_id,
            name=name,
            display=display,
            success=success,
        )
        self.messages.append(msg)
        if max_call_pairs > 0:
            self._prune_tool_pairs(name, max_call_pairs)
        self.touch()
        return msg

    def _prune_tool_pairs(self, tool_name: str, keep: int) -> None:
        """同一工具只保留最近 keep 组调用/结果，从最旧的开始整组移除。"""
        call_ids: List[str] = []
        for msg in self.messages:
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    if (tc.get("function") or {}).get("name") == tool_name:
                        call_ids.append(tc.get("id") or "")
        if len(call_ids) <= keep:
            return
        stale = set(call_ids[:-keep])
        self.messages = [m for m in self.messages if not _message_belongs_to(m, stale)]

    # ---------- 视图 ----------

    def to_llm_messages(self, system_prompt: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for msg in self.messages:
            # 空的 assistant 且无工具调用在协议上非法，跳过
            if msg.role == "assistant" and not msg.content and not msg.tool_calls:
                continue
            result.append(msg.to_llm())
        return result

    def to_chunks(self) -> List[Dict[str, Any]]:
        """投影成前端渲染使用的块列表。

        顺序与 messages 一致；assistant 消息里的 tool_calls 展开成独立的
        tool_call 块，与工具结果块交替出现。
        """
        chunks: List[Dict[str, Any]] = []
        for index, msg in enumerate(self.messages):
            msg_id = f"m{index}"
            if msg.role == "user":
                chunks.append({
                    "type": "user",
                    "msg_id": msg_id,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "tokens": msg.estimate_tokens(),
                    "metadata": {},
                })
            elif msg.role == "assistant":
                if msg.reasoning:
                    chunks.append({
                        "type": "reasoning",
                        "msg_id": msg_id,
                        "content": msg.reasoning,
                        "timestamp": msg.timestamp,
                        "tokens": 0,
                        "metadata": {},
                    })
                if msg.content:
                    chunks.append({
                        "type": "assistant",
                        "msg_id": msg_id,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                        "tokens": msg.estimate_tokens(),
                        "metadata": {"tool_calls": msg.tool_calls} if msg.tool_calls else {},
                    })
                for tc in msg.tool_calls or []:
                    chunks.append({
                        "type": "tool_call",
                        "msg_id": msg_id,
                        "content": json.dumps(tc, ensure_ascii=False),
                        "timestamp": msg.timestamp,
                        "tokens": 0,
                        "metadata": {},
                    })
            elif msg.role == "tool":
                chunks.append({
                    "type": "tool_result",
                    "msg_id": msg_id,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "tokens": msg.estimate_tokens(),
                    "metadata": {
                        "tool_call_id": msg.tool_call_id or "",
                        "name": msg.name or "",
                        "success": msg.success,
                        "display": msg.display,
                    },
                })
        return chunks

    def to_detailed(self) -> List[Dict[str, Any]]:
        """消息编辑器使用的轮次视图。"""
        chunks = self.to_chunks()
        turns: List[Dict[str, Any]] = []
        index = 0
        while index < len(chunks):
            chunk = chunks[index]
            if chunk["type"] == "user":
                turns.append({
                    "turn_index": len(turns),
                    "role": "user",
                    "start_idx": index,
                    "end_idx": index,
                    "chunks": [dict(chunk, chunk_index=index)],
                })
                index += 1
                continue
            start = index
            group = [dict(chunk, chunk_index=index)]
            index += 1
            while index < len(chunks) and chunks[index]["type"] != "user":
                group.append(dict(chunks[index], chunk_index=index))
                index += 1
            turns.append({
                "turn_index": len(turns),
                "role": "assistant",
                "start_idx": start,
                "end_idx": index - 1,
                "chunks": group,
            })
        return turns

    def count_turns(self) -> int:
        return sum(1 for m in self.messages if m.role == "user")

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()
        if not self.is_manual_title and self.title == "新对话":
            auto = self._auto_title()
            if auto:
                self.title = auto

    def _auto_title(self) -> str:
        for msg in self.messages:
            if msg.role == "user" and msg.content.strip():
                return msg.content.strip().replace("\n", " ")[:24]
        return ""

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "is_manual_title": self.is_manual_title,
            "workspace_dir": self.workspace_dir,
            "model": self.model,
            "mode": self.mode,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "compacted_turns": self.compacted_turns,
            "custom_system_prompt": self.custom_system_prompt,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        return cls(
            session_id=data.get("session_id") or str(uuid.uuid4())[:8],
            title=data.get("title") or "新对话",
            is_manual_title=data.get("is_manual_title", False),
            workspace_dir=data.get("workspace_dir", ""),
            model=data.get("model"),
            mode=data.get("mode", "default"),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            created_at=data.get("created_at") or datetime.now().isoformat(),
            updated_at=data.get("updated_at") or datetime.now().isoformat(),
            compacted_turns=data.get("compacted_turns", 0),
            custom_system_prompt=data.get("custom_system_prompt", ""),
        )


def _message_belongs_to(msg: Message, tool_call_ids: set) -> bool:
    if msg.role == "tool" and msg.tool_call_id in tool_call_ids:
        return True
    if msg.role == "assistant" and msg.tool_calls:
        removed = [tc for tc in msg.tool_calls if (tc.get("id") or "") in tool_call_ids]
        if not removed:
            return False
        msg.tool_calls = [tc for tc in msg.tool_calls if (tc.get("id") or "") not in tool_call_ids]
        # 若这条 assistant 只剩工具调用且全被移除，整条一起移除
        return bool(msg.content) or bool(msg.tool_calls)
    return False
