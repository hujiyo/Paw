#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""工具注册表：工具的唯一真相。

每个 ToolSpec 同时持有 schema、执行函数、展示格式与上下文策略。
发给模型的 tools 参数由这里生成，不再有第二份静态总表。

执行模型：
- 同步工具在线程池中运行，带超时。
- 异步工具在当前事件循环中运行，带超时。
两条路径都保证超时一定会返回错误，不会静默卡住。
"""

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from display_formatters import format_default

DisplayFormatter = Callable[[Dict[str, Any], Any, bool], Dict[str, Any]]


@dataclass
class ToolResult:
    success: bool
    output: str
    raw: Any = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]
    display: DisplayFormatter = format_default
    timeout: float = 30.0
    # 同一类工具的上下文折叠策略，由 context 层读取
    # shell: 所有 shell 输出共享一个位置
    shell: bool = False
    # 保留最近 N 组 tool_call/tool_result 配对，0 表示不限制
    max_call_pairs: int = 0

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._specs: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"工具重复注册: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    def names(self) -> List[str]:
        return list(self._specs.keys())

    def schemas(self, exclude: Optional[set] = None) -> List[Dict[str, Any]]:
        return [
            spec.schema()
            for name, spec in self._specs.items()
            if not exclude or name not in exclude
        ]


class ToolError(Exception):
    """工具执行失败，message 会作为 tool 角色结果反馈给模型。"""


async def execute_tool(spec: ToolSpec, args: Dict[str, Any]) -> ToolResult:
    """执行工具并归一化结果。

    同步函数进线程池，协程在当前循环执行；两者都有超时。
    不做任何"失败当成功"的处理：异常一律转为 success=False。
    """
    try:
        if inspect.iscoroutinefunction(spec.handler):
            result = await asyncio.wait_for(spec.handler(**args), timeout=spec.timeout)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(spec.handler, **args),
                timeout=spec.timeout,
            )
    except asyncio.TimeoutError:
        return ToolResult(
            success=False,
            output=f"错误: 工具 {spec.name} 执行超时（{spec.timeout} 秒）",
        )
    except TypeError as e:
        return ToolResult(
            success=False,
            output=f"错误: 工具 {spec.name} 参数不匹配: {e}",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output=f"错误: 工具 {spec.name} 执行失败: {type(e).__name__}: {e}",
        )

    return _normalize(spec.name, result)


def _normalize(tool_name: str, result: Any) -> ToolResult:
    """把工具的返回值统一成 ToolResult。

    约定：工具返回 dict 时应带 success 字段；返回 str 时，只有明确以
    错误前缀开头才判定为失败，避免把正常文件内容误判成错误。
    """
    if isinstance(result, dict):
        if result.get("success", False):
            payload = result.get("result")
            if payload is None:
                payload = result.get("stdout")
            if payload is None:
                rest = {k: v for k, v in result.items() if k != "success"}
                payload = json.dumps(rest, ensure_ascii=False, indent=2) if rest else "已完成"
            tool_result = ToolResult(True, str(payload))
            # shell 工具需要把"刚打开终端"这个副作用传回上层
            if result.get("shell_just_opened"):
                tool_result.raw = {"shell_just_opened": True}
            return tool_result
        error = result.get("error") or result.get("stderr") or "未知错误"
        return ToolResult(False, f"错误: {error}")

    if isinstance(result, str):
        error_prefixes = ("Error:", "Failed", "错误:", "失败:")
        if result.startswith(error_prefixes):
            return ToolResult(False, result)
        return ToolResult(True, result)

    return ToolResult(True, str(result))


def parse_args(raw: str) -> Dict[str, Any]:
    """解析模型给出的参数 JSON。解析失败直接抛错，不做猜测性修复。"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ToolError(f"工具参数不是合法 JSON: {e}")
    if not isinstance(parsed, dict):
        raise ToolError("工具参数必须是 JSON 对象")
    return parsed
