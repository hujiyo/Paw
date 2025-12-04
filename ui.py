#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UI系统 - Claude Code 风格重构版
极简、清晰、现代
"""

import os
import sys
import json
import shutil
from datetime import datetime
from typing import Optional, Dict, List, Any
from colorama import init, Fore, Back, Style

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

    def clear_screen(self):
        """清屏并复位光标"""
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

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

    def show_tool_start(self, tool_name: str, args_str: str):
        """显示工具开始执行"""
        # 计算可用宽度：80 - 2(缩进) - 2(图标+空格) - len(tool_name) - 1(空格)
        max_args_width = self.WIDTH - 5 - len(tool_name)
        if len(args_str) > max_args_width:
            args_str = args_str[:max_args_width - 3] + "..."
        
        # 显示加载中状态：○ tool_name args
        circle = f"{self.COLORS['dim']}○{Style.RESET_ALL}"
        text = f"{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL} {self.COLORS['tool_args']}{args_str}{Style.RESET_ALL}"
        self.print_overwrite(text)

    def show_tool_result(self, tool_name: str, display: dict, success: bool = True):
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
        if len(line2) > max_line2_width:
            line2 = line2[:max_line2_width - 3] + "..."
        
        if success:
            circle = f"{self.COLORS['success']}●{Style.RESET_ALL}"
            # run_command 特殊处理：~$ 用红色
            if is_command:
                prompt_style = f"{self.COLORS['error']}~${Style.RESET_ALL}"
                sys.stdout.write(f"\r{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL} {prompt_style} {self.COLORS['dim']}{line1}{Style.RESET_ALL}\n")
            else:
                sys.stdout.write(f"\r{circle} {self.COLORS['tool_name']}{tool_name}{Style.RESET_ALL} {self.COLORS['dim']}{line1}{Style.RESET_ALL}\n")
            if has_line2 and line2:
                sys.stdout.write(f"    {self.COLORS['dim']}⎿ {line2}{Style.RESET_ALL}\n")
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
        # 运行时间
        runtime = str(datetime.now() - self.start_time).split('.')[0]
        parts.append(f"time: {runtime}")
        
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
    
    def get_user_input(self) -> str:
        """获取用户输入（带提示符）"""
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

    # ==================== 模型选择界面 ====================
    
    def show_model_checking(self):
        """显示正在检测模型"""
        self.print_dim("检测可用模型...")

    def show_model_list(self, models: List[str]):
        """显示可用模型列表"""
        self.print_dim(f"\n可用模型 ({len(models)}):")
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
    
    def show_status_bar(self, model: str = None, autostatus: dict = None):
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
