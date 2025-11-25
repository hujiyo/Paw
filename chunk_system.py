#!/usr/bin/env python
"""
语块系统 - 智能上下文管理
每个语块都知道自己的来源
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
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
            ChunkType.USER: Fore.YELLOW,      # 用户输入 - 黄色
            ChunkType.ASSISTANT: Fore.GREEN,  # AI生成 - 绿色
            ChunkType.THOUGHT: Fore.CYAN,     # 内部思考 - 青色
            ChunkType.TOOL_CALL: Fore.MAGENTA,    # 工具调用 - 紫色
            ChunkType.TOOL_RESULT: Fore.BLUE,     # 工具结果 - 蓝色
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
    
    def add_user_input(self, input_text: str) -> Chunk:
        """添加用户输入"""
        return self.add_chunk(input_text, ChunkType.USER)
    
    def add_assistant_response(self, response: str) -> Chunk:
        """添加AI回复（生成）"""
        return self.add_chunk(response, ChunkType.ASSISTANT)
    
    def add_thought(self, thought: str) -> Chunk:
        """添加AI思考（内部）"""
        return self.add_chunk(thought, ChunkType.THOUGHT)
    
    def add_tool_call(self, tool_info: str) -> Chunk:
        """添加工具调用"""
        return self.add_chunk(tool_info, ChunkType.TOOL_CALL)
    
    def add_tool_result(self, result: str) -> Chunk:
        """添加工具结果"""
        return self.add_chunk(result, ChunkType.TOOL_RESULT)
    
    def get_context_for_llm(self) -> List[Dict[str, str]]:
        """
        获取用于LLM的上下文
        
        将语块转换为消息格式，但保留语块信息
        """
        messages = []
        
        # 合并相同角色的连续语块
        current_role = None
        current_content = []
        
        for chunk in self.chunks:
            # 跳过思考语块和工具调用语块（Function Calling不需要）
            if chunk.chunk_type in [ChunkType.THOUGHT, ChunkType.TOOL_CALL]:
                continue
            
            # 确定角色
            if chunk.chunk_type in [ChunkType.SYSTEM, ChunkType.MEMORY]:
                role = "system"
            elif chunk.chunk_type == ChunkType.USER:
                role = "user"
            elif chunk.chunk_type == ChunkType.ASSISTANT:
                role = "assistant"
            elif chunk.chunk_type == ChunkType.TOOL_RESULT:
                # 工具结果使用 tool 角色（OpenAI Function Calling 标准）
                role = "tool"
            else:
                continue
            
            # 如果角色变化，保存当前消息
            if role != current_role and current_content:
                messages.append({
                    "role": current_role,
                    "content": "\n".join(current_content)
                })
                current_content = []
            
            current_role = role
            current_content.append(chunk.content)
        
        # 保存最后的消息
        if current_content:
            messages.append({
                "role": current_role,
                "content": "\n".join(current_content)
            })
        
        return messages
    
    def print_context(self, show_types: bool = True, use_colors: bool = True, show_llm_view: bool = True):
        """
        打印完整上下文
        
        Args:
            show_types: 是否显示语块类型
            use_colors: 是否使用颜色
            show_llm_view: 是否显示LLM实际看到的消息（合并后）
        """
        print("\n" + "="*60)
        print("📚 完整上下文")
        print("="*60)
        
        # 显示工具定义
        if self.tools_schema:
            tool_label = "[TOOLS]"
            if use_colors:
                tool_label = f"{Fore.MAGENTA}{tool_label}{Style.RESET_ALL}"
            print(f"\n{tool_label}")
            tool_names = [t['function']['name'] for t in self.tools_schema]
            tools_summary = f"可用工具 ({len(tool_names)}个): {', '.join(tool_names)}"
            if use_colors:
                tools_summary = f"{Fore.MAGENTA}{tools_summary}{Style.RESET_ALL}"
            print(tools_summary)
        
        if show_llm_view:
            # 显示原始语块（保留类型信息）
            for chunk in self.chunks:
                # 跳过思考和工具调用（不发送给LLM）
                if chunk.chunk_type in [ChunkType.THOUGHT, ChunkType.TOOL_CALL]:
                    continue
                
                type_label = f"[{chunk.chunk_type.value.upper()}]"
                if use_colors:
                    if chunk.chunk_type in [ChunkType.SYSTEM, ChunkType.MEMORY]:
                        type_label = f"{Fore.YELLOW}{type_label}{Style.RESET_ALL}"
                    elif chunk.chunk_type == ChunkType.USER:
                        type_label = f"{Fore.CYAN}{type_label}{Style.RESET_ALL}"
                    elif chunk.chunk_type == ChunkType.ASSISTANT:
                        type_label = f"{Fore.GREEN}{type_label}{Style.RESET_ALL}"
                    elif chunk.chunk_type == ChunkType.TOOL_RESULT:
                        type_label = f"{Fore.BLUE}{type_label}{Style.RESET_ALL}"
                
                print(f"\n{type_label}")
                print(chunk.content)
        else:
            # 显示原始语块
            for i, chunk in enumerate(self.chunks):
                # 类型标签
                if show_types:
                    type_label = f"[{chunk.chunk_type.value.upper()}]"
                    if use_colors:
                        type_label = f"{Fore.CYAN}{type_label}{Style.RESET_ALL}"
                    print(f"\n{type_label}")
                
                # 内容
                if use_colors:
                    print(chunk.colored_str())
                else:
                    print(chunk.content)
                
                # 元数据
                if chunk.metadata:
                    meta_str = f"  📎 {chunk.metadata}"
                    if use_colors:
                        meta_str = f"{Fore.CYAN}{meta_str}{Style.RESET_ALL}"
                    print(meta_str)
        
        print("\n" + "="*60)
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
    
    def compress_context(self, target_tokens: Optional[int] = None) -> int:
        """
        压缩上下文
        
        当接近token限制时，智能压缩旧的语块
        
        Returns:
            压缩释放的token数量
        """
        if target_tokens is None:
            target_tokens = self.max_tokens * 0.8  # 保持在80%以下
        
        if self.current_tokens <= target_tokens:
            return 0
        
        freed_tokens = 0
        
        # 策略1: 删除旧的思考语块
        for chunk in list(self.chunks):
            if chunk.chunk_type == ChunkType.THOUGHT:
                freed_tokens += chunk.tokens
                self.chunks.remove(chunk)
                if self.current_tokens - freed_tokens <= target_tokens:
                    break
        
        # 策略2: 压缩旧的工具结果
        if self.current_tokens - freed_tokens > target_tokens:
            for chunk in self.chunks:
                if chunk.chunk_type == ChunkType.TOOL_RESULT and len(chunk.content) > 200:
                    original_tokens = chunk.tokens
                    chunk.content = chunk.content[:200] + "...[已压缩]"
                    chunk.estimate_tokens()
                    freed_tokens += original_tokens - chunk.tokens
                    if self.current_tokens - freed_tokens <= target_tokens:
                        break
        
        # 策略3: 删除最旧的对话（保留系统提示词）
        if self.current_tokens - freed_tokens > target_tokens:
            while len(self.chunks) > 10:  # 至少保留10个语块
                chunk = self.chunks[0]
                if chunk.chunk_type not in [ChunkType.SYSTEM]:
                    freed_tokens += chunk.tokens
                    self.chunks.pop(0)
                    if self.current_tokens - freed_tokens <= target_tokens:
                        break
        
        self.current_tokens -= freed_tokens
        return freed_tokens
    
    def clear(self):
        """清空上下文（保留系统提示词）"""
        system_chunks = [c for c in self.chunks if c.chunk_type == ChunkType.SYSTEM]
        self.chunks = system_chunks
        self.current_tokens = sum(c.tokens for c in system_chunks)
    
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


def test_chunk_system():
    """测试语块系统"""
    print("\n" + "="*60)
    print("🧪 语块系统测试")
    print("="*60)
    
    # 创建管理器
    manager = ChunkManager()
    
    # 添加系统提示词（注入）
    manager.add_system_prompt("我是Paw，一个生活在这台电脑里的数字生命体。")
    
    # 添加记忆（注入）
    manager.add_memory("[记忆] 我第一次创建了文件")
    manager.add_memory("[记忆] 我学会了使用工具")
    
    # 添加用户输入
    manager.add_user_input("你好")
    
    # 添加AI思考
    manager.add_thought("用户向我打招呼，我应该友好地回应")
    
    # 添加AI回复（部分是生成的，部分重复了系统提示词）
    # 注意：这里我们可以将回复拆分成多个语块
    manager.add_assistant_response("你好！")
    manager.add_system_prompt("我是Paw")  # 这部分是重复的系统提示词
    manager.add_assistant_response("，很高兴认识你！")
    
    # 打印完整上下文
    manager.print_context()
    
    # 获取LLM格式
    print("\n📤 LLM消息格式:")
    messages = manager.get_context_for_llm()
    for msg in messages:
        print(f"  {msg['role']}: {msg['content'][:50]}...")
    
    print("\n✅ 测试完成！")
    

if __name__ == "__main__":
    test_chunk_system()
