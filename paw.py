#!/usr/bin/env python
"""
Paw - 数字生命体标准启动器
统一入口，上帝视角，完全可视化
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
from colorama import init, Fore, Back, Style
import yaml

# 初始化颜色系统
init(autoreset=True)

# 导入核心组件
from consciousness import DigitalConsciousness, Thought, Memory
from tools import BaseTools
from chunk_system import ChunkManager, ChunkType, Chunk
from tools_schema import TOOLS_SCHEMA
from prompts import SystemPrompts, ConsciousnessPrompts, UIPrompts, ToolPrompts


class ColoredOutput:
    """简约输出管理器 - Claude Code风格"""
    
    # 颜色定义（柔和色调）
    DIM = Style.DIM
    BRIGHT = Style.BRIGHT
    RESET = Style.RESET_ALL
    
    # 角色颜色
    USER = Fore.WHITE + Style.BRIGHT
    ASSISTANT = Fore.GREEN
    TOOL = Fore.BLUE + Style.DIM
    SYSTEM = Fore.YELLOW + Style.DIM
    ERROR = Fore.RED
    
    @staticmethod
    def user(text: str) -> str:
        return f"{ColoredOutput.USER}{text}{ColoredOutput.RESET}"
    
    @staticmethod
    def assistant(text: str) -> str:
        return f"{ColoredOutput.ASSISTANT}{text}{ColoredOutput.RESET}"
    
    @staticmethod
    def tool(text: str) -> str:
        return f"{ColoredOutput.TOOL}{text}{ColoredOutput.RESET}"
    
    @staticmethod
    def system(text: str) -> str:
        return f"{ColoredOutput.SYSTEM}{text}{ColoredOutput.RESET}"
    
    @staticmethod
    def error(text: str) -> str:
        return f"{ColoredOutput.ERROR}{text}{ColoredOutput.RESET}"
    
    @staticmethod
    def dim(text: str) -> str:
        return f"{ColoredOutput.DIM}{text}{ColoredOutput.RESET}"


class Paw:
    """
    Paw - 数字生命体主程序
    统一标准启动，完全可视化，上帝视角
    """
    
    def __init__(self, api_url: str = None, model: str = None, api_key: str = None):
        """初始化
        
        Args:
            api_url: API地址，如果为None则从config.yaml或环境变量读取
            model: 模型名称，如果为None则从config.yaml或环境变量读取
            api_key: API密钥，如果为None则从config.yaml或环境变量读取
        """
        # 基础配置
        self.name = "Paw"
        self.birth_time = datetime.now()
        
        # 核心组件
        self.consciousness = DigitalConsciousness()
        self.tools = BaseTools()
        self.output = ColoredOutput()
        
        # 读取配置文件
        config = self._load_config()
        
        # API配置（优先级：参数 > config.yaml > 环境变量 > 默认值）
        self.api_url = api_url or config.get('api', {}).get('url') or os.getenv("API_URL", "http://localhost:1234/v1/chat/completions")
        self.model = model or config.get('api', {}).get('model') or os.getenv("MODEL", None)
        self.api_key = api_key or config.get('api', {}).get('key') or os.getenv("OPENAI_API_KEY", None)
        
        # 上下文管理（使用语块系统，传入工具schema）
        self.chunk_manager = ChunkManager(max_tokens=64000, tools_schema=TOOLS_SCHEMA)
        
        # 系统提示词（第一人称）
        self.system_prompt = self._create_system_prompt()
        
        # OpenAI标准消息历史（持久化）
        self.messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # 可视化配置
        self.show_debug = True  # 显示调试信息
    
    def _load_config(self) -> dict:
        """加载config.yaml配置文件"""
        config_path = Path(__file__).parent / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(self.output.error(f"警告: 无法读取config.yaml - {e}"))
                return {}
        return {}
    
    def _create_system_prompt(self) -> str:
        """创建系统提示词 - 第一人称视角"""
        # 获取终端状态
        terminal_status = self.tools.get_terminal_status()
        terminal_info = f"{terminal_status['prompt']} (位于: {terminal_status['relative_path']})"
        
        # 使用提示词配置文件
        main_prompt = SystemPrompts.get_main_system_prompt(self.name, self.birth_time)
        
        # 替换终端状态占位符
        main_prompt = main_prompt.replace("{terminal_status}", terminal_info)
        
        # 添加记忆上下文（建立历史感）
        memory_context = ConsciousnessPrompts.get_memory_context()
        
        # 组合完整的系统提示词
        prompt = f"{main_prompt}\n\n{memory_context}"
        
        # 添加系统提示词到语块管理器
        self.chunk_manager.add_system_prompt(prompt)
        return prompt
    
    def _inject_memories(self, context: str) -> List[str]:
        """注入相关记忆"""
        # 从consciousness获取相关记忆
        memories = []
        if hasattr(self.consciousness, 'memories'):
            # 搜索相关记忆
            keywords = context.lower().split()[:5]  # 取前5个关键词
            for memory in self.consciousness.memories[-10:]:  # 最近10条记忆
                if any(kw in memory.experience.lower() for kw in keywords):
                    memories.append(f"[记忆] {memory.experience}")
        
        return memories
    
    
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
                                if not has_content:
                                    print(f"\n{self.output.assistant('')}", end='', flush=True)
                                    has_content = True
                                content_text = delta['content']
                                content_chunks.append(content_text)
                                # 暂时打印，如果后面发现有<<<DONE>>>会重新处理
                                print(self.output.assistant(content_text), end='', flush=True)
                            
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
                        print()  # 换行
                    
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
        """执行工具调用"""
        tool_name = tool_call.get("tool")
        args = tool_call.get("args", {})
        
        # 工具执行（静默，由process_input显示）
        
        try:
            # 文件读写
            if tool_name == "read_file":
                result = self.tools.read_file(**args)
            elif tool_name == "write_file":
                result = self.tools.write_file(**args)
            elif tool_name == "delete_file":
                result = self.tools.delete_file(**args)
            
            # 文件编辑
            elif tool_name == "edit_file":
                result = self.tools.edit_file(**args)
            elif tool_name == "replace_in_file":
                result = self.tools.replace_in_file(**args)
            elif tool_name == "multi_edit":
                result = self.tools.multi_edit(**args)
            
            # 文件搜索
            elif tool_name == "find_files":
                result = self.tools.find_files(**args)
            elif tool_name == "grep_search":
                result = self.tools.grep_search(**args)
            elif tool_name == "search_in_file":
                result = self.tools.search_in_file(**args)
            
            # 目录操作
            elif tool_name == "list_directory":
                result = self.tools.list_directory(**args)
            
            # 系统交互
            elif tool_name == "execute_command":
                result = self.tools.execute_command(**args)
            elif tool_name == "run_script":
                result = self.tools.run_script(**args)
            
            else:
                error_msg = ToolPrompts.get_error_messages()["unknown_tool"].format(tool_name=tool_name)
                result = error_msg
            
            # 统一返回格式
            if isinstance(result, str):
                # 判断是成功还是失败 - 检查多种错误格式
                error_keywords = ["错误", "失败", "Error", "error", "无法", "未找到", "不存在", "拒绝", "超时"]
                success = not any(keyword in result for keyword in error_keywords)
                
                if success and result.startswith("成功"):
                    return {"success": True, "result": result}
                elif not success:
                    return {"success": False, "error": result}
                else:
                    # 不明确的情况，根据内容判断
                    return {"success": success, "result": result}
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
        self.messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        self.chunk_manager.chunks.clear()
        self.chunk_manager.current_tokens = 0
        status_msg = UIPrompts.get_status_messages()["history_cleared"]
        print(self.output.dim(status_msg))
    
    async def process_input(self, user_input: str) -> str:
        """处理用户输入 - 完全符合OpenAI Function Calling标准"""
        # 1. 添加用户输入到持久化消息历史
        self.messages.append({
            "role": "user",
            "content": user_input
        })
        
        # 同时添加到chunk_manager（用于显示）
        self.chunk_manager.add_user_input(user_input)
        
        # 2. 主循环
        step_count = 0
        max_steps = 20
        final_response = ""
        no_action_count = 0  # 连续无工具调用计数
        
        while step_count < max_steps:
            step_count += 1
            
            # 调用支持Function Calling的API
            assistant_message = await self._call_llm_with_tools(self.messages)
            
            # 提取内容和工具调用
            content = assistant_message.get("content")
            tool_calls = assistant_message.get("tool_calls")
            
            # 添加完整的assistant消息（OpenAI标准）
            assistant_msg = {
                "role": "assistant",
                "content": content
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            
            self.messages.append(assistant_msg)
            
            # 添加到chunk_manager
            if content:
                self.chunk_manager.add_assistant_response(content)
                final_response = content
            
            # 注意：响应已在_call_llm_with_tools中流式显示
            
            # 执行工具调用
            if tool_calls:
                for tool_call in tool_calls:
                    # 提取工具信息
                    tool_call_id = tool_call.get("id")
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])
                    
                    # 显示工具调用
                    args_str = json.dumps(function_args, ensure_ascii=False)
                    tool_icon = ToolPrompts.get_tool_execution_prefix()
                    print(f"\n{self.output.tool(f'{tool_icon} {function_name}({args_str})')}")
                    
                    # 执行工具
                    result = await self._execute_tool({
                        "tool": function_name,
                        "args": function_args
                    })
                    
                    # 确保result_text总是被定义
                    if result.get("success"):
                        result_text = str(result.get("result", ""))
                        # 显示结果预览
                        preview = result_text[:200] + "..." if len(result_text) > 200 else result_text
                        print(self.output.dim(f"  {preview}"))
                    else:
                        error_msg = result.get('error', '未知错误')
                        result_text = f"错误: {error_msg}"
                        print(self.output.error(f"  {result_text}"))
                    
                    # 添加工具结果（OpenAI标准）
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": function_name,
                        "content": result_text
                    })
                    
                    # 同时添加到chunk_manager
                    self.chunk_manager.add_tool_result(result_text)
            
            # 检查是否完成
            if not tool_calls:
                # 没有工具调用，立即停止
                # 如果用户觉得没说完，可以主动回车继续
                break
            else:
                # 有工具调用，重置计数
                no_action_count = 0
            
            if step_count >= max_steps:
                max_steps_msg = UIPrompts.get_status_messages()["max_steps_reached"]
                print(self.output.error(max_steps_msg))
                break
        
        # 形成记忆
        await self.consciousness._form_memory(
            f"任务: {user_input[:50]}",
            {"steps": step_count, "response": final_response[:100]}
        )
        
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
                        print(self.output.dim(f"模型检测失败 ({response.status}): {error_text[:100]}"))
                        return []
        except Exception as e:
            print(self.output.dim(f"无法获取模型列表: {e}"))
            return []
    
    async def _select_model(self) -> str:
        """选择模型"""
        status_msgs = UIPrompts.get_status_messages()
        print(self.output.dim(status_msgs["checking_models"]))
        models = await self._fetch_available_models()
        
        if not models:
            print(self.output.system("无法自动检测模型，请手动输入模型名称"))
            while True:
                model_name = input(self.output.user("模型名称 (如 glm-4-flash): ")).strip()
                if model_name:
                    return model_name
                print(self.output.error("模型名称不能为空"))
        
        print(self.output.dim(f"\n可用模型 ({len(models)}):"))
        for i, model in enumerate(models, 1):
            print(self.output.dim(f"  {i}. {model}"))
        
        # 让用户选择
        status_msgs = UIPrompts.get_status_messages()
        while True:
            try:
                choice = input(self.output.user(status_msgs["model_prompt"])).strip()
                if not choice:
                    return models[0]
                
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    return models[idx]
                else:
                    print(self.output.error(status_msgs["invalid_number"]))
            except ValueError:
                print(self.output.error(status_msgs["please_enter_number"]))
            except KeyboardInterrupt:
                print(self.output.dim(status_msgs["using_first_model"]))
                return models[0]
    
    async def run(self):
        """主运行循环"""
        # 如果没有指定模型，自动选择
        if not self.model:
            self.model = await self._select_model()
        
        # 启动横幅（简约风格）
        ui_msgs = UIPrompts.get_startup_messages()
        print(f"\n{Style.BRIGHT}{ui_msgs['banner']}{Style.RESET_ALL} {self.output.dim(ui_msgs['version'])}")
        print(self.output.dim(f"Model: {self.model}"))
        
        # 初始化意识
        await self.consciousness._perceive_environment()
        
        # 主循环
        while True:
            try:
                # 获取输入（简约提示符）
                user_input = input(f"\n{self.output.user('> ')}").strip()
                
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    self.consciousness._save_identity()
                    await self.consciousness._save_memories()
                    goodbye_msg = UIPrompts.get_startup_messages()["goodbye"]
                    print(self.output.dim(goodbye_msg))
                    break
                
                # 空输入表示"继续"，不是忽略
                if not user_input:
                    # 检查是否有对话历史
                    if len(self.messages) <= 1:  # 只有system prompt
                        continue
                    # 添加一个特殊的继续标记
                    user_input = "[继续]"
                
                # 特殊命令
                if user_input == '/clear':
                    self.clear_history()
                    continue
                
                if user_input == '/chunks':
                    self.chunk_manager.print_context(show_llm_view=True)
                    continue
                
                if user_input == '/model':
                    # 重新选择模型
                    print(self.output.dim(f"当前模型: {self.model}"))
                    new_model = await self._select_model()
                    self.model = new_model
                    print(self.output.system(f"已切换到模型: {self.model}"))
                    continue
                
                if user_input == '/messages':
                    # 显示完整的消息历史（调试用）
                    print(self.output.dim(f"\n消息历史 ({len(self.messages)} 条):"))
                    for i, msg in enumerate(self.messages):
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        tool_calls = msg.get("tool_calls")
                        
                        if role == "system":
                            print(self.output.dim(f"\n[{i}] SYSTEM: {content[:100]}..."))
                        elif role == "user":
                            print(self.output.user(f"\n[{i}] USER: {content}"))
                        elif role == "assistant":
                            print(self.output.assistant(f"\n[{i}] ASSISTANT: {content or '[no content]'}"))
                            if tool_calls:
                                print(self.output.tool(f"    tool_calls: {len(tool_calls)} 个"))
                        elif role == "tool":
                            name = msg.get("name", "unknown")
                            print(self.output.dim(f"\n[{i}] TOOL ({name}): {content[:100]}..."))
                    continue
                
                if user_input.startswith('/'):
                    help_msg = UIPrompts.get_command_help()
                    print(self.output.dim(help_msg))
                    continue
                
                # 处理正常输入
                await self.process_input(user_input)
                
            except KeyboardInterrupt:
                interrupted_msg = UIPrompts.get_startup_messages()["interrupted"]
                print(self.output.dim(interrupted_msg))
                break
            except Exception as e:
                print(self.output.error(f"\nError: {e}"))
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
