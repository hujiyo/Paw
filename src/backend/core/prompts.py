#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""系统提示词构建。

基础提示词、模式提示词来自 prompts.py；这里负责组装运行时信息
（工作目录、终端状态、Skill 清单、记忆、会话自定义提示词）。
"""

from datetime import datetime
from pathlib import Path
import yaml

from core.config import AppConfig
from core.session import Session
from prompts import SystemPrompts


# 进程启动时间：用于提示词里的"活跃时长"，不随会话变化
BIRTH_TIME = datetime.now()


def _birth_time_value() -> datetime:
    return BIRTH_TIME


class SystemPromptBuilder:
    def __init__(self, config: AppConfig, tools, memory_manager=None):
        self.config = config
        self.tools = tools
        self.memory_manager = memory_manager

    def rebuild(self) -> None:
        """配置变更后重新构建（例如记忆系统初始化完成）。"""
        return None

    def __call__(self, session: Session) -> str:
        if session.custom_system_prompt:
            return session.custom_system_prompt

        terminal = self.tools.get_terminal_status()
        if terminal.get("is_open"):
            terminal_info = (
                f"共享终端已开启 (PID: {terminal.get('pid')}, "
                f"工作目录: {terminal.get('working_directory')})"
            )
        else:
            terminal_info = f"终端未启动 (工作目录: {terminal.get('working_directory')})"

        identity = self.config.identity
        base = SystemPrompts.get_main_system_prompt(
            identity.name,
            _birth_time_value(),
            Path(session.workspace_dir).name if session.workspace_dir else "workspace",
            hujiyo=identity.username,
            honey=identity.honey,
        ).replace("{terminal_status}", terminal_info)

        parts = [base]

        mode_prompt = SystemPrompts.get_mode_prompt(session.mode)
        if mode_prompt:
            parts.append(mode_prompt)

        skills_prompt = self._skills_prompt()
        if skills_prompt:
            parts.append(skills_prompt)

        if self.memory_manager is not None:
            memory_prompt = self.memory_manager.get_memory_prompt()
            if memory_prompt:
                parts.append(memory_prompt)

        return "\n\n".join(parts)

    @staticmethod
    def _skills_prompt() -> str:
        skills_dir = Path.home() / ".paw" / "skills"
        if not skills_dir.exists():
            return ""

        skills = []
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                content = skill_md.read_text(encoding="utf-8")
                parts = content.split("---")
                if len(parts) < 3:
                    continue
                meta = yaml.safe_load(parts[1].strip()) or {}
                name = meta.get("name", skill_dir.name)
                desc = meta.get("description", "No description")
                skills.append(f"- {name}: {desc}")
            except Exception:
                # 单个 skill 的 frontmatter 损坏不影响其它 skill
                continue

        if not skills:
            return ""

        return (
            "# Available Skills\n\n"
            "Use load_skill(skill_name=\"...\") to read a skill's full instructions "
            "before working on a task that matches its purpose.\n\n"
            + "\n".join(skills)
        )


