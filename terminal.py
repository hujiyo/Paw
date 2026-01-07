import os
import shutil
import subprocess
import time
import threading
import re
from pathlib import Path
from typing import Optional, Dict, Any
from queue import Queue, Empty
import sys

class ThreadedTerminal:
    """基于线程的终端管理器（替代 pexpect 方案）"""
    
    # 调试模式开关（设为 False 隐藏 DEBUG 输出）
    DEBUG = False
    
    def __init__(self, sandbox_dir: Path, shell_config: dict = None):
        self.sandbox_dir = sandbox_dir
        self.shell_config = shell_config or {}
        
        # 线程通信队列
        self.command_queue = Queue()  # 主线程 -> 工作线程
        self.result_queue = Queue()   # 工作线程 -> 主线程
        
        # 状态管理
        self.is_running = False
        self.worker_thread = None
        
        # 输出缓冲（按字节长度限制，以整行为单位截断）
        self.output_buffer = []
        # 从配置读取缓冲区大小（KB），默认24KB，范围4-64KB
        buffer_size_kb = self.shell_config.get('buffer_size', 24)
        buffer_size_kb = max(4, min(64, buffer_size_kb))  # 限制范围
        self.max_buffer_size = buffer_size_kb * 1024  # 转换为字节
        self.lock = threading.Lock()
        
        # 控制信号
        self._stop_flag = False
    
    def _debug(self, msg: str):
        """调试输出（仅在 DEBUG=True 时显示）"""
        if self.DEBUG:
            print(f"[DEBUG]{msg}")
    
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
            
            # 等待终端输出稳定（表示终端真正就绪）
            # 策略：如果连续 0.3 秒没有新输出，认为终端已就绪
            stable_timeout = 3  # 最多等待 3 秒
            stable_duration = 0.3  # 输出稳定时间
            stable_start = time.time()
            last_output = ""
            last_change_time = time.time()
            
            while (time.time() - stable_start) < stable_timeout:
                current_output = self.get_screen_snapshot()
                if current_output != last_output:
                    # 有新输出，重置稳定计时
                    last_output = current_output
                    last_change_time = time.time()
                elif current_output and (time.time() - last_change_time) >= stable_duration:
                    # 输出已稳定且非空，终端就绪
                    break
                time.sleep(0.05)
            
            shell_type = self.shell_config.get('shell', 'powershell')
            return {
                "success": True,
                "message": f"{shell_type.upper()} 终端已就绪",
                "type": "threaded",
                "screen": self.get_screen_snapshot()  # 返回当前屏幕内容
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"启动线程终端失败: {e}",
                "stderr": f"启动线程终端失败: {e}"
            }
    
    def enqueue_command(self, command: str, wait_output: float = 0.5) -> Dict[str, Any]:
        """发送命令到终端
        
        Args:
            command: 要执行的命令
            wait_output: 发送命令后等待输出的时间（秒），默认0.5秒
        """
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
            
            # 等待一小段时间让命令输出产生
            # 这样下一次 LLM 调用时，shell chunk 就能包含命令输出
            if wait_output > 0:
                time.sleep(wait_output)
            
            return {
                "success": True,
                "mode": "threaded_shell",
                "queued_command": command,
                "message": f"命令已发送: {command}",
                "note": "终端输出将自动显示在上下文的[当前终端屏幕]区域"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"发送命令失败: {e}",
                "stderr": f"发送命令失败: {e}"
            }
    
    def _remove_ansi_codes(self, text: str) -> str:
        """去除 ANSI 颜色控制码"""
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def get_screen_snapshot(self) -> str:
        """获取终端屏幕快照（不清空缓冲区）
        
        返回缓冲区内容，模拟真实终端屏幕。
        会自动去除 ANSI 颜色代码，避免影响上下文显示。
        """
        with self.lock:
            if not self.output_buffer:
                return ""
            raw_output = ''.join(self.output_buffer)
            return self._remove_ansi_codes(raw_output)
    
    def _trim_buffer_by_size(self):
        """按字节长度限制缓冲区，以整行为单位截断
        
        当缓冲区总长度超过 max_buffer_size 时，从头部删除整行，
        直到总长度不超过限制。
        注意：此方法应在持有 self.lock 的情况下调用。
        """
        # 计算当前缓冲区总字节数
        total_size = sum(len(line.encode('utf-8')) for line in self.output_buffer)
        
        # 如果超过限制，从头部删除整行
        while total_size > self.max_buffer_size and len(self.output_buffer) > 1:
            removed_line = self.output_buffer.pop(0)
            total_size -= len(removed_line.encode('utf-8'))
    
    def _worker_loop(self):
        """工作线程：管理终端进程和命令执行"""
        shell_cmd = self._get_shell_cmd()
        
        try:
            self._debug(f" 工作线程启动，命令: {' '.join(shell_cmd)}")
            
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
            
            self._debug(f" 终端进程已启动，PID: {self.process.pid}")
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
                        self._debug(f" 执行命令: {command}")
                        
                        # 在 shell 中执行命令
                        self._execute_command_with_timeout(command)
                        
                    elif message["type"] == "interrupt":
                        # 处理中断信号
                        self._interrupt_current_command()
                        
                except Empty:
                    continue  # 没有新命令，继续循环
                except Exception as e:
                    self._debug(f" 命令处理错误: {e}")
                    break
            
            self._debug(" 工作线程结束")
            
        except Exception as e:
            self._debug(f" 工作线程异常: {e}")
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
            self._debug(f" 命令执行错误: {e}")
    
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
                        
                self._debug(" 已发送中断信号")
                
        except Exception as e:
            self._debug(f" 中断命令失败: {e}")
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
        """输出读取线程
        
        持续读取终端输出，按字节长度限制缓冲区，以整行为单位截断。
        使用逐字符读取以确保不带换行符的提示符也能被及时读取。
        """
        try:
            current_line = []
            while not self._stop_flag and self.is_running:
                if not hasattr(self, 'process') or not self.process.stdout:
                    break
                
                # 逐字符读取
                try:
                    char = self.process.stdout.read(1)
                    if char:
                        current_line.append(char)
                        
                        # 如果遇到换行符，或者累积了一定长度，就更新到 buffer
                        if char == '\n' or len(current_line) > 0:
                            with self.lock:
                                # 将当前行内容更新到 buffer 的最后一行
                                line_content = ''.join(current_line)
                                
                                if self.output_buffer and not self.output_buffer[-1].endswith('\n'):
                                    # 如果 buffer 最后一行没结束，追加到最后一行
                                    self.output_buffer[-1] += line_content
                                else:
                                    # 否则作为新行添加
                                    self.output_buffer.append(line_content)
                                
                                # 如果当前字符是换行，重置 current_line
                                if char == '\n':
                                    current_line = []
                                else:
                                    # 如果不是换行，清空 current_line (因为已经追加到 buffer 了)
                                    # 注意：这里为了避免频繁锁操作，可以优化，但为了实时性先这样
                                    current_line = []
                                
                                # 按字节长度限制缓冲区，以整行为单位截断
                                self._trim_buffer_by_size()
                    else:
                        # 进程可能结束了
                        if self.process.poll() is not None:
                            break
                        time.sleep(0.01)
                        
                except Exception as e:
                    self._debug(f" 输出读取错误: {e}")
                    break
                    
        except Exception as e:
            self._debug(f" 输出读取线程异常: {e}")
    
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
        self._debug(" 终端已关闭")
