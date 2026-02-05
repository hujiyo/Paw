"""
工具执行器 - 单线程隔离模式

所有工具在专用线程中执行，与主事件循环隔离。
参考 ThreadedTerminal 的设计模式。
"""

import asyncio
import threading
import time
from typing import Dict, Any, Callable, Optional
from queue import Queue, Empty


class ToolExecutor:
    """
    工具执行器 - 单线程隔离模式

    所有工具在专用线程中执行，与主事件循环隔离，实现风险隔离和超时保护。
    """

    def __init__(self, timeout: float = 30.0):
        """
        初始化工具执行器

        Args:
            timeout: 默认超时时间（秒），单个工具执行的最长时间
        """
        # 通信队列（设置 maxsize 防止内存泄漏）
        self.command_queue = Queue(maxsize=100)  # 主线程 -> 工作线程 (工具执行请求)
        self.result_queue = Queue(maxsize=100)   # 工作线程 -> 主线程 (执行结果)

        # 线程管理
        self.worker_thread: Optional[threading.Thread] = None
        self.is_running = False

        # 配置
        self.timeout = timeout
        self._stop_flag = False

        # 工具处理器获取函数（延迟设置）
        self._tool_handler_getter: Optional[Callable[[str], Callable]] = None

        # 任务事件字典（用于 asyncio.Event 等待机制）
        self._task_events: Dict[str, threading.Event] = {}
        self._events_lock = threading.Lock()

    def set_tool_handler_getter(self, getter: Callable[[str], Callable]):
        """
        设置工具处理器获取函数

        Args:
            getter: 函数签名为 (tool_name: str) -> Callable，返回工具的处理函数
        """
        self._tool_handler_getter = getter

    def start(self):
        """启动工作线程"""
        if self.is_running:
            return

        self._stop_flag = False
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name="ToolExecutorThread",
            daemon=True
        )
        self.worker_thread.start()

        # 等待线程启动
        timeout = 2
        start_time = time.time()
        while not self.is_running and (time.time() - start_time) < timeout:
            time.sleep(0.01)

        if not self.is_running:
            raise RuntimeError("ToolExecutor thread failed to start")

    def stop(self):
        """停止工作线程"""
        self._stop_flag = True

        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)

        self.is_running = False

    def _worker_loop(self):
        """工作线程主循环"""
        self.is_running = True

        try:
            while not self._stop_flag:
                try:
                    # 非阻塞获取任务（超时 0.1 秒）
                    message = self.command_queue.get(timeout=0.1)

                    if message["type"] == "execute_tool":
                        self._execute_tool_in_thread(message)

                except Empty:
                    continue
                except Exception as e:
                    # 捕获工作线程异常，返回给主线程
                    task_id = message.get("task_id", "unknown")
                    self.result_queue.put({
                        "type": "error",
                        "task_id": task_id,
                        "error": f"Worker thread error: {e}"
                    })

        except Exception as e:
            # 工作线程崩溃
            self.result_queue.put({
                "type": "fatal_error",
                "error": f"Worker thread crashed: {e}"
            })

        finally:
            self.is_running = False

    def _execute_tool_in_thread(self, message: dict):
        """
        在工作线程中执行工具

        Args:
            message: {
                "type": "execute_tool",
                "task_id": str,
                "tool_name": str,
                "args": dict,
                "timeout": float
            }
        """
        task_id = message["task_id"]
        tool_name = message["tool_name"]
        args = message["args"]
        timeout = message.get("timeout", self.timeout)

        try:
            # 获取工具处理器
            if not self._tool_handler_getter:
                raise RuntimeError("Tool handler getter not set")

            handler = self._tool_handler_getter(tool_name)
            if handler is None:
                raise ValueError(f"Tool '{tool_name}' not found or not registered")

            # 检查是否为异步工具（协程函数）
            import inspect
            if asyncio.iscoroutinefunction(handler):
                # 异步工具：标记为 async_task，返回主线程执行
                # 避免协程跨线程传递导致事件循环绑定问题
                self.result_queue.put({
                    "type": "async_task",
                    "task_id": task_id,
                    "tool_name": tool_name,
                    "args": args
                })
                return

            # 执行工具（带超时保护）
            start_time = time.time()

            # 调用同步工具处理函数
            result = handler(**args)

            elapsed = time.time() - start_time

            # 超时检查
            if elapsed > timeout:
                raise TimeoutError(f"Tool execution exceeded {timeout}s limit (took {elapsed:.2f}s)")

            # 返回成功结果
            self.result_queue.put({
                "type": "success",
                "task_id": task_id,
                "result": result,
                "elapsed": elapsed
            })

            # 触发事件通知
            self._notify_task_complete(task_id)

        except TimeoutError as e:
            self.result_queue.put({
                "type": "timeout",
                "task_id": task_id,
                "error": str(e)
            })
            self._notify_task_complete(task_id)

        except Exception as e:
            self.result_queue.put({
                "type": "error",
                "task_id": task_id,
                "error": str(e),
                "error_type": type(e).__name__
            })
            self._notify_task_complete(task_id)

    def _notify_task_complete(self, task_id: str):
        """通知任务完成（触发事件）"""
        with self._events_lock:
            if task_id in self._task_events:
                self._task_events[task_id].set()
                del self._task_events[task_id]

    def register_task_event(self, task_id: str) -> threading.Event:
        """注册任务事件，用于等待任务完成"""
        event = threading.Event()
        with self._events_lock:
            self._task_events[task_id] = event
        return event
