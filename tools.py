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
from typing import Any, Dict, List, Optional, Tuple
import time
import sys
from tool_errors import ToolError
from terminal import PersistentTerminal


class BaseTools:
    """基础工具类 - 仅包含 3-5 个核心原子操作"""
    
    def __init__(self, sandbox_dir: Optional[str] = None):
        """初始化工具集
        
        Args:
            sandbox_dir: 沙盒目录路径，如果为 None 则使用 Paw-workspace
        """
        if sandbox_dir:
            self.sandbox_dir = Path(sandbox_dir).resolve()
            self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        else:
            # 使用环境变量获取真实桌面路径
            desktop = self._get_desktop_path()
            # 固定使用 Paw-workspace 作为沙盒
            self.sandbox_dir = desktop / "Paw-workspace"
            self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        
        self.script_timeout = 30  # 默认脚本执行超时时间（秒）
        
        # 创建持久化终端会话
        self.terminal = PersistentTerminal(self.sandbox_dir)
    
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
    
    def read_file(self, path: str, start_line: int = None, end_line: int = None) -> str:
        """读取文件内容（支持按行读取）
        
        Args:
            path: 文件路径
            start_line: 起始行号（1-indexed）
            end_line: 结束行号（包含）
            
        Returns:
            文件内容字符串
        """
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return f"错误: 文件不存在 {file_path}"
            
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # 如果指定行范围
            if start_line is not None:
                start_idx = max(0, start_line - 1)
                end_idx = end_line if end_line else len(lines)
                selected_lines = lines[start_idx:end_idx]
                # 添加行号
                result = []
                for i, line in enumerate(selected_lines, start=start_line):
                    result.append(f"{i:4d}→{line.rstrip()}")
                return "\n".join(result)
            
            return ''.join(lines)
        except Exception as e:
            return f"读取文件失败: {e}"
    
    def write_file(self, path: str, content: str) -> str:
        """写入文件
        
        Args:
            path: 文件路径
            content: 文件内容
            
        Returns:
            成功或失败信息
        """
        try:
            file_path = self._resolve_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return f"成功: 已写入 {file_path} ({len(content)} 字节)"
        except Exception as e:
            return f"写入文件失败: {e}"
    
    def delete_file(self, path: str) -> str:
        """删除文件或目录
        
        Args:
            path: 文件或目录路径
            
        Returns:
            成功或失败信息
        """
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return ToolError.file_not_found(str(file_path))
            
            if file_path.is_file():
                file_path.unlink()
                return ToolError.success("删除文件", f"{file_path.name}")
            elif file_path.is_dir():
                # 删除目录及其内容
                shutil.rmtree(file_path)
                return ToolError.success("删除目录", f"{file_path.name} 及其所有内容")
            else:
                return ToolError.io_error("删除", "未知文件类型")
                
        except PermissionError:
            return ToolError.permission_denied(str(file_path))
        except Exception as e:
            return ToolError.io_error("删除文件", str(e))
    
    def edit_file(self, path: str, line_number: int, new_content: str, action: str = "replace") -> str:
        """行级编辑文件
        
        Args:
            path: 文件路径
            line_number: 行号（1-indexed）
            new_content: 新内容
            action: 操作类型 - 'replace'(替换), 'insert'(插入), 'delete'(删除)
            
        Returns:
            成功或失败信息
        """
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return f"错误: 文件不存在 {file_path}"
            
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            line_idx = line_number - 1
            
            if action == "replace":
                if 0 <= line_idx < len(lines):
                    old_line = lines[line_idx].rstrip()
                    lines[line_idx] = new_content.rstrip() + '\n'
                    message = f"替换第{line_number}行: {old_line} -> {new_content}"
                else:
                    return f"错误: 行号{line_number}超出范围"
            
            elif action == "insert":
                # 在指定行前插入
                if 0 <= line_idx <= len(lines):
                    lines.insert(line_idx, new_content.rstrip() + '\n')
                    message = f"在第{line_number}行前插入: {new_content}"
                else:
                    return f"错误: 行号{line_number}超出范围"
            
            elif action == "delete":
                if 0 <= line_idx < len(lines):
                    deleted = lines[line_idx].rstrip()
                    lines.pop(line_idx)
                    message = f"删除第{line_number}行: {deleted}"
                else:
                    return f"错误: 行号{line_number}超出范围"
            
            else:
                return f"错误: 未知操作 {action}"
            
            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            return f"成功: {message}"
            
        except Exception as e:
            return f"编辑文件失败: {e}"
    
    def replace_in_file(self, path: str, old_text: str, new_text: str) -> str:
        """替换文件中的文本
        
        Args:
            path: 文件路径
            old_text: 要替换的文本
            new_text: 新文本
            
        Returns:
            成功或失败信息
        """
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return f"错误: 文件不存在 {file_path}"
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_text not in content:
                return f"错误: 找不到文本 '{old_text[:50]}...'"
            
            new_content = content.replace(old_text, new_text)
            occurrence_count = content.count(old_text)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return f"成功: 替换了 {occurrence_count} 处文本"
            
        except Exception as e:
            return f"替换文本失败: {e}"
    
    def find_files(self, pattern: str = "*", path: str = ".", max_depth: int = 3) -> str:
        """搜索文件（类似Windsurf的find_by_name）
        
        Args:
            pattern: 文件名模式（支持通配符）
            path: 搜索路径
            max_depth: 最大搜索深度
            
        Returns:
            找到的文件列表
        """
        try:
            import fnmatch
            
            # 参数验证
            if not pattern:
                return ToolError.parameter_error("pattern", "文件名模式（如 *.txt）")
            if not path:
                return ToolError.parameter_error("path", "搜索路径")
                
            search_path = self._resolve_path(path)
            if not search_path.exists():
                return ToolError.path_not_found(str(search_path))
            
            results = []
            
            def search_recursive(current_path: Path, current_depth: int):
                if current_depth > max_depth:
                    return
                
                try:
                    for item in current_path.iterdir():
                        # 检查文件名是否匹配
                        if fnmatch.fnmatch(item.name, pattern):
                            rel_path = item.relative_to(search_path)
                            if item.is_dir():
                                results.append(f"[目录] {rel_path}/")
                            else:
                                size = item.stat().st_size
                                results.append(f"[文件] {rel_path} ({size} 字节)")
                        
                        # 递归搜索子目录
                        if item.is_dir():
                            search_recursive(item, current_depth + 1)
                except PermissionError:
                    pass
            
            search_recursive(search_path, 0)
            
            if results:
                return ToolError.success("文件搜索", f"在 {search_path} 中找到 {len(results)} 个匹配项:\n" + "\n".join(results[:50]))
            else:
                return ToolError.empty_result(pattern)
                
        except PermissionError as e:
            return ToolError.permission_denied(str(search_path))
        except Exception as e:
            return ToolError.io_error("搜索文件", str(e))
    
    def search_in_file(self, path: str, pattern: str) -> str:
        """在文件中搜索文本
        
        Args:
            path: 文件路径
            pattern: 搜索模式
            
        Returns:
            搜索结果
        """
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return f"错误: 文件不存在 {file_path}"
            
            results = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if pattern.lower() in line.lower():
                        results.append(f"{line_num:4d}: {line.rstrip()}")
            
            if results:
                return f"在 {file_path} 中找到 {len(results)} 处匹配:\n" + "\n".join(results)
            else:
                return f"在 {file_path} 中未找到 '{pattern}'"
                
        except Exception as e:
            return f"搜索失败: {e}"
    
    def list_directory(self, path: str = ".") -> str:
        """列出目录内容
        
        Args:
            path: 目录路径
            
        Returns:
            目录内容列表
        """
        try:
            dir_path = self._resolve_path(path)
            if not dir_path.exists():
                return f"错误: 目录不存在 {dir_path}"
            
            if not dir_path.is_dir():
                return f"错误: {dir_path} 不是目录"
            
            items = []
            for item in dir_path.iterdir():
                if item.is_dir():
                    items.append(f"[目录] {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"[文件] {item.name} ({size} 字节)")
            
            if not items:
                return f"目录 {dir_path} 为空"
            
            return f"目录 {dir_path} 内容:\n" + "\n".join(sorted(items))
            
        except Exception as e:
            return f"错误: 列出目录失败 - {str(e)}"
    
    def execute_command(self, command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """在持久化终端中执行命令
        
        Args:
            command: 要执行的命令（可以是cd、ls等任何命令）
            timeout: 超时时间（秒）
            
        Returns:
            包含执行结果的字典，包括终端当前状态
        """
        if timeout is None:
            timeout = self.script_timeout
        
        # 使用持久化终端执行
        result = self.terminal.execute(command, timeout)
        
        # 添加命令本身到结果中
        result["command"] = command
        
        return result
    
    def get_terminal_status(self) -> Dict[str, Any]:
        """获取终端当前状态
        
        Returns:
            终端状态信息（用于显示给AI）
        """
        return self.terminal.get_status()
    
    def run_script(self, language: str, code: str, 
                  args: Optional[List[str]] = None) -> Dict[str, Any]:
        """执行脚本代码
        
        Args:
            language: 脚本语言 (python, bash, node, powershell)
            code: 脚本代码
            args: 脚本参数
            
        Returns:
            包含执行结果的字典
        """
        try:
            # 创建临时脚本文件
            suffix_map = {
                "python": ".py",
                "bash": ".sh",
                "node": ".js",
                "javascript": ".js",
                "powershell": ".ps1"
            }
            
            suffix = suffix_map.get(language.lower(), ".txt")
            
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=suffix,
                dir=str(self.sandbox_dir),
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(code)
                script_path = f.name
            
            try:
                # 构建执行命令
                if language.lower() == "python":
                    cmd = [sys.executable, script_path]
                elif language.lower() == "bash":
                    if sys.platform == "win32":
                        # Windows 上使用 Git Bash 或 WSL
                        cmd = ["bash", script_path]
                    else:
                        cmd = ["bash", script_path]
                elif language.lower() in ["node", "javascript"]:
                    cmd = ["node", script_path]
                elif language.lower() == "powershell":
                    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path]
                else:
                    return {
                        "success": False,
                        "error": f"不支持的脚本语言: {language}"
                    }
                
                # 添加参数
                if args:
                    cmd.extend(args)
                
                # 执行脚本
                start_time = time.time()
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.script_timeout,
                    cwd=str(self.sandbox_dir)
                )
                execution_time = time.time() - start_time
                
                return {
                    "success": result.returncode == 0,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "language": language,
                    "execution_time": execution_time,
                    "script_path": script_path
                }
                
            finally:
                # 清理临时文件
                try:
                    os.unlink(script_path)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"脚本执行超时 ({self.script_timeout}秒)",
                "language": language
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "language": language
            }
    
    def grep_search(self, query: str, path: str = ".", includes: List[str] = None, 
                    case_insensitive: bool = True, is_regex: bool = False) -> str:
        """在文件中搜索内容（类似Windsurf的grep_search）
        
        Args:
            query: 搜索查询
            path: 搜索路径
            includes: 文件类型过滤（如 ['*.py', '*.js']）
            case_insensitive: 是否忽略大小写
            is_regex: 是否使用正则表达式
            
        Returns:
            搜索结果
        """
        try:
            import re
            import fnmatch
            
            # 参数验证
            if not query:
                return ToolError.parameter_error("query", "搜索内容")
            if not path:
                return ToolError.parameter_error("path", "搜索路径")
            
            search_path = self._resolve_path(path)
            if not search_path.exists():
                return ToolError.path_not_found(str(search_path))
            
            # 编译搜索模式
            if is_regex:
                flags = re.IGNORECASE if case_insensitive else 0
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
                            if len(results) >= 100:  # 限制结果数量
                                return
                            search_in_path(item)
                except PermissionError:
                    pass
            
            def search_file(file_path: Path):
                nonlocal files_searched
                try:
                    files_searched += 1
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            # 匹配检查
                            if is_regex:
                                if pattern.search(line):
                                    rel_path = file_path.relative_to(search_path)
                                    results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                            else:
                                search_text = line if not case_insensitive else line.lower()
                                query_text = query if not case_insensitive else query.lower()
                                if query_text in search_text:
                                    rel_path = file_path.relative_to(search_path)
                                    results.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                            
                            if len(results) >= 100:
                                break
                except:
                    pass
            
            search_in_path(search_path)
            
            if results:
                summary = f"在 {files_searched} 个文件中找到 {len(results)} 处匹配\n"
                return ToolError.success("grep搜索", summary + "\n".join(results[:50]))
            else:
                return ToolError.empty_result(query)
                
        except PermissionError as e:
            return ToolError.permission_denied(str(search_path))
        except Exception as e:
            return ToolError.io_error("grep搜索", str(e))
    
    def multi_edit(self, path: str, edits: List[Dict[str, str]]) -> str:
        """多处编辑文件（类似Windsurf的multi_edit）
        
        Args:
            path: 文件路径
            edits: 编辑操作列表，每个包含 old_string 和 new_string
            
        Returns:
            成功或失败信息
        """
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists():
                return f"错误: 文件不存在 {file_path}"
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 依次应用所有编辑
            modified_content = content
            edit_count = 0
            
            for i, edit in enumerate(edits, 1):
                old_string = edit.get('old_string', '')
                new_string = edit.get('new_string', '')
                replace_all = edit.get('replace_all', False)
                
                if old_string not in modified_content:
                    return f"错误: 第{i}个编辑找不到文本 '{old_string[:50]}...'"
                
                if replace_all:
                    count = modified_content.count(old_string)
                    modified_content = modified_content.replace(old_string, new_string)
                    edit_count += count
                else:
                    # 只替换第一次出现
                    modified_content = modified_content.replace(old_string, new_string, 1)
                    edit_count += 1
            
            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            return f"成功: 应用了 {len(edits)} 个编辑，共 {edit_count} 处修改"
            
        except Exception as e:
            return f"多处编辑失败: {e}"
    
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
def create_tools(sandbox_dir: Optional[str] = None) -> BaseTools:
    """创建工具实例"""
    return BaseTools(sandbox_dir)


if __name__ == "__main__":
    # 测试代码
    tools = create_tools()
    
    # 测试文件操作
    print("测试文件写入...")
    result = tools.write_file("test.txt", "Hello, Agent!")
    print(result)
    
    print("\n测试文件读取...")
    result = tools.read_file("test.txt")
    print(result)
    
    print("\n测试目录列表...")
    result = tools.list_directory(".")
    print(result)
    
    print("\n测试命令执行...")
    result = tools.execute_command("echo 'Hello from command'")
    print(result)
    
    print("\n测试 Python 脚本执行...")
    python_code = """
import sys
print("Python version:", sys.version)
print("Hello from Python script!")
"""
    result = tools.run_script("python", python_code)
    print(result)
    
    # 清理
    tools.cleanup()
