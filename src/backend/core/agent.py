#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent 内核：一轮对话的状态机。

一次 run_turn 的生命周期：
    user 消息入会话
    → [请求模型 → 流式文本 → 有 tool_calls 则执行 → 结果回填]*
    → 无工具调用时结束

停止：外部 set_stop() 置位，模型流式阶段通过抛异常中断，工具阶段在
下一个工具开始前中断。中断点都会落盘已产生的部分内容。

内核不认识 WebSocket、不认识 UI 语义，只通过 EventSink 发事件。
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core import events as ev
from core.context import ContextBudget
from core.llm import LLMClient, LLMError
from core.session import Session
from core.storage import SessionStore
from core.tokens import count_json
from core.tools import ToolError, execute_tool


class StopRequested(Exception):
    """用户请求中断当前生成。"""


@dataclass
class TurnOutcome:
    completed: bool
    stopped: bool = False
    error: Optional[str] = None
    final_text: str = ""


class AgentKernel:
    def __init__(
        self,
        sink,
        llm: LLMClient,
        registry,
        store: SessionStore,
        budget: ContextBudget,
        system_prompt_builder,
        max_steps: int = 32,
        show_reasoning: bool = True,
    ):
        self.sink = sink
        self.llm = llm
        self.registry = registry
        self.store = store
        self.budget = budget
        self.build_system_prompt = system_prompt_builder
        self.max_steps = max_steps
        self.show_reasoning = show_reasoning
        self.session: Optional[Session] = None
        self._stop = asyncio.Event()
        self._stream_id: Optional[str] = None
        self._reasoning_id: Optional[str] = None
        # 本轮临时注入的记忆（不进会话历史，避免模型模仿其格式）
        self.pending_context: str = ""
        # 本次流式已产出的文本（中断时用它落盘，避免内容丢失）
        self._streamed_text: str = ""
        self._streamed_reasoning: str = ""

    # ---------- 会话 ----------

    def attach(self, session: Session) -> None:
        self.session = session
        self.store.mark_dirty(session)

    def ensure_session(self, workspace_dir: str, model: Optional[str], mode: str = "default") -> Session:
        """首条消息到达时才真正创建会话，避免启动即产生空会话。"""
        if self.session is None:
            return self.create_session(workspace_dir=workspace_dir, model=model, mode=mode)
        return self.session

    def create_session(self, workspace_dir: str, model: Optional[str], mode: str = "default",
                       title: str = "", system_prompt: str = "") -> Session:
        session = Session(
            workspace_dir=workspace_dir,
            model=model,
            mode=mode,
            title=title or "新对话",
            is_manual_title=bool(title),
        )
        if system_prompt:
            session.custom_system_prompt = system_prompt
        self.attach(session)
        self.store.save(session)
        return session

    def load_session(self, session_id: str) -> Optional[Session]:
        session = self.store.load(session_id)
        if session is None:
            return None
        self.attach(session)
        return session

    def set_stop(self) -> None:
        self._stop.set()

    # ---------- 事件 ----------

    def _emit(self, event: str, data: Dict[str, Any]) -> None:
        self.sink.emit(event, data)

    def _sys(self, text: str, kind: str = "dim") -> None:
        self._emit(ev.SYSTEM_MESSAGE, {"text": text, "type": kind})

    def _status(self, **fields) -> None:
        self._emit(ev.STATUS_UPDATE, fields)

    # ---------- 主循环 ----------

    async def run_turn(self, user_input: str) -> TurnOutcome:
        if self.session is None:
            raise RuntimeError(
                "没有活动会话。调用 run_turn 前必须先 ensure_session()。"
            )

        self._stop.clear()
        self._streamed_text = ""
        self._streamed_reasoning = ""
        self.budget.reset()
        session = self.session
        session.add_user(user_input)
        self.store.mark_dirty(session)
        self._refresh_status()

        final_text = ""
        hit_step_limit = False
        overflow_retried = False
        for step in range(1, self.max_steps + 1):
            if self._stop.is_set():
                return self._finish_stopped(final_text)

            messages = self._prepare_messages()
            if self.pending_context and step == 1:
                messages.append({"role": "assistant", "content": self.pending_context})
                self.pending_context = ""
            try:
                result = await self.llm.chat(
                    messages,
                    tools=self.registry.schemas(),
                    on_delta=self._on_delta,
                    on_reasoning=self._on_reasoning,
                )
            except StopRequested:
                self._end_stream()
                self._end_reasoning()
                if self._streamed_text or self._streamed_reasoning:
                    session.add_assistant(
                        self._streamed_text, None, self._streamed_reasoning or None
                    )
                    self.store.mark_dirty(session)
                self._streamed_text = ""
                self._streamed_reasoning = ""
                return self._finish_stopped(final_text)
            except LLMError as e:
                self._end_stream()
                self._end_reasoning()
                if e.kind == "context_overflow" and not overflow_retried:
                    # 服务端说上下文超了：说明估算偏低，收紧本轮预算后重试一次。
                    # 只重试一次，再失败就是真的超了，直接报给用户。
                    overflow_retried = True
                    target = self.budget.shrink()
                    self._sys(
                        f"[上下文] 服务端报告上下文超限，已收紧到 {target} tokens 并重试",
                        "dim",
                    )
                    continue
                self._sys(str(e), "error")
                return TurnOutcome(completed=False, error=str(e), final_text=final_text)

            self._end_stream()
            self._end_reasoning()
            reasoning = self._streamed_reasoning
            self._streamed_text = ""
            self._streamed_reasoning = ""
            if result.content:
                final_text = result.content
            if result.reasoning:
                reasoning = result.reasoning

            session.add_assistant(
                result.content or "",
                result.tool_calls or None,
                reasoning or None,
            )
            self.store.mark_dirty(session)

            if result.truncated:
                # 截断必须说出来：用户看到的断句和"模型不会写"是两回事
                self._sys(
                    f"[模型] 输出达到长度上限（{self.llm.max_tokens} tokens）被截断，"
                    "可在设置中调高最大输出长度",
                    "error",
                )

            if not result.tool_calls:
                break

            outcome = await self._run_tool_calls(result.tool_calls)
            if outcome == "stop":
                # 未执行的工具调用不能留在会话里：没有对应 tool 结果
                # 的 tool_calls 会让下一次请求直接被协议拒绝
                self._drop_unresolved_tool_calls()
                return self._finish_stopped(final_text)
            if outcome == "silent":
                return self._finish_silent()
        else:
            # 循环自然走完说明到达步数上限，必须让用户看到
            hit_step_limit = True

        if hit_step_limit:
            self._sys(
                f"[Agent] 已达到单轮最大工具步数（{self.max_steps}），本轮已中止",
                "error",
            )
        self.store.mark_dirty(session)
        self.store.flush()
        self._refresh_status()
        return TurnOutcome(completed=True, final_text=final_text)

    async def _run_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> str:
        """执行一轮工具调用。

        返回 "continue" 表示应继续请求模型，"stop" 表示用户中断，
        "silent" 表示模型要求沉默、本轮已丢弃。
        """
        assert self.session is not None
        for call in tool_calls:
            if self._stop.is_set():
                return "stop"

            call_id = call.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            spec = self.registry.get(name)

            self._emit(ev.TOOL_START, {
                "id": call_id,
                "name": name,
                "args": raw_args,
                "raw_request": call,
            })

            args: Dict[str, Any] = {}
            display = None
            if spec is None:
                output, success = f"错误: 未知工具 {name}", False
            else:
                try:
                    args = json.loads(raw_args) if raw_args else {}
                    if not isinstance(args, dict):
                        raise ToolError("工具参数必须是 JSON 对象")
                except (json.JSONDecodeError, ToolError) as e:
                    output, success = f"错误: 工具参数解析失败: {e}", False
                else:
                    result = await execute_tool(spec, args)
                    output, success = result.output, result.success
                    try:
                        display = spec.display(args, output, success)
                    except Exception as e:
                        # 展示层失败不应影响工具结果本身，但要可见
                        self._sys(f"[展示格式化失败] {spec.name}: {e}", "dim")
                    if result.raw and result.raw.get("shell_just_opened"):
                        self._sys("[终端] 共享终端已启动", "dim")

            self.session.add_tool_result(
                tool_call_id=call_id,
                name=name,
                output=output,
                success=success,
                display=display,
                max_call_pairs=spec.max_call_pairs if spec else 0,
            )
            if spec and spec.shell:
                self._emit(ev.TERMINAL_OUTPUT, {
                    "content": self._shell_output(),
                    "is_open": True,
                })
            self.store.mark_dirty(self.session)

            self._emit(ev.TOOL_RESULT, {
                "id": call_id,
                "name": name,
                "display": display,
                "success": success,
                "raw_response": {"success": success, "result": output},
            })

            if name == "stay_silent" and success:
                # 沉默：丢弃本轮产生的助手文本与工具块，直接结束
                self._discard_silent_turn()
                return "silent"

            if name in ("create_todo_list", "add_todos", "mark_todo_as_done", "read_todos"):
                self._emit_todos()

        return "continue"

    def _discard_silent_turn(self) -> None:
        """stay_silent：移除本轮最后一条 user 之后的内容，保留用户输入本身。

        前端在收到 stay_silent 时只移除助手卡片，因此这里也必须保留
        用户消息，否则刷新后用户会发现自己说的话不见了。
        """
        assert self.session is not None
        messages = self.session.messages
        last_user = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == "user":
                last_user = i
                break
        if last_user is not None:
            del messages[last_user + 1:]
        self.store.mark_dirty(self.session)
        self.store.flush()

    # ---------- 消息准备 ----------

    def _prepare_messages(self) -> List[Dict[str, Any]]:
        assert self.session is not None
        system_prompt = self.build_system_prompt(self.session)
        tools_tokens = count_json(self.registry.schemas())
        # 预留输出空间：输入占满预算时模型没有余量生成回复
        reserve = min(4096, max(512, self.llm.max_tokens))
        messages, report = self.budget.fit(
            self.session,
            system_prompt,
            tools_tokens,
            lambda s: s.to_llm_messages(system_prompt),
            reserve=reserve,
        )
        if report.dropped_turns:
            self._sys(
                f"[上下文] 超出预算，已移除最旧的 {report.dropped_turns} 轮对话"
                f"（当前 {report.after}/{self.budget.effective_max()} tokens）",
                "dim",
            )
        return messages

    # ---------- 流式 ----------

    def _on_delta(self, text: str) -> None:
        if self._stop.is_set():
            raise StopRequested()
        self._end_reasoning()
        self._streamed_text += text
        if self._stream_id is None:
            self._stream_id = str(uuid.uuid4())
            self._emit(ev.ASSISTANT_STREAM_START, {"id": self._stream_id})
        self._emit(ev.ASSISTANT_STREAM_CHUNK, {"id": self._stream_id, "text": text})

    def _on_reasoning(self, text: str) -> None:
        """思维链走独立通道，不混入正文。

        部分模型会边思考边输出正文，两者交替到达；一旦开始出正文就
        结束思考块，避免前端把正文挤进折叠区。
        """
        if self._stop.is_set():
            raise StopRequested()
        if not self.show_reasoning:
            return
        self._streamed_reasoning += text
        if self._reasoning_id is None:
            self._reasoning_id = str(uuid.uuid4())
            self._emit(ev.REASONING_START, {"id": self._reasoning_id})
        self._emit(ev.REASONING_CHUNK, {"id": self._reasoning_id, "text": text})

    def _end_stream(self) -> None:
        if self._stream_id is not None:
            self._emit(ev.ASSISTANT_STREAM_END, {"id": self._stream_id})
            self._stream_id = None

    def _end_reasoning(self) -> None:
        if self._reasoning_id is not None:
            self._emit(ev.REASONING_END, {"id": self._reasoning_id})
            self._reasoning_id = None

    def _drop_unresolved_tool_calls(self) -> None:
        """移除没有对应 tool 结果的工具调用。"""
        assert self.session is not None
        resolved = {m.tool_call_id for m in self.session.messages if m.role == "tool"}
        for message in self.session.messages:
            if message.role != "assistant" or not message.tool_calls:
                continue
            message.tool_calls = [
                tc for tc in message.tool_calls
                if (tc.get("id") or "") in resolved
            ] or None
        self.store.mark_dirty(self.session)

    def _finish_silent(self) -> TurnOutcome:
        self._end_stream()
        self.store.mark_dirty(self.session)
        self.store.flush()
        self._refresh_status()
        return TurnOutcome(completed=True, final_text="")

    def _finish_stopped(self, final_text: str) -> TurnOutcome:
        self._end_stream()
        self.store.mark_dirty(self.session)
        self.store.flush()
        self._sys("[已停止]", "dim")
        return TurnOutcome(completed=True, stopped=True, final_text=final_text)

    def _shell_output(self) -> str:
        """从工具实现层读取终端当前屏幕内容。"""
        getter = getattr(self.registry, "shell_snapshot", None)
        if callable(getter):
            return getter() or ""
        return ""

    def _refresh_status(self) -> None:
        if self.session is None:
            return
        tokens = sum(m.estimate_tokens() for m in self.session.messages)
        self._status(
            workspace=self.session.workspace_dir,
            model=self.session.model,
            tokens=tokens,
            limit=self.budget.effective_max(),
        )

    def _emit_todos(self) -> None:
        getter = getattr(self.registry, "todo_plan", None)
        if callable(getter):
            self._emit(ev.TODOS_UPDATED, {"todos": getter()})
