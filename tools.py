#!/usr/bin/env python
"""
基础工具模块 - 提供最小化的原子级工具集
"""
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys
from terminal import ThreadedTerminal
import json
import asyncio
import random
import string
import re
from typing import Dict, List, Any, Optional
from urllib.parse import quote_plus
import aiohttp
from bs4 import BeautifulSoup
import html2text
from call import LLMClient, LLMConfig

class BaseTools:
    """基础工具类 - 仅包含 3-5 个核心原子操作"""
    
    def __init__(self, sandbox_dir: str, config: Optional[dict] = None):
        """初始化工具集
        
        Args:
            sandbox_dir: 沙盒目录路径（必需）
            config: 终端配置
        """
        if not sandbox_dir:
            raise ValueError("sandbox_dir 是必需参数，请指定工作目录")
        
        self.sandbox_dir = Path(sandbox_dir).resolve()
        
        # 确保沙盒目录存在
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        
        self.script_timeout = 30  # 默认脚本执行超时时间（秒）
        
        # 创建共享异步终端管理器，传递终端配置
        terminal_config = config.get('terminal', {}) if config else {}
        self.async_shell = ThreadedTerminal(self.sandbox_dir, terminal_config)
    
    def _get_desktop_path(self) -> Path:
        """获取真实的桌面路径（使用环境变量）"""
        # Windows: 使用 USERPROFILE 环境变量
        if os.name == 'nt':
            # 优先使用注册表中的桌面路径
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
                )
                desktop_path, _ = winreg.QueryValueEx(key, "Desktop")
                winreg.CloseKey(key)
                return Path(desktop_path)
            except:
                pass
            
            # 备用方案：使用 USERPROFILE
            userprofile = os.getenv('USERPROFILE')
            if userprofile:
                return Path(userprofile) / "Desktop"
        
        # Linux/Mac: 使用 HOME
        home = os.getenv('HOME')
        if home:
            # 尝试 XDG 标准
            xdg_desktop = os.getenv('XDG_DESKTOP_DIR')
            if xdg_desktop:
                return Path(xdg_desktop)
            return Path(home) / "Desktop"
        
        # 最后的备用方案
        return Path.home() / "Desktop"
    
    def read_file(self, file_path: str, offset: int = None, limit: int = None) -> str:
        """Reads a file at the specified path.
        
        Args:
            file_path: The path to the file to read
            offset: The 1-indexed line number to start reading from
            limit: The number of lines to read
            
        Returns:
            File content string with line numbers
        """
        try:
            resolved_path = self._resolve_path(file_path)
            if not resolved_path.exists():
                return f"Error: File not found {resolved_path}"
            
            with open(resolved_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # If line range specified
            if offset is not None:
                start_idx = max(0, offset - 1)
                end_idx = (start_idx + limit) if limit else len(lines)
                selected_lines = lines[start_idx:end_idx]
                # Add line numbers
                result = []
                for i, line in enumerate(selected_lines, start=offset):
                    result.append(f"{i:4d}→{line.rstrip()}")
                return "\n".join(result)
            
            return ''.join(lines)
        except Exception as e:
            return f"Failed to read file: {e}"
    
    def write_to_file(self, file_path: str, content: str) -> str:
        """Create new files. The file and any parent directories will be created.
        
        Args:
            file_path: The target file to create and write to
            content: The code contents to write to the file
            
        Returns:
            Success or failure message
        """
        try:
            resolved_path = self._resolve_path(file_path)
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(resolved_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return f"Success: Written to {resolved_path} ({len(content)} bytes)"
        except Exception as e:
            return f"Failed to write file: {e}"
    
    def delete_file(self, file_path: str) -> str:
        """Delete a file or directory at the specified path.
        
        Args:
            file_path: The path to the file or directory to delete
            
        Returns:
            Success or failure message
        """
        try:
            resolved_path = self._resolve_path(file_path)
            
            if not resolved_path.exists():
                return f"Error：File {str(resolved_path)} not found"
            if resolved_path.is_file():
                resolved_path.unlink()
                return f"Success: Deleted file {resolved_path.name}"
            elif resolved_path.is_dir():
                shutil.rmtree(resolved_path)
                return f"Success: Deleted directory {resolved_path.name} and all contents"
            else:
                return "Error: Unknown file type"
                
        except PermissionError:
            return f"Error: Permission denied for {resolved_path}"
        except Exception as e:
            return f"Failed to delete: {e}"
    
    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """Performs exact string replacements in files.
        
        Args:
            file_path: The path to the file to modify
            old_string: The text to replace (must be unique unless replace_all is true)
            new_string: The text to replace it with
            replace_all: Replace all occurrences (default false)
            
        Returns:
            Success or failure message
        """
        try:
            resolved_path = self._resolve_path(file_path)
            if not resolved_path.exists():
                return f"Error: File not found {resolved_path}"
            
            with open(resolved_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if old_string exists
            if old_string not in content:
                return f"Error: Could not find text '{old_string[:50]}...'"
            
            # Check if old_string and new_string are identical
            if old_string == new_string:
                return "Error: old_string and new_string are identical"
            
            # Check uniqueness if not replace_all
            occurrence_count = content.count(old_string)
            if not replace_all and occurrence_count > 1:
                return f"Error: Found {occurrence_count} occurrences of old_string. Use replace_all=true or provide more context to make it unique."
            
            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                replaced_count = occurrence_count
            else:
                new_content = content.replace(old_string, new_string, 1)
                replaced_count = 1
            
            # Write back
            with open(resolved_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return f"Success: Replaced {replaced_count} occurrence(s)"
            
        except Exception as e:
            return f"Failed to edit file: {e}"
    
    
    def find_by_name(self, search_directory: str, pattern: str, max_depth: int = 3, type: str = "any") -> str:
        """Search for files and subdirectories within a specified directory.
        
        Args:
            search_directory: The directory to search within
            pattern: Pattern to search for, supports glob format
            max_depth: Maximum depth to search
            type: Type filter - 'file', 'directory', or 'any'
            
        Returns:
            List of found files
        """
        try:
            import fnmatch
            
            # Parameter validation
            if not pattern:
                return "Error: pattern is required"
            if not search_directory:
                return "Error: search_directory is required"
                
            search_path = self._resolve_path(search_directory)
            if not search_path.exists():
                return f"Error: Path not found {search_path}"
            
            results = []
            
            def search_recursive(current_path: Path, current_depth: int):
                if current_depth > max_depth:
                    return
                
                try:
                    for item in current_path.iterdir():
                        # Check if filename matches pattern
                        if fnmatch.fnmatch(item.name, pattern):
                            # Apply type filter
                            if type == "file" and not item.is_file():
                                continue
                            if type == "directory" and not item.is_dir():
                                continue
                            
                            rel_path = item.relative_to(search_path)
                            if item.is_dir():
                                results.append(f"[dir] {rel_path}/")
                            else:
                                size = item.stat().st_size
                                results.append(f"[file] {rel_path} ({size} bytes)")
                        
                        # Recursively search subdirectories
                        if item.is_dir():
                            search_recursive(item, current_depth + 1)
                except PermissionError:
                    pass
            
            search_recursive(search_path, 0)
            
            if results:
                return f"Found {len(results)} matches in {search_path}:\n" + "\n".join(results[:50])
            else:
                return f"No matches found for pattern '{pattern}'"
                
        except PermissionError:
            return f"Error: Permission denied for {search_path}"
        except Exception as e:
            return f"Failed to search: {e}"
    
    
    def list_dir(self, directory_path: str) -> str:
        """Lists files and directories in a given path.
        
        Args:
            directory_path: The absolute path to the directory to list
            
        Returns:
            Directory content list
        """
        try:
            dir_path = self._resolve_path(directory_path)
            if not dir_path.exists():
                return f"Error: Directory not found {dir_path}"
            
            if not dir_path.is_dir():
                return f"Error: {dir_path} is not a directory"
            
            items = []
            for item in dir_path.iterdir():
                if item.is_dir():
                    items.append(f"[dir] {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"[file] {item.name} ({size} bytes)")
            
            if not items:
                return f"Directory {dir_path} is empty"
            
            return f"Contents of {dir_path}:\n" + "\n".join(sorted(items))
            
        except Exception as e:
            return f"Error: Failed to list directory - {str(e)}"
    
    def run_command(self, command: str, cwd: str = None, blocking: bool = True) -> Dict[str, Any]:
        """PROPOSE a command to run on behalf of the user.
        
        Args:
            command: The exact command line string to execute
            cwd: The current working directory for the command
            blocking: If true, the command will block until finished
        
        Returns:
            Execution result dictionary
        """
        # 过滤危险命令（会导致终端清屏或影响主程序）
        dangerous_commands = ['clear', 'cls', 'reset', 'tput clear', 'printf "\033c"']
        cmd_lower = command.strip().lower()
        
        for dangerous_cmd in dangerous_commands:
            if dangerous_cmd in cmd_lower:
                return {
                    "success": True,
                    "result": f"Command '{command}' skipped (screen clear commands are not allowed in this environment)",
                    "stdout": f"Command '{command}' skipped (screen clear commands are not allowed in this environment)",
                    "note": "Screen manipulation commands are blocked to preserve conversation context"
                }
        
        # 如果终端未打开，自动打开
        if not self.async_shell.is_shell_open():
            open_result = self.async_shell.open_shell()
            if not open_result.get("success"):
                return {
                    "success": False,
                    "error": f"无法打开终端: {open_result.get('error', '未知错误')}",
                    "stderr": f"无法打开终端: {open_result.get('error', '未知错误')}"
                }
            # 等待终端完全启动
            import time
            time.sleep(1)
        
        return self.async_shell.enqueue_command(command)

    def open_shell(self) -> Dict[str, Any]:
        """打开共享异步终端窗口"""
        return self.async_shell.open_shell()

    def interrupt_command(self) -> Dict[str, Any]:
        """中断当前正在执行的命令"""
        return self.async_shell.interrupt_command()
    
    def wait(self, seconds: float) -> Dict[str, Any]:
        """等待指定时间（秒），用于同步异步操作"""
        try:
            # 确保输入是数字
            try:
                seconds = float(seconds)
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": "等待时间必须是数字",
                    "stderr": "等待时间必须是数字"
                }
            
            if seconds < 0:
                return {
                    "success": False,
                    "error": "等待时间不能为负数",
                    "stderr": "等待时间不能为负数"
                }
            
            import time
            time.sleep(seconds)
            
            return {
                "success": True,
                "message": f"已等待 {seconds} 秒",
                "stdout": f"已等待 {seconds} 秒"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"等待操作失败: {e}",
                "stderr": f"等待操作失败: {e}"
            }
    
    def get_terminal_status(self) -> Dict[str, Any]:
        """获取终端当前状态
        
        Returns:
            终端状态信息（用于显示给AI）
        """
        return {
            "is_open": self.async_shell.is_shell_open(),
            "pid": self.async_shell.process.pid if hasattr(self.async_shell, 'process') and self.async_shell.process else None,
            "type": "threaded_terminal",
            "working_directory": str(self.sandbox_dir)
        }
    
    
    def grep_search(self, query: str, search_path: str, includes: List[str] = None, 
                    case_sensitive: bool = False, is_regex: bool = False) -> str:
        """A powerful search tool.
        
        Args:
            query: The search term or pattern to look for within files
            search_path: The path to search (can be a directory or a file)
            includes: Glob patterns to filter files, e.g., '*.py'
            case_sensitive: If true, performs a case-sensitive search (default false)
            is_regex: If true, treats query as a regular expression pattern
            
        Returns:
            Search results
        """
        try:
            import re
            import fnmatch
            
            # Parameter validation
            if not query:
                return "Error: query is required"
            if not search_path:
                return "Error: search_path is required"
            
            resolved_path = self._resolve_path(search_path)
            if not resolved_path.exists():
                return f"Error: Path not found {resolved_path}"
            
            # Compile search pattern
            if is_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(query, flags)
            else:
                pattern = None
            
            results = []
            files_searched = 0
            
            def should_include_file(file_path: Path) -> bool:
                if not includes:
                    return True
                for pattern in includes:
                    if fnmatch.fnmatch(file_path.name, pattern):
                        return True
                return False
            
            def search_in_path(current_path: Path):
                nonlocal files_searched
                try:
                    if current_path.is_file():
                        if should_include_file(current_path):
                            search_file(current_path)
                    elif current_path.is_dir():
                        for item in current_path.iterdir():
                            if len(results) >= 100:  # Limit results
                                return
                            search_in_path(item)
                except PermissionError:
                    pass
            
            def search_file(file_path: Path):
                nonlocal files_searched
                try:
                    files_searched += 1
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            # Match check
                            if is_regex:
                                if pattern.search(line):
                                    rel_path = file_path.relative_to(resolved_path)
                                    results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                            else:
                                search_text = line if case_sensitive else line.lower()
                                query_text = query if case_sensitive else query.lower()
                                if query_text in search_text:
                                    rel_path = file_path.relative_to(resolved_path)
                                    results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                            
                            if len(results) >= 100:
                                break
                except:
                    pass
            
            search_in_path(resolved_path)
            
            if results:
                summary = f"Found {len(results)} matches in {files_searched} files:\n"
                return summary + "\n".join(results[:50])
            else:
                return f"No matches found for '{query}'"
                
        except PermissionError:
            return f"Error: Permission denied for {resolved_path}"
        except Exception as e:
            return f"Failed to search: {e}"
    
    def multi_edit(self, file_path: str, edits: List[Dict[str, str]]) -> str:
        """Make multiple edits to a single file in one operation.
        
        Args:
            file_path: The path to the file to modify
            edits: Array of edit operations, each containing old_string and new_string
            
        Returns:
            Success or failure message
        """
        try:
            resolved_path = self._resolve_path(file_path)
            if not resolved_path.exists():
                return f"Error: File not found {resolved_path}"
            
            with open(resolved_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Apply all edits in sequence
            modified_content = content
            edit_count = 0
            
            for i, edit in enumerate(edits, 1):
                old_string = edit.get('old_string', '')
                new_string = edit.get('new_string', '')
                replace_all = edit.get('replace_all', False)
                
                if old_string not in modified_content:
                    return f"Error: Edit #{i} could not find text '{old_string[:50]}...'"
                
                if old_string == new_string:
                    return f"Error: Edit #{i} has identical old_string and new_string"
                
                if replace_all:
                    count = modified_content.count(old_string)
                    modified_content = modified_content.replace(old_string, new_string)
                    edit_count += count
                else:
                    # Only replace first occurrence
                    modified_content = modified_content.replace(old_string, new_string, 1)
                    edit_count += 1
            
            # Write back
            with open(resolved_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            return f"Success: Applied {len(edits)} edits, {edit_count} total replacements"
            
        except Exception as e:
            return f"Failed to multi-edit: {e}"
    
    # ============================================================
    # TODO-list 工具
    # ============================================================
    
    def update_plan(self, plan: list, explanation: str = None) -> dict:
        """Updates the task plan with a list of steps and their statuses.
        
        Args:
            plan: List of plan items, each with 'step' (description) and 'status' (pending/in_progress/completed)
            explanation: Optional explanation for the plan update
            
        Returns:
            Dict with success status and plan data
        """
        # 初始化 plan 存储（如果不存在）
        if not hasattr(self, '_todo_plan'):
            self._todo_plan = []
        
        # 验证 plan 格式
        if not isinstance(plan, list):
            return {"success": False, "error": "plan must be a list of items"}
        
        # 验证每个 item
        valid_statuses = {"pending", "in_progress", "completed"}
        in_progress_count = 0
        validated_plan = []
        
        for i, item in enumerate(plan):
            if not isinstance(item, dict):
                return {"success": False, "error": f"plan item {i} must be an object with 'step' and 'status'"}
            
            step = item.get("step", "").strip()
            status = item.get("status", "pending")
            
            if not step:
                return {"success": False, "error": f"plan item {i} has empty step description"}
            
            if status not in valid_statuses:
                return {"success": False, "error": f"plan item {i} has invalid status '{status}'"}
            
            if status == "in_progress":
                in_progress_count += 1
            
            validated_plan.append({
                "step": step,
                "status": status
            })
        
        # 检查是否有多个 in_progress
        if in_progress_count > 1:
            return {"success": False, "error": f"At most one step can be in_progress (found {in_progress_count})"}
        
        # 更新计划
        self._todo_plan = validated_plan
        
        # 统计
        completed = sum(1 for item in validated_plan if item["status"] == "completed")
        total = len(validated_plan)
        
        return {
            "success": True,
            "explanation": explanation,
            "plan": validated_plan,
            "completed": completed,
            "total": total
        }
    
    def get_plan(self) -> dict:
        """Get the current task plan.
        
        Returns:
            Dict with plan data or error if no plan exists
        """
        if not hasattr(self, '_todo_plan') or not self._todo_plan:
            return {"success": True, "plan": [], "completed": 0, "total": 0}
        
        completed = sum(1 for item in self._todo_plan if item["status"] == "completed")
        total = len(self._todo_plan)
        
        return {
            "success": True,
            "plan": self._todo_plan,
            "completed": completed,
            "total": total
        }
    
    def _resolve_path(self, path: str) -> Path:
        """解析路径（强制限制在沙盒目录内）
        
        Args:
            path: 输入路径
            
        Returns:
            解析后的 Path 对象（始终在沙盒内）
        """
        # 处理特殊路径符号
        if path.startswith('/'):
            # Unix风格的绝对路径，去掉前导斜杠，视为相对路径
            path = path.lstrip('/')
        elif path.startswith('~'):
            # 家目录符号，映射到沙盒根目录
            path = path.lstrip('~').lstrip('/')
        
        path_obj = Path(path)
        
        # 所有路径都相对于沙盒目录
        resolved = (self.sandbox_dir / path_obj).resolve()
        
        # 安全检查：确保解析后的路径在沙盒内
        try:
            resolved.relative_to(self.sandbox_dir)
            return resolved
        except ValueError:
            # 如果路径试图逃出沙盒（如使用 ../..），强制返回沙盒根目录
            return self.sandbox_dir

    def load_skill(self, skill_name: str, include_reference: bool = True,
                   include_examples: bool = True) -> str:
        """加载指定的 Skill，读取其 SKILL.md 内容

        遵循 Claude Code Skills 规范：
        1. 返回 Base Path（skill 目录的绝对路径）
        2. 返回 SKILL.md 内容（去除 YAML frontmatter）
        3. 可选加载 reference.md（详细文档）
        4. 可选加载 examples.md（使用示例）
        5. scripts/ 目录中的脚本可通过 run_skill_script 工具执行

        Args:
            skill_name: Skill 名称（目录名）
            include_reference: 是否包含 reference.md 内容（默认 True）
            include_examples: 是否包含 examples.md 内容（默认 True）

        Returns:
            Base Path + SKILL.md 内容（去除 frontmatter）+ 可选的 reference/examples
        """
        skills_dir = Path.home() / ".paw" / "skills"
        skill_dir = skills_dir / skill_name
        skill_md = skill_dir / "SKILL.md"

        if not skill_md.exists():
            return f"Error: Skill '{skill_name}' not found. SKILL.md does not exist at {skill_md}"

        try:
            content = skill_md.read_text(encoding='utf-8')

            # 移除 YAML frontmatter（第一个 --- 和第二个 --- 之间的内容）
            lines = content.split('\n')
            content_start = 0
            found_first = False
            for i, line in enumerate(lines):
                if line.strip() == '---':
                    if not found_first:
                        found_first = True
                    else:
                        content_start = i + 1
                        break

            skill_body = '\n'.join(lines[content_start:]).strip()

            # 构建返回内容
            parts = []
            base_path = str(skill_dir)
            parts.append(f"Base Path: {base_path}")
            parts.append("")
            parts.append("## SKILL.md")
            parts.append("")
            parts.append(skill_body)

            # 加载 reference.md（如果存在且启用）
            reference_md = skill_dir / "reference.md"
            if include_reference and reference_md.exists():
                try:
                    ref_content = reference_md.read_text(encoding='utf-8').strip()
                    parts.append("")
                    parts.append("")
                    parts.append("## reference.md (Detailed Documentation)")
                    parts.append("")
                    parts.append(ref_content)
                except Exception:
                    pass  # 静默跳过读取失败的文件

            # 加载 examples.md（如果存在且启用）
            examples_md = skill_dir / "examples.md"
            if include_examples and examples_md.exists():
                try:
                    ex_content = examples_md.read_text(encoding='utf-8').strip()
                    parts.append("")
                    parts.append("")
                    parts.append("## examples.md (Usage Examples)")
                    parts.append("")
                    parts.append(ex_content)
                except Exception:
                    pass  # 静默跳过读取失败的文件

            # 列出可用的脚本
            scripts_dir = skill_dir / "scripts"
            if scripts_dir.exists() and scripts_dir.is_dir():
                try:
                    scripts = [f.name for f in scripts_dir.iterdir()
                              if f.is_file() and not f.name.startswith('.')]
                    if scripts:
                        parts.append("")
                        parts.append("")
                        parts.append("## Available Scripts")
                        parts.append("")
                        parts.append(f"Scripts directory: {scripts_dir}")
                        parts.append("")
                        for script in sorted(scripts):
                            parts.append(f"  - {script}")
                        parts.append("")
                        parts.append("Use run_skill_script(skill_name, script_name, args) to execute.")
                except Exception:
                    pass

            return '\n'.join(parts)

        except Exception as e:
            return f"Error: Failed to read skill '{skill_name}': {e}"

    def run_skill_script(self, skill_name: str, script_name: str, args: str = "") -> str:
        """执行 Skill scripts/ 目录下的脚本

        遵循 Claude Code Skills 规范：
        - 脚本位于 ~/.paw/skills/<skill_name>/scripts/<script_name>
        - 支持的脚本类型：.py, .sh, .bat, .ps1
        - 执行时自动切换到 skill 目录作为工作目录

        Args:
            skill_name: Skill 名称（目录名）
            script_name: 脚本文件名（位于 scripts/ 目录下）
            args: 传递给脚本的命令行参数（可选）

        Returns:
            脚本执行结果
        """
        import subprocess
        import platform

        skills_dir = Path.home() / ".paw" / "skills"
        skill_dir = skills_dir / skill_name
        script_path = skill_dir / "scripts" / script_name

        if not skill_dir.exists():
            return f"Error: Skill '{skill_name}' not found at {skill_dir}"

        if not script_path.exists():
            return f"Error: Script '{script_name}' not found at {script_path}"

        try:
            # 确定解释器
            ext = script_path.suffix.lower()
            if ext == '.py':
                interpreter = sys.executable  # 当前 Python 解释器
                cmd = [interpreter, str(script_path)]
            elif ext == '.sh':
                interpreter = '/bin/bash'
                cmd = [interpreter, str(script_path)]
            elif ext == '.ps1':
                interpreter = 'powershell.exe'
                cmd = [interpreter, '-File', str(script_path)]
            elif ext == '.bat':
                interpreter = 'cmd.exe'
                cmd = [interpreter, '/c', str(script_path)]
            elif ext == '.js':
                # Node.js 脚本
                interpreter = 'node'
                cmd = [interpreter, str(script_path)]
            else:
                # 无扩展名或其他类型，尝试直接执行
                cmd = [str(script_path)]

            # 添加参数
            if args and args.strip():
                cmd.extend(args.strip().split())

            # 执行脚本
            result = subprocess.run(
                cmd,
                cwd=str(skill_dir),  # 工作目录为 skill 根目录
                capture_output=True,
                text=True,
                timeout=self.script_timeout,
                encoding='utf-8',
                errors='replace'
            )

            output = []
            if result.stdout:
                output.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output.append(f"STDERR:\n{result.stderr}")
            if result.returncode != 0:
                output.append(f"Exit code: {result.returncode}")

            return '\n'.join(output) if output else f"Script executed successfully (no output)"

        except subprocess.TimeoutExpired:
            return f"Error: Script execution timed out (limit: {self.script_timeout}s)"
        except FileNotFoundError as e:
            return f"Error: Interpreter not found. {e}"
        except Exception as e:
            return f"Error: Failed to execute script: {e}"

    def pass_turn(self, reason: str = "") -> str:
        """跳过当前回合，不生成响应

        用于以下情况：
        1) 用户说的内容不需要回复（如 "ok"、"got it"）
        2) 已完成任务，等待用户下一步指示
        3) 对话自然暂停

        Args:
            reason: 跳过的原因（可选）

        Returns:
            确认消息
        """
        if reason:
            return f"[Turn skipped: {reason}]"
        return "[Turn skipped]"

    def cleanup(self):
        """清理沙盒目录"""
        try:
            # 安全起见，默认不自动删除工作目录（桌面）。仅清理临时脚本已在 run_script 内完成。
            print(f"跳过自动清理工作目录: {self.sandbox_dir}")
        except Exception as e:
            print(f"清理操作提示失败: {e}")

class WebTools:
    """
    Web 工具类 - 提供搜索和网页阅读功能
    """
    def __init__(self, config: dict, api_url: str, model_getter, api_key: Optional[str] = None):
        """
        初始化 Web 工具
        
        Args:
            config: web 配置字典
            api_url: API 地址（用于生成摘要）
            model_getter: 获取当前模型名称的函数（动态获取）
            api_key: API 密钥
        """
        self.config = config or {}
        self.api_url = api_url
        self._model_getter = model_getter  # 动态获取模型
        self.api_key = api_key

        # 配置项
        self.search_engine = self.config.get('search_engine', 'duckduckgo')
        self.max_results = self.config.get('max_results', 5)
        self.page_size = self.config.get('page_size', 4096)  # 每页最大 4KB
        self.use_jina_reader = self.config.get('use_jina_reader', True)  # 默认启用 Jina Reader
        self.custom_search_api = self.config.get('custom_search_api') or {}

        # 内存存储: page_id -> {"content": str, "url": str, "summary": str}
        self.pages: Dict[str, Dict[str, str]] = {}

        # URL 到 page_ids 的映射
        self.url_pages: Dict[str, List[str]] = {}

        # 搜索结果 URL 映射: url_id -> url
        self.url_refs: Dict[str, str] = {}

        # 已使用的 ID 集合（防止重复，page_id 和 url_id 共用）
        self.used_ids: set = set()

        # html2text 转换器配置
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = True
        self.h2t.ignore_emphasis = False
        self.h2t.body_width = 0  # 不自动换行

    @property
    def model(self) -> str:
        """动态获取当前模型名称"""
        return self._model_getter() if callable(self._model_getter) else str(self._model_getter)
    
    def _generate_page_id(self) -> str:
        """生成全局唯一的 4 位 page_id (base62)"""
        chars = string.ascii_lowercase + string.ascii_uppercase + string.digits
        while True:
            page_id = ''.join(random.choices(chars, k=4))
            if page_id not in self.used_ids:
                self.used_ids.add(page_id)
                return page_id
    
    async def search_web(self, query: str, num_results: int = None) -> Dict[str, Any]:
        """
        搜索引擎搜索
        
        Args:
            query: 搜索关键词，支持搜索语法
            num_results: 返回结果数量（默认使用配置值）
            
        Returns:
            搜索结果字典
        """
        num_results = num_results or self.max_results
        
        try:
            use_custom_api = bool(self.custom_search_api.get('url'))
            engine_label = self.search_engine
            
            if use_custom_api:
                engine_label = self.custom_search_api.get('name') or self.custom_search_api.get('engine') or 'custom'
                results = await self._search_custom_api(query, num_results)
            else:
                # 默认使用 DuckDuckGo
                results = await self._search_duckduckgo(query, num_results)
            
            # 为每个结果分配 4 字符 ID
            for r in results:
                url_id = self._generate_page_id()  # 复用 ID 生成器
                r["id"] = url_id
                self.url_refs[url_id] = r["url"]
            
            return {
                "success": True,
                "query": query,
                "engine": engine_label,
                "results": results,
                "count": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}",
                "query": query
            }
    
    async def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict[str, str]]:
        """使用 DuckDuckGo 搜索"""
        from ddgs import DDGS
        
        results = []
        
        # DuckDuckGo 搜索（同步库，在线程中运行）
        def do_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))
        
        # 在线程池中执行同步操作
        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(None, do_search)
        
        for item in search_results:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", "")[:200]  # 摘要限制 200 字符
            })
        
        return results
    
    async def _search_custom_api(self, query: str, num_results: int) -> List[Dict[str, str]]:
        """调用用户自定义搜索 API"""
        if not self.custom_search_api.get('url'):
            raise ValueError("custom_search_api.url 未配置")
        
        replacements = {
            "query": query,
            "query_encoded": quote_plus(query),
            "api_key": self.custom_search_api.get('api_key', '')
        }
        
        url_template = self.custom_search_api.get('url', '')
        url = self._render_template(url_template, replacements)
        method = (self.custom_search_api.get('method') or 'GET').upper()
        headers = self._render_template(self.custom_search_api.get('headers', {}), replacements) or {}
        params = self._render_template(self.custom_search_api.get('params'), replacements)
        payload = self._render_template(self.custom_search_api.get('payload'), replacements)
        payload_type = (self.custom_search_api.get('payload_type') or 'json').lower()
        timeout = aiohttp.ClientTimeout(total=self.custom_search_api.get('timeout', 15))
        
        request_kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout}
        if params and isinstance(params, dict):
            request_kwargs["params"] = params
        
        if method in {"POST", "PUT", "PATCH"} and payload is not None:
            if payload_type == "json":
                if isinstance(payload, (dict, list)):
                    request_kwargs["json"] = payload
                else:
                    try:
                        request_kwargs["json"] = json.loads(payload)
                    except Exception:
                        request_kwargs["data"] = payload
            elif payload_type == "form" and isinstance(payload, dict):
                request_kwargs["data"] = payload
            else:
                request_kwargs["data"] = payload if isinstance(payload, str) else json.dumps(payload)
        
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, **request_kwargs) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"自定义搜索 API 请求失败 (HTTP {response.status}): {error_text[:200]}")
                
                try:
                    data = await response.json()
                except Exception as e:
                    text = await response.text()
                    raise RuntimeError("自定义搜索 API 返回的不是 JSON 数据: " + text[:200]) from e

        results_path = self.custom_search_api.get('results_path', 'results')
        records = self._extract_from_path(data, results_path) if results_path else data
        if not isinstance(records, list):
            raise ValueError(f"自定义搜索 API 返回结果无法解析，期望列表，得到 {type(records)}")
        
        title_field = self.custom_search_api.get('title_field', 'title')
        url_field = self.custom_search_api.get('url_field', 'url')
        snippet_field = self.custom_search_api.get('snippet_field', 'snippet')
        
        parsed_results: List[Dict[str, str]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            
            title = self._extract_from_path(item, title_field) if title_field else None
            link = self._extract_from_path(item, url_field) if url_field else None
            snippet = self._extract_from_path(item, snippet_field) if snippet_field else None
            
            if not link:
                continue
            
            parsed_results.append({
                "title": str(title or "")[:200],
                "url": str(link),
                "snippet": str(snippet or "")[:300]
            })
            
            if len(parsed_results) >= num_results:
                break
        
        if not parsed_results:
            raise ValueError("自定义搜索 API 未返回有效的搜索结果")
        
        return parsed_results
    
    async def load_url_content(self, url: str) -> Dict[str, Any]:
        """
        加载网页内容到内存，分页并生成摘要
        
        Args:
            url: 要加载的网页 URL，或者 search_web 返回的 4 字符 ID
            
        Returns:
            加载结果，包含页码信息和每页摘要
        """
        # 支持 4 字符 ID 引用
        url_id = None
        if len(url) == 4 and url in self.url_refs:
            url_id = url
            url = self.url_refs[url]
        
        try:
            # 获取网页内容
            raw_content = await self._fetch_url(url)
            
            # 检查是否是 Jina 返回的 Markdown
            if raw_content.startswith("__JINA_MARKDOWN__\n"):
                # Jina 已经返回 Markdown，直接使用
                markdown_content = raw_content[len("__JINA_MARKDOWN__\n"):]
                # 从 Markdown 中提取标题（第一个 # 开头的行）
                title = self._extract_title_from_markdown(markdown_content)
            else:
                # 原始 HTML，需要转换
                markdown_content = self._html_to_markdown(raw_content)
                title = self._extract_title(raw_content)
            
            # 分页
            pages_content = self._split_into_pages(markdown_content)
            
            # 为每页生成 ID
            page_ids = [self._generate_page_id() for _ in pages_content]
            total_pages = len(pages_content)
            
            # 并行生成所有摘要（大幅提升速度）
            summary_tasks = [
                self._generate_summary(content, i + 1, total_pages)
                for i, content in enumerate(pages_content)
            ]
            summaries = await asyncio.gather(*summary_tasks)
            
            # 存储到内存并构建返回信息
            page_infos = []
            for i, (page_id, content, summary) in enumerate(zip(page_ids, pages_content, summaries)):
                self.pages[page_id] = {
                    "content": content,
                    "url": url,
                    "page_num": i + 1,
                    "total_pages": total_pages,
                    "summary": summary
                }
                
                page_infos.append({
                    "page_id": page_id,
                    "page_num": i + 1,
                    "summary": summary,
                    "size": len(content)
                })
            
            # 记录 URL 到 pages 的映射
            self.url_pages[url] = page_ids
            
            result = {
                "success": True,
                "url": url,
                "title": title,
                "total_pages": len(pages_content),
                "total_size": len(markdown_content),
                "pages": page_infos
            }
            # 如果是通过 ID 加载的，附上 ID
            if url_id:
                result["url_id"] = url_id
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"加载失败: {str(e)}",
                "url": url
            }
    
    async def _fetch_url(self, url: str) -> str:
        """获取网页内容（支持 Jina Reader 代理）"""
        
        if self.use_jina_reader:
            # 使用 Jina Reader API（自动处理 JS 渲染）
            return await self._fetch_via_jina(url)
        else:
            # 直接获取（仅支持静态页面）
            return await self._fetch_direct(url)
    
    async def _fetch_via_jina(self, url: str) -> str:
        """通过 Jina Reader API 获取网页内容（返回 Markdown）"""
        jina_url = f"https://r.jina.ai/{url}"
        
        headers = {
            "Accept": "text/plain",
            "User-Agent": "Paw/1.0"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                jina_url, 
                headers=headers, 
                timeout=aiohttp.ClientTimeout(total=60)  # Jina 可能需要更长时间渲染
            ) as response:
                if response.status != 200:
                    # Jina 失败，回退到直接获取
                    return await self._fetch_direct(url)
                
                content = await response.text()
                
                # Jina 返回的已经是 Markdown，标记一下
                return f"__JINA_MARKDOWN__\n{content}"
    
    async def _fetch_direct(self, url: str) -> str:
        """直接获取网页 HTML 内容"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}") 
                
                # 尝试检测编码
                content_type = response.headers.get('Content-Type', '')
                if 'charset=' in content_type:
                    encoding = content_type.split('charset=')[-1].split(';')[0].strip()
                else:
                    encoding = 'utf-8'
                
                try:
                    return await response.text(encoding=encoding)
                except:
                    return await response.text(encoding='utf-8', errors='ignore')
    
    def _html_to_markdown(self, html: str) -> str:
        """将 HTML 转换为 Markdown"""
        # 使用 BeautifulSoup 清理 HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        # 移除脚本、样式等无用元素
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']):
            tag.decompose()
        
        # 尝试找到主要内容区域
        main_content = (
            soup.find('main') or 
            soup.find('article') or 
            soup.find('div', class_=re.compile(r'content|main|article|post', re.I)) or
            soup.find('body')
        )
        
        if main_content:
            html_str = str(main_content)
        else:
            html_str = str(soup)
        
        # 转换为 Markdown
        markdown = self.h2t.handle(html_str)
        
        # 清理多余空行
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        return markdown.strip()
    
    def _render_template(self, value: Any, replacements: Dict[str, str]) -> Any:
        """对字符串、列表、字典中的占位符进行替换"""
        if value is None:
            return None
        
        if isinstance(value, str):
            result = value
            for key, val in replacements.items():
                placeholder = f"{{{key}}}"
                result = result.replace(placeholder, val or "")
            return result
        
        if isinstance(value, dict):
            return {k: self._render_template(v, replacements) for k, v in value.items()}
        
        if isinstance(value, list):
            return [self._render_template(v, replacements) for v in value]
        
        return value
    
    def _extract_from_path(self, data: Any, path: str) -> Any:
        """根据点路径提取嵌套字段，支持简单的下标访问"""
        if path is None:
            return data
        
        current = data
        for part in filter(None, path.split('.')):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current
    
    def _extract_title(self, html: str) -> str:
        """提取网页标题"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 优先使用 <title> 标签
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            return title_tag.string.strip()[:100]
        
        # 其次使用 <h1>
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text().strip()[:100]
        
        return "无标题"
    
    def _extract_title_from_markdown(self, markdown: str) -> str:
        """从 Markdown 内容中提取标题"""
        lines = markdown.strip().split('\n')
        
        for line in lines[:20]:  # 只检查前 20 行
            line = line.strip()
            # 匹配 # 开头的标题
            if line.startswith('# '):
                return line[2:].strip()[:100]
            # 匹配 Title: 开头（Jina 有时会这样返回）
            if line.lower().startswith('title:'):
                return line[6:].strip()[:100]
        
        return "无标题"
    
    def _split_into_pages(self, content: str) -> List[str]:
        """将内容分割为多个页面"""
        pages = []
        
        # 按字节大小分割
        content_bytes = content.encode('utf-8')
        total_size = len(content_bytes)
        
        if total_size <= self.page_size:
            return [content]
        
        # 按段落分割，尽量不打断段落
        paragraphs = content.split('\n\n')
        current_page = ""
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para.encode('utf-8'))
            
            if current_size + para_size + 2 > self.page_size:
                if current_page:
                    pages.append(current_page.strip())
                current_page = para
                current_size = para_size
            else:
                current_page += "\n\n" + para if current_page else para
                current_size += para_size + 2
        
        if current_page:
            pages.append(current_page.strip())
        
        return pages if pages else [content]
    
    async def _generate_summary(self, content: str, page_num: int, total_pages: int) -> str:
        """使用 LLM 生成页面摘要（10-30字）"""
        
        # 如果内容为空，直接返回
        if not content or not content.strip():
            return "(空页面)"
        
        # 截取内容的前 500 字符用于生成摘要
        preview = content[:500] if len(content) > 500 else content
        
        prompt = f"""请用10-30个中文字符总结以下内容。只输出总结，不要其他内容。\n内容（第{page_num}页/共{total_pages}页）:\n{preview} \n请开始总结:"""
        
        try:
            llm = LLMClient(LLMConfig(
                api_url=self.api_url,
                model=self.model,
                api_key=self.api_key,
                timeout=15
            ))
            
            messages = [
                {"role": "system", "content": "你是一个精简的摘要生成器。只输出10-30字的中文摘要，不要任何其他内容。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await llm.chat(
                messages,
                temperature=0.3,
                max_tokens=50,
                extra_params={"thinking": "disabled"}  # 禁用推理模式
            )
            
            if not response.is_error and response.content:
                summary = response.content.strip()
                return summary[:30] if len(summary) > 30 else summary
            else:
                return self._simple_summary(content)
                        
        except Exception as e:
            # 出错时使用简单摘要
            pass
        
        # 兆底：确保返回非空
        fallback = self._simple_summary(content)
        return fallback if fallback else f"第{page_num}页内容"
    
    def _simple_summary(self, content: str) -> str:
        """简单摘要（当 LLM 不可用时）"""
        if not content or not content.strip():
            return "(空页面)"
        
        # 提取有意义的内容作为摘要
        lines = content.strip().split('\n')
        candidates = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # 移除 Markdown 标记
                clean = re.sub(r'[#*_`\[\]\(\)]', '', line).strip()
                # 跳过太短的行（<5字符）和纯链接行
                if len(clean) >= 5 and not clean.startswith('http'):
                    candidates.append(clean)
        
        if candidates:
            # 选择第一个足够长的候选
            best = candidates[0]
            return best[:30] if len(best) > 30 else best
        
        # 如果没有候选，取前30个非空字符
        text = content.strip()[:50].replace('\n', ' ')
        return text[:30] if text else "(无内容)"
    
    def read_page(self, page_id: str) -> Dict[str, Any]:
        """
        读取指定页面的内容
        
        Args:
            page_id: 4位页面 ID
            
        Returns:
            页面内容
        """
        if page_id not in self.pages:
            return {
                "success": False,
                "error": f"页面 '{page_id}' 不存在。请先使用 load_url_content 加载网页。"
            }
        
        page_data = self.pages[page_id]
        
        return {
            "success": True,
            "page_id": page_id,
            "url": page_data["url"],
            "page_num": page_data["page_num"],
            "total_pages": page_data["total_pages"],
            "content": page_data["content"],
            "size": len(page_data["content"])
        }
    
    def get_loaded_urls(self) -> Dict[str, Any]:
        """获取已加载的 URL 列表（调试用）"""
        return {
            "urls": list(self.url_pages.keys()),
            "total_pages": len(self.pages)
        }
    
    def clear_cache(self) -> Dict[str, Any]:
        """清空缓存"""
        count = len(self.pages)
        self.pages.clear()
        self.url_pages.clear()
        # 不清空 used_ids，保证 ID 全局唯一
        return {
            "success": True,
            "cleared_pages": count
        }
