#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""上下文预算管理。

职责：保证发往模型的整个请求不超预算；超出时按策略压缩，并把
压缩动作显式记录到会话（而不是悄悄丢弃）。

策略顺序（从最便宜到最贵）：
1. 折叠 shell 输出：只保留最近一次。
2. 修剪旧工具结果：保留配对结构，但把内容截断成摘要。
3. 裁剪最旧的轮次：以 user 消息为边界整轮移除。

第 3 步会真正丢信息，因此必须在事件流里告知用户，且保留最近
keep_recent_turns 轮不动。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.session import Message, Session
from core.tokens import count_messages

# 工具结果截断后保留的字符数
TOOL_RESULT_KEEP_CHARS = 1200
SHELL_KEEP_CHARS = 4000
# 共享终端的工具名：它们的输出是同一块屏幕的重复快照
SHELL_TOOL_NAMES = {"run_command", "open_shell", "interrupt_command"}


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    return count_messages(messages)


@dataclass
class BudgetReport:
    before: int
    after: int
    dropped_turns: int
    trimmed_tool_results: int
    collapsed_shells: int


class ContextBudget:
    def __init__(self, max_tokens: int, keep_recent_turns: int = 4):
        self.max_tokens = max_tokens
        self.keep_recent_turns = keep_recent_turns
        # 服务端报告上下文超长后，本轮改用更小的目标，避免重试时再次超限
        self.override: Optional[int] = None

    def effective_max(self) -> int:
        return self.override or self.max_tokens

    def shrink(self, ratio: float = 0.6) -> int:
        """把本轮的预算目标下调，返回新的目标值。"""
        self.override = max(1024, int(self.effective_max() * ratio))
        return self.override

    def reset(self) -> None:
        self.override = None

    def fit(
        self,
        session: Session,
        system_prompt: str,
        tools_tokens: int,
        build: callable,
        reserve: int = 0,
    ) -> Tuple[List[Dict[str, Any]], BudgetReport]:
        """把会话压到预算内，返回最终消息与报告。

        build(session) -> messages 由调用方提供（复用 session.to_llm_messages），
        以便压缩后重新构建时保持一致。reserve 是本轮要预留的输出空间，
        必须从可用预算里扣掉，否则输入占满后模型没有余量生成回复。
        """
        available = self.effective_max() - tools_tokens - reserve
        messages = build(session)
        before = estimate_tokens(messages)

        report = BudgetReport(before=before, after=before, dropped_turns=0,
                              trimmed_tool_results=0, collapsed_shells=0)
        if before <= available:
            return messages, report

        self._collapse_shells(session, report)
        messages = build(session)
        if estimate_tokens(messages) <= available:
            report.after = estimate_tokens(messages)
            return messages, report

        self._trim_tool_results(session, report)
        messages = build(session)
        if estimate_tokens(messages) <= available:
            report.after = estimate_tokens(messages)
            return messages, report

        dropped = self._drop_oldest_turns(session, available, build)
        report.dropped_turns = dropped
        messages = build(session)
        report.after = estimate_tokens(messages)
        return messages, report

    # ---------- 压缩动作 ----------

    @staticmethod
    def _collapse_shells(session: Session, report: BudgetReport) -> None:
        """同名的 shell 结果只保留最近一条的完整内容，其余截断。"""
        shell_msgs = [
            m for m in session.messages
            if m.role == "tool" and m.name in SHELL_TOOL_NAMES
        ]
        for msg in shell_msgs[:-1]:
            if len(msg.content) > SHELL_KEEP_CHARS:
                msg.content = _truncate(msg.content, SHELL_KEEP_CHARS)
                report.collapsed_shells += 1

    @staticmethod
    def _trim_tool_results(session: Session, report: BudgetReport) -> None:
        for msg in session.messages:
            if msg.role != "tool":
                continue
            if len(msg.content) <= TOOL_RESULT_KEEP_CHARS:
                continue
            msg.content = _truncate(msg.content, TOOL_RESULT_KEEP_CHARS)
            report.trimmed_tool_results += 1

    def _drop_oldest_turns(self, session: Session, available: int, build: callable) -> int:
        """以 user 消息为边界整轮丢弃，保留最近 keep_recent_turns 轮。"""
        dropped = 0
        while True:
            messages = build(session)
            if estimate_tokens(messages) <= available:
                return dropped

            user_indices = [i for i, m in enumerate(session.messages) if m.role == "user"]
            # 至少保留最近 keep_recent_turns 轮，避免删到空会话
            if len(user_indices) <= self.keep_recent_turns:
                return dropped

            cut_index = user_indices[0]
            end_index = user_indices[1]
            del session.messages[cut_index:end_index]
            session.compacted_turns += 1
            dropped += 1


def _truncate(text: str, keep: int) -> str:
    if len(text) <= keep:
        return text
    omitted = len(text) - keep
    return f"{text[:keep]}\n…[已省略 {omitted} 字符，原始内容不在上下文中]"
