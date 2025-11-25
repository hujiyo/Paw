#!/usr/bin/env python
"""
AutoStatus - 动态状态评估模块
通过独立的API调用评估AI的当前状态，并注入到系统提示词中
"""

import json
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime


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
            "fatigue": 0.0,                # 疲劳度: 0.0-1.0
            "recent_focus": "系统初始化"     # 最近焦点
        }
        
        # 状态历史（保留最近5个状态）
        self.state_history = []
        self.conversation_rounds = 0
        
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
        
        # 构建提示词
        prompt = f"""你是一个状态评估器，需要根据对话内容和执行结果评估AI的当前状态。

最近对话：
{history_text if history_text else "（无对话）"}

工具调用结果：
{tools_text if tools_text else "（无工具调用）"}

之前的状态：
{json.dumps(self.current_state, ensure_ascii=False, indent=2)}

已进行 {self.conversation_rounds} 轮对话

评估规则：
1. cognitive_load（认知负载）:
   - low: 简单查询、单一操作
   - medium: 常规任务、多步操作
   - high: 复杂调试、多重错误、嵌套问题

2. execution_mode（执行模式）:
   - exploring: 初次了解、搜索信息
   - analyzing: 分析问题、理解需求
   - executing: 执行任务、修改文件
   - optimizing: 优化代码、改进方案

3. confidence（置信度）0-1:
   - 成功操作 +0.1
   - 失败操作 -0.2
   - 连续成功 额外+0.1
   - 保持在[0.0, 1.0]范围

4. fatigue（疲劳度）0-1:
   - 每轮对话 +0.1
   - 遇到错误 +0.2
   - 成功完成任务 -0.1
   - 保持在[0.0, 1.0]范围

5. recent_focus（最近焦点）:
   - 用2-4个字概括刚才的任务类型
   - 例如：代码调试、文件创建、错误分析、优化算法

请直接输出JSON格式的新状态，不要任何解释或其他内容：
{{
    "cognitive_load": "low/medium/high",
    "execution_mode": "exploring/analyzing/executing/optimizing",
    "confidence": 0.0-1.0,
    "fatigue": 0.0-1.0,
    "recent_focus": "2-4个字"
}}"""
        
        return prompt
    
    async def _call_api_for_state(self, prompt: str) -> Dict[str, Any]:
        """
        调用API获取状态评估
        """
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个精确的状态评估器。只输出JSON，不要解释。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,  # 低温度，保证稳定
            "max_tokens": 100
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API调用失败 [{response.status}]: {error_text[:200]}")
                    
                    result = await response.json()
                    
                    # 检查响应结构
                    if result is None:
                        raise Exception("API返回了None响应")
                    
                    if "choices" not in result:
                        raise Exception(f"API响应缺少choices字段，实际响应: {json.dumps(result, ensure_ascii=False)[:200]}")
                    
                    if not result["choices"]:
                        raise Exception("API响应的choices数组为空")
                    
                    if "message" not in result["choices"][0]:
                        raise Exception(f"choices[0]缺少message字段: {json.dumps(result['choices'][0], ensure_ascii=False)[:200]}")
                    
                    content = result["choices"][0]["message"]["content"]
                    
                    # 解析JSON
                    try:
                        # 清理可能的markdown标记
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
                        
        except aiohttp.ClientError as e:
            raise Exception(f"网络请求失败: {str(e)}. 请确认本地模型服务器 ({self.api_url}) 已启动")
    
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
        
        # 验证fatigue（0-1范围）
        fatigue = state.get("fatigue", 0.0)
        if not isinstance(fatigue, (int, float)):
            fatigue = 0.0
        state["fatigue"] = max(0.0, min(1.0, float(fatigue)))
        
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
        # 疲劳度增加
        self.current_state["fatigue"] = min(1.0, self.current_state["fatigue"] + 0.1)
        
        # 置信度略微下降
        self.current_state["confidence"] = max(0.0, self.current_state["confidence"] - 0.05)
        
        # 执行模式回归到exploring
        if self.current_state["fatigue"] > 0.8:
            self.current_state["execution_mode"] = "exploring"
            self.current_state["cognitive_load"] = "low"
        
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
        
        # 根据疲劳度调整策略
        if self.current_state["fatigue"] > 0.7:
            fatigue_strategy = "疲劳较高 - 简化方案，避免复杂操作"
        elif self.current_state["fatigue"] > 0.4:
            fatigue_strategy = "轻微疲劳 - 保持专注，合理分配精力"
        else:
            fatigue_strategy = "精力充沛 - 可处理复杂任务"
        
        return f"""
# 当前状态 (DYNAMIC STATE)
<current_state>
认知负载: {self.current_state['cognitive_load']} - {load_impact}
执行模式: {self.current_state['execution_mode']} - {mode_approach}
置信水平: {self.current_state['confidence']:.1f} - {confidence_style}
疲劳程度: {self.current_state['fatigue']:.1f} - {fatigue_strategy}
任务焦点: {self.current_state['recent_focus']}
对话轮次: 第{self.conversation_rounds}轮

状态影响:
- 回答风格: {'简洁直接' if self.current_state['cognitive_load'] == 'high' else '详细完整'}
- 错误容忍: {'需要更仔细' if self.current_state['fatigue'] > 0.6 else '正常水平'}
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
            "fatigue": 0.0,
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
                f"置信:{self.current_state['confidence']:.1f} | "
                f"疲劳:{self.current_state['fatigue']:.1f}")


# 测试
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # 创建状态管理器
        status = AutoStatus(
            api_url="http://localhost:1234/v1/chat/completions",
            model="test-model"
        )
        
        print("初始状态:")
        print(json.dumps(status.current_state, ensure_ascii=False, indent=2))
        
        # 模拟对话
        history = [
            {"role": "user", "content": "帮我写个Python脚本"},
            {"role": "assistant", "content": "好的，我来帮您写脚本"}
        ]
        
        tools = [
            {"tool": "write_file", "success": True},
            {"tool": "execute_command", "success": False}
        ]
        
        # 评估状态
        new_state = await status.evaluate_state(history, tools)
        print("\n评估后的状态:")
        print(json.dumps(new_state, ensure_ascii=False, indent=2))
        
        # 注入到提示词
        base = "# 身份与角色\n我是Paw\n\n# 环境认知\n工作目录..."
        enhanced = status.inject_to_prompt(base)
        print("\n增强后的提示词:")
        print(enhanced)
    
    # asyncio.run(test())
