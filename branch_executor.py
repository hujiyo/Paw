#!/usr/bin/env python
"""
分支执行器 - Branch Executor

负责在上下文编辑分支中执行LLM调用和工具调用。
这是一个独立的执行环境，与主分支完全隔离。
"""

import json
import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

from context_branch import ContextBranch, ContextBranchManager, BranchTrigger
from chunk_system import ChunkType
from tool_registry import ToolRegistry
from tool_definitions import register_branch_tools, activate_branch_mode, deactivate_branch_mode
from call import LLMClient, LLMConfig


@dataclass
class BranchExecutorConfig:
    """分支执行器配置"""
    api_url: str
    model: str
    api_key: Optional[str] = None
    max_iterations: int = 10  # 最大迭代次数
    temperature: float = 0.3  # 较低温度，更精确的编辑


class BranchExecutor:
    """
    分支执行器
    
    在隔离的分支环境中执行上下文编辑任务。
    使用与主分支相同的LLM，但使用专门的工具集。
    """
    
    def __init__(self, 
                 branch: ContextBranch,
                 config: BranchExecutorConfig,
                 ui_callback: Optional[Callable[[str], None]] = None):
        """
        初始化分支执行器
        
        Args:
            branch: 上下文编辑分支
            config: 执行器配置
            ui_callback: UI回调函数（用于显示进度）
        """
        self.branch = branch
        self.config = config
        self.ui_callback = ui_callback or print
        
        # 注册分支工具到 ToolRegistry（如果还没注册）
        if not ToolRegistry.is_registered("view_chunk_detail"):
            register_branch_tools(branch)
        else:
            # 已注册，更新 handler 指向新的 branch 实例
            self._update_branch_handlers(branch)
        
        # 激活分支模式（禁用主工具，启用分支工具）
        activate_branch_mode()
    
    def _log(self, message: str):
        """输出日志"""
        self.ui_callback(f"[分支] {message}")
    
    def _update_branch_handlers(self, branch: ContextBranch):
        """更新分支工具的 handler 指向新的 branch 实例"""
        handler_map = {
            "view_chunk_detail": branch.view_chunk_detail,
            "compress_chunks": branch.compress_chunks,
            "remove_chunks": branch.remove_chunks,
            "rewrite_chunk": branch.rewrite_chunk,
            "preview_changes": branch.preview_changes,
            "commit_changes": branch.commit_changes,
            "rollback_changes": branch.rollback_changes,
            "exit_branch": branch.exit_branch,
        }
        for name, handler in handler_map.items():
            config = ToolRegistry.get(name)
            if config:
                config.handler = handler
    
    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """执行工具调用（统一使用 ToolRegistry）"""
        config = ToolRegistry.get(tool_name)
        if config is None:
            return json.dumps({"error": f"未知工具: {tool_name}"})
        
        if not config.enabled:
            return json.dumps({"error": f"工具未启用: {tool_name}"})
        
        try:
            result = config.handler(**args)
            # 结果统一转为 JSON 字符串
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False, indent=2)
            return str(result)
        except Exception as e:
            return json.dumps({"error": f"工具执行失败: {str(e)}"})
    
    # ==================== LLM调用 ====================
    
    async def _call_llm(self, messages: List[Dict], tools: List[Dict]) -> Dict[str, Any]:
        """调用LLM（使用统一的 LLMClient）"""
        llm = LLMClient(LLMConfig(
            api_url=self.config.api_url,
            model=self.config.model,
            api_key=self.config.api_key
        ))
        
        response = await llm.chat(
            messages,
            tools=tools,
            tool_choice="auto",
            temperature=self.config.temperature,
            max_tokens=2000,
            stream=False  # 分支执行不需要流式
        )
        
        return {
            "content": response.content,
            "tool_calls": response.tool_calls,
            "finish_reason": response.finish_reason
        }
    
    # ==================== 主执行流程 ====================
    
    async def run(self, 
                  initial_instruction: Optional[str] = None,
                  auto_mode: bool = True) -> Dict[str, Any]:
        """
        运行分支执行器
        
        Args:
            initial_instruction: 初始指令（可选，默认让LLM自主决定）
            auto_mode: 是否自动模式（True=LLM自主完成，False=每步需确认）
            
        Returns:
            执行结果
        """
        self._log("进入上下文编辑模式")
        
        # 获取当前启用的工具 schema（分支工具已在 __init__ 中激活）
        tools = ToolRegistry.get_schemas()
        
        # 初始指令
        if initial_instruction:
            user_message = initial_instruction
        else:
            # 默认指令：让LLM自主分析和优化
            user_message = """请分析当前上下文状态，并进行必要的优化。

工作流程：
1. 分析哪些内容可以压缩、合并或删除
2. 执行必要的编辑操作
3. 使用 preview_changes 预览修改
4. 确认无误后使用 commit_changes 提交
5. 最后使用 exit_branch 退出

请开始。"""
        
        # 添加用户消息到分支
        self.branch.add_branch_message("user", user_message)
        
        # 迭代执行
        iteration = 0
        while iteration < self.config.max_iterations and self.branch.is_active:
            iteration += 1
            self._log(f"迭代 {iteration}/{self.config.max_iterations}")
            
            # 获取分支消息
            messages = self.branch.get_branch_messages()
            
            # 调用LLM
            response = await self._call_llm(messages, tools)
            
            content = response.get("content")
            tool_calls = response.get("tool_calls")
            
            # 添加助手回复（必须包含 tool_calls 以符合 OpenAI 标准）
            if content or tool_calls:
                if content:
                    self._log(f"LLM: {content[:100]}...")
                # 使用 chunk_manager 的标准方法添加，包含 tool_calls
                self.branch.branch_chunk_manager.add_assistant_response(
                    content or "",
                    tool_calls=tool_calls
                )
            
            # 处理工具调用
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    tool_args_str = tc.get("function", {}).get("arguments", "{}")
                    tool_call_id = tc.get("id", "")
                    
                    try:
                        tool_args = json.loads(tool_args_str) if tool_args_str else {}
                    except json.JSONDecodeError:
                        tool_args = {}
                    
                    self._log(f"执行工具: {tool_name}")
                    
                    # 执行工具
                    result = self._execute_tool(tool_name, tool_args)
                    
                    # 添加工具结果到分支消息（使用标准方法）
                    self.branch.branch_chunk_manager.add_tool_result(
                        result,
                        tool_call_id=tool_call_id,
                        tool_name=tool_name
                    )
                    
                    # 检查是否退出
                    if tool_name == "exit_branch":
                        result_data = json.loads(result)
                        if result_data.get("success"):
                            self._log("编辑完成，退出分支")
                            # 恢复主工具模式
                            deactivate_branch_mode()
                            return {
                                "success": True,
                                "iterations": iteration,
                                "committed": self.branch.changes_committed,
                                "operations": len(self.branch.edit_operations)
                            }
            else:
                # 没有工具调用，检查是否应该结束
                if not self.branch.is_active:
                    break
                
                # 如果LLM没有调用工具也没有退出，提醒它
                self.branch.add_branch_message(
                    "user", 
                    "请继续执行编辑操作，或使用 exit_branch 退出编辑模式。"
                )
        
        # 达到最大迭代或异常退出
        self._log(f"分支执行结束（迭代{iteration}次）")
        
        # 恢复主工具模式
        deactivate_branch_mode()
        
        return {
            "success": self.branch.changes_committed,
            "iterations": iteration,
            "committed": self.branch.changes_committed,
            "operations": len(self.branch.edit_operations),
            "reason": "max_iterations" if iteration >= self.config.max_iterations else "branch_closed"
        }


class AutoContextManager:
    """
    自动上下文管理器
    
    监控主分支状态，在适当时机自动触发上下文编辑。
    这是整个系统的入口点。
    """
    
    def __init__(self,
                 chunk_manager,
                 system_prompt_getter: Callable[[], str],
                 api_url: str,
                 model: str,
                 api_key: Optional[str] = None,
                 ui_callback: Optional[Callable[[str], None]] = None,
                 token_threshold: float = 0.7,
                 turn_threshold: int = 20):
        """
        初始化自动上下文管理器
        
        Args:
            chunk_manager: 主分支的ChunkManager
            system_prompt_getter: 获取系统提示词的函数
            api_url: API地址
            model: 模型名称
            api_key: API密钥
            ui_callback: UI回调
            token_threshold: Token使用率阈值
            turn_threshold: 对话轮数阈值
        """
        self.branch_manager = ContextBranchManager(
            main_chunk_manager=chunk_manager,
            system_prompt_getter=system_prompt_getter,
            token_threshold=token_threshold,
            turn_threshold=turn_threshold
        )
        
        self.executor_config = BranchExecutorConfig(
            api_url=api_url,
            model=model,
            api_key=api_key
        )
        
        self.ui_callback = ui_callback or print
        
        # 统计信息
        self.auto_trigger_count = 0
        self.manual_trigger_count = 0
        self.total_tokens_saved = 0
    
    def check_and_trigger(self) -> bool:
        """
        检查是否需要触发上下文编辑
        
        Returns:
            是否触发了编辑
        """
        should_trigger, trigger_reason = self.branch_manager.should_trigger_branch()
        return should_trigger
    
    async def auto_optimize(self, 
                           instruction: Optional[str] = None) -> Dict[str, Any]:
        """
        自动优化上下文
        
        Args:
            instruction: 自定义指令（可选）
            
        Returns:
            优化结果
        """
        # 检查是否需要触发
        should_trigger, trigger_reason = self.branch_manager.should_trigger_branch()
        
        if not should_trigger and instruction is None:
            return {"triggered": False, "reason": "no_need"}
        
        trigger = trigger_reason or BranchTrigger.MANUAL
        
        # 创建分支
        try:
            branch = self.branch_manager.create_branch(trigger)
        except RuntimeError as e:
            return {"triggered": False, "error": str(e)}
        
        # 记录优化前状态
        before_tokens = self.branch_manager.main_chunk_manager.current_tokens
        
        # 创建执行器
        executor = BranchExecutor(
            branch=branch,
            config=self.executor_config,
            ui_callback=self.ui_callback
        )
        
        # 执行优化
        result = await executor.run(initial_instruction=instruction)
        
        # 记录优化后状态
        after_tokens = self.branch_manager.main_chunk_manager.current_tokens
        tokens_saved = before_tokens - after_tokens
        
        # 更新统计
        if trigger == BranchTrigger.MANUAL:
            self.manual_trigger_count += 1
        else:
            self.auto_trigger_count += 1
        
        if tokens_saved > 0:
            self.total_tokens_saved += tokens_saved
        
        # 关闭分支
        self.branch_manager.close_branch()
        
        result["triggered"] = True
        result["trigger_reason"] = trigger.value
        result["tokens_saved"] = tokens_saved
        
        return result
    
    async def manual_optimize(self, instruction: str = None) -> Dict[str, Any]:
        """
        手动触发上下文优化
        
        Args:
            instruction: 自定义指令
            
        Returns:
            优化结果
        """
        return await self.auto_optimize(instruction=instruction or "请优化当前上下文。")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "auto_triggers": self.auto_trigger_count,
            "manual_triggers": self.manual_trigger_count,
            "total_tokens_saved": self.total_tokens_saved,
            "branch_history": self.branch_manager.branch_history
        }
