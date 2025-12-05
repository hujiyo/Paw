"""
工具注册系统 - 声明式工具定义 + 策略驱动的上下文管理

核心理念：
- 工具自己声明上下文策略
- ChunkManager 根据策略自动管理
- 解耦工具逻辑和上下文管理
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
import json


@dataclass
class ToolConfig:
    """
    工具配置 - 声明式定义
    
    只关注两件事：
    1. 工具的基本信息（name, schema, handler）
    2. 工具的上下文策略（如何管理 chunks）
    """
    
    # === 基础信息 ===
    name: str                              # 工具名称（唯一标识）
    schema: Dict[str, Any]                 # OpenAI function calling schema
    handler: Callable                      # 执行函数引用
    
    # === 上下文策略 ===
    
    singleton_key: Optional[Callable] = None
    # 单例模式的 key 生成函数
    # - None: 普通模式，每次调用都产生新 chunk
    # - Callable: 返回字符串 key，相同 key 的 chunk 会被覆盖
    # 函数签名: (args: dict, result: Any) -> str
    # 
    # 示例：
    # - shell 工具: lambda args, result: "shell"  # 所有 shell 操作共享一个 chunk
    # - read_file: lambda args, result: args.get("file_path")  # 按文件路径去重
    
    max_instances: int = 0
    # 同类 tool_result chunk 的最大数量（仅针对 tool_result）
    # - 0: 不限制（默认）
    # - >0: 最多保留 N 个，超出时淘汰最旧的
    # 注意：singleton_key 优先级更高，设置了 singleton_key 时此参数通常无意义
    # 注意：此参数只删除 tool_result，不删除对应的 tool_call
    
    max_call_pairs: int = 0
    # 配对保留数量（tool_call + tool_result 作为一对）
    # - 0: 不限制（默认）
    # - >0: 最多保留 N 对，超出时删除最旧的配对
    # 删除时会同时移除 assistant 消息中的 tool_call 和对应的 tool_result
    # 适用于：wait 等辅助工具，保留最近几次调用记录即可
    
    result_transform: Optional[Callable] = None
    # 结果转换函数（用于压缩/摘要）
    # - None: 保留原始结果
    # - Callable: 转换结果后再存入 chunk
    # 函数签名: (args: dict, result: Any) -> str
    #
    # 示例：
    # - write_to_file: lambda args, r: f"✓ 写入 {args['file_path']}"
    # - grep_search: lambda args, r: truncate_results(r, max_lines=10)
    
    # === 元数据（可选）===
    category: str = "general"              # 工具分类（用于 UI 分组等）
    

class ToolRegistry:
    """
    工具注册表 - 单例模式
    
    管理所有已注册的工具配置
    """
    
    _instance = None
    _tools: Dict[str, ToolConfig] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._tools = {}
        return cls._instance
    
    @classmethod
    def register(cls, config: ToolConfig) -> None:
        """注册工具"""
        cls._tools[config.name] = config
    
    @classmethod
    def get(cls, name: str) -> Optional[ToolConfig]:
        """获取工具配置"""
        return cls._tools.get(name)
    
    @classmethod
    def get_all(cls) -> Dict[str, ToolConfig]:
        """获取所有工具配置"""
        return cls._tools.copy()
    
    @classmethod
    def get_schemas(cls) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI schema（用于 API 调用）"""
        return [config.schema for config in cls._tools.values()]
    
    @classmethod
    def clear(cls) -> None:
        """清空注册表（主要用于测试）"""
        cls._tools = {}
    
    @classmethod
    def is_registered(cls, name: str) -> bool:
        """检查工具是否已注册"""
        return name in cls._tools


def register_tool(
    name: str,
    schema: Dict[str, Any],
    handler: Callable,
    singleton_key: Optional[Callable] = None,
    max_instances: int = 0,
    max_call_pairs: int = 0,
    result_transform: Optional[Callable] = None,
    category: str = "general"
) -> ToolConfig:
    """
    便捷的工具注册函数
    
    Args:
        name: 工具名称
        schema: OpenAI function schema
        handler: 执行函数
        singleton_key: 单例 key 生成函数（相同 key 覆盖）
        max_instances: tool_result 最大数量（仅删 result）
        max_call_pairs: 配对最大数量（同时删 call + result）
        result_transform: 结果转换函数
        category: 工具分类
    
    Returns:
        注册的 ToolConfig 对象
    """
    config = ToolConfig(
        name=name,
        schema=schema,
        handler=handler,
        singleton_key=singleton_key,
        max_instances=max_instances,
        max_call_pairs=max_call_pairs,
        result_transform=result_transform,
        category=category
    )
    ToolRegistry.register(config)
    return config


# === 常用的 singleton_key 生成函数 ===

def key_by_arg(arg_name: str) -> Callable:
    """根据指定参数生成 key"""
    def _key_fn(args: dict, result: Any) -> str:
        return str(args.get(arg_name, ""))
    return _key_fn


def key_constant(key: str) -> Callable:
    """返回固定的 key（真正的单例）"""
    def _key_fn(args: dict, result: Any) -> str:
        return key
    return _key_fn


# === 常用的 result_transform 函数 ===

def transform_to_summary(template: str) -> Callable:
    """
    将结果转换为摘要
    
    template 中可以使用 {arg_name} 引用参数
    示例: "✓ 写入 {file_path}"
    """
    def _transform(args: dict, result: Any) -> str:
        try:
            return template.format(**args)
        except KeyError:
            return template
    return _transform


def transform_truncate(max_lines: int = 10, max_chars: int = 2000) -> Callable:
    """截断过长的结果"""
    def _transform(args: dict, result: Any) -> str:
        if not isinstance(result, str):
            result = str(result)
        
        lines = result.split('\n')
        if len(lines) > max_lines:
            truncated = '\n'.join(lines[:max_lines])
            truncated += f"\n... (共 {len(lines)} 行，已截断)"
            result = truncated
        
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n... (共 {len(result)} 字符，已截断)"
        
        return result
    return _transform


if __name__ == "__main__":
    # 简单测试
    print("=== 工具注册系统测试 ===")
    
    # 模拟注册一个工具
    test_config = register_tool(
        name="test_tool",
        schema={"type": "function", "function": {"name": "test_tool"}},
        handler=lambda: "test",
        singleton_key=key_constant("test"),
        max_instances=3
    )
    
    print(f"注册工具: {test_config.name}")
    print(f"已注册: {ToolRegistry.is_registered('test_tool')}")
    print(f"获取配置: {ToolRegistry.get('test_tool')}")
    print(f"所有 schema: {ToolRegistry.get_schemas()}")
    
    # 清理
    ToolRegistry.clear()
    print("测试完成")
