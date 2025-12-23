"""
基础工具模块 - 提供最小化的原子级工具集
遵循 MCP (Model Context Protocol) 标准
"""
import os
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import time
import sys
from terminal import ThreadedTerminal

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
    
    def cleanup(self):
        """清理沙盒目录"""
        try:
            # 安全起见，默认不自动删除工作目录（桌面）。仅清理临时脚本已在 run_script 内完成。
            print(f"跳过自动清理工作目录: {self.sandbox_dir}")
        except Exception as e:
            print(f"清理操作提示失败: {e}")


# 工具函数的简化接口
def create_tools(sandbox_dir: str) -> BaseTools:
    """创建工具实例"""
    return BaseTools(sandbox_dir)
