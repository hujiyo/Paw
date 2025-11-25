import os
import shutil
import subprocess
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from queue import Queue, Empty
import sys

class ThreadedTerminal:
    """基于线程的终端管理器（替代 pexpect 方案）"""
    
    def __init__(self, sandbox_dir: Path, shell_config: dict = None):
        self.sandbox_dir = sandbox_dir
        self.shell_config = shell_config or {}
        
        # 线程通信队列
        self.command_queue = Queue()  # 主线程 -> 工作线程
        self.result_queue = Queue()   # 工作线程 -> 主线程
        
        # 状态管理
        self.is_running = False
        self.worker_thread = None
        
        # 输出缓冲
        self.output_buffer = []
        self.lock = threading.Lock()
        
        # 控制信号
        self._stop_flag = False
    
    def _get_shell_cmd(self) -> list:
        """获取 Shell 命令"""
        shell_type = self.shell_config.get('shell', 'powershell').lower()
        
        if shell_type == 'cmd':
            return self._get_cmd_command()
        else:  # 默认 powershell
            return self._get_powershell_command()
    
    def _get_powershell_command(self) -> list:
        """获取 PowerShell 命令"""
        candidates = [
            shutil.which("pwsh"),  # PowerShell Core
            shutil.which("powershell"),  # Windows PowerShell
            os.path.join(os.environ.get("SystemRoot", "C:/Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        ]
        for path in candidates:
            if path and Path(path).exists():
                return [path, "-NoLogo", "-NoExit"]
        return ["powershell.exe", "-NoLogo", "-NoExit"]
    
    def _get_cmd_command(self) -> list:
        """获取 CMD 命令"""
        cmd_path = os.path.join(os.environ.get("SystemRoot", "C:/Windows"), "System32", "cmd.exe")
        if Path(cmd_path).exists():
            return [cmd_path]
        return ["cmd.exe"]
    
    def is_shell_open(self) -> bool:
        """检查终端是否打开"""
        return self.is_running and self.worker_thread and self.worker_thread.is_alive()
    
    def open_shell(self) -> Dict[str, Any]:
        """启动终端"""
        if os.name != "nt":
            return {
                "success": False,
                "error": "仅在 Windows 平台上支持线程终端",
                "stderr": "仅在 Windows 平台上支持线程终端"
            }
        
        if self.is_shell_open():
            return {
                "success": True,
                "message": "终端已在运行",
                "type": "threaded"
            }
        
        try:
            self._stop_flag = False
            self.output_buffer.clear()
            
            # 启动工作线程
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            
            # 等待终端启动完成
            timeout = 5
            start_time = time.time()
            while not self.is_shell_open() and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if not self.is_shell_open():
                return {
                    "success": False,
                    "error": "终端启动超时",
                    "stderr": "终端启动超时"
                }
            
            shell_type = self.shell_config.get('shell', 'powershell')
            return {
                "success": True,
                "message": f"{shell_type.upper()} 线程终端已启动",
                "type": "threaded"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"启动线程终端失败: {e}",
                "stderr": f"启动线程终端失败: {e}"
            }
    
    def enqueue_command(self, command: str) -> Dict[str, Any]:
        """发送命令到终端"""
        if not self.is_shell_open():
            return {
                "success": False,
                "error": "终端尚未启动，请先调用 open_shell",
                "stderr": "终端尚未启动，请先调用 open_shell"
            }
        
        try:
            # 发送命令到工作线程
            self.command_queue.put({
                "type": "command",
                "command": command
            }, timeout=1)
            
            return {
                "success": True,
                "mode": "threaded_shell",
                "queued_command": command,
                "message": f"命令已发送: {command}",
                "stdout": f"命令已发送: {command}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"发送命令失败: {e}",
                "stderr": f"发送命令失败: {e}"
            }
    
    def peek_output(self) -> Dict[str, Any]:
        """读取终端输出"""
        if not self.is_shell_open():
            return {
                "success": False,
                "error": "终端尚未启动",
                "stderr": "终端尚未启动"
            }
        
        with self.lock:
            if not self.output_buffer:
                return {
                    "success": True,
                    "stdout": "",
                    "message": "没有新的终端输出"
                }
            
            # 取出所有缓冲输出并清空
            output = ''.join(self.output_buffer)
            self.output_buffer.clear()
        
        return {
            "success": True,
            "stdout": output
        }
    
    def _worker_loop(self):
        """工作线程：管理终端进程和命令执行"""
        shell_cmd = self._get_shell_cmd()
        
        try:
            print(f"[DEBUG] 工作线程启动，命令: {' '.join(shell_cmd)}")
            
            # 启动终端进程（作为交互式 shell）
            self.process = subprocess.Popen(
                shell_cmd,
                cwd=str(self.sandbox_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并 stdout 和 stderr
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )
            
            print(f"[DEBUG] 终端进程已启动，PID: {self.process.pid}")
            self.is_running = True
            
            # 启动输出读取线程
            output_thread = threading.Thread(target=self._read_output_loop, daemon=True)
            output_thread.start()
            
            # 主循环：处理命令
            while not self._stop_flag and self.process.poll() is None:
                try:
                    # 非阻塞获取命令（超时 0.1 秒）
                    message = self.command_queue.get(timeout=0.1)
                    
                    if message["type"] == "command":
                        command = message["command"]
                        print(f"[DEBUG] 执行命令: {command}")
                        
                        # 在 shell 中执行命令
                        self._execute_command_with_timeout(command)
                        
                    elif message["type"] == "interrupt":
                        # 处理中断信号
                        self._interrupt_current_command()
                        
                except Empty:
                    continue  # 没有新命令，继续循环
                except Exception as e:
                    print(f"[DEBUG] 命令处理错误: {e}")
                    break
            
            print("[DEBUG] 工作线程结束")
            
        except Exception as e:
            print(f"[DEBUG] 工作线程异常: {e}")
            self.result_queue.put({
                "type": "error",
                "error": str(e)
            })
        finally:
            self.is_running = False
            self._cleanup_processes()
    
    def _execute_command_with_timeout(self, command: str):
        """在 shell 中执行命令"""
        try:
            # 在 shell 中执行命令（通过 stdin 发送）
            if self.process and self.process.stdin:
                # 发送命令到 shell
                self.process.stdin.write(command + '\n')
                self.process.stdin.flush()
                
        except Exception as e:
            print(f"[DEBUG] 命令执行错误: {e}")
    
    def _interrupt_current_command(self):
        """中断当前正在执行的命令"""
        try:
            if self.process and self.process.poll() is None:
                # 发送 Ctrl+C 等效信号（向进程组发送 SIGINT）
                import signal
                if hasattr(signal, 'CTRL_C_EVENT'):  # Windows
                    # 在 Windows 上，发送 CTRL_C_EVENT 到进程组
                    try:
                        os.kill(self.process.pid, signal.CTRL_C_EVENT)
                    except:
                        # 如果失败，强制终止
                        self.process.terminate()
                else:
                    # Unix 系统
                    try:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
                    except:
                        self.process.terminate()
                        
                print("[DEBUG] 已发送中断信号")
                
        except Exception as e:
            print(f"[DEBUG] 中断命令失败: {e}")
            # 最后的手段：强制终止进程
            try:
                self.process.kill()
            except:
                pass
    
    def _cleanup_processes(self):
        """清理所有相关进程"""
        # 终止主 shell 进程
        if hasattr(self, 'process') and self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.write('exit\n')
                    self.process.stdin.flush()
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try:
                    self.process.kill()
                except:
                    pass
    
    def _read_output_loop(self):
        """输出读取线程"""
        try:
            while not self._stop_flag and self.is_running:
                if not hasattr(self, 'process') or not self.process.stdout:
                    break
                
                # 非阻塞读取
                try:
                    line = self.process.stdout.readline()
                    if line:
                        with self.lock:
                            self.output_buffer.append(line)
                    else:
                        # 没有更多输出，短暂等待
                        time.sleep(0.01)
                        
                except Exception as e:
                    print(f"[DEBUG] 输出读取错误: {e}")
                    break
                    
        except Exception as e:
            print(f"[DEBUG] 输出读取线程异常: {e}")
    
    def interrupt_command(self) -> Dict[str, Any]:
        """中断当前正在执行的命令"""
        if not self.is_shell_open():
            return {
                "success": False,
                "error": "终端尚未启动",
                "stderr": "终端尚未启动"
            }
        
        try:
            # 发送中断信号到工作线程
            self.command_queue.put({
                "type": "interrupt"
            }, timeout=1)
            
            return {
                "success": True,
                "message": "中断信号已发送",
                "stdout": "中断信号已发送"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"发送中断信号失败: {e}",
                "stderr": f"发送中断信号失败: {e}"
            }
    
    def close(self):
        """关闭终端"""
        self._stop_flag = True
        
        # 等待工作线程结束
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)
        
        # 清理进程（在 _cleanup_processes 中完成）
        print("[DEBUG] 终端已关闭")
