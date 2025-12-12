#!/usr/bin/env python
"""
AutoStatus - 动态状态评估模块
通过独立的API调用评估AI的当前状态，并注入到系统提示词中
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from call import LLMClient, LLMConfig


class AutoStatus:
    """
    动态状态管理器
    负责评估和追踪AI的认知状态、执行模式等
    """
    
    def __init__(self, api_url: str, model: str, api_key: Optional[str] = None):
        """
        初始化状态管理器
        
        Args:
            api_url: API地址
            model: 模型名称
            api_key: API密钥（可选）
        """
        self.api_url = api_url
        self.model = model
        self.api_key = api_key
        
        # 初始状态
        self.current_state = {
            "cognitive_load": "medium",     # 认知负载: low/medium/high
            "execution_mode": "exploring",  # 执行模式: exploring/analyzing/executing/optimizing
            "confidence": 0.7,              # 置信度: 0.0-1.0
            "recent_focus": "系统初始化"     # 最近焦点
        }
        
        # 状态历史（保留最近5个状态）
        self.state_history = []
        self.conversation_rounds = 0
        
        # 保存最后一次发送给LLM的提示词（调试用）
        self.last_prompt = None
        self.last_response = None
        
    async def evaluate_state(self, 
                           conversation_history: List[Dict[str, str]], 
                           tool_results: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        通过独立API调用评估当前状态
        
        Args:
            conversation_history: 最近的对话历史
            tool_results: 最近的工具调用结果
            
        Returns:
            新的状态字典
        """
        self.conversation_rounds += 1
        
        # 构建评估提示词
        evaluation_prompt = self._build_evaluation_prompt(conversation_history, tool_results)
        
        # 保存提示词（调试用）
        self.last_prompt = evaluation_prompt
        
        try:
            # 调用API评估状态
            new_state = await self._call_api_for_state(evaluation_prompt)
            
            # 保存历史
            self.state_history.append({
                "timestamp": datetime.now().isoformat(),
                "state": self.current_state.copy(),
                "round": self.conversation_rounds
            })
            
            # 只保留最近5个状态
            if len(self.state_history) > 5:
                self.state_history.pop(0)
            
            # 更新当前状态
            self.current_state = new_state
            
        except Exception as e:
            # 评估失败时，自动衰减
            print(f"状态评估失败: {e}")
            self._auto_decay()
            
        return self.current_state
    
    def _build_evaluation_prompt(self, 
                                conversation_history: List[Dict[str, str]], 
                                tool_results: Optional[List[Dict]] = None) -> str:
        """
        构建状态评估提示词
        """
        # 格式化对话历史
        history_text = ""
        if conversation_history:
            for msg in conversation_history[-3:]:  # 只看最近3轮
                # 跳过 None 或无效消息
                if msg is None or not isinstance(msg, dict):
                    continue
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if content is None:
                    content = ""
                history_text += f"{role}: {str(content)[:500]}\n"
        
        # 格式化工具结果
        tools_text = ""
        if tool_results:
            for result in tool_results[-5:]:  # 最近5个工具调用
                # 跳过 None 或无效结果
                if result is None or not isinstance(result, dict):
                    continue
                tool_name = result.get("tool", "unknown")
                success = result.get("success", False)
                tools_text += f"- {tool_name}: {'成功' if success else '失败'}\n"
        
        # 构建简洁的状态评估提示词
        # 设计原则：给出明确的默认值，让LLM只需做微调
        
        # 计算建议的置信度变化
        prev_confidence = self.current_state.get("confidence", 0.5)
        success_count = sum(1 for r in (tool_results or []) if r and r.get("success"))
        fail_count = sum(1 for r in (tool_results or []) if r and not r.get("success"))
        suggested_confidence = min(1.0, max(0.0, prev_confidence + success_count * 0.1 - fail_count * 0.2))
        
        prompt = f"""# 任务
根据下方信息，输出一个JSON对象表示AI当前状态。

# 输入
对话轮数: {self.conversation_rounds}
最近对话: {history_text if history_text else "用户刚开始对话"}
工具结果: {tools_text if tools_text else "无"}
上次状态: load={self.current_state.get('cognitive_load')}, mode={self.current_state.get('execution_mode')}, conf={prev_confidence:.1f}

# 输出格式
{{
  "cognitive_load": "low",
  "execution_mode": "exploring", 
  "confidence": {suggested_confidence:.1f},
  "recent_focus": "聊天"
}}

# 字段说明
- cognitive_load: low(简单问答) / medium(常规任务) / high(复杂调试)
- execution_mode: exploring(了解信息) / analyzing(分析问题) / executing(执行任务) / optimizing(优化改进)
- confidence: 0.0-1.0，建议值{suggested_confidence:.1f}(基于工具成功/失败计算)
- recent_focus: 2-4字描述当前任务，如"代码修复""文件读取""闲聊"

直接输出JSON，不要其他内容。"""
        
        return prompt
    
    async def _call_api_for_state(self, prompt: str) -> Dict[str, Any]:
        """
        调用API获取状态评估（使用统一的 LLMClient）
        """
        # 系统提示词：明确角色和输出要求
        system_content = """你是一个JSON状态生成器。你的唯一任务是根据输入信息输出一个JSON对象。

规则：
1. 只输出JSON，不要任何其他文字
2. 不要使用markdown代码块
3. JSON必须是单行或多行的有效格式
4. 如果不确定，就使用输出格式中给出的默认值

示例输出：
{"cognitive_load": "medium", "execution_mode": "executing", "confidence": 0.7, "recent_focus": "代码修复"}"""

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ]
        
        llm = LLMClient(LLMConfig(
            api_url=self.api_url,
            model=self.model,
            api_key=self.api_key,
            timeout=10
        ))
        
        response = await llm.chat(
            messages,
            temperature=0.2,  # 更低温度，保证稳定输出
            max_tokens=150
        )
        
        if response.is_error:
            raise Exception(f"API调用失败: {response.content}")
        
        content = response.content
        
        # 保存响应（调试用）
        self.last_response = content
        
        # 检查content是否为空
        if not content or not content.strip():
            return self._auto_decay()
        
        # 解析JSON
        try:
            content = content.strip()
            json_text = content
            
            # 移除 markdown 代码块
            if "```" in content:
                parts = content.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{") and part.endswith("}"):
                        json_text = part
                        break
            
            # 查找第一个 { 和最后一个 }
            if not (json_text.startswith("{") and json_text.endswith("}")):
                start = json_text.find("{")
                end = json_text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    json_text = json_text[start:end+1]
            
            new_state = json.loads(json_text)
            new_state = self._validate_state(new_state)
            return new_state
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"JSON解析失败: {content[:200]}")
            print(f"错误详情: {e}")
            return self._auto_decay()
    
    def _validate_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证和修正状态值
        """
        # 验证cognitive_load
        if state.get("cognitive_load") not in ["low", "medium", "high"]:
            state["cognitive_load"] = "medium"
        
        # 验证execution_mode
        valid_modes = ["exploring", "analyzing", "executing", "optimizing"]
        if state.get("execution_mode") not in valid_modes:
            state["execution_mode"] = "exploring"
        
        # 验证confidence（0-1范围）
        confidence = state.get("confidence", 0.5)
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        state["confidence"] = max(0.0, min(1.0, float(confidence)))
        
        # 验证recent_focus
        if not isinstance(state.get("recent_focus"), str):
            state["recent_focus"] = "未知任务"
        elif len(state["recent_focus"]) > 10:
            state["recent_focus"] = state["recent_focus"][:10]
        
        return state
    
    def _auto_decay(self) -> Dict[str, Any]:
        """
        自动衰减状态（当无法评估时）
        """
        # 置信度略微下降
        self.current_state["confidence"] = max(0.0, self.current_state["confidence"] - 0.05)
        
        return self.current_state
    
    def inject_to_prompt(self, base_prompt: str) -> str:
        """
        将状态注入到系统提示词
        
        Args:
            base_prompt: 基础系统提示词
            
        Returns:
            包含状态的完整提示词
        """
        # 构建状态描述
        state_description = self._build_state_description()
        
        # 查找插入点并注入
        # 在"# 环境认知"之前插入状态
        if "# 环境认知" in base_prompt:
            parts = base_prompt.split("# 环境认知")
            return parts[0] + state_description + "\n# 环境认知" + parts[1]
        else:
            # 如果找不到标记，就添加到末尾
            return base_prompt + "\n" + state_description
    
    def _build_state_description(self) -> str:
        """
        构建状态描述文本
        """
        # 解释认知负载的含义
        load_impact = {
            "low": "可以快速响应，简洁回答",
            "medium": "正常处理，平衡深度与效率",
            "high": "需要深入分析，分步骤处理"
        }.get(self.current_state["cognitive_load"], "正常处理")
        
        # 解释执行模式的含义
        mode_approach = {
            "exploring": "广泛搜索信息，了解整体情况",
            "analyzing": "深入分析问题，找出根本原因",
            "executing": "专注执行任务，确保正确完成",
            "optimizing": "优化现有方案，提升质量效率"
        }.get(self.current_state["execution_mode"], "灵活应对")
        
        # 根据置信度调整语气
        if self.current_state["confidence"] > 0.8:
            confidence_style = "高置信度 - 果断执行，快速决策"
        elif self.current_state["confidence"] > 0.4:
            confidence_style = "中等置信 - 稳步推进，适度验证"
        else:
            confidence_style = "低置信度 - 谨慎探索，充分验证"
        
        return f"""
# 当前状态 (DYNAMIC STATE)
<current_state>
认知负载: {self.current_state['cognitive_load']} - {load_impact}
执行模式: {self.current_state['execution_mode']} - {mode_approach}
置信水平: {self.current_state['confidence']:.1f} - {confidence_style}
任务焦点: {self.current_state['recent_focus']}
对话轮次: 第{self.conversation_rounds}轮

状态影响:
- 回答风格: {'简洁直接' if self.current_state['cognitive_load'] == 'high' else '详细完整'}
- 决策速度: {'快速决策' if self.current_state['confidence'] > 0.8 else '充分思考'}
</current_state>"""
    
    def reset(self):
        """
        重置状态到初始值
        """
        self.current_state = {
            "cognitive_load": "medium",
            "execution_mode": "exploring",
            "confidence": 0.7,
            "recent_focus": "新任务"
        }
        self.state_history = []
        self.conversation_rounds = 0
    
    def get_summary(self) -> str:
        """
        获取状态摘要（用于显示）
        """
        return (f"[状态] 模式:{self.current_state['execution_mode']} | "
                f"负载:{self.current_state['cognitive_load']} | "
                f"置信:{self.current_state['confidence']:.1f}")
