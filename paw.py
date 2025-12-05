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
import aiohttp
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import re
import yaml

# 设置环境为UTF-8（Windows兼容）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# 导入核心组件
from autostatus import AutoStatus
from tools import BaseTools
from chunk_system import ChunkManager, ChunkType, Chunk
from tool_definitions import TOOLS_SCHEMA, register_all_tools, get_tools_schema
from tool_registry import ToolRegistry
from prompts import SystemPrompts, UIPrompts, ToolPrompts
from ui import UI


class Paw:
    """
    Paw - 数字生命体主程序
    统一标准启动，完全可视化，上帝视角
    """

    def __init__(self, api_url: str = None, model: str = None, api_key: str = None, minimal: bool = False):
        """初始化

        Args:
            api_url: API地址，如果为None则从config.yaml或环境变量读取
            model: 模型名称，如果为None则从config.yaml或环境变量读取
            api_key: API密钥，如果为None则从config.yaml或环境变量读取
            minimal: 是否使用极简模式（减少状态栏等装饰）
        """
        # 基础配置
        self.name = "Paw"
        self.birth_time = datetime.now()

        # UI系统（统一入口）
        self.ui = UI(minimal_mode=minimal)

        # 读取配置文件
        config = self._load_config()

        # 核心组件（传递配置）
        self.tools = BaseTools(config=config)
        
        # 注册所有工具到 ToolRegistry
        register_all_tools(self.tools)
        
        # API配置（优先级：参数 > config.yaml > 环境变量 > 默认值）
        self.api_url = api_url or config.get('api', {}).get('url') or os.getenv("API_URL", "http://localhost:1234/v1/chat/completions")
        self.model = model or config.get('api', {}).get('model') or os.getenv("MODEL", None)
        self.api_key = api_key or config.get('api', {}).get('key') or os.getenv("OPENAI_API_KEY", None)
        
        # 动态状态管理器（延迟初始化，等模型确定后）
        self.autostatus = None
        
        # 上下文管理（使用语块系统，传入工具schema）
        self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)
        
        # 系统提示词（第一人称）
        self.system_prompt = self._create_system_prompt()
        
        # 注意：消息历史现在完全由chunk_manager管理
        # 不再使用self.messages
        
        # 可视化配置
        self.show_debug = True  # 显示调试信息
        
        # 工具调用结果收集（用于状态评估）
        self.last_tool_results = []
    
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
    
    def _create_system_prompt(self, include_state: bool = False) -> str:
        """创建系统提示词 - 第一人称视角
        
        Args:
            include_state: 是否包含动态状态
        """
        # 获取终端状态
        terminal_status = self.tools.get_terminal_status()
        
        # 构建终端信息
        if terminal_status.get('is_open'):
            terminal_info = f"共享终端已开启 (PID: {terminal_status.get('pid')}, 工作目录: {terminal_status.get('working_directory')})"
        else:
            terminal_info = f"终端未启动 (工作目录: {terminal_status.get('working_directory')})"
        
        # 使用提示词配置文件
        main_prompt = SystemPrompts.get_main_system_prompt(self.name, self.birth_time)
        
        # 替换终端状态占位符
        main_prompt = main_prompt.replace("{terminal_status}", terminal_info)
        
        # 组合基础系统提示词
        prompt = main_prompt
        
        # 如果需要，注入动态状态
        if include_state and self.autostatus is not None:
            prompt = self.autostatus.inject_to_prompt(prompt)
        
        # 添加或更新系统提示词到语块管理器
        has_system = any(c.chunk_type == ChunkType.SYSTEM for c in self.chunk_manager.chunks)
        if has_system:
            self.chunk_manager.update_latest_system_prompt(prompt)
        else:
            self.chunk_manager.add_system_prompt(prompt)
        return prompt
    
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
        
        else:
            # 默认
            brief = result.replace('\n', ' ')[:40]
            return {'line1': brief, 'line2': '', 'has_line2': False}
    
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
        try:
            # 准备请求头
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "tools": TOOLS_SCHEMA,
                        "tool_choice": "auto",
                        "temperature": 0.7,
                        "max_tokens": 4000,
                        "stream": True  # 启用流式输出
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        error_template = ToolPrompts.get_error_messages()["api_error"]
                        error_msg = error_template.format(status=response.status, error=error_text)
                        return {
                            "content": error_msg,
                            "tool_calls": [],
                            "finish_reason": "error"
                        }
                    
                    # 流式处理
                    content_chunks = []
                    tool_calls_dict = {}  # 累积tool_calls
                    finish_reason = "stop"
                    has_content = False
                    
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if not line or not line.startswith('data: '):
                            continue
                        
                        if line == 'data: [DONE]':
                            break
                        
                        try:
                            json_str = line[6:]  # 移除 'data: ' 前缀
                            chunk = json.loads(json_str)
                            
                            if 'choices' not in chunk or len(chunk['choices']) == 0:
                                continue
                            
                            delta = chunk['choices'][0].get('delta', {})
                            finish_reason = chunk['choices'][0].get('finish_reason', finish_reason)
                            
                            # 处理内容（流式打印）
                            if 'content' in delta and delta['content']:
                                content_text = delta['content']
                                # 首次输出时去除前导换行
                                if not has_content:
                                    content_text = content_text.lstrip('\n')
                                    if not content_text:
                                        continue
                                    has_content = True
                                content_chunks.append(content_text)

                                # 流式输出
                                self.ui.print_assistant(content_text, end='', flush=True)
                            
                            # 处理tool_calls（累积）
                            if 'tool_calls' in delta:
                                for tc_delta in delta['tool_calls']:
                                    idx = tc_delta.get('index', 0)
                                    if idx not in tool_calls_dict:
                                        tool_calls_dict[idx] = {
                                            'id': '',
                                            'type': 'function',
                                            'function': {'name': '', 'arguments': ''}
                                        }
                                    
                                    if 'id' in tc_delta:
                                        tool_calls_dict[idx]['id'] = tc_delta['id']
                                    if 'function' in tc_delta:
                                        if 'name' in tc_delta['function']:
                                            tool_calls_dict[idx]['function']['name'] += tc_delta['function']['name']
                                        if 'arguments' in tc_delta['function']:
                                            tool_calls_dict[idx]['function']['arguments'] += tc_delta['function']['arguments']
                        
                        except json.JSONDecodeError:
                            continue
                    
                    if has_content:
                        # 只有当最后一行不是换行符时，才打印换行
                        # 这样可以避免 tool call 前出现空行
                        if not content_chunks[-1].endswith('\n'):
                            print()
                    
                    # 组合完整内容
                    full_content = ''.join(content_chunks) if content_chunks else None
                    tool_calls = list(tool_calls_dict.values()) if tool_calls_dict else None
                    
                    return {
                        "role": "assistant",
                        "content": full_content,
                        "tool_calls": tool_calls,
                        "finish_reason": finish_reason
                    }
                    
        except Exception as e:
            error_template = ToolPrompts.get_error_messages()["connection_error"]
            error_msg = error_template.format(error=str(e))
            return {
                "content": error_msg,
                "tool_calls": [],
                "finish_reason": "error"
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
            
            # 调用工具的 handler
            handler = tool_config.handler
            result = handler(**args)
            
            # Shell 工具特殊处理：刷新终端 chunk
            if tool_config.category == "shell":
                self._refresh_shell_chunk(move_to_end=False)
            
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
                # 如果已经是字典格式（execute_command, run_script）
                # 转换为统一的字符串结果
                if result.get("success"):
                    output = result.get("stdout", "")
                    if output:
                        return {"success": True, "result": output}
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
    
    async def process_input(self, user_input: str) -> str:
        """处理用户输入 - 完全符合OpenAI Function Calling标准"""
        # 1. 添加用户输入到chunk_manager（唯一的上下文来源）
        self.chunk_manager.add_user_input(user_input)
        
        # 2. 主循环（无步数限制）
        step_count = 0
        final_response = ""
        no_action_count = 0  # 连续无工具调用计数
        
        while True:
            step_count += 1
            
            # 更新系统提示词，注入动态状态
            if step_count > 1:  # 从第二次调用开始注入状态
                updated_prompt = self._create_system_prompt(include_state=True)
            
            # 刷新Shell输出到chunk（如果终端已打开）
            self._refresh_shell_chunk()
            
            # 从chunk_manager获取上下文消息
            messages = self.chunk_manager.get_context_for_llm()
            
            # 调用支持Function Calling的API
            assistant_message = await self._call_llm_with_tools(messages)
            
            # 提取内容和工具调用
            content = assistant_message.get("content")
            tool_calls = assistant_message.get("tool_calls")
            
            # 添加assistant消息到chunk_manager（包含tool_calls）
            self.chunk_manager.add_assistant_response(content, tool_calls=tool_calls)
            if content:
                final_response = content
            
            # 注意：响应已在_call_llm_with_tools中流式显示
            
            # 执行工具调用
            if tool_calls:
                for i, tool_call in enumerate(tool_calls):
                    # 提取工具信息
                    tool_call_id = tool_call.get("id")
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])
                    
                    # 显示工具调用（简洁格式，紧凑排列）
                    args_str = json.dumps(function_args, ensure_ascii=False) if function_args else ""
                    self.ui.show_tool_start(function_name, args_str)
                    
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
                        self.ui.show_tool_result(function_name, display, success=True)
                    else:
                        error_msg = result.get('error', '未知错误')
                        result_text = f"错误: {error_msg}"
                        self.ui.show_tool_result(function_name, {'line1': error_msg, 'line2': '', 'has_line2': False}, success=False)
                    
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
                    
                    # 收集工具结果用于状态评估
                    self.last_tool_results.append({
                        "tool": function_name,
                        "success": success
                    })
            
            # 检查是否完成
            if not tool_calls:
                # 没有工具调用，立即停止
                # 如果用户觉得没说完，可以主动回车继续
                break
            else:
                # 有工具调用，重置计数
                no_action_count = 0
        
        # 评估状态（使用独立的API调用）
        if self.autostatus is not None:
            try:
                # 只保留最近5个工具结果
                if len(self.last_tool_results) > 5:
                    self.last_tool_results = self.last_tool_results[-5:]
                
                # 从chunk_manager获取最近的消息用于状态评估
                recent_messages = self.chunk_manager.get_context_for_llm()[-6:]
                
                # 评估新状态
                await self.autostatus.evaluate_state(
                    conversation_history=recent_messages,
                    tool_results=self.last_tool_results
                )
                
                # 显示状态摘要
                if self.show_debug:
                    status_summary = self.autostatus.get_summary()
                    self.ui.print_dim(status_summary)
                    
            except Exception as e:
                # 状态评估失败不影响主流程
                if self.show_debug:
                    import traceback
                    self.ui.print_dim(f"状态评估失败: {e}")
                    traceback.print_exc()
        
        return final_response
    
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
    
    async def _select_model(self) -> str:
        """选择模型"""
        self.ui.show_model_checking()
        models = await self._fetch_available_models()
        
        if not models:
            self.ui.show_model_input_prompt()
            while True:
                model_name = self.ui.get_input("模型名称 (如 glm-4-flash): ")
                if model_name:
                    return model_name
                self.ui.print_error("模型名称不能为空")
        
        self.ui.show_model_list(models)
        
        # 让用户选择
        status_msgs = UIPrompts.get_status_messages()
        while True:
            try:
                choice = self.ui.get_model_choice(status_msgs["model_prompt"])
                if not choice:
                    return models[0]
                
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    return models[idx]
                else:
                    self.ui.print_error(status_msgs["invalid_number"])
            except ValueError:
                self.ui.print_error(status_msgs["please_enter_number"])
            except KeyboardInterrupt:
                self.ui.print_dim(status_msgs["using_first_model"])
                return models[0]
    
    async def run(self):
        """主运行循环"""
        # 如果没有指定模型，自动选择
        if not self.model:
            self.model = await self._select_model()
            
        # 模型选择完毕，清屏准备进入主界面
        self.ui.clear_screen()
        
        # 现在模型已确定，初始化AutoStatus
        if self.autostatus is None:
            self.autostatus = AutoStatus(self.api_url, self.model, self.api_key)
        
        # 启动横幅
        self.ui.print_welcome()
        self.ui.show_status_bar(self.model, self.autostatus.current_state if self.autostatus else None)
        
        # 主循环
        while True:
            try:
                # 获取用户输入
                user_input = self.ui.get_user_input()
                
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
                
                # 特殊命令
                if user_input == '/clear':
                    self.clear_history()
                    continue
                
                if user_input == '/chunks':
                    self.chunk_manager.print_context(show_llm_view=True)
                    # 打印 autostatus 上下文
                    if self.autostatus is not None:
                        self.ui.show_autostatus_debug(
                            self.autostatus.conversation_rounds,
                            self.autostatus.current_state,
                            self.autostatus.last_prompt,
                            self.autostatus.last_response
                        )
                    continue
                
                if user_input == '/model':
                    # 重新选择模型
                    self.ui.print_dim(f"当前模型: {self.model}")
                    new_model = await self._select_model()
                    self.model = new_model
                    self.ui.show_model_selected(self.model)
                    continue
                
                if user_input == '/messages':
                    # 显示完整的消息历史（调试用）
                    messages = self.chunk_manager.get_context_for_llm()
                    self.ui.show_messages_debug(messages)
                    continue
                
                if user_input.startswith('/'):
                    help_msg = UIPrompts.get_command_help()
                    self.ui.show_command_help(help_msg)
                    continue
                
                # 处理正常输入
                await self.process_input(user_input)
                
            except KeyboardInterrupt:
                interrupted_msg = UIPrompts.get_startup_messages()["interrupted"]
                self.ui.print_dim(interrupted_msg)
                break
            except Exception as e:
                self.ui.print_error(f"Error: {e}")
                if self.show_debug:
                    import traceback
                    traceback.print_exc()


async def main():
    """主入口 - 唯一标准启动方式"""
    # 检查依赖
    try:
        import colorama
    except ImportError:
        print("请安装 colorama: pip install colorama")
        return
    
    # 创建并运行Paw
    paw = Paw()
    await paw.run()


if __name__ == "__main__":
    # 标准启动
    asyncio.run(main())
