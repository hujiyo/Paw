#!/usr/bin/env python
"""
语块系统 - 上下文管理架构
通过语块来管理上下文
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal, Tuple
from enum import Enum
from colorama import Fore, Style


class ChunkType(Enum):
    """语块类型枚举"""
    SYSTEM = "system"          # 系统提示词
    MEMORY = "memory"          # 注入的记忆
    USER = "user"              # 用户输入
    ASSISTANT = "assistant"    # AI生成
    THOUGHT = "thought"        # AI内部思考
    TOOL_CALL = "tool_call"    # 工具调用
    TOOL_RESULT = "tool_result"  # 工具结果
    SHELL = "shell"            # Shell终端输出（动态刷新）


@dataclass
class Chunk:
    """
    语块 - 上下文的基本单元
    
    每个语块在创建时就知道自己的类型，
    不需要通过检测关键词来判断
    """
    content: str                    # 内容
    chunk_type: ChunkType           # 类型
    timestamp: datetime = field(default_factory=datetime.now)
    tokens: int = 0                 # token数量
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        """字符串表示（不带颜色）"""
        return self.content
    
    def colored_str(self) -> str:
        """带颜色的字符串表示"""
        color_map = {
            ChunkType.SYSTEM: Fore.RED,       # 系统注入 - 红色
            ChunkType.MEMORY: Fore.RED,       # 记忆注入 - 红色
            ChunkType.USER: Fore.WHITE,       # 用户输入 - 白色
            ChunkType.ASSISTANT: Fore.GREEN,  # AI生成 - 绿色
            ChunkType.THOUGHT: Fore.CYAN,     # 内部思考 - 青色
            ChunkType.TOOL_CALL: Fore.CYAN,       # 工具调用 - 青色
            ChunkType.TOOL_RESULT: Fore.YELLOW,   # 工具结果 - 黄色
            ChunkType.SHELL: Fore.MAGENTA,        # Shell输出 - 紫色
        }
        
        color = color_map.get(self.chunk_type, Fore.WHITE)
        return f"{color}{self.content}{Style.RESET_ALL}"
    
    def estimate_tokens(self) -> int:
        """估算token数量"""
        if self.tokens > 0:
            return self.tokens
        # 粗略估算：4个字符约1个token
        self.tokens = len(self.content) // 4
        return self.tokens


class ChunkManager:
    """
    语块管理器 - 管理整个对话的上下文
    """
    
    def __init__(self, max_tokens: int = 64000, tools_schema: Optional[List[Dict]] = None):
        """初始化
        
        Args:
            max_tokens: 最大token数
            tools_schema: 工具定义schema（OpenAI格式）
        """
        self.chunks: List[Chunk] = []
        self.max_tokens = max_tokens
        self.current_tokens = 0
        self.tools_schema = tools_schema or []
        self.tools_tokens = self._estimate_tools_tokens()
    
    def _estimate_tools_tokens(self) -> int:
        """估算工具schema的token数"""
        if not self.tools_schema:
            return 0
        import json
        tools_json = json.dumps(self.tools_schema, ensure_ascii=False)
        # 粗略估算：4个字符约1个token
        return len(tools_json) // 4
    
    def add_chunk(self, content: str, chunk_type: ChunkType, 
                  metadata: Optional[Dict[str, Any]] = None) -> Chunk:
        """
        添加语块
        
        在添加时就明确标记类型，不需要后续猜测
        """
        chunk = Chunk(
            content=content,
            chunk_type=chunk_type,
            metadata=metadata or {}
        )
        chunk.estimate_tokens()
        self.chunks.append(chunk)
        self.current_tokens += chunk.tokens
        return chunk
    
    def add_system_prompt(self, prompt: str) -> Chunk:
        """添加系统提示词（注入）"""
        return self.add_chunk(prompt, ChunkType.SYSTEM)

    def update_latest_system_prompt(self, prompt: str) -> Chunk:
        """更新最近的系统提示词内容"""
        for chunk in reversed(self.chunks):
            if chunk.chunk_type == ChunkType.SYSTEM:
                old_tokens = chunk.tokens
                chunk.content = prompt
                chunk.tokens = 0
                chunk.estimate_tokens()
                self.current_tokens += chunk.tokens - old_tokens
                return chunk
        return self.add_system_prompt(prompt)
    
    def add_memory(self, memory: str) -> Chunk:
        """添加记忆（注入）"""
        return self.add_chunk(memory, ChunkType.MEMORY)
    
    def update_or_add_memory(self, memory: str) -> Chunk:
        """更新或添加记忆 chunk
        
        如果已存在 MEMORY chunk，则替换其内容；否则新建。
        确保上下文中只有一个记忆 chunk。
        """
        for chunk in self.chunks:
            if chunk.chunk_type == ChunkType.MEMORY:
                old_tokens = chunk.tokens
                chunk.content = memory
                chunk.tokens = 0
                chunk.estimate_tokens()
                self.current_tokens += chunk.tokens - old_tokens
                return chunk
        return self.add_memory(memory)
    
    def remove_memory(self):
        """移除记忆 chunk"""
        for i, chunk in enumerate(self.chunks):
            if chunk.chunk_type == ChunkType.MEMORY:
                self.current_tokens -= chunk.tokens
                self.chunks.pop(i)
                return True
        return False
    
    def add_user_input(self, input_text: str) -> Chunk:
        """添加用户输入"""
        return self.add_chunk(input_text, ChunkType.USER)
    
    def add_assistant_response(self, response: str, tool_calls: Optional[List[Dict]] = None) -> Chunk:
        """添加AI回复（生成）
        
        Args:
            response: 回复内容
            tool_calls: 工具调用列表（OpenAI格式）
        """
        metadata = {}
        if tool_calls:
            metadata['tool_calls'] = tool_calls
        return self.add_chunk(response or "", ChunkType.ASSISTANT, metadata=metadata)
    
    def add_thought(self, thought: str) -> Chunk:
        """添加AI思考（内部）"""
        return self.add_chunk(thought, ChunkType.THOUGHT)
    
    def add_tool_call(self, tool_info: str) -> Chunk:
        """添加工具调用"""
        return self.add_chunk(tool_info, ChunkType.TOOL_CALL)
    
    def add_tool_result(self, result: str, tool_call_id: str = None, tool_name: str = None,
                        max_call_pairs: int = 0, display_info: dict = None) -> Chunk:
        """添加工具结果

        Args:
            result: 工具执行结果
            tool_call_id: 工具调用ID（OpenAI标准）
            tool_name: 工具名称
            max_call_pairs: 最大配对数量，超出时删除最旧的 (tool_call + tool_result)
            display_info: 工具显示信息（用于恢复历史时保持显示一致性），包含 line1/line2/has_line2
        """
        metadata = {}
        if tool_call_id:
            metadata['tool_call_id'] = tool_call_id
        if tool_name:
            metadata['name'] = tool_name
        if display_info:
            metadata['display'] = display_info

        # 添加新的 tool_result
        chunk = self.add_chunk(result, ChunkType.TOOL_RESULT, metadata=metadata)

        # 如果设置了 max_call_pairs，执行配对清理
        if max_call_pairs > 0 and tool_name:
            self._enforce_max_call_pairs(tool_name, max_call_pairs)

        return chunk
    
    def _enforce_max_call_pairs(self, tool_name: str, max_pairs: int):
        """
        强制执行配对数量限制
        
        删除最旧的 (tool_call + tool_result) 配对，直到数量 <= max_pairs
        """
        # 1. 找出该工具的所有 tool_result 及其 tool_call_id
        tool_results = []
        for i, chunk in enumerate(self.chunks):
            if (chunk.chunk_type == ChunkType.TOOL_RESULT and 
                chunk.metadata.get('name') == tool_name):
                tool_results.append({
                    'index': i,
                    'chunk': chunk,
                    'tool_call_id': chunk.metadata.get('tool_call_id')
                })
        
        # 2. 如果数量超过限制，删除最旧的配对
        while len(tool_results) > max_pairs:
            oldest = tool_results.pop(0)  # 最旧的
            tool_call_id = oldest['tool_call_id']
            
            # 删除对应的 tool_call（在 assistant 消息的 tool_calls 中）
            self._remove_tool_call_by_id(tool_call_id)
            
            # 删除 tool_result chunk
            self._remove_chunk_by_tool_call_id(tool_call_id)
    
    def _remove_tool_call_by_id(self, tool_call_id: str):
        """
        从 assistant 消息中移除指定的 tool_call
        
        如果 assistant 消息的 tool_calls 变空，则删除整个 assistant 消息
        """
        for i, chunk in enumerate(self.chunks):
            if chunk.chunk_type == ChunkType.ASSISTANT and 'tool_calls' in chunk.metadata:
                tool_calls = chunk.metadata['tool_calls']
                # 找到并移除匹配的 tool_call
                new_tool_calls = [tc for tc in tool_calls if tc.get('id') != tool_call_id]
                
                if len(new_tool_calls) < len(tool_calls):
                    # 找到了，更新或删除
                    if len(new_tool_calls) == 0 and not chunk.content:
                        # tool_calls 为空且无文本内容，删除整个 assistant chunk
                        self.current_tokens -= chunk.tokens
                        self.chunks.pop(i)
                    else:
                        # 还有其他 tool_calls 或有文本内容，只更新
                        chunk.metadata['tool_calls'] = new_tool_calls
                    return
    
    def _remove_chunk_by_tool_call_id(self, tool_call_id: str):
        """删除指定 tool_call_id 的 tool_result chunk"""
        for i, chunk in enumerate(self.chunks):
            if (chunk.chunk_type == ChunkType.TOOL_RESULT and 
                chunk.metadata.get('tool_call_id') == tool_call_id):
                self.current_tokens -= chunk.tokens
                self.chunks.pop(i)
                return
    
    def add_shell_output(self, output: str) -> Chunk:
        """添加Shell输出语块（首次创建）"""
        return self.add_chunk(output, ChunkType.SHELL)
    
    def update_shell_output(self, output: str, move_to_end: bool = False) -> Chunk:
        """更新Shell输出语块

        Args:
            output: 终端屏幕内容
            move_to_end: 是否移动到末尾（仅在终端操作后设为True）

        - move_to_end=False: 原地更新内容，位置不变（用于定时刷新）
        - move_to_end=True: 保留历史内容，追加新输出到末尾（用于终端操作后）
        """
        if move_to_end:
            # 检查是否已存在 shell_chunk
            existing_content = None
            for chunk in self.chunks:
                if chunk.chunk_type == ChunkType.SHELL:
                    existing_content = chunk.content
                    self.remove_shell_chunk()
                    break

            # 如果有旧内容，追加新输出（用分隔线分开）
            if existing_content:
                combined = existing_content.rstrip() + "\n\n=== 新终端 ===\n" + output
                return self.add_shell_output(combined)
            else:
                return self.add_shell_output(output)
        else:
            # 原地更新内容
            for chunk in self.chunks:
                if chunk.chunk_type == ChunkType.SHELL:
                    old_tokens = chunk.tokens
                    chunk.content = output
                    chunk.tokens = 0
                    chunk.estimate_tokens()
                    self.current_tokens += chunk.tokens - old_tokens
                    chunk.timestamp = datetime.now()
                    return chunk
            # 不存在则创建（首次）
            return self.add_shell_output(output)
    
    def has_shell_chunk(self) -> bool:
        """检查是否存在Shell语块"""
        return any(c.chunk_type == ChunkType.SHELL for c in self.chunks)
    
    def remove_shell_chunk(self) -> bool:
        """移除Shell语块（终端关闭时调用）"""
        for i, chunk in enumerate(self.chunks):
            if chunk.chunk_type == ChunkType.SHELL:
                self.current_tokens -= chunk.tokens
                self.chunks.pop(i)
                return True
        return False
    
    def get_context_for_llm(self) -> List[Dict[str, Any]]:
        """
        获取用于LLM的上下文（完整支持OpenAI Function Calling）
        
        将语块转换为OpenAI标准消息格式，支持tool_calls和tool角色
        Shell输出按其在chunks中的位置出现，位置会随终端操作动态移动
        """
        messages = []
        
        # 不再合并，而是逐个处理以保持tool_calls结构
        current_system_content = []
        
        for chunk in self.chunks:
            # 跳过思考语块和工具调用语块
            if chunk.chunk_type in [ChunkType.THOUGHT, ChunkType.TOOL_CALL]:
                continue
            
            # 系统提示词和记忆 - 合并为一个system消息
            if chunk.chunk_type in [ChunkType.SYSTEM, ChunkType.MEMORY]:
                current_system_content.append(chunk.content)
                continue
            
            # 如果有累积的系统内容，先添加
            if current_system_content:
                messages.append({
                    "role": "system",
                    "content": "\n".join(current_system_content)
                })
                current_system_content = []
            
            # 用户输入
            if chunk.chunk_type == ChunkType.USER:
                messages.append({
                    "role": "user",
                    "content": chunk.content
                })
            
            # AI回复（可能包含tool_calls）
            elif chunk.chunk_type == ChunkType.ASSISTANT:
                msg = {
                    "role": "assistant",
                    "content": chunk.content if chunk.content else None
                }
                # 添加tool_calls（如果有）
                if 'tool_calls' in chunk.metadata:
                    msg['tool_calls'] = chunk.metadata['tool_calls']
                messages.append(msg)
            
            # 工具结果
            elif chunk.chunk_type == ChunkType.TOOL_RESULT:
                msg = {
                    "role": "tool",
                    "content": chunk.content
                }
                # 添加tool_call_id和name（OpenAI标准要求）
                if 'tool_call_id' in chunk.metadata:
                    msg['tool_call_id'] = chunk.metadata['tool_call_id']
                if 'name' in chunk.metadata:
                    msg['name'] = chunk.metadata['name']
                messages.append(msg)
            
            # Shell输出 - 作为 user 消息插入（表示环境反馈）
            elif chunk.chunk_type == ChunkType.SHELL:
                messages.append({
                    "role": "user",
                    "content": f"[当前终端屏幕]\n{chunk.content}\n[终端屏幕结束]"
                })
        
        # 添加剩余的系统内容
        if current_system_content:
            messages.append({
                "role": "system",
                "content": "\n".join(current_system_content)
            })
        
        return messages
    
    def print_context(self, show_types: bool = True, use_colors: bool = True, show_llm_view: bool = True):
        """
        打印完整上下文 - 显示LLM实际看到的内容
        
        Args:
            show_types: 是否显示语块类型
            use_colors: 是否使用颜色
            show_llm_view: 是否显示LLM实际看到的消息（推荐，内容一致）
        """
        print("\n" + "="*60)
        print("📚 完整上下文（LLM实际视角）")
        print("="*60)
        
        # 显示完整工具定义（橙色）- LLM通过tools参数看到的
        if self.tools_schema:
            tool_label = "[TOOLS] (通过API的tools参数传递，不在messages中)"
            if use_colors:
                tool_label = f"{Fore.LIGHTRED_EX}{tool_label}{Style.RESET_ALL}"  # 橙色
            print(f"\n{tool_label}")
            
            # 显示每个工具的完整定义
            for tool in self.tools_schema:
                func = tool['function']
                func_name = func['name']
                func_desc = func.get('description', '无描述')
                params = func.get('parameters', {}).get('properties', {})
                required = func.get('parameters', {}).get('required', [])
                
                # 工具名称和描述
                tool_header = f"\n  🔧 {func_name}"
                if use_colors:
                    tool_header = f"{Fore.LIGHTRED_EX}{tool_header}{Style.RESET_ALL}"
                print(tool_header)
                
                desc_text = f"     {func_desc}"
                if use_colors:
                    desc_text = f"{Fore.LIGHTRED_EX}{desc_text}{Style.RESET_ALL}"
                print(desc_text)
                
                # 参数列表
                if params:
                    params_text = "     参数:"
                    if use_colors:
                        params_text = f"{Fore.LIGHTRED_EX}{params_text}{Style.RESET_ALL}"
                    print(params_text)
                    
                    for param_name, param_info in params.items():
                        param_type = param_info.get('type', 'unknown')
                        param_desc = param_info.get('description', '无描述')
                        is_required = " (必需)" if param_name in required else " (可选)"
                        
                        param_line = f"       - {param_name} ({param_type}){is_required}: {param_desc}"
                        if use_colors:
                            param_line = f"{Fore.LIGHTRED_EX}{param_line}{Style.RESET_ALL}"
                        print(param_line)
        
        # 获取LLM实际看到的消息（OpenAI标准格式）
        messages = self.get_context_for_llm()
        
        # 直接按照真实的OpenAI消息格式打印
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content')
            
            # 显示OpenAI标准的role（直接从消息中获取，不硬编码）
            role_label = f"[{role}]"  # 保持原始role名称
            if use_colors:
                if role == 'system':
                    role_label = f"{Fore.RED}{role_label}{Style.RESET_ALL}"  # 系统提示词：红色
                elif role == 'user':
                    role_label = f"{Fore.WHITE}{role_label}{Style.RESET_ALL}"  # 用户输入：白色
                elif role == 'assistant':
                    role_label = f"{Fore.GREEN}{role_label}{Style.RESET_ALL}"  # LLM生成：绿色
                elif role == 'tool':
                    role_label = f"{Fore.YELLOW}{role_label}{Style.RESET_ALL}"  # 工具结果：黄色
                else:
                    # 其他未知role也能正常显示
                    role_label = f"{Fore.WHITE}{role_label}{Style.RESET_ALL}"
            
            print(f"\n{role_label}")
            
            # 内容
            if content:
                # 根据role设置内容颜色
                if use_colors:
                    if role == 'system':
                        print(f"{Fore.RED}{content}{Style.RESET_ALL}")  # 系统提示词：红色
                    elif role == 'user':
                        print(f"{Fore.WHITE}{content}{Style.RESET_ALL}")  # 用户输入：白色
                    elif role == 'assistant':
                        print(f"{Fore.GREEN}{content}{Style.RESET_ALL}")  # LLM生成：绿色
                    elif role == 'tool':
                        print(f"{Fore.YELLOW}{content}{Style.RESET_ALL}")  # 工具结果：黄色
                    else:
                        print(content)
                else:
                    print(content)
            else:
                # 内容为空时显示占位符
                placeholder = "[无文本内容]"
                if use_colors:
                    placeholder = f"{Fore.LIGHTBLACK_EX}{placeholder}{Style.RESET_ALL}"
                print(placeholder)
            
            # 显示tool_calls（如果有）- 工具调用：青色
            if 'tool_calls' in msg:
                tool_calls = msg['tool_calls']
                tc_label = f"  🔧 tool_calls ({len(tool_calls)}个):"
                if use_colors:
                    tc_label = f"{Fore.CYAN}{tc_label}{Style.RESET_ALL}"  # 青色
                print(tc_label)
                
                for tc in tool_calls:
                    tc_id = tc.get('id', 'unknown')
                    func_name = tc.get('function', {}).get('name', 'unknown')
                    func_args = tc.get('function', {}).get('arguments', '{}')
                    
                    tc_info = f"    • {func_name}({func_args})"
                    if use_colors:
                        tc_info = f"{Fore.CYAN}{tc_info}{Style.RESET_ALL}"  # 青色
                    print(tc_info)
                    
                    tc_id_info = f"      id: {tc_id}"
                    if use_colors:
                        tc_id_info = f"{Fore.CYAN}{tc_id_info}{Style.RESET_ALL}"  # 青色（ID也是工具调用的一部分）
                    print(tc_id_info)
            
            # 显示tool相关字段（如果有）- 工具结果元数据：黄色
            if 'tool_call_id' in msg or 'name' in msg:
                tool_info = []
                if 'name' in msg:
                    tool_info.append(f"tool_name: {msg['name']}")
                if 'tool_call_id' in msg:
                    tool_info.append(f"tool_call_id: {msg['tool_call_id']}")
                
                info_str = f"  📎 {' | '.join(tool_info)}"
                if use_colors:
                    info_str = f"{Fore.YELLOW}{info_str}{Style.RESET_ALL}"  # 黄色（和tool结果一致）
                print(info_str)
        
        print("\n" + "="*60)
        print(f"消息数量: {len(messages)} 条")
        total_tokens = self.current_tokens + self.tools_tokens
        print(f"消息Token数: {self.current_tokens}")
        if self.tools_tokens > 0:
            print(f"工具Token数: {self.tools_tokens}")
        print(f"总Token数: {total_tokens}/{self.max_tokens} "
              f"({total_tokens/self.max_tokens*100:.1f}%)")
        print("="*60)
    
    def print_mixed_response(self, response_chunks: List[Chunk]):
        """
        打印混合响应（一段话中包含不同类型的语块）
        
        这是更高级的显示方式，将多个语块合并成一段自然的输出
        """
        # 将连续的语块合并成一个输出流
        output = ""
        for chunk in response_chunks:
            if chunk.chunk_type in [ChunkType.SYSTEM, ChunkType.MEMORY]:
                # 注入的内容 - 红色
                output += f"{Fore.RED}{chunk.content}{Style.RESET_ALL}"
            elif chunk.chunk_type == ChunkType.ASSISTANT:
                # AI生成的内容 - 绿色
                output += f"{Fore.GREEN}{chunk.content}{Style.RESET_ALL}"
            else:
                # 其他 - 默认颜色
                output += chunk.content
        
        print(output)
    
    def clear(self):
        """清空上下文（保留系统提示词）"""
        system_chunks = [c for c in self.chunks if c.chunk_type == ChunkType.SYSTEM]
        self.chunks = system_chunks
        self.current_tokens = sum(c.tokens for c in system_chunks)
    
    # ==================== 对话编辑功能 ====================
    
    def get_editable_chunks(self) -> List[Tuple[int, 'Chunk']]:
        """获取可编辑的语块列表（排除系统提示词）
        
        Returns:
            [(index, chunk), ...] 列表，index 是在 self.chunks 中的真实索引
        """
        editable = []
        for i, chunk in enumerate(self.chunks):
            # 排除系统提示词和记忆（这些是注入的，不应该被用户编辑）
            if chunk.chunk_type not in [ChunkType.SYSTEM, ChunkType.MEMORY]:
                editable.append((i, chunk))
        return editable
    
    def get_chunk_by_index(self, index: int) -> Optional['Chunk']:
        """根据索引获取语块"""
        if 0 <= index < len(self.chunks):
            return self.chunks[index]
        return None
    
    def delete_chunk(self, index: int) -> bool:
        """删除指定索引的语块
        
        Args:
            index: 在 self.chunks 中的真实索引
            
        Returns:
            是否删除成功
        """
        if 0 <= index < len(self.chunks):
            chunk = self.chunks[index]
            # 不允许删除系统提示词
            if chunk.chunk_type == ChunkType.SYSTEM:
                return False
            
            # 如果是 assistant 消息且有 tool_calls，需要同时删除对应的 tool_result
            if chunk.chunk_type == ChunkType.ASSISTANT and 'tool_calls' in chunk.metadata:
                tool_call_ids = [tc.get('id') for tc in chunk.metadata['tool_calls']]
                # 删除对应的 tool_result
                self.chunks = [
                    c for c in self.chunks 
                    if not (c.chunk_type == ChunkType.TOOL_RESULT and 
                           c.metadata.get('tool_call_id') in tool_call_ids)
                ]
            
            # 如果是 tool_result，需要从对应的 assistant 消息中移除 tool_call
            if chunk.chunk_type == ChunkType.TOOL_RESULT:
                tool_call_id = chunk.metadata.get('tool_call_id')
                if tool_call_id:
                    self._remove_tool_call_by_id(tool_call_id)
            
            # 删除语块
            self.current_tokens -= chunk.tokens
            self.chunks = [c for i, c in enumerate(self.chunks) if i != index]
            return True
        return False
    
    def delete_chunks_from(self, index: int) -> int:
        """删除从指定索引开始的所有语块（用于回滚到某个点）
        
        Args:
            index: 在 self.chunks 中的真实索引
            
        Returns:
            删除的语块数量
        """
        if index < 0 or index >= len(self.chunks):
            return 0
        
        # 不允许删除系统提示词
        if self.chunks[index].chunk_type == ChunkType.SYSTEM:
            return 0
        
        # 计算要删除的 token 数
        deleted_tokens = sum(c.tokens for c in self.chunks[index:])
        deleted_count = len(self.chunks) - index
        
        # 截断
        self.chunks = self.chunks[:index]
        self.current_tokens -= deleted_tokens
        
        return deleted_count
    
    def edit_chunk_content(self, index: int, new_content: str) -> bool:
        """编辑指定语块的内容
        
        Args:
            index: 在 self.chunks 中的真实索引
            new_content: 新内容
            
        Returns:
            是否编辑成功
        """
        if 0 <= index < len(self.chunks):
            chunk = self.chunks[index]
            # 不允许编辑系统提示词
            if chunk.chunk_type == ChunkType.SYSTEM:
                return False
            
            # 更新内容和 token 数
            old_tokens = chunk.tokens
            chunk.content = new_content
            chunk.tokens = 0
            chunk.estimate_tokens()
            self.current_tokens += chunk.tokens - old_tokens
            
            return True
        return False
    
    def get_chunk_preview(self, chunk: 'Chunk', max_length: int = 50) -> str:
        """获取语块的预览文本
        
        Args:
            chunk: 语块
            max_length: 最大长度
            
        Returns:
            预览文本
        """
        content = chunk.content.replace('\n', ' ').strip()
        if len(content) > max_length:
            content = content[:max_length - 3] + "..."
        return content
    
    def to_json(self) -> List[Dict[str, Any]]:
        """导出为JSON格式"""
        return [
            {
                "content": chunk.content,
                "type": chunk.chunk_type.value,
                "timestamp": chunk.timestamp.isoformat(),
                "tokens": chunk.tokens,
                "metadata": chunk.metadata
            }
            for chunk in self.chunks
        ]

    @classmethod
    def from_json(cls, data: List[Dict[str, Any]], max_tokens: int = 64000,
                  tools_schema: Optional[List[Dict]] = None) -> 'ChunkManager':
        """从JSON导入

        Args:
            data: JSON格式的语块数据
            max_tokens: 最大token数
            tools_schema: 工具定义schema

        Returns:
            新的ChunkManager实例
        """
        manager = cls(max_tokens=max_tokens, tools_schema=tools_schema)

        for item in data:
            chunk_type = ChunkType(item.get("type", "user"))
            content = item.get("content", "")

            # 解析时间戳
            timestamp_str = item.get("timestamp")
            if timestamp_str:
                try:
                    from datetime import datetime
                    timestamp = datetime.fromisoformat(timestamp_str)
                except Exception:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()

            # 创建chunk
            chunk = Chunk(
                content=content,
                chunk_type=chunk_type,
                timestamp=timestamp,
                tokens=item.get("tokens", 0),
                metadata=item.get("metadata", {})
            )

            # 如果没有token数，重新估算
            if chunk.tokens == 0:
                chunk.estimate_tokens()

            manager.chunks.append(chunk)
            manager.current_tokens += chunk.tokens

        return manager    
