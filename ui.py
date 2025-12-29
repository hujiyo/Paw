#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UI系统 - Claude Code 风格重构版
极简、清晰、现代
"""

import os
import sys
import json
import re
import shutil
from datetime import datetime
from typing import Optional, Dict, List, Any
from colorama import init, Fore, Back, Style

# 实时键盘输入支持
if sys.platform == "win32":
    import msvcrt
else:
    import tty
    import termios

# 初始化colorama
init(autoreset=True)

class UI:
    """
    现代极简UI系统
    统一的用户界面层，负责所有终端 I/O 操作
    """

    # 极简配色方案
    COLORS = {
        'reset': Style.RESET_ALL,
        'dim': Style.DIM,
        'bright': Style.BRIGHT,
        
        # 角色标识
        'user_label': Fore.BLACK + Back.CYAN + Style.BRIGHT,      # 用户标签改为青底黑字，更醒目
        'assistant_label': Fore.WHITE + Back.MAGENTA + Style.BRIGHT,
        'system_label': Fore.WHITE + Back.BLACK + Style.BRIGHT,
        'tool_label': Fore.BLACK + Back.WHITE,
        
        # 文本颜色
        'user_text': Fore.CYAN + Style.BRIGHT,     # 用户文字改为亮青色
        'assistant_text': "\033[38;5;210m",        # AI文字改为橘粉色 (210)
        'dim_text': Fore.LIGHTBLACK_EX,
        
        # 状态颜色
        'success': Fore.GREEN,
        'error': Fore.RED,
        'warning': Fore.YELLOW,
        'info': Fore.BLUE,
        
        # 兼容旧版键名
        'user': Fore.WHITE + Style.BRIGHT,
        'assistant': Fore.WHITE,
        'system': Fore.CYAN,
        'tool_name': Fore.CYAN,
        'tool_args': Fore.LIGHTBLACK_EX,
        'tool_success': Fore.GREEN,
        'tool_error': Fore.RED,
        'status_error': Fore.RED,
        'border': Fore.LIGHTBLACK_EX,
        'timestamp': Fore.LIGHTBLACK_EX,
        'debug': Fore.LIGHTBLACK_EX,
        'accent': Fore.MAGENTA,
    }

    # 极简图标
    ICONS = {
        'arrow_right': '›',
        'arrow_left': '‹',
        'bullet': '•',
        'check': '✓',
        'cross': '✗',
        'info': 'i',
        'warning': '!',
        'error': '!',
        'loading': '⟳',
        'tool': 'ƒ',
        'dot': '·',
        'done': '✓',
    }

    # UI 固定宽度（不跟随终端大小变化）
    WIDTH = 80
    
    # 内容区域宽度（左右各留 2 字符边距）
    CONTENT_WIDTH = 76
    
    # 工具结果最大宽度
    TOOL_RESULT_WIDTH = 60

    def __init__(self, minimal_mode: bool = False):
        self.minimal_mode = minimal_mode
        self.start_time = datetime.now()
        self.performance_data = {
            'last_response_time': 0,
            'total_tokens': 0,
            'tool_calls': 0,
            'errors': 0
        }
        # 获取终端实际尺寸（仅用于参考）
        try:
            self._terminal_width = shutil.get_terminal_size().columns
            self._terminal_height = shutil.get_terminal_size().lines
        except:
            self._terminal_width = 80
            self._terminal_height = 24
        
        # 当前行号跟踪（用于 gotoxy 定位）
        self._current_row = 1
        
        # 主屏幕对话区域起始行号（logo 和状态栏之后）
        # 用于编辑后重新渲染对话历史
        self._conversation_start_row = 1

    def clear_screen(self):
        """清屏并复位光标"""
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
    
    def enter_alternate_screen(self):
        """进入备用屏幕缓冲区（用于临时界面，如编辑器、模型选择等）
        
        退出后会自动恢复到原来的主屏幕内容，就像 vim/htop 那样
        """
        sys.stdout.write("\033[?1049h")  # 切换到备用屏幕
        sys.stdout.write("\033[2J\033[H")  # 清屏并移动光标到左上角
        sys.stdout.flush()
    
    def leave_alternate_screen(self):
        """离开备用屏幕缓冲区，恢复主屏幕"""
        sys.stdout.write("\033[?1049l")  # 返回主屏幕
        sys.stdout.flush()
    
    def clear_from_row(self, row: int):
        """清除从指定行到屏幕底部的所有内容
        
        Args:
            row: 起始行号 (1-based)
        """
        self.move_cursor(row, 1)
        sys.stdout.write("\033[J")  # 清除从光标到屏幕底部
        sys.stdout.flush()
    
    def scroll_up(self, lines: int = 1):
        """向上滚动屏幕"""
        sys.stdout.write(f"\033[{lines}S")
        sys.stdout.flush()
    
    def get_cursor_position(self) -> tuple:
        """获取当前光标位置
        
        Returns:
            (row, col) 元组，1-based
        """
        # 发送查询序列
        sys.stdout.write("\033[6n")
        sys.stdout.flush()
        
        # 读取响应（格式: ESC[row;colR）
        if sys.platform == "win32":
            import msvcrt
            response = ""
            while True:
                ch = msvcrt.getwch()
                response += ch
                if ch == 'R':
                    break
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                response = ""
                while True:
                    ch = sys.stdin.read(1)
                    response += ch
                    if ch == 'R':
                        break
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        
        # 解析响应
        try:
            # 格式: \x1b[row;colR
            match = re.search(r'\[(\d+);(\d+)R', response)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        except:
            pass
        return (1, 1)
    
    def mark_conversation_start(self):
        """标记对话区域的起始位置（在 logo 和状态栏之后调用）"""
        row, _ = self.get_cursor_position()
        self._conversation_start_row = row
    
    def get_conversation_start_row(self) -> int:
        """获取对话区域的起始行号"""
        return self._conversation_start_row

    def move_cursor(self, row: int, col: int):
        """移动光标到指定位置 (1-based)"""
        sys.stdout.write(f"\033[{row};{col}H")
        sys.stdout.flush()

    def clear_line(self):
        """清除当前行"""
        sys.stdout.write("\033[2K\r")
        sys.stdout.flush()

    def save_cursor(self):
        """保存当前光标位置"""
        sys.stdout.write("\033[s")
        sys.stdout.flush()

    def restore_cursor(self):
        """恢复光标位置"""
        sys.stdout.write("\033[u")
        sys.stdout.flush()
        
    def hide_cursor(self):
        """隐藏光标"""
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
        
    def show_cursor(self):
        """显示光标"""
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    # ==================== 文本处理工具 ====================
    
    def truncate(self, text: str, max_width: int = None, suffix: str = "...") -> str:
        """截断文本到指定宽度"""
        if max_width is None:
            max_width = self.CONTENT_WIDTH
        if len(text) <= max_width:
            return text
        return text[:max_width - len(suffix)] + suffix
    
    def wrap_text(self, text: str, width: int = None, indent: int = 0) -> List[str]:
        """将文本按宽度换行，返回行列表"""
        if width is None:
            width = self.CONTENT_WIDTH
        
        lines = []
        indent_str = " " * indent
        effective_width = width - indent
        
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append("")
                continue
            
            # 简单按宽度切分
            while len(paragraph) > effective_width:
                # 尝试在空格处断行
                break_point = paragraph.rfind(' ', 0, effective_width)
                if break_point == -1:
                    break_point = effective_width
                lines.append(indent_str + paragraph[:break_point])
                paragraph = paragraph[break_point:].lstrip()
            if paragraph:
                lines.append(indent_str + paragraph)
        
        return lines
    
    def center_text(self, text: str, width: int = None, fill_char: str = " ") -> str:
        """居中文本"""
        if width is None:
            width = self.WIDTH
        padding = (width - len(text)) // 2
        if padding < 0:
            return text[:width]
        return fill_char * padding + text + fill_char * padding
    
    def right_align(self, text: str, width: int = None) -> str:
        """右对齐文本"""
        if width is None:
            width = self.WIDTH
        if len(text) >= width:
            return text[:width]
        return " " * (width - len(text)) + text
    
    def draw_line(self, char: str = "─", width: int = None) -> str:
        """绘制水平线"""
        if width is None:
            width = self.WIDTH
        return char * width
    
    def print_at(self, row: int, col: int, text: str):
        """在指定位置打印文本"""
        self.move_cursor(row, col)
        # 确保不超出 80 列
        available = self.WIDTH - col + 1
        if len(text) > available:
            text = text[:available]
        sys.stdout.write(text)
        sys.stdout.flush()
    
    def print_line_at(self, row: int, text: str, align: str = "left"):
        """在指定行打印一整行文本"""
        self.move_cursor(row, 1)
        self.clear_line()
        
        # 截断到 80 列
        if len(text) > self.WIDTH:
            text = self.truncate(text, self.WIDTH)
        
        if align == "center":
            text = self.center_text(text)
        elif align == "right":
            text = self.right_align(text)
        
        sys.stdout.write(text)
        sys.stdout.flush()

    def print_overwrite(self, text: str):
        """覆盖当前行打印"""
        self.clear_line()
        sys.stdout.write(f"\r{text}")
        sys.stdout.flush()

    def show_tool_start(self, tool_call_id: str, tool_name: str, args_str: str):
        """显示工具开始执行"""
        # 计算可用宽度：80 - 2(缩进) - 2(图标+空格) - len(tool_name) - 1(空格)
        max_args_width = self.WIDTH - 5 - len(tool_name)
        if len(args_str) > max_args_width:
            args_str = args_str[:max_args_width - 3] + "..."
        
        # 显示加载中状态：○ tool_name args
        circle = f"{self.COLORS['dim']}○{Style.RESET_ALL}"
        text = f"{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL} {self.COLORS['tool_args']}{args_str}{Style.RESET_ALL}"
        self.print_overwrite(text)

    def show_tool_result(self, tool_call_id: str, tool_name: str, display: dict, success: bool = True):
        """显示工具执行结果 - Claude Code 风格
        
        Args:
            tool_name: 工具名称
            display: 显示信息字典 {'line1': str, 'line2': str, 'has_line2': bool, 'is_command': bool}
            success: 是否成功
        """
        self.clear_line()
        
        line1 = display.get('line1', '')
        line2 = display.get('line2', '')
        has_line2 = display.get('has_line2', False)
        is_command = display.get('is_command', False)
        
        # 第一行可用宽度：80 - 2(图标+空格) - len(tool_name) - 1(空格)
        max_line1_width = self.WIDTH - 3 - len(tool_name)
        if len(line1) > max_line1_width:
            line1 = line1[:max_line1_width - 3] + "..."
        
        # 第二行可用宽度：80 - 6(缩进 "    ⎿ ")
        max_line2_width = self.WIDTH - 6
        
        if success:
            circle = f"{self.COLORS['success']}●{Style.RESET_ALL}"
            # run_command 特殊处理：~$ 用红色
            if is_command:
                prompt_style = f"{self.COLORS['error']}~${Style.RESET_ALL}"
                sys.stdout.write(f"\r{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL} {prompt_style} {self.COLORS['dim']}{line1}{Style.RESET_ALL}\n")
            else:
                sys.stdout.write(f"\r{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL} {self.COLORS['dim']}{line1}{Style.RESET_ALL}\n")
            if has_line2 and line2:
                # 支持多行显示
                sub_lines = line2.split('\n')
                for i, sub_line in enumerate(sub_lines):
                    # 如果行以 │ 开头，保留原样（用于连接线）
                    if sub_line.startswith('│'):
                        if len(sub_line) > max_line2_width:
                            sub_line = sub_line[:max_line2_width - 3] + "..."
                        sys.stdout.write(f"    {self.COLORS['dim']}{sub_line}{Style.RESET_ALL}\n")
                    else:
                        if len(sub_line) > max_line2_width:
                            sub_line = sub_line[:max_line2_width - 3] + "..."
                        sys.stdout.write(f"    {self.COLORS['dim']}⎿ {sub_line}{Style.RESET_ALL}\n")
        else:
            circle = f"{self.COLORS['error']}●{Style.RESET_ALL}"
            sys.stdout.write(f"\r{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL}\n")
            error_text = line1 if line1 else "未知错误"
            if len(error_text) > max_line2_width:
                error_text = error_text[:max_line2_width - 3] + "..."
            sys.stdout.write(f"    {self.COLORS['dim']}⎿ {self.COLORS['error']}{error_text}{Style.RESET_ALL}\n")
        sys.stdout.flush()

    def _pad(self, text: str, width: int = 0) -> str:
        return text

    def get_timestamp(self) -> str:
        return datetime.now().strftime("%H:%M")

    def format_message_header(self, role: str, content: Optional[str] = None) -> str:
        """格式化消息头部 - 徽章风格"""
        timestamp = f"{self.COLORS['dim']}{self.get_timestamp()}{Style.RESET_ALL}"
        
        if role == 'user':
            badge = f"{self.COLORS['user_label']} USER {Style.RESET_ALL}"
            return f"\n{badge} "
        elif role == 'assistant':
            badge = f"{self.COLORS['assistant_label']} PAW  {Style.RESET_ALL}"
            return f"\n{badge} "
        elif role == 'system':
            badge = f"{self.COLORS['system_label']} SYS  {Style.RESET_ALL}"
            return f"\n{badge} "
        elif role == 'tool':
            badge = f"{self.COLORS['tool_label']} TOOL {Style.RESET_ALL}"
            return f"{badge} "
        else:
            return f"\n[{role.upper()}]"

    def format_tool_call(self, tool_name: str, args: Dict[str, Any]) -> str:
        """格式化工具调用 - 代码行风格"""
        # 计算参数可用宽度：80 - 4(缩进+图标) - len(tool_name) - 1(空格)
        max_args_width = self.WIDTH - 5 - len(tool_name)
        
        args_str = ""
        if args:
            items = []
            for k, v in args.items():
                v_str = str(v)
                if len(v_str) > 30:
                    v_str = v_str[:27] + "..."
                items.append(f"{k}={v_str}")
            args_str = " ".join(items)
            # 截断参数字符串
            if len(args_str) > max_args_width:
                args_str = args_str[:max_args_width - 3] + "..."
            
        prefix = f"{self.COLORS['dim']}⟳{Style.RESET_ALL}"
        name = f"{self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL}"
        params = f"{self.COLORS['tool_args']}{args_str}{Style.RESET_ALL}"
        
        return f"  {prefix} {name} {params}"

    def format_tool_result(self, tool_name: str, result: str, success: bool = True) -> str:
        """格式化工具结果 - 简洁状态"""
        # 结果最大宽度：80 - 4(缩进+图标)
        max_width = self.WIDTH - 4
        
        if success:
            icon = f"{self.COLORS['success']}✓{Style.RESET_ALL}"
            clean_result = result.strip().replace('\n', ' ↵ ')
            if len(clean_result) > max_width:
                clean_result = clean_result[:max_width - 3] + "..."
            text = f"{self.COLORS['dim']}{clean_result}{Style.RESET_ALL}"
            return f"  {icon} {text}"
        else:
            error_text = result
            if len(error_text) > max_width:
                error_text = error_text[:max_width - 3] + "..."
            icon = f"{self.COLORS['error']}✗{Style.RESET_ALL}"
            return f"  {icon} {self.COLORS['error']}{error_text}{Style.RESET_ALL}"

    def format_status_bar(self, extra_info: Optional[Dict] = None) -> str:
        """极其简约的状态栏，仅作为分割线上的信息"""
        if self.minimal_mode:
            return ""

        parts = []

        if extra_info:
            if 'model' in extra_info:
                parts.append(f"model: {extra_info['model']}")
            if 'autostatus' in extra_info:
                status = extra_info['autostatus']
                if isinstance(status, dict):
                    mode = status.get('execution_mode', 'unknown')
                    parts.append(f"mode: {mode}")

        if self.performance_data['tool_calls'] > 0:
            parts.append(f"tools: {self.performance_data['tool_calls']}")

        info_str = " · ".join(parts)

        # 灰色分割线，中间嵌信息（固定 80 列）
        text_len = len(info_str) + 2
        padding = (self.WIDTH - text_len) // 2
        if padding < 0: padding = 0
        right_padding = self.WIDTH - padding - text_len
        if right_padding < 0: right_padding = 0

        bar = f"{self.COLORS['dim']}{'─' * padding} {info_str} {'─' * right_padding}{Style.RESET_ALL}"
        return f"\n{bar}\n"

    def format_separator(self, char: str = '─', length: int = None) -> str:
        """绘制分隔线（默认 80 列）"""
        if length is None:
            length = self.WIDTH
        return f"{self.COLORS['dim']}{char * length}{Style.RESET_ALL}"

    def format_debug_info(self, info: Dict[str, Any]) -> str:
        if self.minimal_mode:
            return ""
        
        lines = [f"\n{self.COLORS['dim']}--- Debug Info ---{Style.RESET_ALL}"]
        for k, v in info.items():
            lines.append(f"{self.COLORS['dim']}{k}: {v}{Style.RESET_ALL}")
        return "\n".join(lines)

    def format_error(self, error: str, context: Optional[str] = None) -> str:
        return f"\n{self.COLORS['error']}Error: {error}{Style.RESET_ALL}"

    def update_performance(self, response_time: float = None, tokens: int = None, tool_call: bool = False, error: bool = False):
        if response_time: self.performance_data['last_response_time'] = response_time
        if tokens: self.performance_data['total_tokens'] += tokens
        if tool_call: self.performance_data['tool_calls'] += 1
        if error: self.performance_data['errors'] += 1

    # ASCII Art Logo
    LOGO = [
        "██████╗    █████╗   ██╗    ██╗",
        "██╔══██╗  ██╔══██╗  ██║ █╗ ██║",
        "██████╔╝  ███████║  ██║███╗██║",
        "██╔═══╝   ██╔══██║  ╚███╔███╔╝",
        "╚═╝       ╚═╝  ╚═╝   ╚══╝╚══╝ ",
    ]
    
    def print_welcome(self):
        """显示 ASCII Art Logo"""
        # 珊瑚橘粉色 (ANSI 256 色: 216 偏暖的珊瑚色)
        logo_color = "\033[38;5;210m"
        reset = Style.RESET_ALL
        
        print()
        for line in self.LOGO:
            # 居中显示每行
            print(f"{logo_color}{self.center_text(line)}{reset}")
        print(f"{self.COLORS['dim']}{self.center_text('Type exit to quit')}{reset}")
        print()

    def print_goodbye(self):
        """极简告别 - 80 列居中显示"""
        runtime = str(datetime.now() - self.start_time).split('.')[0]
        goodbye = f"Session ended. Runtime: {runtime}. Bye."
        print()
        print(f"{self.COLORS['dim']}{self.center_text(goodbye)}{Style.RESET_ALL}")

    # ==================== 输入方法 ====================

    async def get_user_input(self) -> str:
        """获取用户输入（带提示符）- 异步接口以兼容 WebUI"""
        header = self.format_message_header('user')
        prompt_style = self.COLORS['user_text']
        reset_style = self.COLORS['reset']
        user_input = input(f"{header}{prompt_style}").strip()
        print(reset_style, end='')  # 重置颜色
        return user_input

    def get_input(self, prompt: str) -> str:
        """获取用户输入（自定义提示符）"""
        styled_prompt = f"{self.COLORS['user_text']}{prompt}{self.COLORS['reset']}"
        return input(styled_prompt).strip()

    # ==================== 输出方法 ====================
    
    def print_text(self, text: str, wrap: bool = False):
        """打印普通文本"""
        if wrap and len(text) > self.WIDTH:
            for line in self.wrap_text(text):
                print(line)
        else:
            print(text)

    def print_dim(self, text: str, wrap: bool = False):
        """打印淡色文本"""
        if wrap and len(text) > self.WIDTH:
            for line in self.wrap_text(text):
                print(f"{self.COLORS['dim']}{line}{Style.RESET_ALL}")
        else:
            print(f"{self.COLORS['dim']}{text}{Style.RESET_ALL}")

    def print_system(self, text: str, wrap: bool = False):
        """打印系统消息"""
        if wrap and len(text) > self.WIDTH:
            for line in self.wrap_text(text):
                print(f"{self.COLORS['system']}{line}{Style.RESET_ALL}")
        else:
            print(f"{self.COLORS['system']}{text}{Style.RESET_ALL}")

    def print_error(self, text: str):
        """打印错误消息"""
        # 错误消息截断而不是换行
        if len(text) > self.CONTENT_WIDTH:
            text = self.truncate(text, self.CONTENT_WIDTH)
        print(f"{self.COLORS['error']}{text}{Style.RESET_ALL}")

    def print_success(self, text: str):
        """打印成功消息"""
        if len(text) > self.CONTENT_WIDTH:
            text = self.truncate(text, self.CONTENT_WIDTH)
        print(f"{self.COLORS['success']}{text}{Style.RESET_ALL}")

    def print_assistant(self, text: str, end: str = '\n', flush: bool = False):
        """打印 AI 助手响应（支持流式输出）"""
        # 流式输出不截断，让终端自然换行
        print(f"{self.COLORS['assistant_text']}{text}{Style.RESET_ALL}", end=end, flush=flush)

    # ==================== 对话历史重渲染 ====================
    
    def refresh_conversation_history(self, chunks: List, model: str = None, autostatus: dict = None):
        """从对话起始位置重新渲染整个对话历史
        
        用于编辑对话后同步更新主屏幕显示
        
        Args:
            chunks: ChunkManager 的 chunks 列表
            model: 当前模型名称（用于状态栏）
            autostatus: AutoStatus 状态（用于状态栏）
        """
        from chunk_system import ChunkType
        
        # 移动到对话起始位置并清除之后的所有内容
        self.clear_from_row(self._conversation_start_row)
        
        # 重新渲染每个 chunk（保持与原始打印一致的格式）
        for chunk in chunks:
            if chunk.chunk_type == ChunkType.USER:
                # 用户消息：带 USER 徽章
                header = self.format_message_header('user')
                print(f"{header}{self.COLORS['user_text']}{chunk.content}{Style.RESET_ALL}")
                
            elif chunk.chunk_type == ChunkType.ASSISTANT:
                # AI 回复：直接打印内容，无徽章（与流式输出一致）
                print(f"{self.COLORS['assistant_text']}{chunk.content}{Style.RESET_ALL}")
                
            elif chunk.chunk_type == ChunkType.TOOL_CALL:
                # 工具调用
                content = chunk.content
                if ':' in content:
                    tool_name = content.split(':')[0].strip()
                else:
                    tool_name = content[:30] if len(content) > 30 else content
                circle = f"{self.COLORS['success']}●{Style.RESET_ALL}"
                print(f"{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL}")
                
            elif chunk.chunk_type == ChunkType.TOOL_RESULT:
                # 工具结果
                result_preview = chunk.content.replace('\n', ' ')[:50]
                if len(chunk.content) > 50:
                    result_preview += "..."
                print(f"    {self.COLORS['dim']}⎿ {result_preview}{Style.RESET_ALL}")

    # ==================== 启动设置界面 ====================

    def show_startup_screen(self, models: List[str], api_url: str = None) -> str:
        """显示启动设置界面（首次启动时，支持方向键导航）

        这是一个独立的设置界面，用户可以：
        - 选择模型（支持上下键导航）
        - 查看当前配置
        - 未来可扩展更多设置选项

        Args:
            models: 可用模型列表
            api_url: API 地址

        Returns:
            用户选择的模型名称
        """
        import os

        # 清屏（使用系统命令完全清空缓冲区）
        os.system('cls' if os.name == 'nt' else 'clear')

        # 如果没有模型，回退到手动输入
        if not models:
            self.print_system("未检测到可用模型，请手动输入模型名称")
            print()
            while True:
                model_name = self.get_input(f"{self.COLORS['user_text']}模型名称 (如 glm-4-flash): {Style.RESET_ALL}")
                if model_name:
                    return model_name
                self.print_error("模型名称不能为空")

        # 有模型，显示交互式选择界面
        current_index = 0

        while True:
            os.system('cls' if os.name == 'nt' else 'clear')

            # 显示欢迎标题
            print()
            title = "═══════════════════ Paw 启动设置 ═══════════════════"
            print(f"{self.COLORS['dim']}{self.center_text(title)}{Style.RESET_ALL}")
            print()

            # 显示 API 信息
            if api_url:
                api_display = api_url[:50] + "..." if len(api_url) > 50 else api_url
                print(f"{self.COLORS['dim']}{self.center_text(f'API: {api_display}')}{Style.RESET_ALL}")
                print()

            # 显示分隔线
            print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
            print()

            # 显示模型列表
            self.print_dim(f"检测到 {len(models)} 个可用模型:")
            print()

            max_model_width = self.WIDTH - 10
            for i, model in enumerate(models):
                if len(model) > max_model_width:
                    model = self.truncate(model, max_model_width)

                is_selected = (i == current_index)
                if is_selected:
                    marker = f"{Fore.CYAN}›{Style.RESET_ALL}"
                    line = f"  {marker} {self.COLORS['bright']}{i+1}.{Style.RESET_ALL} {self.COLORS['assistant_text']}{model}{Style.RESET_ALL}"
                else:
                    line = f"    {self.COLORS['dim']}{i+1}.{Style.RESET_ALL} {self.COLORS['dim']}{model}{Style.RESET_ALL}"

                print(line)

            print()
            print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
            print()

            # 显示操作提示
            hint = "↑↓ 选择  │  Enter 确认"
            print(f"{self.COLORS['dim']}{self.center_text(hint)}{Style.RESET_ALL}")
            print()

            # 显示当前选中项
            print(f"{self.COLORS['user_text']}当前选择: {models[current_index]}{Style.RESET_ALL}", end='', flush=True)

            # 获取按键
            try:
                key = self._get_key()

                if key == 'UP':
                    current_index = max(0, current_index - 1)
                elif key == 'DOWN':
                    current_index = min(len(models) - 1, current_index + 1)
                elif key == 'ENTER':
                    # 用户确认选择
                    return models[current_index]
                elif key == 'ESC':
                    # ESC 退出，选择第一个
                    return models[0]
            except KeyboardInterrupt:
                return models[0]

    # ==================== 模型选择界面 ====================
    def show_model_list(self, models: List[str]):
        """显示可用模型列表（运行时 /model 命令使用）"""
        self.print_dim(f"可用模型 ({len(models)}):")
        # 计算模型名最大宽度：80 - 5(缩进+序号+点+空格)
        max_model_width = self.WIDTH - 6
        for i, model in enumerate(models, 1):
            if len(model) > max_model_width:
                model = self.truncate(model, max_model_width)
            self.print_dim(f"  {i}. {model}")

    def get_model_choice(self, prompt: str = "Select model (number or Enter for first): ") -> str:
        """获取用户的模型选择"""
        return self.get_input(prompt)

    def show_model_input_prompt(self):
        """提示用户手动输入模型名称"""
        self.print_system("无法自动检测模型，请手动输入模型名称")

    def show_model_selected(self, model: str):
        """显示已选择的模型"""
        self.print_system(f"已切换到模型: {model}")

    # ==================== 状态栏 ====================

    def show_status_bar(self, model: str = None, autostatus: dict = None, start_time: datetime = None):
        """显示状态栏"""
        extra_info = {}
        if model:
            extra_info['model'] = model
        if autostatus:
            extra_info['autostatus'] = autostatus
        print(self.format_status_bar(extra_info))

    # ==================== 命令帮助 ====================
    
    def show_command_help(self, help_text: str):
        """显示命令帮助"""
        self.print_dim(help_text)

    # ==================== 调试信息 ====================
    
    def show_debug(self, title: str, content: str):
        """显示调试信息"""
        # 标题行居中
        header = f"--- {title} ---"
        self.print_dim(f"\n{self.center_text(header)}")
        # 内容自动换行
        self.print_dim(content, wrap=True)

    def show_chunks_debug(self, chunks_info: str):
        """显示 chunks 调试信息"""
        # 按行处理，每行截断到 80 列
        for line in chunks_info.split('\n'):
            if len(line) > self.WIDTH:
                line = self.truncate(line, self.WIDTH)
            print(line)

    def show_autostatus_debug(self, rounds: int, state: dict, prompt: str = None, response: str = None):
        """显示 AutoStatus 调试信息"""
        self.print_dim(f"\n{self.draw_line()}")
        self.print_dim("AutoStatus 调试信息")
        self.print_dim(f"对话轮次: {rounds}")
        
        # 状态 JSON 可能很长，截断显示
        state_str = json.dumps(state, ensure_ascii=False)
        if len(state_str) > self.CONTENT_WIDTH:
            state_str = self.truncate(state_str, self.CONTENT_WIDTH)
        self.print_dim(f"当前状态: {state_str}")
        
        if prompt:
            self.print_dim("\n[发送给LLM的提示词]")
            self.print_dim(self.truncate(prompt, self.CONTENT_WIDTH * 2))
        if response:
            self.print_dim(f"\n[LLM响应] {self.truncate(response, self.CONTENT_WIDTH)}")
        self.print_dim(self.draw_line())

    def show_messages_debug(self, messages: List[Dict]):
        """显示消息历史调试信息"""
        self.print_dim(f"\n{self.draw_line()}")
        self.print_dim(f"消息历史 ({len(messages)} 条):")
        
        # 内容截断宽度
        content_max = self.CONTENT_WIDTH - 15  # 留出前缀空间
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            
            # 截断内容
            if len(content) > content_max:
                content = content[:content_max - 3] + "..."
            
            if role == "system":
                self.print_dim(f"\n[{i}] SYSTEM: {content}")
            elif role == "user":
                print(f"\n{self.COLORS['user_text']}[{i}] USER: {content}{Style.RESET_ALL}")
            elif role == "assistant":
                print(f"\n{self.COLORS['assistant_text']}[{i}] ASSISTANT: {content or '[no content]'}{Style.RESET_ALL}")
                if tool_calls:
                    print(f"{self.COLORS['tool_name']}    tool_calls: {len(tool_calls)} 个{Style.RESET_ALL}")
            elif role == "tool":
                name = msg.get("name", "unknown")
                self.print_dim(f"\n[{i}] TOOL ({name}): {content}")
        
        self.print_dim(self.draw_line())

    # ==================== 对话编辑界面 ====================
    
    def show_chunk_editor(self, chunks: List[tuple], current_index: int = 0) -> tuple:
        """显示语块编辑器界面（实时按键响应）
        
        Args:
            chunks: [(real_index, chunk), ...] 可编辑的语块列表
            current_index: 当前选中的索引（在 chunks 列表中的位置）
            
        Returns:
            (action, real_index, new_content)
            action: 'edit', 'delete', 'delete_from', 'quit', 'view'
            real_index: 在 chunk_manager.chunks 中的真实索引
            new_content: 编辑后的新内容（仅 action='edit' 时有效）
        """
        from chunk_system import ChunkType
        
        # 类型标签映射
        type_labels = {
            ChunkType.USER: ('USER', self.COLORS['user_text']),
            ChunkType.ASSISTANT: ('PAW ', self.COLORS['assistant_text']),
            ChunkType.TOOL_CALL: ('CALL', self.COLORS['tool_name']),
            ChunkType.TOOL_RESULT: ('TOOL', self.COLORS['dim']),
            ChunkType.SHELL: ('TERM', Fore.MAGENTA),
            ChunkType.THOUGHT: ('MIND', Fore.CYAN),
        }
        
        self.enter_alternate_screen()  # 进入备用屏幕
        self.hide_cursor()  # 隐藏光标，更清爽
        
        try:
            while True:
                # 清屏并显示标题（在备用屏幕内）
                self.clear_screen()
                print()
                title = "═══════════════════ 对话编辑器 ═══════════════════"
                print(f"{self.COLORS['dim']}{self.center_text(title)}{Style.RESET_ALL}")
                print()
                
                # 显示操作提示
                hint = "↑↓ 选择  │  E 编辑  │  D 删除  │  R 回滚  │  V 查看  │  Q/Esc 退出"
                print(f"{self.COLORS['dim']}{self.center_text(hint)}{Style.RESET_ALL}")
                print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
                print()
                
                # 显示语块列表
                if not chunks:
                    print(f"{self.COLORS['dim']}  (没有可编辑的语块){Style.RESET_ALL}")
                else:
                    # 计算显示范围（滚动窗口）
                    max_visible = 12
                    start_idx = max(0, current_index - max_visible // 2)
                    end_idx = min(len(chunks), start_idx + max_visible)
                    if end_idx - start_idx < max_visible:
                        start_idx = max(0, end_idx - max_visible)
                    
                    # 显示滚动指示
                    if start_idx > 0:
                        print(f"{self.COLORS['dim']}  ↑ 还有 {start_idx} 条...{Style.RESET_ALL}")
                    
                    for i in range(start_idx, end_idx):
                        real_idx, chunk = chunks[i]
                        is_selected = (i == current_index)
                        
                        # 获取类型标签和颜色
                        label, color = type_labels.get(chunk.chunk_type, ('????', self.COLORS['dim']))
                        
                        # 获取预览内容
                        preview = chunk.content.replace('\n', ' ').strip()
                        # 计算可用宽度
                        max_preview = self.WIDTH - 15
                        if len(preview) > max_preview:
                            preview = preview[:max_preview - 3] + "..."
                        
                        # 选中标记
                        if is_selected:
                            marker = f"{Fore.CYAN}›{Style.RESET_ALL}"
                            line = f" {marker} {self.COLORS['bright']}{i:2d}{Style.RESET_ALL} {color}[{label}]{Style.RESET_ALL} {self.COLORS['bright']}{preview}{Style.RESET_ALL}"
                        else:
                            line = f"   {self.COLORS['dim']}{i:2d}{Style.RESET_ALL} {color}[{label}]{Style.RESET_ALL} {self.COLORS['dim']}{preview}{Style.RESET_ALL}"
                        
                        print(line)
                    
                    # 显示滚动指示
                    if end_idx < len(chunks):
                        print(f"{self.COLORS['dim']}  ↓ 还有 {len(chunks) - end_idx} 条...{Style.RESET_ALL}")
                
                print()
                print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
                
                # 显示当前选中项的详细信息
                if chunks and 0 <= current_index < len(chunks):
                    real_idx, chunk = chunks[current_index]
                    label, color = type_labels.get(chunk.chunk_type, ('????', self.COLORS['dim']))
                    print(f"\n{color}[{label}]{Style.RESET_ALL} #{real_idx} | {chunk.tokens} tokens | {chunk.timestamp.strftime('%H:%M:%S')}")
                    
                    # 显示内容预览（最多3行）
                    lines = chunk.content.split('\n')[:3]
                    for line in lines:
                        if len(line) > self.CONTENT_WIDTH:
                            line = line[:self.CONTENT_WIDTH - 3] + "..."
                        print(f"  {self.COLORS['dim']}{line}{Style.RESET_ALL}")
                    if len(chunk.content.split('\n')) > 3:
                        print(f"  {self.COLORS['dim']}... (共 {len(chunk.content.split(chr(10)))} 行){Style.RESET_ALL}")
                
                # 实时获取按键
                try:
                    key = self._get_key()
                    
                    if not chunks:
                        if key in ['q', 'Q', 'ESC', 'ENTER']:
                            return ('quit', -1, None)
                        continue
                    
                    real_idx, chunk = chunks[current_index]
                    label, _ = type_labels.get(chunk.chunk_type, ('????', self.COLORS['dim']))
                    
                    # 方向键导航
                    if key == 'UP' and current_index > 0:
                        current_index -= 1
                    elif key == 'DOWN' and current_index < len(chunks) - 1:
                        current_index += 1
                    elif key == 'PAGEUP':
                        current_index = max(0, current_index - 5)
                    elif key == 'PAGEDOWN':
                        current_index = min(len(chunks) - 1, current_index + 5)
                    elif key == 'HOME':
                        current_index = 0
                    elif key == 'END':
                        current_index = len(chunks) - 1
                    
                    # 编辑
                    elif key in ['e', 'E', 'ENTER']:
                        self.show_cursor()
                        new_content = self._show_chunk_edit_dialog(chunk)
                        self.hide_cursor()
                        if new_content is not None:
                            return ('edit', real_idx, new_content)
                    
                    # 删除
                    elif key in ['d', 'D', 'DELETE']:
                        self.show_cursor()
                        if self._confirm_action(f"确定删除这条 [{label}] 消息吗？"):
                            return ('delete', real_idx, None)
                        self.hide_cursor()
                    
                    # 回滚
                    elif key in ['r', 'R']:
                        self.show_cursor()
                        if self._confirm_action(f"确定回滚到此处吗？将删除此条及之后的所有消息。"):
                            return ('delete_from', real_idx, None)
                        self.hide_cursor()
                    
                    # 查看完整内容
                    elif key in ['v', 'V']:
                        self.show_cursor()
                        self._show_chunk_full_content(chunk)
                        self.hide_cursor()
                    
                    # 退出
                    elif key in ['q', 'Q', 'ESC']:
                        return ('quit', -1, None)
                        
                except KeyboardInterrupt:
                    return ('quit', -1, None)
        
        finally:
            self.show_cursor()  # 确保退出时恢复光标
            self.leave_alternate_screen()  # 返回主屏幕
        
        return ('quit', -1, None)
    
    def _show_chunk_edit_dialog(self, chunk) -> Optional[str]:
        """显示语块编辑对话框
        
        Returns:
            编辑后的新内容，如果取消则返回 None
        """
        # 注意：此时已经在备用屏幕中，只需清屏
        self.clear_screen()
        print()
        print(f"{self.COLORS['dim']}═══════════════════ 编辑内容 ═══════════════════{Style.RESET_ALL}")
        print()
        print(f"{self.COLORS['dim']}当前内容:{Style.RESET_ALL}")
        print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
        
        # 显示当前内容
        for line in chunk.content.split('\n'):
            print(f"  {line}")
        
        print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
        print()
        print(f"{self.COLORS['dim']}输入新内容（输入空行结束，输入 /cancel 取消）:{Style.RESET_ALL}")
        print()
        
        # 多行输入
        lines = []
        try:
            while True:
                line = input(f"{self.COLORS['user_text']}> {Style.RESET_ALL}")
                if line == '/cancel':
                    return None
                if line == '' and lines:
                    # 空行结束输入
                    break
                lines.append(line)
        except KeyboardInterrupt:
            return None
        
        if not lines:
            return None
        
        return '\n'.join(lines)
    
    def _show_chunk_full_content(self, chunk):
        """显示语块的完整内容"""
        # 注意：此时已经在备用屏幕中，只需清屏
        self.clear_screen()
        print()
        print(f"{self.COLORS['dim']}═══════════════════ 完整内容 ═══════════════════{Style.RESET_ALL}")
        print()
        print(f"{self.COLORS['dim']}类型: {chunk.chunk_type.value} | Tokens: {chunk.tokens} | 时间: {chunk.timestamp.strftime('%H:%M:%S')}{Style.RESET_ALL}")
        print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
        print()
        
        # 显示完整内容
        print(chunk.content)
        
        print()
        print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
        print(f"{self.COLORS['dim']}按任意键返回...{Style.RESET_ALL}", end='', flush=True)
        self._get_key()  # 任意键返回
    
    def _confirm_action(self, message: str) -> bool:
        """确认操作（实时按键）
        
        Returns:
            用户是否确认
        """
        print()
        print(f"{self.COLORS['warning']}{message} (y/N): {Style.RESET_ALL}", end='', flush=True)
        key = self._get_key()
        print()  # 换行
        return key.lower() in ['y', '是']
    
    def _get_key(self) -> str:
        """获取单个按键（实时响应，无需回车）
        
        Returns:
            按键字符，特殊键返回特定字符串：
            - 'UP', 'DOWN', 'LEFT', 'RIGHT' 方向键
            - 'ENTER' 回车键
            - 'ESC' 退出键
            - 'BACKSPACE' 退格键
        """
        if sys.platform == "win32":
            # Windows 使用 msvcrt
            key = msvcrt.getch()
            
            # 处理特殊键（方向键等以 0xe0 或 0x00 开头）
            if key in (b'\xe0', b'\x00'):
                key2 = msvcrt.getch()
                key_map = {
                    b'H': 'UP',
                    b'P': 'DOWN',
                    b'K': 'LEFT',
                    b'M': 'RIGHT',
                    b'S': 'DELETE',
                    b'G': 'HOME',
                    b'O': 'END',
                    b'I': 'PAGEUP',
                    b'Q': 'PAGEDOWN',
                }
                return key_map.get(key2, '')
            
            # 处理普通键
            if key == b'\r':
                return 'ENTER'
            elif key == b'\x1b':
                return 'ESC'
            elif key == b'\x08':
                return 'BACKSPACE'
            elif key == b'\x03':  # Ctrl+C
                raise KeyboardInterrupt
            else:
                try:
                    return key.decode('utf-8')
                except:
                    return ''
        else:
            # Unix/Linux 使用 termios
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                key = sys.stdin.read(1)
                
                # 处理 ESC 序列（方向键等）
                if key == '\x1b':
                    key2 = sys.stdin.read(1)
                    if key2 == '[':
                        key3 = sys.stdin.read(1)
                        key_map = {
                            'A': 'UP',
                            'B': 'DOWN',
                            'C': 'RIGHT',
                            'D': 'LEFT',
                            '3': 'DELETE',  # 需要再读一个 ~
                            '5': 'PAGEUP',
                            '6': 'PAGEDOWN',
                        }
                        if key3 in ['3', '5', '6']:
                            sys.stdin.read(1)  # 读取 ~
                        return key_map.get(key3, 'ESC')
                    return 'ESC'
                elif key == '\r' or key == '\n':
                    return 'ENTER'
                elif key == '\x7f':
                    return 'BACKSPACE'
                elif key == '\x03':  # Ctrl+C
                    raise KeyboardInterrupt
                else:
                    return key
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    def show_edit_result(self, action: str, success: bool, detail: str = ""):
        """显示编辑结果"""
        if success:
            action_names = {
                'edit': '编辑',
                'delete': '删除',
                'delete_from': '回滚'
            }
            action_name = action_names.get(action, action)
            self.print_success(f"✓ {action_name}成功 {detail}")
        else:
            self.print_error(f"✗ 操作失败 {detail}")

    # ==================== 记忆管理界面 ====================
    
    def show_memory_editor(self, conversations: List[Dict], current_index: int = 0) -> tuple:
        """显示记忆管理界面
        
        Returns:
            (action, doc_id, extra_data)
        """
        self.enter_alternate_screen()
        self.hide_cursor()
        selected_ids = set()
        multi_select_mode = False
        
        try:
            while True:
                self.clear_screen()
                print()
                title = "═══════════════════ 记忆管理 ═══════════════════"
                print(f"{self.COLORS['dim']}{self.center_text(title)}{Style.RESET_ALL}")
                print()
                
                total = len(conversations)
                selected_count = len(selected_ids)
                stats = f"共 {total} 条记忆"
                if multi_select_mode:
                    stats += f" | 已选 {selected_count} 条 | [多选模式]"
                print(f"{self.COLORS['dim']}{self.center_text(stats)}{Style.RESET_ALL}")
                print()
                
                if multi_select_mode:
                    hint = "↑↓选择 │ Space勾选 │ D删除已选 │ A全选 │ M退出多选 │ Q退出"
                else:
                    hint = "↑↓选择 │ V查看 │ D删除 │ M多选 │ C清理重复 │ /搜索 │ Q退出"
                print(f"{self.COLORS['dim']}{self.center_text(hint)}{Style.RESET_ALL}")
                print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
                print()
                
                if not conversations:
                    print(f"{self.COLORS['dim']}  (没有记忆记录){Style.RESET_ALL}")
                else:
                    max_visible = 10
                    start_idx = max(0, current_index - max_visible // 2)
                    end_idx = min(len(conversations), start_idx + max_visible)
                    if end_idx - start_idx < max_visible:
                        start_idx = max(0, end_idx - max_visible)
                    
                    if start_idx > 0:
                        print(f"{self.COLORS['dim']}  ↑ 还有 {start_idx} 条...{Style.RESET_ALL}")
                    
                    for i in range(start_idx, end_idx):
                        conv = conversations[i]
                        is_selected = (i == current_index)
                        is_checked = conv['id'] in selected_ids
                        
                        user_msg = conv.get('metadata', {}).get('user_message', '')[:40]
                        timestamp = conv.get('metadata', {}).get('timestamp', '')[:16]
                        
                        checkbox = "[✓]" if is_checked else "[ ]"
                        if not multi_select_mode:
                            checkbox = "   "
                        
                        max_msg_width = self.WIDTH - 25
                        if len(user_msg) > max_msg_width:
                            user_msg = user_msg[:max_msg_width - 3] + "..."
                        
                        if is_selected:
                            marker = f"{Fore.CYAN}›{Style.RESET_ALL}"
                            cb = f"{Fore.GREEN}[✓]{Style.RESET_ALL}" if is_checked else checkbox
                            line = f" {marker} {cb} {self.COLORS['bright']}{user_msg:<{max_msg_width}}{Style.RESET_ALL} {self.COLORS['dim']}{timestamp}{Style.RESET_ALL}"
                        else:
                            cb = f"{Fore.GREEN}[✓]{Style.RESET_ALL}" if is_checked else checkbox
                            line = f"   {cb} {self.COLORS['dim']}{user_msg:<{max_msg_width}} {timestamp}{Style.RESET_ALL}"
                        print(line)
                    
                    if end_idx < len(conversations):
                        print(f"{self.COLORS['dim']}  ↓ 还有 {len(conversations) - end_idx} 条...{Style.RESET_ALL}")
                
                print()
                print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
                
                if conversations and 0 <= current_index < len(conversations):
                    conv = conversations[current_index]
                    metadata = conv.get('metadata', {})
                    print(f"\n{self.COLORS['info']}ID:{Style.RESET_ALL} {conv['id']} | {self.COLORS['info']}项目:{Style.RESET_ALL} {metadata.get('project', '(无)')}")
                    
                    user_msg = metadata.get('user_message', '')
                    if user_msg:
                        lines = user_msg.split('\n')[:2]
                        print(f"{self.COLORS['user_text']}用户:{Style.RESET_ALL}")
                        for line in lines:
                            if len(line) > self.CONTENT_WIDTH - 4:
                                line = line[:self.CONTENT_WIDTH - 7] + "..."
                            print(f"  {self.COLORS['dim']}{line}{Style.RESET_ALL}")
                
                try:
                    key = self._get_key()
                    
                    if not conversations:
                        if key in ['q', 'Q', 'ESC']:
                            return ('quit', None, None)
                        continue
                    
                    conv = conversations[current_index]
                    
                    if key == 'UP' and current_index > 0:
                        current_index -= 1
                    elif key == 'DOWN' and current_index < len(conversations) - 1:
                        current_index += 1
                    elif key == 'PAGEUP':
                        current_index = max(0, current_index - 5)
                    elif key == 'PAGEDOWN':
                        current_index = min(len(conversations) - 1, current_index + 5)
                    elif key == 'HOME':
                        current_index = 0
                    elif key == 'END':
                        current_index = len(conversations) - 1
                    elif key == ' ' and multi_select_mode:
                        if conv['id'] in selected_ids:
                            selected_ids.remove(conv['id'])
                        else:
                            selected_ids.add(conv['id'])
                        if current_index < len(conversations) - 1:
                            current_index += 1
                    elif key in ['a', 'A'] and multi_select_mode:
                        if len(selected_ids) == len(conversations):
                            selected_ids.clear()
                        else:
                            selected_ids = {c['id'] for c in conversations}
                    elif key in ['m', 'M']:
                        multi_select_mode = not multi_select_mode
                        if not multi_select_mode:
                            selected_ids.clear()
                    elif key in ['d', 'D', 'DELETE']:
                        self.show_cursor()
                        if multi_select_mode and selected_ids:
                            if self._confirm_action(f"确定删除选中的 {len(selected_ids)} 条记忆吗？"):
                                return ('delete_batch', None, list(selected_ids))
                        else:
                            if self._confirm_action("确定删除这条记忆吗？"):
                                return ('delete', conv['id'], None)
                        self.hide_cursor()
                    elif key in ['v', 'V', 'ENTER']:
                        self.show_cursor()
                        self._show_memory_full_content(conv)
                        self.hide_cursor()
                    elif key in ['c', 'C'] and not multi_select_mode:
                        return ('clean_duplicates', None, None)
                    elif key == '/' and not multi_select_mode:
                        self.show_cursor()
                        keyword = self._get_search_keyword()
                        self.hide_cursor()
                        if keyword:
                            return ('search', None, keyword)
                    elif key in ['q', 'Q', 'ESC']:
                        return ('quit', None, None)
                        
                except KeyboardInterrupt:
                    return ('quit', None, None)
        finally:
            self.show_cursor()
            self.leave_alternate_screen()
        
        return ('quit', None, None)
    
    def _show_memory_full_content(self, conv: Dict):
        """显示记忆的完整内容"""
        self.clear_screen()
        print()
        print(f"{self.COLORS['dim']}═══════════════════ 记忆详情 ═══════════════════{Style.RESET_ALL}")
        print()
        
        metadata = conv.get('metadata', {})
        print(f"{self.COLORS['info']}ID:{Style.RESET_ALL} {conv['id']}")
        print(f"{self.COLORS['info']}项目:{Style.RESET_ALL} {metadata.get('project', '(无)')}")
        print(f"{self.COLORS['info']}时间:{Style.RESET_ALL} {metadata.get('timestamp', '(未知)')}")
        print()
        print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
        
        user_msg = metadata.get('user_message', '')
        assistant_msg = metadata.get('assistant_message', '')
        
        print(f"\n{self.COLORS['user_text']}[用户]{Style.RESET_ALL}")
        print(user_msg or "(无内容)")
        
        print(f"\n{self.COLORS['assistant_text']}[AI]{Style.RESET_ALL}")
        print(assistant_msg or "(无内容)")
        
        print()
        print(f"{self.COLORS['dim']}{self.draw_line('─')}{Style.RESET_ALL}")
        print(f"{self.COLORS['dim']}按任意键返回...{Style.RESET_ALL}", end='', flush=True)
        self._get_key()
    
    def _get_search_keyword(self) -> Optional[str]:
        """获取搜索关键词"""
        print()
        print(f"{self.COLORS['dim']}输入搜索关键词 (回车取消):{Style.RESET_ALL}")
        try:
            keyword = input(f"{self.COLORS['user_text']}> {Style.RESET_ALL}").strip()
            return keyword if keyword else None
        except KeyboardInterrupt:
            return None
    
    def show_memory_result(self, action: str, success: bool, detail: str = ""):
        """显示记忆操作结果"""
        if success:
            action_names = {
                'delete': '删除',
                'delete_batch': '批量删除',
                'clean_duplicates': '清理重复'
            }
            action_name = action_names.get(action, action)
            self.print_success(f"✓ {action_name}成功 {detail}")
        else:
            self.print_error(f"✗ 操作失败 {detail}")
