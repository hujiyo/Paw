#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Paw的启动器
统一入口，上帝视角，完全可视化
科幻风格的神经界面体验
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import re
import yaml
import aiohttp
import time

# 设置环境为UTF-8（Windows兼容）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 导入核心组件
from tools import BaseTools,WebTools
from chunk_system import ChunkManager, ChunkType, Chunk
from tool_definitions import TOOLS_SCHEMA, register_all_tools, register_web_tools
from tool_registry import ToolRegistry
from prompts import SystemPrompts, UIPrompts, ToolPrompts
from memory import MemoryManager
from branch_executor import AutoContextManager
from session_manager import SessionManager
from call import LLMClient, LLMConfig


class Paw:
    """
    Paw - 数字生命体主程序
    统一标准启动，完全可视化，上帝视角
    """

    def __init__(self, ui: Any, api_url: str = None, model: str = None, api_key: str = None, workspace_dir: str = None):
        """初始化

        Args:
            api_url: API地址，如果为None则从config.yaml或环境变量读取
            model: 模型名称，如果为None则从config.yaml或环境变量读取
            api_key: API密钥，如果为None则从config.yaml或环境变量读取
            minimal: 是否使用极简模式（减少状态栏等装饰）
            workspace_dir: 工作目录路径，如果为None则从 PAW_HOME 环境变量读取
        """
        # 基础配置
        self.birth_time = datetime.now()
        self._startup_t0 = time.perf_counter()
        self._startup_marks = []

        def _mark(label: str):
            now = time.perf_counter()
            self._startup_marks.append((label, now - self._startup_t0))

        # UI系统（统一入口）
        self.ui = ui
        _mark("UI 初始化")

        # 读取配置文件
        config = self._load_config()
        _mark("读取 config.yaml")
        
        # 从配置读取身份信息（支持用户自定义名字和称谓）
        # 变量命名: paw=Paw的名字, hujiyo=用户名, honey=用户昵称
        identity = config.get('identity', {})
        self.paw = identity.get('name', 'Paw')
        self.hujiyo = identity.get('username', 'hujiyo')
        self.honey = identity.get('honey', '老公')

        # 核心组件（传递配置和工作目录）
        self.tools = BaseTools(sandbox_dir=workspace_dir, config=config)
        _mark("BaseTools 初始化")
        
        # 保存工作目录信息（用于提示词）
        self.workspace_dir = self.tools.sandbox_dir
        self.workspace_name = self.workspace_dir.name
        
        # 注册所有工具到 ToolRegistry
        register_all_tools(self.tools)
        _mark("注册工具")
        
        # API配置（优先级：参数 > config.yaml > 默认值）
        self.api_url = api_url or config.get('api', {}).get('url') or "http://localhost:1234/v1/chat/completions"
        self.model = model or config.get('api', {}).get('model') or "default"
        self.api_key = api_key or config.get('api', {}).get('key') or ""
        
        # LLM 客户端（统一的 API 调用）
        self.llm = LLMClient(LLMConfig(
            api_url=self.api_url,
            model=self.model,
            api_key=self.api_key
        ))
        
        # Web 工具（需要 API 配置来生成摘要）
        self.web_tools = WebTools(
            config=config.get('web', {}),
            api_url=self.api_url,
            model_getter=lambda: self.model,  # 动态获取当前模型
            api_key=self.api_key
        )
        register_web_tools(self.web_tools)
        _mark("WebTools 初始化")

        # 上下文管理（使用语块系统，传入工具schema）
        self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)
        _mark("ChunkManager 初始化")

        # 记忆系统：延迟初始化到 run() 里
        # 避免首次运行下载/加载 embedding 导致冷启动卡住进不了首屏
        self.memory_manager = None
        
        # 会话ID（用于记忆整理）
        import uuid
        self.session_id = str(uuid.uuid4())[:8]
        
        # 上下文分支管理器（延迟初始化，等API配置确定后）
        self.context_manager = None

        # 会话管理器（用于保存/恢复完整对话状态）
        self.session_manager = SessionManager()
        self.current_session_id = None  # 当前会话ID（用于更新现有会话）

        # 停止事件（用于中断生成）
        self._stop_event = None

        # 注册停止回调（用于 WebUI 立即响应 /stop 命令）
        if hasattr(ui, 'set_stop_callback'):
            ui.set_stop_callback(self._handle_stop_request)

        # 系统提示词（第一人称）
        self.system_prompt = self._create_system_prompt()
        _mark("构建 system_prompt")
        
        # 注意：消息历史现在完全由chunk_manager管理
        # 不再使用self.messages

        # 启动耗时记录仅供内部排查，不对用户输出

    def _handle_stop_request(self):
        """处理停止请求（由 WebUI 直接调用，绕过消息队列）"""
        if self._stop_event:
            self._stop_event.set()

    def _load_config(self) -> dict:
        """加载config.yaml配置文件"""
        config_path = Path(__file__).parent / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                self.ui.print_error(f"警告: 无法读取config.yaml - {e}")
                return {}
        return {}
    
    async def _init_memory_system_async(self):
        """异步初始化记忆系统（不阻塞主流程）"""
        try:
            config = self._load_config()
            memory_cfg = config.get('memory') or {}
            
            # 检查是否启用记忆系统
            if not memory_cfg.get('enabled', False):
                self.memory_manager = None
                if hasattr(self.ui, 'send_message'):
                    await self.ui.send_message("memory_ready", {"status": "disabled"})
                return
            
            embedding_url = memory_cfg.get('embedding_url', 'http://localhost:11434/api/embeddings')
            embedding_key = memory_cfg.get('embedding_key', '')
            embedding_model = memory_cfg.get('embedding_model', 'nomic-embed-text')
            
            # 在后台线程中执行初始化
            def _load_memory():
                return MemoryManager(
                    project_path=self.workspace_dir,
                    embedding_url=embedding_url,
                    embedding_key=embedding_key,
                    embedding_model=embedding_model,
                )
            
            self.memory_manager = await asyncio.to_thread(_load_memory)
            
            # 记忆系统初始化完成后，重建 system_prompt 以注入记忆
            self.system_prompt = self._create_system_prompt()
            
            # 通知前端记忆系统已就绪
            if hasattr(self.ui, 'send_message'):
                await self.ui.send_message("memory_ready", {"status": "ok"})
                
        except Exception as e:
            # 记忆系统初始化失败，静默降级为无记忆模式
            self.memory_manager = None
            if hasattr(self.ui, 'send_message'):
                await self.ui.send_message("memory_ready", {"status": "failed", "error": str(e)})
    
    def _create_system_prompt(self) -> str:
        """创建系统提示词 - 第一人称视角"""
        # 获取终端状态
        terminal_status = self.tools.get_terminal_status()
        
        # 构建终端信息
        if terminal_status.get('is_open'):
            terminal_info = f"共享终端已开启 (PID: {terminal_status.get('pid')}, 工作目录: {terminal_status.get('working_directory')})"
        else:
            terminal_info = f"终端未启动 (工作目录: {terminal_status.get('working_directory')})"
        
        # 使用提示词配置文件（传入工作目录名称和身份信息）
        main_prompt = SystemPrompts.get_main_system_prompt(
            self.paw, self.birth_time, self.workspace_name,
            hujiyo=self.hujiyo, honey=self.honey
        )
        
        # 替换终端状态占位符
        main_prompt = main_prompt.replace("{terminal_status}", terminal_info)

        # 组合基础系统提示词
        prompt = main_prompt

        # === 注入 Skill 列表（Level 1: name + description）===
        skills_prompt = self._get_skills_prompt()
        if skills_prompt:
            prompt = prompt + "\n\n" + skills_prompt
        
        # 注入记忆（如果有）
        if self.memory_manager is not None:
            memory_prompt = self.memory_manager.get_memory_prompt()
            if memory_prompt:
                prompt = prompt + "\n\n" + memory_prompt

        # 添加或更新系统提示词到语块管理器
        has_system = any(c.chunk_type == ChunkType.SYSTEM for c in self.chunk_manager.chunks)
        if has_system:
            self.chunk_manager.update_latest_system_prompt(prompt)
        else:
            self.chunk_manager.add_system_prompt(prompt)
        return prompt

    def _get_skills_prompt(self) -> str:
        """扫描并生成 Skill 列表提示词

        Returns:
            Skill 提示词，如果没有 Skill 则返回空字符串
        """
        import yaml
        from pathlib import Path

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
                content = skill_md.read_text(encoding='utf-8')
                # 提取 YAML frontmatter
                parts = content.split('---')
                if len(parts) >= 3:
                    yaml_part = parts[1].strip()
                    metadata = yaml.safe_load(yaml_part)
                    name = metadata.get('name', skill_dir.name)
                    desc = metadata.get('description', 'No description')
                    skills.append(f"- {name}: {desc}")
            except Exception as e:
                # 跳过解析失败的 Skill
                continue

        if not skills:
            return ""

        return f"""# Available Skills

You have access to specialized skills. When a task matches a skill's purpose,
use the load_skill tool to read its full SKILL.md file for detailed instructions.

Available skills:
{chr(10).join(skills)}

**IMPORTANT**: Before working on any task, check if a relevant skill exists.
If so, call load_skill(skill_name="...") to get detailed instructions."""

    def _try_fix_json(self, raw_json: str) -> dict:
        """尝试修复常见的 JSON 格式问题
        
        Args:
            raw_json: 原始的无效 JSON 字符串
            
        Returns:
            修复后的 dict，如果无法修复则返回 None
        """
        import re
        
        fixed = raw_json.strip()
        
        # 1. 补全被截断的 JSON（缺少结尾 }）
        if not fixed.endswith('}'):
            fixed += '}'
        
        # 2. 修复未加引号的值，如 "includes":*.py -> "includes":"*.py"
        # 匹配 :"值" 或 :值 的模式，值不是 { [ " 数字 true false null 开头的
        fixed = re.sub(
            r':(\s*)([^"\[\]{}\s,][^,}\]]*?)(\s*[,}])',
            r':"\2"\3',
            fixed
        )
        
        # 3. 修复数组中未加引号的值，如 [*.py] -> ["*.py"]
        fixed = re.sub(
            r'\[(\s*)([^"\[\]{}\s,][^,\]]*?)(\s*)\]',
            r'["\2"]',
            fixed
        )
        
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        
        # 4. 更激进的修复：尝试用 ast.literal_eval（处理单引号等）
        try:
            import ast
            # 把单引号替换成双引号
            fixed2 = raw_json.replace("'", '"')
            return json.loads(fixed2)
        except:
            pass
        
        return None
    
    def _get_tool_display(self, tool_name: str, result: str, args: dict = None) -> dict:
        """生成工具显示信息
        
        Returns:
            {
                'line1': 第一行内容,
                'line2': 第二行内容(可选),
                'has_line2': 是否有第二行
            }
        """
        args = args or {}
        
        if tool_name == "open_shell":
            cwd = args.get("working_directory", ".")
            return {'line1': cwd, 'line2': '', 'has_line2': False}
        
        elif tool_name == "run_command":
            cmd = args.get("command", "")[:60]
            return {'line1': cmd, 'line2': '', 'has_line2': False, 'is_command': True}
        
        elif tool_name == "interrupt_command":
            return {'line1': '已中断', 'line2': '', 'has_line2': False}
        
        elif tool_name == "read_file":
            path = args.get("file_path", "")
            filename = path.split('/')[-1].split('\\')[-1] if path else ""
            total_lines = result.count('\n') + 1 if result else 0
            offset = args.get("offset")
            limit = args.get("limit")
            if offset and limit:
                end = offset + limit - 1
                range_str = f"({offset}-{end}/{total_lines})"
            elif offset:
                range_str = f"({offset}-end/{total_lines})"
            else:
                range_str = f"(all {total_lines}行)"
            return {'line1': f"{filename} {range_str}", 'line2': '', 'has_line2': False}
        
        elif tool_name == "write_to_file":
            path = args.get("file_path", "")
            filename = path.split('/')[-1].split('\\')[-1] if path else ""
            return {'line1': filename, 'line2': '', 'has_line2': False}
        
        elif tool_name == "delete_file":
            path = args.get("file_path", "")
            filename = path.split('/')[-1].split('\\')[-1] if path else ""
            return {'line1': filename, 'line2': '', 'has_line2': False}
        
        elif tool_name in ["edit", "multi_edit"]:
            path = args.get("file_path", "")
            filename = path.split('/')[-1].split('\\')[-1] if path else ""
            return {'line1': filename, 'line2': '', 'has_line2': False}
        
        elif tool_name == "list_dir":
            path = args.get("directory_path", ".")
            # 解析 list_dir 返回格式: "[dir] name/" 或 "[file] name (size)"
            lines = result.strip().split('\n') if result.strip() else []
            # 跳过第一行 "Contents of ..." 
            items = [l for l in lines if l.startswith('[')]
            count = len(items)
            # 提取文件/目录名
            names = []
            for item in items[:3]:
                # "[dir] name/" 或 "[file] name (size)"
                if '] ' in item:
                    name = item.split('] ')[1].split(' (')[0].rstrip('/')
                    names.append(name)
            preview = ', '.join(names)
            if count > 3:
                preview += f'... (+{count-3})'
            return {'line1': path, 'line2': preview, 'has_line2': count > 0}
        
        elif tool_name == "find_by_name":
            pattern = args.get("pattern", "")
            search_dir = args.get("search_directory", ".")
            items = result.strip().split('\n') if result.strip() else []
            count = len(items) if items and items[0] else 0
            if count == 0:
                return {'line1': f'"{pattern}" 无匹配', 'line2': '', 'has_line2': False}
            # 提取文件名
            names = [i.split('/')[-1].split('\\')[-1] for i in items[:3]]
            preview = ', '.join(names)
            if count > 3:
                preview += f'... (+{count-3})'
            return {'line1': f'"{pattern}" {count}匹配', 'line2': preview, 'has_line2': True}
        
        elif tool_name == "grep_search":
            query = args.get("query", "")
            # 结果可能是 "Found X matches in Y files" 或具体匹配行
            result_text = result.strip()
            if not result_text or "no matches" in result_text.lower():
                return {'line1': f'"{query}" 无匹配', 'line2': '', 'has_line2': False}
            # 第一行显示搜索词，第二行显示结果摘要
            lines = result_text.split('\n')
            summary = lines[0][:60] + '...' if len(lines[0]) > 60 else lines[0]
            if len(lines) > 1:
                summary += f' (+{len(lines)-1})'
            return {'line1': f'"{query}"', 'line2': summary, 'has_line2': True}
        
        elif tool_name == "wait":
            seconds = args.get("seconds", 0)
            return {'line1': f"{seconds}s", 'line2': '', 'has_line2': False}

        elif tool_name == "load_skill":
            skill_name = args.get("skill_name", "")
            # 解析结果（格式：Base Path: xxx\n\nSKILL内容）
            if result.startswith("Base Path:"):
                parts = result.split('\n\n', 1)
                base_path = parts[0].replace("Base Path:", "").strip()
                # 提取 SKILL.md 第一行作为摘要
                if len(parts) > 1:
                    skill_lines = parts[1].strip().split('\n')
                    summary = skill_lines[0][:50] + '...' if len(skill_lines[0]) > 50 else skill_lines[0]
                else:
                    summary = "SKILL.md"
                return {'line1': f"Skill: {skill_name}", 'line2': summary, 'has_line2': True}
            elif result.startswith("Error:"):
                return {'line1': f"Skill: {skill_name}", 'line2': result[:60], 'has_line2': True}
            else:
                return {'line1': f"Skill: {skill_name}", 'line2': '', 'has_line2': False}

        elif tool_name == "run_skill_script":
            skill_name = args.get("skill_name", "")
            script_name = args.get("script_name", "")
            if result.startswith("Error:"):
                return {'line1': f"Script: {script_name}", 'line2': result[:60], 'has_line2': True}
            elif result.startswith("STDOUT:"):
                # 提取第一行作为摘要
                lines = result.split('\n')
                first_line = lines[0][:50] + '...' if len(lines[0]) > 50 else lines[0]
                return {'line1': f"Script: {script_name}", 'line2': first_line, 'has_line2': True}
            else:
                return {'line1': f"Script: {script_name}", 'line2': 'executed', 'has_line2': True}

        elif tool_name == "update_plan":
            # 解析 JSON 结果
            try:
                data = json.loads(result) if isinstance(result, str) else result
                if not data.get("success"):
                    return {'line1': data.get("error", "未知错误"), 'line2': '', 'has_line2': False}
                completed = data.get("completed", 0)
                total = data.get("total", 0)
                explanation = data.get("explanation", "")
                plan = data.get("plan", [])
                # line1: 进度摘要
                line1 = f"{completed}/{total} completed"
                if explanation:
                    line1 = f"{explanation} ({line1})"
                # line2: 每个步骤一行
                if plan:
                    status_icons = {"pending": "○", "in_progress": "◉", "completed": "●"}
                    lines = []
                    for item in plan:
                        icon = status_icons.get(item["status"], "○")
                        step = item["step"][:50] + "..." if len(item["step"]) > 50 else item["step"]
                        lines.append(f"{icon} {step}")
                    return {'line1': line1, 'line2': '\n'.join(lines), 'has_line2': True}
                return {'line1': line1, 'line2': '', 'has_line2': False}
            except:
                return {'line1': '计划已更新', 'line2': '', 'has_line2': False}
        
        elif tool_name == "get_plan":
            # 解析 JSON 结果
            try:
                data = json.loads(result) if isinstance(result, str) else result
                plan = data.get("plan", [])
                completed = data.get("completed", 0)
                total = data.get("total", 0)
                if not plan:
                    return {'line1': '无计划', 'line2': '', 'has_line2': False}
                # line1: 进度
                line1 = f"{completed}/{total} completed"
                # line2: 步骤列表
                status_icons = {"pending": "○", "in_progress": "◉", "completed": "●"}
                lines = []
                for item in plan:
                    icon = status_icons.get(item["status"], "○")
                    step = item["step"][:50] + "..." if len(item["step"]) > 50 else item["step"]
                    lines.append(f"{icon} {step}")
                return {'line1': line1, 'line2': '\n'.join(lines), 'has_line2': True}
            except:
                return {'line1': '查询计划', 'line2': '', 'has_line2': False}
        
        elif tool_name == "search_web":
            query = args.get("query", "")
            # 解析 JSON 结果
            try:
                import json
                data = json.loads(result) if isinstance(result, str) else result
                results = data.get("results", [])
                count = len(results)
                if count == 0:
                    return {'line1': f'无结果 "{query}"', 'line2': '', 'has_line2': False}
                # 每行显示: [id] title
                lines = []
                for r in results:
                    url_id = r.get("id", "????")
                    title = r.get("title", "")
                    if len(title) > 55:
                        title = title[:52] + "..."
                    lines.append(f"[{url_id}] {title}")
                # 把条数放前面，query 放后面（会被截断）
                return {'line1': f'{count}条 "{query}"', 'line2': '\n'.join(lines), 'has_line2': True}
            except:
                return {'line1': f'"{query}"', 'line2': '', 'has_line2': False}
        
        elif tool_name == "load_url_content":
            url_arg = args.get("url", "")
            # 解析 JSON 结果
            try:
                import json
                data = json.loads(result) if isinstance(result, str) else result
                title = data.get("title", "无标题")[:40]
                url_id = data.get("url_id", "")
                pages = data.get("pages", [])
                # line1 显示: [url_id] title 或 title
                if url_id:
                    line1 = f"[{url_id}] {title}"
                else:
                    line1 = title
                if not pages:
                    return {'line1': line1, 'line2': '(空内容)', 'has_line2': True}
                # 每行显示一个 page: page_id + summary（摘要最多30字，不截断）
                lines = []
                for p in pages:
                    pid = p.get("page_id", "????")
                    summary = p.get("summary", "")
                    lines.append(f"[{pid}] {summary}")
                return {'line1': line1, 'line2': '\n'.join(lines), 'has_line2': True}
            except:
                return {'line1': url_arg[:40], 'line2': '', 'has_line2': False}
        
        elif tool_name == "read_page":
            page_id = args.get("page_id", "")
            # 解析 JSON 结果
            try:
                import json
                data = json.loads(result) if isinstance(result, str) else result
                page_num = data.get("page_num", "?")
                total = data.get("total_pages", "?")
                size = data.get("size", 0)
                return {'line1': f"[{page_id}] 第{page_num}/{total}页 ({size}字节)", 'line2': '', 'has_line2': False}
            except:
                return {'line1': f"[{page_id}]", 'line2': '', 'has_line2': False}
        
        else:
            # 默认
            brief = result.replace('\n', ' ')[:40]
            return {'line1': brief, 'line2': '', 'has_line2': False}
    
    def _update_status_bar(self):
        """更新状态栏显示"""
        if hasattr(self.ui, 'show_status_bar') and callable(self.ui.show_status_bar):
            # 完整上下文 token = 消息 token + 工具 schema token
            total_tokens = self.chunk_manager.current_tokens + self.chunk_manager.tools_tokens
            self.ui.show_status_bar(
                workspace=str(self.workspace_dir),
                model=self.model,
                tokens=total_tokens
            )
    
    def _refresh_shell_chunk(self, move_to_end: bool = False):
        """刷新Shell输出到chunk（如果终端已打开）
        
        Args:
            move_to_end: 是否将 Shell chunk 移动到末尾
                - True: 终端操作后调用，Shell chunk 紧跟在操作之后
                - False: 普通刷新，只更新内容不移动位置
        """
        if self.tools.async_shell.is_shell_open():
            # 获取终端屏幕快照
            screen_output = self.tools.async_shell.get_screen_snapshot()
            if screen_output:
                # 更新Shell chunk
                self.chunk_manager.update_shell_output(screen_output, move_to_end=move_to_end)
        else:
            # 终端已关闭，移除Shell chunk
            if self.chunk_manager.has_shell_chunk():
                self.chunk_manager.remove_shell_chunk()
    
    async def _call_llm_with_tools(self, messages: List[Dict]) -> Dict[str, Any]:
        """调用语言模型（支持Function Calling + 流式输出）

        Returns:
            {
                "role": "assistant",
                "content": str | None,
                "tool_calls": List[Dict] | None,
                "finish_reason": str
            }
        """
        # 用于跟踪是否有内容输出（控制换行）
        has_content = [False]
        last_chunk = ['']
        was_stopped = [False]  # 是否被用户停止

        def on_content(text: str):
            """流式内容回调"""
            # 检查停止请求
            if self._stop_event and self._stop_event.is_set():
                was_stopped[0] = True
                raise RuntimeError("User stopped")

            if not has_content[0]:
                has_content[0] = True
            last_chunk[0] = text
            self.ui.print_assistant(text, end='', flush=True)

        # 使用统一的 LLM 客户端（传入当前 model，因为可能在运行时选择）
        response = await self.llm.chat(
            messages,
            model=self.model,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=4000,
            stream=True,
            on_content=on_content
        )

        # 检查是否被用户停止
        if was_stopped[0]:
            if has_content[0] and last_chunk[0] and not last_chunk[0].endswith('\n'):
                print()
            # 通知 WebUI 流式结束
            if hasattr(self.ui, 'assistant_stream_end') and callable(getattr(self.ui, 'assistant_stream_end')):
                try:
                    self.ui.assistant_stream_end()
                except Exception:
                    pass
            return {
                "content": last_chunk[0] if has_content[0] else None,
                "tool_calls": [],
                "finish_reason": "stopped"
            }

        # 处理换行（只有当最后一行不是换行符时才打印换行）
        if has_content[0] and last_chunk[0] and not last_chunk[0].endswith('\n'):
            print()

        # 通知 WebUI 流式结束（如果支持）
        if hasattr(self.ui, 'assistant_stream_end') and callable(getattr(self.ui, 'assistant_stream_end')):
            try:
                self.ui.assistant_stream_end()
            except Exception:
                pass
        
        # 错误处理（打印可见错误文本，避免“静默卡住”）
        if response.is_error:
            if "API错误" in (response.content or ""):
                error_template = ToolPrompts.get_error_messages()["api_error"]
                error_msg = error_template.format(status="", error=response.content)
            else:
                error_template = ToolPrompts.get_error_messages()["connection_error"]
                error_msg = error_template.format(error=response.content)
            if error_msg:
                self.ui.print_assistant(error_msg + "\n")
            return {
                "content": error_msg,
                "tool_calls": [],
                "finish_reason": "error"
            }
        
        # 若整个流期间无任何输出但有最终文本，也要打印
        if (not has_content[0]) and response.content:
            self.ui.print_assistant(response.content + "\n")
        
        return {
            "role": "assistant",
            "content": response.content,
            "tool_calls": response.tool_calls,
            "finish_reason": response.finish_reason
        }
    
    async def _execute_tool(self, tool_call: Dict) -> Dict[str, Any]:
        """执行工具调用 - 使用 ToolRegistry 统一管理"""
        tool_name = tool_call.get("tool")
        args = tool_call.get("args", {})
        
        try:
            # 从 ToolRegistry 获取工具配置
            tool_config = ToolRegistry.get(tool_name)
            
            if tool_config is None:
                # 工具未注册
                error_msg = ToolPrompts.get_error_messages()["unknown_tool"].format(tool_name=tool_name)
                return {"success": False, "error": error_msg}
            
            # 调用工具的 handler（支持同步和异步）
            handler = tool_config.handler
            result = handler(**args)

            # 如果是协程（异步函数），需要 await
            if asyncio.iscoroutine(result):
                result = await result

            # 统一返回格式
            if isinstance(result, str):
                # 判断是成功还是失败 - 只检查错误前缀，避免误判文件内容
                error_prefixes = ["Error:", "Failed", "错误:", "失败:"]
                is_error = any(result.startswith(prefix) for prefix in error_prefixes)
                
                if is_error:
                    return {"success": False, "error": result}
                else:
                    # 默认视为成功（包括read_file返回的文件内容）
                    return {"success": True, "result": result}
            elif isinstance(result, dict):
                # 如果已经是字典格式
                if result.get("success"):
                    # 优先使用 result 字段，其次 stdout，最后序列化整个字典
                    output = result.get("result") or result.get("stdout")
                    if output:
                        return {"success": True, "result": output}
                    else:
                        # 将整个结果字典序列化为 JSON 字符串（Web 工具等）
                        import json
                        result_copy = {k: v for k, v in result.items() if k != "success"}
                        if result_copy:
                            return {"success": True, "result": json.dumps(result_copy, ensure_ascii=False, indent=2)}
                        else:
                            success_msg = ToolPrompts.get_error_messages()["command_success"]
                            return {"success": True, "result": success_msg}
                else:
                    default_error = ToolPrompts.get_error_messages()["unknown_error"]
                    error = result.get("error") or result.get("stderr", default_error)
                    return {"success": False, "error": error}
            else:
                return result
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """估算token数量"""
        total_chars = 0
        for msg in messages:
            total_chars += len(msg.get("content", ""))
        return int(total_chars * 0.25)  # 粗略估算
    
    def clear_history(self):
        """清空对话历史（保留system prompt）"""
        self.chunk_manager.clear()
        # 重新添加系统提示词
        self.chunk_manager.add_system_prompt(self.system_prompt)
        status_msg = UIPrompts.get_status_messages()["history_cleared"]
        self.ui.print_dim(status_msg)
    
    def _show_memory_status(self):
        """显示记忆系统状态"""
        stats = self.memory_manager.get_stats()

        # 规则
        rules = stats["rules"]
        self.ui.print_dim(f"[规则] (永远注入)")
        self.ui.print_dim(f"   用户规则: {rules['user_rules_count']} 条 ({self.memory_manager.user_rules_file})")
        self.ui.print_dim(f"   项目规范: {rules['project_conventions_count']} 条 ({self.memory_manager.project_conventions_file})")

        # 对话存储
        convs = stats["conversations"]
        self.ui.print_dim(f"[对话记录] (RAG 检索)")
        self.ui.print_dim(f"   总对话数: {convs['total_conversations']} 条")

        # 活跃记忆统计（从 recall_manager 获取）
        recall_stats = stats.get("recall", {})
        if recall_stats:
            self.ui.print_dim(f"   活跃记忆: {recall_stats.get('active_count', 0)} 条")

        self.ui.print_dim("提示: 使用 /memory edit 进入记忆管理模式")

    def _show_sessions(self):
        """显示会话列表"""
        sessions = self.session_manager.list_sessions(limit=20)

        if not sessions:
            self.ui.print_dim("没有历史会话")
            return

        # 表头
        print("\n" + "="*70)
        print(f"{'ID':<10} {'标题':<30} {'时间':<16} {'消息数':<6} {'Token':<8}")
        print("-"*70)

        for s in sessions:
            session_id = s.get('session_id', '')
            title = s.get('title', '')[:28]
            timestamp = s.get('timestamp', '')[:16]
            msg_count = s.get('message_count', 0)
            token_count = s.get('token_count', 0)

            # 标记当前会话
            prefix = "* " if session_id == self.current_session_id else "  "

            print(f"{prefix}{session_id:<8} {title:<30} {timestamp:<16} {msg_count:<6} {token_count:<8}")

        print("="*70)
        print(f"共 {len(sessions)} 个会话")
        print("使用 /load <id> 恢复会话，/delete-session <id> 删除会话")
    
    def _build_recent_context(self, max_chars: int = 16000) -> str:
        """构建近期对话上下文（用于记忆意图判断）
        
        只包含用户输入和 AI 回复，排除系统提示词、工具调用等。
        从最新的对话开始向前收集，直到达到字符限制。
        
        Args:
            max_chars: 最大字符数
            
        Returns:
            近期对话的纯文本
        """
        from chunk_system import ChunkType
        
        parts = []
        total_chars = 0
        
        # 从最新的 chunk 开始向前遍历
        for chunk in reversed(self.chunk_manager.chunks):
            # 只包含用户输入和 AI 回复
            if chunk.chunk_type == ChunkType.USER:
                text = f"用户: {chunk.content}"
            elif chunk.chunk_type == ChunkType.ASSISTANT:
                if chunk.content:  # 排除空内容（如纯工具调用）
                    text = f"AI: {chunk.content}"
                else:
                    continue
            else:
                continue
            
            # 检查是否超出限制
            if total_chars + len(text) > max_chars:
                break
            
            parts.append(text)
            total_chars += len(text)
        
        # 反转回时间顺序（旧 -> 新）
        parts.reverse()
        return "\n".join(parts)

    def _save_conversation(self, user_message: str, assistant_message: str):
        """保存一轮对话到记忆系统"""
        if not user_message or not assistant_message:
            return
        # 过滤掉系统消息
        if user_message.startswith("[系统"):
            return
        # 记忆系统未初始化则跳过
        if self.memory_manager is None:
            return
        try:
            # 新记忆后端可能需要异步保存（llama.cpp embeddings + SQLite）
            # 这里保持接口不阻塞主流程：失败则降级跳过
            if hasattr(self.memory_manager, "save_conversation_async"):
                asyncio.create_task(self.memory_manager.save_conversation_async(
                    user_message=user_message,
                    assistant_message=assistant_message
                ))
            else:
                self.memory_manager.save_conversation(
                    user_message=user_message,
                    assistant_message=assistant_message
                )
        except Exception as e:
            self.ui.print_dim(f"[Memory] 保存对话失败: {e}")

    def _save_session(self):
        """保存当前会话快照"""
        try:
            # 获取 Shell 状态
            terminal_status = self.tools.get_terminal_status()

            snapshot = self.session_manager.save_session(
                chunk_manager=self.chunk_manager,
                workspace_dir=str(self.workspace_dir),
                model=self.model or "unknown",
                shell_open=terminal_status.get('is_open', False),
                shell_pid=terminal_status.get('pid'),
                session_id=self.current_session_id
            )

            # 更新当前会话ID
            if self.current_session_id is None:
                self.current_session_id = snapshot.session_id

            # 同步会话列表到 Web UI
            self._sync_session_list()

        except Exception as e:
            self.ui.print_dim(f"[Session] 保存会话失败: {e}")

    def _load_session(self, session_id: str, sync_ui: bool = True) -> bool:
        """加载会话

        Args:
            session_id: 会话ID
            sync_ui: 是否同步到 Web UI

        Returns:
            是否加载成功
        """
        snapshot = self.session_manager.load_session(session_id)
        if snapshot is None:
            self.ui.print_error(f"会话 {session_id} 不存在")
            return False

        try:
            # 恢复 ChunkManager
            from chunk_system import ChunkManager
            self.chunk_manager = ChunkManager.from_json(
                snapshot.chunks,
                max_tokens=64000,
                tools_schema=TOOLS_SCHEMA
            )
            
            # 恢复工作目录（每个会话有独立的工作区）
            if snapshot.workspace_dir:
                self.workspace_dir = Path(snapshot.workspace_dir)
                self.workspace_name = self.workspace_dir.name
                self.tools.sandbox_dir = self.workspace_dir
                # 更新终端的工作目录
                if hasattr(self.tools.async_shell, 'working_directory'):
                    self.tools.async_shell.working_directory = self.workspace_dir
            
            # 恢复模型（如果会话保存了模型信息）
            if snapshot.model and snapshot.model != 'unknown':
                self.model = snapshot.model
                self.llm.config.model = snapshot.model

            # 如果存在 shell_chunk，添加终端已关闭的提示
            # 防止多次恢复会话时重复添加提示
            if self.chunk_manager.has_shell_chunk():
                for chunk in reversed(self.chunk_manager.chunks):
                    if chunk.chunk_type == ChunkType.SHELL:
                        lines = chunk.content.splitlines()
                        shell_closed_hint = "[Terminal closed. Reopen available]"
                        if lines and not lines[-1].startswith("[Terminal closed. Reopen available]"):
                            chunk.content = chunk.content.rstrip() + "\n" + shell_closed_hint + "\n"
                            # 更新 token 计数
                            old_tokens = chunk.tokens
                            chunk.tokens = 0
                            chunk.estimate_tokens()
                            self.chunk_manager.current_tokens += chunk.tokens - old_tokens
                        break

            # 更新当前会话ID
            self.current_session_id = snapshot.session_id

            # 如果 Shell 是打开的，尝试恢复
            # 注意：Shell 状态恢复需要终端支持会话恢复，这里只记录状态
            if snapshot.shell_open:
                self.ui.print_dim(f"[Session] 上次对话时终端是打开的 (PID: {snapshot.shell_pid})")

            # 同步到 Web UI
            if sync_ui and hasattr(self.ui, 'send_session_load'):
                # 发送完整 chunks 给前端渲染（使用更新后的 chunks）
                self.ui.send_session_load(self.chunk_manager.to_json())
                self.ui.send_session_loaded(snapshot.session_id, snapshot.title)

            self.ui.print_success(f"已恢复会话: {snapshot.title}")
            
            # 更新状态栏
            self._update_status_bar()
            
            return True

        except Exception as e:
            self.ui.print_error(f"恢复会话失败: {e}")
            return False

    def _sync_session_list(self):
        """同步会话列表到 Web UI"""
        if not hasattr(self.ui, 'send_session_list'):
            return

        sessions = self.session_manager.list_sessions(limit=50)
        self.ui.send_session_list(sessions, self.current_session_id)
    
    async def _ensure_active_session(self):
        """确保启动时有一个活动会话
        
        逻辑：
        1. 如果已有会话，加载最近的会话
        2. 如果没有会话，创建一个新的空会话
        """
        sessions = self.session_manager.list_sessions(limit=50)
        
        if sessions:
            # 有历史会话，加载最近的一个
            latest_session = sessions[0]
            if self._load_session(latest_session['session_id'], sync_ui=True):
                self.system_prompt = self._create_system_prompt()
        else:
            # 没有历史会话，创建新会话
            from chunk_system import ChunkManager
            self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)
            
            new_session = self.session_manager.save_session(
                chunk_manager=self.chunk_manager,
                workspace_dir=str(self.workspace_dir),
                model=self.model,
                shell_open=False,
                shell_pid=None,
                session_id=None
            )
            self.current_session_id = new_session.session_id
            
            # 通知前端
            if hasattr(self.ui, 'send_message'):
                sessions = self.session_manager.list_sessions(limit=50)
                await self.ui.send_message("session_list", {
                    "sessions": sessions,
                    "current_id": self.current_session_id
                })
                await self.ui.send_message('new_chat', {
                    'session_id': new_session.session_id
                })
    
    async def process_input(self, user_input: str) -> str:
        """处理用户输入 - 完全符合OpenAI Function Calling标准"""
        # 重置停止事件
        self._stop_event = asyncio.Event()

        # 0. 添加用户输入
        self.chunk_manager.add_user_input(user_input)
        
        # 1. 生命值递减：衰减已有记忆
        try:
            forgotten = self.memory_manager.tick_recall() if self.memory_manager else []
            if forgotten:
                self.ui.print_dim(f"[Memory] 遗忘了 {len(forgotten)} 条记忆")
        except Exception as e:
            self.ui.print_dim(f"[Memory] 记忆衰减失败(已跳过): {e}")
        
        # 2. RAG 检索 + 唤醒记忆（生命值递减法）
        # 新机制：高相关记忆持续被唤醒 -> 生命值高 -> 长期保留
        #        临时记忆只被唤醒一次 -> 几轮后自然遗忘
        if self.memory_manager and (not user_input.startswith("[系统")):
            try:
                # 构建近期上下文用于意图判断（最多 16K 字符）
                recent_context = self._build_recent_context(max_chars=16000)
                
                if hasattr(self.memory_manager, "recall_async"):
                    new_recalled = await self.memory_manager.recall_async(
                        user_input, n_results=3, min_score=0.4, context=recent_context
                    )
                else:
                    new_recalled = self.memory_manager.recall(
                        user_input, n_results=3, min_score=0.4, context=recent_context
                    )
                if new_recalled:
                    self.ui.print_dim(f"[Memory] 新唤醒 {new_recalled} 条记忆")
            except Exception as e:
                # embeddings 服务不可用/超时等，直接降级，不影响对话
                self.ui.print_dim(f"[Memory] 记忆检索失败(已降级跳过): {e}")
        
        # 3. 获取当前活跃记忆的提示词
        recalled_prefix = ""
        if self.memory_manager:
            try:
                recalled_prefix = self.memory_manager.get_recalled_prompt()
                if recalled_prefix:
                    stats = self.memory_manager.recall_manager.get_stats()
                    self.ui.print_dim(f"[Memory] 活跃记忆: {stats['active_count']} 条, {stats['capacity_ratio']}")
            except Exception as e:
                self.ui.print_dim(f"[Memory] 获取活跃记忆失败(已跳过): {e}")
        
        # 2. 主循环（无步数限制）
        step_count = 0
        final_response = ""
        no_action_count = 0  # 连续无工具调用计数
        
        while True:
            step_count += 1

            # 从chunk_manager获取上下文消息
            messages = self.chunk_manager.get_context_for_llm()
            
            # 如果有活跃记忆，作为独立的 assistant 消息块添加（仅第一步）
            # 注意：这是临时添加到 messages 中，不保存到历史记录
            # 这样 LLM 不会学习模仿 <recall> 格式
            use_recall = recalled_prefix and step_count == 1
            if use_recall:
                messages.append({
                    "role": "assistant",
                    "content": recalled_prefix
                })
            
            # 调用支持Function Calling的API
            assistant_message = await self._call_llm_with_tools(messages)

            # 检查是否被停止
            if assistant_message.get("finish_reason") == "stopped":
                # 用户停止了生成，退出循环
                self.stop_requested = False  # 重置标志
                break

            # 提取内容和工具调用
            content = assistant_message.get("content")
            tool_calls = assistant_message.get("tool_calls")
            
            # 检测 stay_silent 调用：如果存在，丢弃所有其他内容和工具调用
            stay_silent_call = None
            if tool_calls:
                for tc in tool_calls:
                    if tc.get("function", {}).get("name") == "stay_silent":
                        stay_silent_call = tc
                        break
            
            if stay_silent_call:
                # stay_silent 模式：丢弃 content 和其他工具调用，只保留这个
                content = None
                tool_calls = [stay_silent_call]
            
            # 添加assistant消息到chunk_manager（不包含recall，保持历史干净）
            self.chunk_manager.add_assistant_response(content, tool_calls=tool_calls)
            if content:
                final_response = content
            
            # 注意：响应已在_call_llm_with_tools中流式显示

            # 执行工具调用
            if tool_calls:
                for i, tool_call in enumerate(tool_calls):
                    # 检查是否被停止
                    if self._stop_event and self._stop_event.is_set():
                        self.ui.print_dim("\n[已停止]")
                        # 标记为停止状态，退出主循环
                        return

                    # 提取工具信息
                    tool_call_id = tool_call.get("id")
                    function_name = tool_call["function"]["name"]
                    raw_args = tool_call["function"]["arguments"]

                    # 安全解析工具参数（处理 API 返回的无效 JSON）
                    try:
                        function_args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError as e:
                        self.ui.print_error(f"工具参数解析失败: {e}")
                        self.ui.print_dim(f"原始参数: {raw_args[:200]}..." if len(raw_args) > 200 else f"原始参数: {raw_args}")
                        # 尝试修复常见的 JSON 问题
                        function_args = self._try_fix_json(raw_args)
                        if function_args is not None:
                            self.ui.print_dim("已自动修复 JSON 格式")
                        else:
                            # 无法修复，跳过此工具调用
                            self.ui.print_error(f"跳过工具调用: {function_name}")
                            continue
                    
                    # 显示工具调用（简洁格式，紧凑排列）
                    args_str = json.dumps(function_args, ensure_ascii=False) if function_args else ""
                    self.ui.show_tool_start(tool_call_id, function_name, args_str)

                    # 执行工具
                    result = await self._execute_tool({
                        "tool": function_name,
                        "args": function_args
                    })

                    # 获取工具执行结果
                    success = result.get("success", False)

                    # 确保result_text总是被定义
                    if success:
                        result_text = str(result.get("result", ""))
                        # 获取显示信息
                        display = self._get_tool_display(function_name, result_text, function_args)
                        self.ui.show_tool_result(tool_call_id, function_name, display, success=True)
                    else:
                        error_msg = result.get('error', '未知错误')
                        result_text = f"错误: {error_msg}"
                        self.ui.show_tool_result(tool_call_id, function_name, {'line1': error_msg, 'line2': '', 'has_line2': False}, success=False)

                    # 获取工具配置，检查上下文策略
                    tool_config = ToolRegistry.get(function_name)

                    # 获取 max_call_pairs 配置（用于配对清理）
                    max_call_pairs = tool_config.max_call_pairs if tool_config else 0

                    # 添加工具结果到chunk_manager（OpenAI标准）
                    # 如果设置了 max_call_pairs，会自动清理超出的旧配对
                    self.chunk_manager.add_tool_result(
                        result_text,
                        tool_call_id=tool_call_id,
                        tool_name=function_name,
                        max_call_pairs=max_call_pairs
                    )
                    
                    # 如果是 Shell 相关工具，移动 Shell chunk 到末尾
                    # 确保 Shell Output 出现在 Tool Result 之后（作为下一轮对话的开始）
                    # 避免插在 Assistant 和 Tool Result 之间破坏 API 规范
                    if tool_config and tool_config.category == "shell":
                        self._refresh_shell_chunk(move_to_end=True)
                    
                    # stay_silent 调用后立即退出，不继续循环
                    if function_name == "stay_silent":
                        # 自动保存会话但不保存到记忆（沉默回复无需记忆）
                        self._save_session()
                        return None

            # 检查是否完成
            if not tool_calls:
                # 没有工具调用，立即停止
                # 如果 LLM 完全没响应（无内容、无工具调用），提示用户
                if not content and step_count == 1:
                    self.ui.print_dim("[LLM 无响应，可能是模型问题或上下文过长]")
                break
            else:
                # 有工具调用，重置计数
                no_action_count = 0
        
        # 保存对话到记忆系统
        if final_response and not user_input.startswith("[系统"):
            self._save_conversation(user_input, final_response)

        # 自动保存会话
        self._save_session()

        # 更新状态栏（显示当前 token 用量）
        self._update_status_bar()

        return final_response
    
    async def _terminal_output_loop(self):
        """定期推送终端输出到前端工作区
        
        显示逻辑：只要有 shell_chunk 就显示内容，否则显示“未打开”
        """
        last_output = ""
        while True:
            try:
                await asyncio.sleep(0.5)  # 每 0.5 秒检查一次
                
                # 检查是否有 send_terminal_output 方法
                if not hasattr(self.ui, 'send_terminal_output'):
                    continue
                
                # 检查是否有 shell_chunk
                has_shell = self.chunk_manager.has_shell_chunk()
                
                if has_shell:
                    # 有 shell_chunk，获取其内容
                    output = self._get_shell_chunk_content()
                    # 只有内容变化时才发送
                    if output != last_output:
                        last_output = output
                        self.ui.send_terminal_output(output or "", is_open=True)
                else:
                    # 没有 shell_chunk
                    if last_output != "__no_shell__":
                        last_output = "__no_shell__"
                        self.ui.send_terminal_output("Paw 未打开终端", is_open=False)
                        
            except Exception:
                # 静默失败，不影响主流程
                pass
    
    def _get_shell_chunk_content(self) -> str:
        """获取 shell_chunk 的内容"""
        for chunk in self.chunk_manager.chunks:
            if chunk.chunk_type == ChunkType.SHELL:
                return chunk.content
        return ""
    
    async def _fetch_available_models(self) -> List[str]:
        """获取API可用的模型列表"""
        try:
            # 准备请求头
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # 提取base URL（去掉/chat/completions）
            base_url = self.api_url.replace("/chat/completions", "")
            # 智谱AI的模型列表端点
            if "bigmodel.cn" in base_url:
                models_url = f"{base_url.replace('/v4', '')}/v4/models"
            else:
                models_url = f"{base_url.replace('/v1', '')}/v1/models"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    models_url, 
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 智谱AI返回格式: {"data": [{"id": "model_name"}, ...]}
                        models = [m["id"] for m in data.get("data", [])]
                        return models
                    else:
                        error_text = await response.text()
                        self.ui.print_dim(f"模型检测失败 ({response.status}): {error_text[:100]}")
                        return []
        except Exception as e:
            self.ui.print_dim(f"无法获取模型列表: {e}")
            return []
    
    async def _enter_edit_mode(self):
        """进入对话编辑模式"""
        # 获取可编辑的语块
        editable_chunks = self.chunk_manager.get_editable_chunks()
        
        if not editable_chunks:
            self.ui.print_dim("没有可编辑的对话内容")
            return
        
        # 显示编辑器界面
        current_index = len(editable_chunks) - 1  # 默认选中最后一条
        
        while True:
            # 重新获取可编辑语块（因为可能被删除了）
            editable_chunks = self.chunk_manager.get_editable_chunks()
            if not editable_chunks:
                self.ui.print_dim("所有对话内容已清空")
                break
            
            # 确保索引有效
            if current_index >= len(editable_chunks):
                current_index = len(editable_chunks) - 1
            if current_index < 0:
                current_index = 0
            
            # 显示编辑器并获取用户操作
            action, real_idx, new_content = self.ui.show_chunk_editor(editable_chunks, current_index)
            
            if action == 'quit':
                break
            
            elif action == 'edit':
                # 编辑语块内容
                success = self.chunk_manager.edit_chunk_content(real_idx, new_content)
                self.ui.show_edit_result('edit', success)
            
            elif action == 'delete':
                # 删除单个语块
                success = self.chunk_manager.delete_chunk(real_idx)
                self.ui.show_edit_result('delete', success)
                # 删除后调整索引
                if success and current_index > 0:
                    current_index -= 1
            
            elif action == 'delete_from':
                # 回滚：删除此条及之后的所有
                deleted_count = self.chunk_manager.delete_chunks_from(real_idx)
                self.ui.show_edit_result('delete_from', deleted_count > 0, f"(删除了 {deleted_count} 条)")
                # 删除后调整索引
                if deleted_count > 0:
                    current_index = max(0, len(self.chunk_manager.get_editable_chunks()) - 1)
        
        # 退出编辑模式，备用屏幕已自动恢复主屏幕
        # 重新渲染对话历史，同步编辑后的内容到主屏幕
        self.ui.refresh_conversation_history(
            self.chunk_manager.chunks,
            self.model
        )
    
    async def _enter_memory_edit_mode(self, search_keyword: str = None):
        """进入记忆管理模式
        
        Args:
            search_keyword: 搜索关键词（可选，用于过滤显示）
        """
        current_index = 0
        
        while True:
            # 获取记忆列表
            if search_keyword:
                # 使用 RAG 搜索
                conversations = self.memory_manager.conversation_store.search(
                    query=search_keyword,
                    n_results=50,
                    min_score=0.2
                )
            else:
                # 列出所有记忆
                conversations = self.memory_manager.conversation_store.list_all(limit=100)
            
            if not conversations and not search_keyword:
                self.ui.print_dim("没有记忆记录")
                return
            
            # 确保索引有效
            if current_index >= len(conversations):
                current_index = max(0, len(conversations) - 1)
            
            # 显示记忆管理界面
            action, doc_id, extra_data = self.ui.show_memory_editor(conversations, current_index)
            
            if action == 'quit':
                break
            
            elif action == 'delete':
                # 删除单条记忆
                success = self.memory_manager.conversation_store.delete(doc_id)
                self.ui.show_memory_result('delete', success)
                if success and current_index > 0:
                    current_index -= 1
            
            elif action == 'delete_batch':
                # 批量删除
                doc_ids = extra_data
                deleted = self.memory_manager.conversation_store.delete_batch(doc_ids)
                self.ui.show_memory_result('delete_batch', deleted > 0, f"(删除了 {deleted} 条)")
                current_index = 0
            
            elif action == 'clean_duplicates':
                # 清理重复记忆
                duplicates = self.memory_manager.conversation_store.find_duplicates(threshold=0.9)
                if not duplicates:
                    self.ui.print_dim("没有发现重复记忆")
                    continue
                
                # 每组保留第一条，删除其余
                to_delete = []
                for group in duplicates:
                    to_delete.extend(group[1:])  # 保留第一条
                
                if to_delete:
                    deleted = self.memory_manager.conversation_store.delete_batch(to_delete)
                    self.ui.show_memory_result('clean_duplicates', deleted > 0, f"(清理了 {deleted} 条重复记忆)")
                current_index = 0
            
            elif action == 'search':
                # 搜索记忆
                search_keyword = extra_data
                current_index = 0
                # 继续循环，使用新的搜索关键词
        
        # 退出记忆管理模式
        if search_keyword:
            self.ui.print_dim(f"已退出搜索模式")
    
    async def _enter_context_branch_mode(self, instruction: str = None):
        """进入上下文编辑分支模式
        
        Args:
            instruction: 自定义编辑指令（可选）
        """
        if self.context_manager is None:
            self.ui.print_error("上下文管理器未初始化")
            return
        
        self.ui.print_dim("\n" + "="*50)
        self.ui.print_dim("进入上下文编辑分支...")
        self.ui.print_dim("="*50)
        
        # 显示当前状态
        current_tokens = self.chunk_manager.current_tokens
        max_tokens = self.chunk_manager.max_tokens
        usage_ratio = current_tokens / max_tokens * 100
        
        self.ui.print_dim(f"当前Token使用: {current_tokens}/{max_tokens} ({usage_ratio:.1f}%)")
        self.ui.print_dim(f"当前Chunk数量: {len(self.chunk_manager.chunks)}")
        
        # 执行优化
        try:
            result = await self.context_manager.manual_optimize(instruction)
            
            if result.get("triggered"):
                self.ui.print_dim("\n[优化结果]")
                self.ui.print_dim(f"  触发原因: {result.get('trigger_reason', 'manual')}")
                self.ui.print_dim(f"  迭代次数: {result.get('iterations', 0)}")
                self.ui.print_dim(f"  操作数量: {result.get('operations', 0)}")
                self.ui.print_dim(f"  已提交: {result.get('committed', False)}")
                self.ui.print_dim(f"  节省Token: {result.get('tokens_saved', 0)}")
                
                # 显示优化后状态
                new_tokens = self.chunk_manager.current_tokens
                new_ratio = new_tokens / max_tokens * 100
                self.ui.print_dim(f"\n优化后Token使用: {new_tokens}/{max_tokens} ({new_ratio:.1f}%)")
            else:
                self.ui.print_dim(f"\n未执行优化: {result.get('reason', result.get('error', '未知'))}")
                
        except Exception as e:
            self.ui.print_error(f"上下文优化失败: {e}")
        
        self.ui.print_dim("="*50 + "\n")
    
    def _show_context_stats(self):
        """显示上下文管理统计信息"""
        if self.context_manager is None:
            self.ui.print_error("上下文管理器未初始化")
            return
        
        stats = self.context_manager.get_stats()
        
        print("\n" + "="*50)
        print("上下文管理统计")
        print("="*50)
        print(f"自动触发次数: {stats['auto_triggers']}")
        print(f"手动触发次数: {stats['manual_triggers']}")
        print(f"累计节省Token: {stats['total_tokens_saved']}")
        
        if stats['branch_history']:
            print(f"\n最近分支历史 (最多5条):")
            for i, record in enumerate(stats['branch_history'][-5:], 1):
                print(f"  {i}. {record['timestamp'][:19]} - {record['trigger']} - {record['operations']}次操作")
        
        # 当前状态
        current_tokens = self.chunk_manager.current_tokens
        max_tokens = self.chunk_manager.max_tokens
        print(f"\n当前Token使用: {current_tokens}/{max_tokens} ({current_tokens/max_tokens*100:.1f}%)")
        print(f"当前Chunk数量: {len(self.chunk_manager.chunks)}")
        print("="*50 + "\n")
    
    async def _select_model(self, use_alternate_screen: bool = False) -> str:
        """选择模型

        Args:
            use_alternate_screen: 忽略（保留参数兼容性）
        """
        # Web UI 模式：循环直到拿到有效模型名
        while True:
            models = await self._fetch_available_models()
            if not models:
                self.ui.show_model_input_prompt()
            else:
                self.ui.show_model_list(models)
            # 等待前端通过WebSocket返回模型名称（显式模型选择通道）
            chosen_model = await self.ui.get_model_choice_async("请选择模型或输入模型名")
            chosen_model = (chosen_model or '').strip()

            # 检查是否是命令输入（以 / 开头）
            if chosen_model.startswith('/'):
                self.ui.print_error(f"请先选择模型后再使用命令。输入的 '{chosen_model}' 被识别为命令而非模型名。")
                continue

            if chosen_model:
                # 若提供了列表且选择不在其中，给出提示并继续循环
                if models and chosen_model not in models:
                    self.ui.print_error(f"模型不存在: {chosen_model}")
                    continue
                return chosen_model
    
    async def run(self):
        """主运行循环"""
        # 模型选择（仅当未配置时）
        if not self.model:
            self.model = await self._select_model()
        if hasattr(self.ui, 'show_model_selected'):
            self.ui.show_model_selected(self.model)

        # 初始化上下文分支管理器
        if self.context_manager is None:
            self.context_manager = AutoContextManager(
                chunk_manager=self.chunk_manager,
                system_prompt_getter=lambda: self.system_prompt,
                api_url=self.api_url,
                model=self.model,
                api_key=self.api_key,
                ui_callback=self.ui.print_dim,
                token_threshold=0.7,  # 70% token使用率触发
                turn_threshold=20     # 20轮对话触发
            )
        
        # 启动横幅
        self.ui.print_welcome()

        # 记忆系统异步初始化：不阻塞首屏加载
        # 在后台线程中初始化，用户可以立即开始对话
        if self.memory_manager is None:
            asyncio.create_task(self._init_memory_system_async())
        
        # 启动终端输出定时推送任务（工作区显示）
        asyncio.create_task(self._terminal_output_loop())
        
        # 标记对话区域起始位置（用于编辑后重渲染）
        self.ui.mark_conversation_start()

        # 同步会话列表到 Web UI，并确保有活动会话
        await self._ensure_active_session()

        # 显示状态栏（在会话加载后，此时 token 数已正确计算）
        self._update_status_bar()

        # 主循环
        while True:
            # 标记是否需要发送 turn_end（只有处理普通消息时才需要）
            should_send_turn_end = False
            try:
                # 获取用户输入
                user_input = await self.ui.get_user_input()
                
                # 尝试解析为 JSON 消息（用于处理前端配置化命令）
                try:
                    msg_data = json.loads(user_input)
                    if isinstance(msg_data, dict) and msg_data.get('type') == 'create_new_chat':
                        # 处理新建对话配置
                        workspace_dir = msg_data.get('workspace_dir', str(Path.home()))
                        title = msg_data.get('title', '').strip()
                        model = msg_data.get('model', '').strip()
                        
                        # 解析工作目录（支持 ~ 符号）
                        if workspace_dir == '~':
                            workspace_dir = str(Path.home())
                        else:
                            workspace_dir = str(Path(workspace_dir).expanduser().resolve())
                        
                        # 如果指定了模型且不为空，切换模型
                        if model:
                            self.model = model
                            self.llm.config.model = model
                        
                        # 更新工作目录
                        self.workspace_dir = Path(workspace_dir)
                        self.workspace_name = self.workspace_dir.name
                        self.tools.sandbox_dir = self.workspace_dir
                        # 更新终端的工作目录
                        if hasattr(self.tools.async_shell, 'working_directory'):
                            self.tools.async_shell.working_directory = self.workspace_dir
                        
                        # 创建新的 ChunkManager
                        from chunk_system import ChunkManager
                        self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)
                        
                        # 重新生成系统提示词（包含新的工作目录信息）
                        self.system_prompt = self._create_system_prompt()
                        
                        # 保存新会话
                        new_session = self.session_manager.save_session(
                            chunk_manager=self.chunk_manager,
                            workspace_dir=workspace_dir,
                            model=self.model,
                            shell_open=False,
                            shell_pid=None,
                            session_id=None
                        )
                        self.current_session_id = new_session.session_id
                        
                        # 如果用户指定了标题，更新会话标题
                        if title:
                            # 直接修改会话文件中的标题
                            session_file = self.session_manager.storage_path / f"{new_session.session_id}.json"
                            if session_file.exists():
                                try:
                                    with open(session_file, 'r', encoding='utf-8') as f:
                                        session_data = json.load(f)
                                    session_data['title'] = title
                                    with open(session_file, 'w', encoding='utf-8') as f:
                                        json.dump(session_data, f, ensure_ascii=False, indent=2)
                                    # 更新索引
                                    if new_session.session_id in self.session_manager._index:
                                        self.session_manager._index[new_session.session_id]['title'] = title
                                        self.session_manager._save_index()
                                except Exception as e:
                                    self.ui.print_dim(f"[Session] 更新标题失败: {e}")
                        
                        # 同步到 Web UI
                        if hasattr(self.ui, 'send_message'):
                            sessions = self.session_manager.list_sessions(limit=50)
                            await self.ui.send_message("session_list", {
                                "sessions": sessions,
                                "current_id": self.current_session_id
                            })
                            await self.ui.send_message('new_chat', {
                                'session_id': new_session.session_id
                            })
                        
                        # 更新状态栏
                        self._update_status_bar()
                        
                        self.ui.print_success(f'新对话已创建 (工作区: {self.workspace_name})')
                        continue
                except (json.JSONDecodeError, ValueError):
                    # 不是 JSON，继续作为普通消息处理
                    pass
                
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    self.ui.print_goodbye()
                    break
                
                # 空输入处理
                if not user_input:
                    # 检查是否有对话历史（通过chunk数量判断）
                    user_chunks = [c for c in self.chunk_manager.chunks if c.chunk_type == ChunkType.USER]
                    if len(user_chunks) == 0:  # 没有用户输入，是第一次空输入
                        # 发送系统唤醒消息，让AI开始自主生活
                        system_wake_msg = "[系统提示]: Paw闹铃启动... 请赶紧醒过来开始今天的生活。[系统提示]hujiyo状态：[离线]"
                        self.ui.print_system(system_wake_msg)
                        user_input = system_wake_msg
                    else:
                        # 有对话历史，添加继续标记
                        user_input = "[系统提示:继续]"
                
                # 特殊命令（不触发 turn_end）
                if user_input == '/clear':
                    self.clear_history()
                    continue
                
                if user_input == '/chunks':
                    self.chunk_manager.print_context(show_llm_view=True)
                    continue
                
                if user_input == '/model':
                    # 重新选择模型（使用备用屏幕，退出后恢复对话历史）
                    new_model = await self._select_model(use_alternate_screen=True)
                    self.model = new_model
                    self.ui.show_model_selected(self.model)
                    continue
                
                if user_input == '/messages':
                    # 显示完整的消息历史（调试用）
                    messages = self.chunk_manager.get_context_for_llm()
                    self.ui.show_messages_debug(messages)
                    continue
                
                if user_input == '/edit':
                    # 进入对话编辑模式
                    await self._enter_edit_mode()
                    continue
                
                if user_input == '/memory edit':
                    # 进入记忆管理模式
                    await self._enter_memory_edit_mode()
                    continue
                
                if user_input == '/memory':
                    # 显示记忆系统状态
                    self._show_memory_status()
                    continue
                
                if user_input == '/save':
                    # /save 命令已废弃，对话会自动保存
                    self.ui.print_dim("[提示] 对话已自动保存，无需手动操作")
                    continue

                if user_input == '/sessions':
                    # 显示会话列表（终端）
                    self._show_sessions()
                    # 同步到 Web UI
                    self._sync_session_list()
                    continue

                if user_input.startswith('/load '):
                    # 加载会话
                    session_id = user_input.split(' ', 1)[1].strip()
                    if session_id:
                        if self._load_session(session_id, sync_ui=True):
                            # 加载成功后刷新系统提示词
                            self.system_prompt = self._create_system_prompt()
                            # 同步会话列表
                            self._sync_session_list()
                    continue

                if user_input.startswith('/delete-session '):
                    # 删除会话
                    session_id = user_input.split(' ', 1)[1].strip()
                    if session_id:
                        if self.session_manager.delete_session(session_id):
                            self.ui.print_success(f"已删除会话: {session_id}")
                            # 同步会话列表
                            self._sync_session_list()
                        else:
                            self.ui.print_error(f"删除会话失败: {session_id}")
                    continue

                if user_input == '/new':
                    # 新对话：立即创建空会话记录并显示在侧边栏
                    from chunk_system import ChunkManager, ChunkType

                    # 检查当前是否已经是空会话（且会话仍存在）
                    can_reuse_current = False
                    if self.current_session_id:
                        # 检查会话是否还存在
                        session_exists = self.session_manager.load_session(self.current_session_id) is not None
                        if session_exists:
                            # 检查是否有用户消息
                            user_msg_count = sum(1 for c in self.chunk_manager.chunks
                                                if c.chunk_type in (ChunkType.USER, ChunkType.ASSISTANT))
                            can_reuse_current = (user_msg_count == 0)

                    if can_reuse_current:
                        # 已经在空会话中，直接清空聊天区并同步列表
                        if hasattr(self.ui, 'send_message'):
                            await self.ui.send_message('new_chat', {
                                'session_id': self.current_session_id
                            })
                            # 同步会话列表确保前端状态一致
                            sessions = self.session_manager.list_sessions(limit=50)
                            await self.ui.send_message("session_list", {
                                "sessions": sessions,
                                "current_id": self.current_session_id
                            })
                    else:
                        # 检查是否存在其他空会话
                        existing_sessions = self.session_manager.list_sessions(limit=50)
                        existing_empty = None
                        for s in existing_sessions:
                            if s.get('message_count', 0) == 0:
                                existing_empty = s
                                break
                        
                        if existing_empty:
                            # 切换到已存在的空会话
                            if self._load_session(existing_empty['session_id'], sync_ui=True):
                                self.system_prompt = self._create_system_prompt()
                                if hasattr(self.ui, 'send_message'):
                                    await self.ui.send_message('new_chat', {
                                        'session_id': existing_empty['session_id']
                                    })
                                    sessions = self.session_manager.list_sessions(limit=50)
                                    await self.ui.send_message("session_list", {
                                        "sessions": sessions,
                                        "current_id": self.current_session_id
                                    })
                        else:
                            # 创建新的空会话
                            self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)

                            new_session = self.session_manager.save_session(
                                chunk_manager=self.chunk_manager,
                                workspace_dir=str(self.workspace_dir),
                                model=self.model,
                                shell_open=False,
                                shell_pid=None,
                                session_id=None
                            )
                            self.current_session_id = new_session.session_id

                            # 同步到 Web UI
                            if hasattr(self.ui, 'send_message'):
                                sessions = self.session_manager.list_sessions(limit=50)
                                await self.ui.send_message("session_list", {
                                    "sessions": sessions,
                                    "current_id": self.current_session_id
                                })
                                await self.ui.send_message('new_chat', {
                                    'session_id': new_session.session_id
                                })

                    self.ui.print_success('新对话已开始')
                    continue
                
                if user_input == '/context' or user_input == '/ctx':
                    # 手动触发上下文优化
                    await self._enter_context_branch_mode()
                    continue
                
                if user_input == '/context stats':
                    # 显示上下文管理统计
                    self._show_context_stats()
                    continue
                
                if user_input == '/pass':
                    # 用户跳过本轮输入，不发送任何内容给 LLM
                    self.ui.print_dim("[跳过本轮输入]")
                    continue

                if user_input == '/stop':
                    # /stop 命令现在由 WebUI 直接处理，不会进入这里
                    # 保留此分支以兼容终端模式
                    if self._stop_event:
                        self._stop_event.set()
                    continue
                
                if user_input.startswith('/'):
                    help_msg = UIPrompts.get_command_help()
                    self.ui.show_command_help(help_msg)
                    continue

                # 处理正常输入（需要发送 turn_end）
                should_send_turn_end = True
                await self.process_input(user_input)
            except KeyboardInterrupt:
                interrupted_msg = UIPrompts.get_startup_messages()["interrupted"]
                self.ui.print_dim(interrupted_msg)
                break
            except Exception as e:
                self.ui.print_error(f"Error: {e}")
                # 异常时也需要发送 turn_end（如果之前标记了）
            finally:
                # 只有处理普通消息时才发送 turn_end
                if should_send_turn_end and hasattr(self.ui, 'turn_end'):
                    self.ui.turn_end()

    async def _create_chat_with_config(self, workspace_dir: str = None, title: str = None, model: str = None):
        """创建带配置的新对话"""
        from chunk_system import ChunkManager
        
        # 1. 更新环境配置
        if workspace_dir:
            try:
                new_workspace = Path(workspace_dir).resolve()
                if not new_workspace.exists():
                    self.ui.print_error(f"工作区不存在，已创建: {new_workspace}")
                    new_workspace.mkdir(parents=True, exist_ok=True)
                
                self.workspace_dir = new_workspace
                self.workspace_name = self.workspace_dir.name
                
                # 更新工具集的工作目录
                # 注意：重新初始化 BaseTools 会重置终端状态，这在新对话中是预期的
                config = self._load_config()
                self.tools = BaseTools(sandbox_dir=str(self.workspace_dir), config=config)
                register_all_tools(self.tools)
            except Exception as e:
                self.ui.print_error(f"切换工作区失败: {e}")
                return

        if model:
            self.model = model
            # 更新 LLM 客户端配置
            self.llm = LLMClient(LLMConfig(
                api_url=self.api_url,
                model=self.model,
                api_key=self.api_key
            ))

        # 2. 创建新会话
        self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)
        
        # 3. 初始化 System Prompt (注入新的工作目录等)
        self.system_prompt = self._create_system_prompt()
        
        # 4. 保存会话
        new_session = self.session_manager.save_session(
            chunk_manager=self.chunk_manager,
            workspace_dir=str(self.workspace_dir),
            model=self.model,
            shell_open=False,
            shell_pid=None,
            session_id=None,
            title=title # 传入手动设置的标题
        )
        self.current_session_id = new_session.session_id
        
        # 5. 同步 UI
        if hasattr(self.ui, 'send_message'):
            self._sync_session_list()
            await self.ui.send_message('new_chat', {
                'session_id': new_session.session_id
            })
            
        self.ui.print_success(f'新对话已创建 (工作区: {self.workspace_dir})')

    async def _create_chat_with_config(self, workspace_dir: str = None, title: str = None, model: str = None):
        """创建带配置的新对话"""
        from chunk_system import ChunkManager
        
        # 1. 更新环境配置
        if workspace_dir:
            try:
                new_workspace = Path(workspace_dir).resolve()
                if not new_workspace.exists():
                    self.ui.print_error(f"工作区不存在，已创建: {new_workspace}")
                    new_workspace.mkdir(parents=True, exist_ok=True)
                
                self.workspace_dir = new_workspace
                self.workspace_name = self.workspace_dir.name
                
                # 更新工具集的工作目录
                # 注意：重新初始化 BaseTools 会重置终端状态，这在新对话中是预期的
                config = self._load_config()
                self.tools = BaseTools(sandbox_dir=str(self.workspace_dir), config=config)
                register_all_tools(self.tools)
            except Exception as e:
                self.ui.print_error(f"切换工作区失败: {e}")
                return

        if model:
            self.model = model
            # 更新 LLM 客户端配置
            self.llm = LLMClient(LLMConfig(
                api_url=self.api_url,
                model=self.model,
                api_key=self.api_key
            ))

        # 2. 创建新会话
        self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)
        
        # 3. 初始化 System Prompt (注入新的工作目录等)
        self.system_prompt = self._create_system_prompt()
        
        # 4. 保存会话
        new_session = self.session_manager.save_session(
            chunk_manager=self.chunk_manager,
            workspace_dir=str(self.workspace_dir),
            model=self.model,
            shell_open=False,
            shell_pid=None,
            session_id=None,
            title=title # 传入手动设置的标题
        )
        self.current_session_id = new_session.session_id
        
        # 5. 同步 UI
        if hasattr(self.ui, 'send_message'):
            self._sync_session_list()
            await self.ui.send_message('new_chat', {
                'session_id': new_session.session_id
            })
            
        self.ui.print_success(f'新对话已创建 (工作区: {self.workspace_dir})')

async def main():
    """主入口 - 唯一标准启动方式"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='Paw - AGI级别的桌面智能体',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  paw                      # 使用用户主目录作为默认工作目录
  paw my_project/          # 使用 my_project 作为工作目录
  paw /path/to/workspace   # 使用绝对路径作为工作目录
'''
    )
    parser.add_argument(
        'workspace',
        nargs='?',
        default=None,
        help='工作目录路径 (默认: 用户主目录 ~)'
    )
    parser.add_argument(
        '--host', '-H',
        default='127.0.0.1',
        help='Web服务器监听地址 (默认: 127.0.0.1)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8081,
        help='Web服务器端口 (默认: 8081)'
    )
    args = parser.parse_args()

    # 确定工作目录: 命令行参数 > 默认用户主目录
    workspace_dir = args.workspace or str(Path.home())

    # 检查Web UI依赖
    try:
        from ui_web import WebUI
    except ImportError:
        print("\033[31m错误: Web UI 依赖未安装。\033[0m")
        print("请运行: pip install fastapi uvicorn python-multipart websockets")
        return

    # 创建Web UI
    ui = WebUI(host=args.host, port=args.port)
    paw = Paw(ui=ui, workspace_dir=workspace_dir)

    # 并发运行Web服务器和Paw主循环
    await asyncio.gather(
        ui.run_server(),
        paw.run()
    )


if __name__ == "__main__":
    # 标准启动
    asyncio.run(main())
