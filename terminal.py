#!/usr/bin/env python
"""
持久化终端会话
AI通过这个终端执行命令，终端保持自己的状态（工作目录、环境变量等）
"""
import subprocess
import threading
import queue
import time
from pathlib import Path
from typing import Optional, Dict, Any
import sys


class PersistentTerminal:
    """持久化的命令行会话"""
    
    def __init__(self, workspace_dir: Path):
        """初始化终端
        
        Args:
            workspace_dir: 工作空间根目录
        """
        self.workspace_dir = workspace_dir
        self.current_dir = workspace_dir  # 终端当前所在目录
        self.command_history = []  # 命令历史
        self.last_output = ""  # 上次输出
        self.last_error = ""   # 上次错误
        self.env_vars = {}     # 环境变量
        
        # 不创建真实持久进程，而是记录状态
        # 每次执行命令时模拟在持久会话中的行为
    
    def get_prompt(self) -> str:
        """获取命令行提示符"""
        if sys.platform == "win32":
            return f"PS {self.current_dir}>"
        else:
            rel_path = self.current_dir.relative_to(self.workspace_dir)
            return f"~/workspace/{rel_path}$"
    
    def get_status(self) -> Dict[str, Any]:
        """获取终端当前状态（用于显示给AI）"""
        return {
            "prompt": self.get_prompt(),
            "current_directory": str(self.current_dir),
            "relative_path": str(self.current_dir.relative_to(self.workspace_dir)),
            "last_command": self.command_history[-1] if self.command_history else None,
            "last_output": self.last_output[:500],  # 最近输出的前500字符
            "command_count": len(self.command_history)
        }
    
    def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """在终端中执行命令
        
        Args:
            command: 要执行的命令
            timeout: 超时时间（秒）
            
        Returns:
            执行结果
        """
        # 记录命令
        self.command_history.append({
            "command": command,
            "directory": str(self.current_dir),
            "timestamp": time.time()
        })
        
        try:
            # 检查是否是cd命令
            if command.strip().startswith('cd '):
                return self._handle_cd(command)
            
            # 检查是否是设置环境变量
            if '=' in command and not command.startswith('echo'):
                return self._handle_env_var(command)
            
            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.current_dir)
            )
            
            # 保存输出
            self.last_output = result.stdout
            self.last_error = result.stderr
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "current_directory": str(self.current_dir),
                "prompt": self.get_prompt()
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"命令执行超时（{timeout}秒）",
                "current_directory": str(self.current_dir),
                "prompt": self.get_prompt()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "current_directory": str(self.current_dir),
                "prompt": self.get_prompt()
            }
    
    def _handle_cd(self, command: str) -> Dict[str, Any]:
        """处理cd命令"""
        # 解析目标路径
        parts = command.strip().split(maxsplit=1)
        if len(parts) < 2:
            target = self.workspace_dir  # cd without args goes to root
        else:
            target_path = parts[1].strip()
            
            # 处理特殊路径
            if target_path == '..':
                target = self.current_dir.parent
            elif target_path == '.':
                target = self.current_dir
            elif target_path.startswith('/') or target_path.startswith('\\'):
                # 绝对路径（相对于workspace）
                target = self.workspace_dir / target_path.lstrip('/\\')
            else:
                # 相对路径
                target = self.current_dir / target_path
        
        # 解析并验证路径
        try:
            target = target.resolve()
            
            # 确保在workspace内
            target.relative_to(self.workspace_dir)
            
            # 检查目录是否存在
            if not target.exists():
                return {
                    "success": False,
                    "error": f"目录不存在: {target.relative_to(self.workspace_dir)}",
                    "current_directory": str(self.current_dir),
                    "prompt": self.get_prompt()
                }
            
            if not target.is_dir():
                return {
                    "success": False,
                    "error": f"不是目录: {target.relative_to(self.workspace_dir)}",
                    "current_directory": str(self.current_dir),
                    "prompt": self.get_prompt()
                }
            
            # 切换目录
            old_dir = self.current_dir
            self.current_dir = target
            
            return {
                "success": True,
                "stdout": f"目录已切换: {old_dir.relative_to(self.workspace_dir)} → {self.current_dir.relative_to(self.workspace_dir)}",
                "stderr": "",
                "current_directory": str(self.current_dir),
                "prompt": self.get_prompt()
            }
            
        except ValueError:
            # 路径在workspace外
            return {
                "success": False,
                "error": "无法切换到工作空间外的目录",
                "current_directory": str(self.current_dir),
                "prompt": self.get_prompt()
            }
    
    def _handle_env_var(self, command: str) -> Dict[str, Any]:
        """处理环境变量设置（简化版）"""
        # TODO: 完整的环境变量支持
        return {
            "success": True,
            "stdout": "环境变量设置（暂不支持持久化）",
            "stderr": "",
            "current_directory": str(self.current_dir),
            "prompt": self.get_prompt()
        }
    
    def reset(self):
        """重置终端到初始状态"""
        self.current_dir = self.workspace_dir
        self.last_output = ""
        self.last_error = ""
        # 保留命令历史
