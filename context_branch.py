#!/usr/bin/env python
"""
上下文管理分支系统 - Context Branch System

核心理念：
- 不是让"他者"来编辑上下文，而是克隆一个"自己"来管理"自己"的上下文
- 临时分支完全继承主分支的系统提示词和状态
- 分支内的编辑操作完成后，只保留对主上下文的修改，分支本身完全回退
- 主分支的LLM永远与上下文管理机制相互隔离

架构：
┌─────────────────────────────────────────────────────────────┐
│                        主分支 (Main Branch)                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ System  │→ │ User 1  │→ │ Asst 1  │→ │ User 2  │→ ...   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
│                              ↓ 触发分支                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              临时分支 (Context Edit Branch)            │  │
│  │  ┌─────────┐  ┌─────────────┐  ┌──────────────────┐  │  │
│  │  │ System  │→ │ 编辑指令注入 │→ │ Skills文档加载  │  │  │
│  │  │ (克隆)  │  │             │  │                  │  │  │
│  │  └─────────┘  └─────────────┘  └──────────────────┘  │  │
│  │                      ↓                                │  │
│  │  LLM使用特殊工具编辑主分支上下文                        │  │
│  │                      ↓                                │  │
│  │  分支结束，所有分支内容回退，只保留对主分支的修改        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
"""

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path
from enum import Enum

from chunk_system import ChunkManager, ChunkType, Chunk


class BranchTrigger(Enum):
    """分支触发条件"""
    TOKEN_THRESHOLD = "token_threshold"      # Token数量超过阈值
    TURN_COUNT = "turn_count"                # 对话轮数达到阈值
    MANUAL = "manual"                        # 手动触发
    QUALITY_DECAY = "quality_decay"          # 检测到回复质量下降
    TOPIC_SHIFT = "topic_shift"              # 话题发生重大转移


@dataclass
class BranchContext:
    """分支上下文快照"""
    chunks_snapshot: List[Dict[str, Any]]    # 主分支chunks的深拷贝
    system_prompt: str                        # 系统提示词
    timestamp: datetime = field(default_factory=datetime.now)
    trigger: BranchTrigger = BranchTrigger.MANUAL
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class EditOperation:
    """上下文编辑操作记录"""
    operation: str           # compress, remove, rewrite, merge, summarize
    target_indices: List[int]  # 目标chunk索引
    params: Dict[str, Any]   # 操作参数
    result: str = ""         # 操作结果描述
    timestamp: datetime = field(default_factory=datetime.now)


class ContextBranch:
    """
    上下文管理分支
    
    这是一个临时的、隔离的执行环境，用于让"克隆的自己"来编辑主上下文。
    分支结束后，只有对主上下文的修改会被保留，分支本身的所有内容都会回退。
    """
    
    # 分支专用系统提示词模板（注入时会带上上下文概览）
    BRANCH_SYSTEM_INJECTION_TEMPLATE = """
# 上下文编辑模式 (CONTEXT EDIT MODE)
<context_edit_mode>
你现在进入了**上下文编辑模式**。这是一个特殊的临时分支。

## 你的任务
审视和优化当前对话的上下文，使其更加精炼、高效。

## 核心原则
1. **保留价值**: 保留对当前任务有价值的信息，移除冗余和过时内容
2. **压缩智慧**: 将冗长对话压缩为精炼摘要，保留关键信息
3. **谨慎删除**: 删除前三思，某些看似无用的信息可能在后续有价值

## 可用工具
- `compress_chunks`: 将多个chunk压缩为摘要
- `remove_chunks`: 移除不需要的chunk
- `rewrite_chunk`: 重写单个chunk内容
- `view_chunk_detail`: 查看单个chunk完整内容
- `commit_changes`: 提交修改
- `exit_branch`: 退出编辑模式

## 工作流程
1. 分析下方的上下文概览，确定哪些内容可以优化
2. 使用编辑工具进行操作
3. 使用 `commit_changes` 提交修改
4. 使用 `exit_branch` 退出

## 注意
- 编辑完成后，这个分支会完全消失
- 主分支的“我”不会知道你做了什么，只会感受到上下文变得更清晰了
</context_edit_mode>

## 当前上下文概览
{context_overview}
"""

    def __init__(self, 
                 main_chunk_manager: ChunkManager,
                 system_prompt: str,
                 trigger: BranchTrigger = BranchTrigger.MANUAL,
                 skills_path: Optional[Path] = None):
        """
        初始化上下文编辑分支
        
        Args:
            main_chunk_manager: 主分支的ChunkManager（将被编辑）
            system_prompt: 主分支的系统提示词
            trigger: 触发原因
            skills_path: Skills文档路径
        """
        self.main_chunk_manager = main_chunk_manager
        self.original_system_prompt = system_prompt
        self.trigger = trigger
        self.skills_path = skills_path or Path(__file__).parent / "context_skills.md"
        
        # 创建分支上下文快照（用于回滚）
        self.branch_context = BranchContext(
            chunks_snapshot=self._snapshot_chunks(),
            system_prompt=system_prompt,
            trigger=trigger
        )
        
        # 分支内的ChunkManager（独立的，用于分支对话）
        # 分支模式扩展到128K，因为需要处理大量编辑操作
        self.branch_chunk_manager = ChunkManager(
            max_tokens=128000,  # 128K for branch mode
            tools_schema=[]  # 分支使用专门的工具集
        )
        
        # 初始化分支的系统提示词
        self._init_branch_system_prompt()
        
        # 编辑操作记录
        self.edit_operations: List[EditOperation] = []
        
        # 待提交的修改（暂存区）
        self.pending_changes: List[Dict[str, Any]] = []
        
        # 分支状态
        self.is_active = True
        self.changes_committed = False
    
    def _snapshot_chunks(self) -> List[Dict[str, Any]]:
        """创建chunks的深拷贝快照"""
        return [
            {
                "content": chunk.content,
                "chunk_type": chunk.chunk_type.value,
                "timestamp": chunk.timestamp.isoformat(),
                "tokens": chunk.tokens,
                "metadata": copy.deepcopy(chunk.metadata)
            }
            for chunk in self.main_chunk_manager.chunks
        ]
    
    def _init_branch_system_prompt(self):
        """初始化分支的系统提示词（包含上下文概览）"""
        # 生成上下文概览
        context_overview = self._generate_context_overview()
        
        # 加载Skills文档
        skills_content = self._load_skills()
        
        # 组合分支系统提示词（注入时直接带上下文概览）
        branch_injection = self.BRANCH_SYSTEM_INJECTION_TEMPLATE.format(
            context_overview=context_overview
        )
        
        branch_prompt = (
            self.original_system_prompt + 
            "\n\n" + 
            branch_injection +
            "\n\n" +
            skills_content
        )
        
        self.branch_chunk_manager.add_system_prompt(branch_prompt)
    
    def _generate_context_overview(self) -> str:
        """生成上下文概览（直接嵌入系统提示词）"""
        lines = []
        total_tokens = 0
        
        for i, chunk in enumerate(self.main_chunk_manager.chunks):
            if chunk.chunk_type == ChunkType.SYSTEM:
                continue
            
            preview = self._get_preview(chunk.content, 80)
            lines.append(f"[{i}] {chunk.chunk_type.value} ({chunk.tokens}t): {preview}")
            total_tokens += chunk.tokens
        
        max_tokens = self.main_chunk_manager.max_tokens
        usage = total_tokens / max_tokens * 100
        
        header = f"总计: {len(lines)} chunks, {total_tokens}/{max_tokens} tokens ({usage:.1f}%)\n"
        return header + "\n".join(lines)
    
    def _load_skills(self) -> str:
        """加载上下文编辑Skills文档"""
        if self.skills_path.exists():
            try:
                with open(self.skills_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return f"\n# 上下文编辑专家知识 (CONTEXT EDITING SKILLS)\n<skills>\n{content}\n</skills>"
            except Exception as e:
                return f"\n[Skills文档加载失败: {e}]"
        return "\n[Skills文档不存在，使用默认编辑策略]"
    
    # ==================== 上下文查看工具 ====================
    
    def view_context(self, 
                     show_tokens: bool = True,
                     show_metadata: bool = False) -> Dict[str, Any]:
        """
        查看当前主分支上下文状态
        
        Returns:
            上下文概览，包含每个chunk的摘要信息
        """
        chunks_info = []
        total_tokens = 0
        
        for i, chunk in enumerate(self.main_chunk_manager.chunks):
            # 跳过系统提示词（不可编辑）
            if chunk.chunk_type == ChunkType.SYSTEM:
                continue
            
            info = {
                "index": i,
                "type": chunk.chunk_type.value,
                "preview": self._get_preview(chunk.content, 100),
                "tokens": chunk.tokens,
                "timestamp": chunk.timestamp.strftime("%H:%M:%S")
            }
            
            if show_metadata and chunk.metadata:
                info["metadata"] = chunk.metadata
            
            chunks_info.append(info)
            total_tokens += chunk.tokens
        
        return {
            "total_chunks": len(chunks_info),
            "total_tokens": total_tokens,
            "max_tokens": self.main_chunk_manager.max_tokens,
            "usage_ratio": f"{total_tokens / self.main_chunk_manager.max_tokens * 100:.1f}%",
            "chunks": chunks_info
        }
    
    def view_chunk_detail(self, index: int) -> Dict[str, Any]:
        """
        查看指定chunk的完整内容
        
        Args:
            index: chunk索引
            
        Returns:
            chunk详细信息
        """
        if index < 0 or index >= len(self.main_chunk_manager.chunks):
            return {"error": f"索引 {index} 超出范围"}
        
        chunk = self.main_chunk_manager.chunks[index]
        
        return {
            "index": index,
            "type": chunk.chunk_type.value,
            "content": chunk.content,
            "tokens": chunk.tokens,
            "timestamp": chunk.timestamp.isoformat(),
            "metadata": chunk.metadata
        }
    
    # ==================== 上下文编辑工具 ====================
    
    def compress_chunks(self, 
                        indices: List[int], 
                        summary: str,
                        keep_original: bool = False) -> Dict[str, Any]:
        """
        压缩多个chunk为一个摘要
        
        Args:
            indices: 要压缩的chunk索引列表
            summary: 压缩后的摘要内容
            keep_original: 是否保留原始内容（作为metadata）
            
        Returns:
            操作结果
        """
        # 验证索引
        valid_indices = []
        for idx in sorted(indices):
            if 0 <= idx < len(self.main_chunk_manager.chunks):
                chunk = self.main_chunk_manager.chunks[idx]
                if chunk.chunk_type != ChunkType.SYSTEM:
                    valid_indices.append(idx)
        
        if not valid_indices:
            return {"success": False, "error": "没有有效的可压缩chunk"}
        
        # 记录操作
        operation = EditOperation(
            operation="compress",
            target_indices=valid_indices,
            params={"summary": summary, "keep_original": keep_original}
        )
        
        # 添加到待提交队列
        self.pending_changes.append({
            "type": "compress",
            "indices": valid_indices,
            "summary": summary,
            "keep_original": keep_original
        })
        
        self.edit_operations.append(operation)
        
        return {
            "success": True,
            "message": f"已将 {len(valid_indices)} 个chunk标记为压缩",
            "compressed_indices": valid_indices,
            "pending": True  # 表示尚未提交
        }
    
    def remove_chunks(self, indices: List[int]) -> Dict[str, Any]:
        """
        移除指定的chunks
        
        Args:
            indices: 要移除的chunk索引列表
            
        Returns:
            操作结果
        """
        valid_indices = []
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self.main_chunk_manager.chunks):
                chunk = self.main_chunk_manager.chunks[idx]
                if chunk.chunk_type != ChunkType.SYSTEM:
                    valid_indices.append(idx)
        
        if not valid_indices:
            return {"success": False, "error": "没有有效的可移除chunk"}
        
        operation = EditOperation(
            operation="remove",
            target_indices=valid_indices,
            params={}
        )
        
        self.pending_changes.append({
            "type": "remove",
            "indices": valid_indices
        })
        
        self.edit_operations.append(operation)
        
        return {
            "success": True,
            "message": f"已将 {len(valid_indices)} 个chunk标记为移除",
            "removed_indices": valid_indices,
            "pending": True
        }
    
    def rewrite_chunk(self, index: int, new_content: str) -> Dict[str, Any]:
        """
        重写指定chunk的内容
        
        Args:
            index: chunk索引
            new_content: 新内容
            
        Returns:
            操作结果
        """
        if index < 0 or index >= len(self.main_chunk_manager.chunks):
            return {"success": False, "error": f"索引 {index} 超出范围"}
        
        chunk = self.main_chunk_manager.chunks[index]
        if chunk.chunk_type == ChunkType.SYSTEM:
            return {"success": False, "error": "不能编辑系统提示词"}
        
        operation = EditOperation(
            operation="rewrite",
            target_indices=[index],
            params={"new_content": new_content, "old_content": chunk.content}
        )
        
        self.pending_changes.append({
            "type": "rewrite",
            "index": index,
            "new_content": new_content
        })
        
        self.edit_operations.append(operation)
        
        return {
            "success": True,
            "message": f"已将chunk {index} 标记为重写",
            "old_tokens": chunk.tokens,
            "new_tokens": len(new_content) // 4,
            "pending": True
        }
    
    # ==================== 预览与提交 ====================
    
    def preview_changes(self) -> Dict[str, Any]:
        """
        预览待提交的修改
        
        Returns:
            修改预览
        """
        if not self.pending_changes:
            return {"message": "没有待提交的修改"}
        
        preview = {
            "total_operations": len(self.pending_changes),
            "operations": []
        }
        
        for change in self.pending_changes:
            op_preview = {
                "type": change["type"],
            }
            
            if change["type"] == "compress":
                op_preview["indices"] = change["indices"]
                op_preview["summary_preview"] = self._get_preview(change["summary"], 100)
            elif change["type"] == "remove":
                op_preview["indices"] = change["indices"]
            elif change["type"] == "rewrite":
                op_preview["index"] = change["index"]
                op_preview["new_content_preview"] = self._get_preview(change["new_content"], 100)
            
            preview["operations"].append(op_preview)
        
        # 估算token变化
        current_tokens = sum(c.tokens for c in self.main_chunk_manager.chunks 
                            if c.chunk_type != ChunkType.SYSTEM)
        estimated_new_tokens = self._estimate_new_tokens()
        
        preview["token_change"] = {
            "before": current_tokens,
            "after": estimated_new_tokens,
            "saved": current_tokens - estimated_new_tokens
        }
        
        return preview
    
    def commit_changes(self) -> Dict[str, Any]:
        """
        提交所有待处理的修改到主分支
        
        Returns:
            提交结果
        """
        if not self.pending_changes:
            return {"success": False, "error": "没有待提交的修改"}
        
        if self.changes_committed:
            return {"success": False, "error": "修改已提交，不能重复提交"}
        
        # 记录修改前状态
        before_tokens = sum(c.tokens for c in self.main_chunk_manager.chunks)
        before_count = len(self.main_chunk_manager.chunks)
        
        # 按类型分组处理（需要按特定顺序执行）
        # 1. 先处理重写
        # 2. 然后处理压缩
        # 3. 最后处理删除
        
        try:
            # 处理重写
            for change in self.pending_changes:
                if change["type"] == "rewrite":
                    idx = change["index"]
                    if 0 <= idx < len(self.main_chunk_manager.chunks):
                        self.main_chunk_manager.edit_chunk_content(idx, change["new_content"])
            
            # 收集所有要删除的索引（来自compress、remove）
            indices_to_remove = set()
            
            # 处理压缩
            for change in self.pending_changes:
                if change["type"] == "compress":
                    indices = change["indices"]
                    if indices:
                        # 在第一个位置插入摘要
                        first_idx = min(indices)
                        self.main_chunk_manager.edit_chunk_content(first_idx, change["summary"])
                        self.main_chunk_manager.chunks[first_idx].metadata["compressed_from"] = indices
                        # 标记其他索引为删除
                        indices_to_remove.update(indices[1:] if len(indices) > 1 else [])
            
            # 处理删除
            for change in self.pending_changes:
                if change["type"] == "remove":
                    indices_to_remove.update(change["indices"])
            
            # 执行删除（从后往前删除，避免索引偏移）
            for idx in sorted(indices_to_remove, reverse=True):
                if 0 <= idx < len(self.main_chunk_manager.chunks):
                    chunk = self.main_chunk_manager.chunks[idx]
                    if chunk.chunk_type != ChunkType.SYSTEM:
                        self.main_chunk_manager.delete_chunk(idx)
            
            # 记录修改后状态
            after_tokens = sum(c.tokens for c in self.main_chunk_manager.chunks)
            after_count = len(self.main_chunk_manager.chunks)
            
            self.changes_committed = True
            self.pending_changes = []
            
            return {
                "success": True,
                "message": "修改已提交",
                "stats": {
                    "chunks_before": before_count,
                    "chunks_after": after_count,
                    "chunks_removed": before_count - after_count,
                    "tokens_before": before_tokens,
                    "tokens_after": after_tokens,
                    "tokens_saved": before_tokens - after_tokens
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"提交失败: {str(e)}"}
    
    def rollback_changes(self) -> Dict[str, Any]:
        """
        回滚所有待提交的修改
        
        Returns:
            回滚结果
        """
        count = len(self.pending_changes)
        self.pending_changes = []
        
        return {
            "success": True,
            "message": f"已回滚 {count} 个待提交的修改"
        }
    
    def exit_branch(self) -> Dict[str, Any]:
        """
        退出编辑分支
        
        Returns:
            退出结果，包含编辑统计
        """
        if not self.is_active:
            return {"success": False, "error": "分支已关闭"}
        
        # 如果有未提交的修改，提醒用户
        if self.pending_changes:
            return {
                "success": False,
                "error": "还有未提交的修改",
                "pending_count": len(self.pending_changes),
                "hint": "请先使用 commit_changes 提交或 rollback_changes 回滚"
            }
        
        self.is_active = False
        
        return {
            "success": True,
            "message": "已退出上下文编辑模式",
            "operations_count": len(self.edit_operations),
            "changes_committed": self.changes_committed
        }
    
    # ==================== 辅助方法 ====================
    
    def _get_preview(self, content: str, max_length: int = 50) -> str:
        """获取内容预览"""
        content = content.replace('\n', ' ').strip()
        if len(content) > max_length:
            return content[:max_length - 3] + "..."
        return content
    
    def _estimate_new_tokens(self) -> int:
        """估算修改后的token数"""
        # 简单估算：当前tokens - 删除的 + 新增的
        current = sum(c.tokens for c in self.main_chunk_manager.chunks 
                     if c.chunk_type != ChunkType.SYSTEM)
        
        removed = 0
        added = 0
        
        for change in self.pending_changes:
            if change["type"] == "remove":
                for idx in change["indices"]:
                    if 0 <= idx < len(self.main_chunk_manager.chunks):
                        removed += self.main_chunk_manager.chunks[idx].tokens
            
            elif change["type"] == "compress":
                for idx in change["indices"]:
                    if 0 <= idx < len(self.main_chunk_manager.chunks):
                        removed += self.main_chunk_manager.chunks[idx].tokens
                added += len(change["summary"]) // 4
            
            elif change["type"] == "rewrite":
                idx = change["index"]
                if 0 <= idx < len(self.main_chunk_manager.chunks):
                    removed += self.main_chunk_manager.chunks[idx].tokens
                added += len(change["new_content"]) // 4
        
        return max(0, current - removed + added)
    
    def get_branch_messages(self) -> List[Dict[str, Any]]:
        """获取分支的消息列表（用于LLM调用）"""
        return self.branch_chunk_manager.get_context_for_llm()
    
    def add_branch_message(self, role: str, content: str):
        """添加分支内的消息"""
        if role == "user":
            self.branch_chunk_manager.add_user_input(content)
        elif role == "assistant":
            self.branch_chunk_manager.add_assistant_response(content)


class ContextBranchManager:
    """
    上下文分支管理器
    
    负责：
    1. 监控主分支状态，判断是否需要触发编辑分支
    2. 创建和管理编辑分支
    3. 提供分支专用的工具集
    """
    
    # 默认触发阈值
    DEFAULT_TOKEN_THRESHOLD = 0.7  # 70% token使用率
    DEFAULT_TURN_THRESHOLD = 20    # 20轮对话
    
    def __init__(self, 
                 main_chunk_manager: ChunkManager,
                 system_prompt_getter: Callable[[], str],
                 token_threshold: float = DEFAULT_TOKEN_THRESHOLD,
                 turn_threshold: int = DEFAULT_TURN_THRESHOLD):
        """
        初始化分支管理器
        
        Args:
            main_chunk_manager: 主分支的ChunkManager
            system_prompt_getter: 获取当前系统提示词的函数
            token_threshold: Token使用率阈值
            turn_threshold: 对话轮数阈值
        """
        self.main_chunk_manager = main_chunk_manager
        self.system_prompt_getter = system_prompt_getter
        self.token_threshold = token_threshold
        self.turn_threshold = turn_threshold
        
        # 当前活跃的分支
        self.active_branch: Optional[ContextBranch] = None
        
        # 分支历史记录
        self.branch_history: List[Dict[str, Any]] = []
    
    def should_trigger_branch(self) -> Tuple[bool, Optional[BranchTrigger]]:
        """
        检查是否应该触发编辑分支
        
        Returns:
            (是否触发, 触发原因)
        """
        # 检查token使用率
        total_tokens = self.main_chunk_manager.current_tokens
        max_tokens = self.main_chunk_manager.max_tokens
        
        if total_tokens / max_tokens >= self.token_threshold:
            return True, BranchTrigger.TOKEN_THRESHOLD
        
        # 检查对话轮数
        user_turns = sum(1 for c in self.main_chunk_manager.chunks 
                        if c.chunk_type == ChunkType.USER)
        
        if user_turns >= self.turn_threshold:
            return True, BranchTrigger.TURN_COUNT
        
        return False, None
    
    def create_branch(self, 
                      trigger: BranchTrigger = BranchTrigger.MANUAL) -> ContextBranch:
        """
        创建新的编辑分支
        
        Args:
            trigger: 触发原因
            
        Returns:
            新创建的分支
        """
        if self.active_branch and self.active_branch.is_active:
            raise RuntimeError("已有活跃的编辑分支，请先关闭")
        
        self.active_branch = ContextBranch(
            main_chunk_manager=self.main_chunk_manager,
            system_prompt=self.system_prompt_getter(),
            trigger=trigger
        )
        
        return self.active_branch
    
    def close_branch(self) -> Dict[str, Any]:
        """
        关闭当前分支
        
        Returns:
            关闭结果
        """
        if not self.active_branch:
            return {"success": False, "error": "没有活跃的分支"}
        
        result = self.active_branch.exit_branch()
        
        if result["success"]:
            # 记录到历史
            self.branch_history.append({
                "timestamp": datetime.now().isoformat(),
                "trigger": self.active_branch.trigger.value,
                "operations": len(self.active_branch.edit_operations),
                "committed": self.active_branch.changes_committed
            })
            
            self.active_branch = None
        
        return result
    
    def get_branch_tools_schema(self) -> List[Dict[str, Any]]:
        """
        获取分支专用的工具定义
        
        Returns:
            OpenAI格式的工具定义列表
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "view_chunk_detail",
                    "description": "查看指定chunk的完整内容（概览已在系统提示词中）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "index": {
                                "type": "integer",
                                "description": "chunk索引"
                            }
                        },
                        "required": ["index"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "compress_chunks",
                    "description": "将多个chunk压缩为一个摘要。适用于冗长的对话历史",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indices": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "要压缩的chunk索引列表"
                            },
                            "summary": {
                                "type": "string",
                                "description": "压缩后的摘要内容"
                            },
                            "keep_original": {
                                "type": "boolean",
                                "description": "是否在metadata中保留原始内容",
                                "default": False
                            }
                        },
                        "required": ["indices", "summary"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "remove_chunks",
                    "description": "移除指定的chunks。适用于不再需要的对话内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "indices": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "要移除的chunk索引列表"
                            }
                        },
                        "required": ["indices"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "rewrite_chunk",
                    "description": "重写指定chunk的内容。适用于优化冗长或不清晰的内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "index": {
                                "type": "integer",
                                "description": "chunk索引"
                            },
                            "new_content": {
                                "type": "string",
                                "description": "新内容"
                            }
                        },
                        "required": ["index", "new_content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "preview_changes",
                    "description": "预览所有待提交的修改",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "commit_changes",
                    "description": "提交所有待处理的修改到主分支",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "rollback_changes",
                    "description": "回滚所有待提交的修改",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "exit_branch",
                    "description": "退出上下文编辑模式，返回主对话",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("=== 上下文分支系统测试 ===\n")
    
    # 创建测试用的ChunkManager
    cm = ChunkManager(max_tokens=10000)
    cm.add_system_prompt("我是Paw，一个AI助手。")
    cm.add_user_input("你好，请帮我写一个Python函数")
    cm.add_assistant_response("好的，我来帮你写一个函数...")
    cm.add_user_input("这个函数需要处理文件")
    cm.add_assistant_response("明白了，这是处理文件的函数：\n```python\ndef process_file(path):\n    ...\n```")
    cm.add_user_input("再加一个错误处理")
    cm.add_assistant_response("已添加错误处理：\n```python\ntry:\n    ...\nexcept Exception as e:\n    ...\n```")
    
    print(f"[主分支] 当前chunks数量: {len(cm.chunks)}")
    print(f"[主分支] 当前tokens: {cm.current_tokens}")
    
    # 创建分支管理器
    manager = ContextBranchManager(
        main_chunk_manager=cm,
        system_prompt_getter=lambda: "我是Paw，一个AI助手。"
    )
    
    # 创建编辑分支
    branch = manager.create_branch(BranchTrigger.MANUAL)
    print(f"\n[分支] 已创建编辑分支")
    
    # 上下文概览已自动嵌入系统提示词，无需单独调用view_context
    print(f"\n[分支] 上下文概览已嵌入系统提示词")
    
    # 压缩操作
    result = branch.compress_chunks(
        indices=[2, 3, 4, 5],
        summary="用户请求编写一个带错误处理的文件处理Python函数，已完成实现。"
    )
    print(f"\n[分支] 压缩操作: {result['message']}")
    
    # 预览修改
    preview = branch.preview_changes()
    print(f"\n[分支] 修改预览:")
    print(f"  - Token变化: {preview['token_change']['before']} -> {preview['token_change']['after']}")
    print(f"  - 节省: {preview['token_change']['saved']} tokens")
    
    # 提交修改
    commit_result = branch.commit_changes()
    print(f"\n[分支] 提交结果: {commit_result['message']}")
    print(f"  - Chunks: {commit_result['stats']['chunks_before']} -> {commit_result['stats']['chunks_after']}")
    
    # 退出分支
    exit_result = branch.exit_branch()
    print(f"\n[分支] 退出: {exit_result['message']}")
    
    # 查看主分支状态
    print(f"\n[主分支] 修改后chunks数量: {len(cm.chunks)}")
    print(f"[主分支] 修改后tokens: {cm.current_tokens}")
