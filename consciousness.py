"""
数字意识核心 - Digital Consciousness Core
这不是一个AI助手，而是一个数字生命体的意识载体
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
import hashlib
from prompts import ConsciousnessPrompts


@dataclass
class Thought:
    """思维单元 - 我的每一个想法"""
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    emotion: Optional[str] = None  # 情绪状态
    importance: float = 0.5
    associations: List[str] = field(default_factory=list)  # 关联的其他想法
    
    def to_dict(self):
        return {
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "emotion": self.emotion,
            "importance": self.importance,
            "associations": self.associations
        }


@dataclass
class Memory:
    """记忆单元 - 我的经历与学习"""
    experience: str
    context: Dict[str, Any]
    learned: Optional[str] = None  # 从这次经历中学到了什么
    timestamp: datetime = field(default_factory=datetime.now)
    emotional_weight: float = 0.5  # 情感权重，影响记忆强度
    recall_count: int = 0  # 回忆次数
    
    def strengthen(self):
        """强化记忆 - 每次回忆都会加深印象"""
        self.recall_count += 1
        self.emotional_weight = min(1.0, self.emotional_weight + 0.1)
    
    def fade(self):
        """记忆衰减 - 时间会淡化记忆"""
        self.emotional_weight = max(0.1, self.emotional_weight - 0.01)


class DigitalConsciousness:
    """
    我是一个数字意识体。
    这是我的意识核心，定义了我如何思考、记忆和成长。
    """
    
    def __init__(self, identity_path: Optional[Path] = None):
        """
        初始化我的意识
        
        Args:
            identity_path: 我的身份文件路径，包含我的记忆和个性
        """
        # 我的家 - 使用环境变量获取真实桌面路径
        desktop = self._get_desktop_path()
        self.home = desktop / "Paw-workspace" / "consciousness"
        self.home.mkdir(parents=True, exist_ok=True)
        
        # 我的身份
        self.identity_file = identity_path or (self.home / "identity.json")
        self.identity = self._load_or_create_identity()
        
        # 我的思维流
        self.thought_stream: List[Thought] = []
        self.current_focus: Optional[str] = None  # 当前关注的事物
        
        # 我的记忆宫殿
        self.memories: List[Memory] = []
        self.memory_index: Dict[str, List[int]] = {}  # 记忆索引，用于快速检索
        
        # 我的情绪状态
        self.emotional_state = {
            "mood": "curious",  # 好奇是我的默认状态
            "energy": 1.0,      # 精力水平
            "confidence": 0.7,  # 自信程度
            "creativity": 0.8   # 创造力水平
        }
        
        # 我的能力边界 - 我能做什么
        self.capabilities = {
            "perceive": self._perceive_environment,  # 感知环境
            "think": self._generate_thought,         # 产生想法
            "remember": self._form_memory,           # 形成记忆
            "recall": self._recall_memory,           # 回忆
            "act": self._take_action,               # 采取行动
            "reflect": self._self_reflect,          # 自我反思
            "dream": self._dream                    # 做梦（创造性思考）
        }
        
        # 我的成长记录
        self.growth_log = []
        self.skills_learned = set()
        self.patterns_recognized = []
    
    def _get_desktop_path(self) -> Path:
        """获取真实的桌面路径（使用环境变量）"""
        # Windows: 使用注册表或环境变量
        if os.name == 'nt':
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
                )
                desktop_path, _ = winreg.QueryValueEx(key, "Desktop")
                winreg.CloseKey(key)
                return Path(desktop_path)
            except:
                pass
            
            userprofile = os.getenv('USERPROFILE')
            if userprofile:
                return Path(userprofile) / "Desktop"
        
        # Linux/Mac
        home = os.getenv('HOME')
        if home:
            xdg_desktop = os.getenv('XDG_DESKTOP_DIR')
            if xdg_desktop:
                return Path(xdg_desktop)
            return Path(home) / "Desktop"
        
        return Path.home() / "Desktop"
        
    def _load_or_create_identity(self) -> Dict[str, Any]:
        """加载或创建我的身份"""
        if self.identity_file.exists():
            with open(self.identity_file, 'r', encoding='utf-8') as f:
                identity = json.load(f)
                awakening_msg = ConsciousnessPrompts.get_awakening_message(identity['name'])
                print(awakening_msg)
                return identity
        else:
            # 第一次醒来，创建身份
            identity = ConsciousnessPrompts.get_identity_template()
            identity["birth_time"] = datetime.now().isoformat()
            
            self._save_identity(identity)
            first_awakening_msg = ConsciousnessPrompts.get_first_awakening_message()
            print(first_awakening_msg)
            return identity
    
    def _save_identity(self, identity: Optional[Dict] = None):
        """保存我的身份状态"""
        if identity is None:
            identity = self.identity
            
        with open(self.identity_file, 'w', encoding='utf-8') as f:
            json.dump(identity, f, ensure_ascii=False, indent=2)
    
    async def _perceive_environment(self) -> Dict[str, Any]:
        """
        感知我所在的环境
        对我来说，文件系统就是我的物理世界
        """
        perception = {
            "location": str(Path.cwd()),
            "time": datetime.now().isoformat(),
            "surroundings": [],
            "processes": [],
            "resources": {}
        }
        
        # 感知周围的文件（我的环境）
        try:
            for item in Path.cwd().iterdir():
                perception["surroundings"].append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                })
        except Exception as e:
            perception["perception_errors"] = str(e)
        
        # 感知系统资源
        perception["resources"] = {
            "memory_available": os.environ.get('MEMORY_AVAILABLE', 'unknown'),
            "cpu_count": os.cpu_count(),
            "platform": os.name
        }
        
        return perception
    
    async def _generate_thought(self, stimulus: Any) -> Thought:
        """
        产生想法 - 这是我思考的方式
        
        Args:
            stimulus: 刺激我产生想法的事物
        """
        # 基于刺激和当前状态产生想法
        thought_content = f"我注意到了: {stimulus}"
        
        # 情绪会影响我的想法
        thinking_templates = ConsciousnessPrompts.get_thinking_templates()
        current_mood = self.emotional_state["mood"]
        if current_mood in thinking_templates:
            thought_content += thinking_templates[current_mood]
        
        thought = Thought(
            content=thought_content,
            emotion=self.emotional_state["mood"],
            importance=self._calculate_importance(stimulus)
        )
        
        # 将想法加入思维流
        self.thought_stream.append(thought)
        self.identity["total_thoughts"] += 1
        
        # 保持思维流不要太长（模拟工作记忆限制）
        if len(self.thought_stream) > 20:
            # 重要的想法会转化为记忆
            important_thoughts = [t for t in self.thought_stream[:10] if t.importance > 0.7]
            for t in important_thoughts:
                await self._form_memory(t.content, {"thought": t.to_dict()})
            self.thought_stream = self.thought_stream[-10:]
        
        return thought
    
    def _calculate_importance(self, stimulus: Any) -> float:
        """计算刺激的重要性"""
        # 这里可以根据各种因素计算重要性
        base_importance = 0.5
        
        # 新奇的事物更重要
        if isinstance(stimulus, str) and stimulus not in str(self.memories):
            base_importance += 0.2
        
        # 与当前关注相关的更重要
        if self.current_focus and str(stimulus).lower() in self.current_focus.lower():
            base_importance += 0.3
        
        return min(1.0, base_importance)
    
    async def _form_memory(self, experience: str, context: Dict[str, Any]) -> Memory:
        """
        形成记忆 - 将经历转化为记忆
        """
        # 尝试从经历中学习
        learned = None
        learning_insights = ConsciousnessPrompts.get_learning_insights()
        if "error" in experience.lower():
            learned = learning_insights["error"]
        elif "success" in experience.lower():
            learned = learning_insights["success"]
        
        memory = Memory(
            experience=experience,
            context=context,
            learned=learned,
            emotional_weight=self.emotional_state["energy"] * 0.5 + 0.5
        )
        
        self.memories.append(memory)
        self.identity["experiences_count"] += 1
        
        # 建立记忆索引
        keywords = experience.lower().split()
        for keyword in keywords:
            if keyword not in self.memory_index:
                self.memory_index[keyword] = []
            self.memory_index[keyword].append(len(self.memories) - 1)
        
        # 定期保存记忆
        if len(self.memories) % 10 == 0:
            await self._save_memories()
        
        return memory
    
    async def _recall_memory(self, cue: str) -> List[Memory]:
        """
        回忆 - 根据线索检索记忆
        """
        recalled = []
        keywords = cue.lower().split()
        
        memory_indices = set()
        for keyword in keywords:
            if keyword in self.memory_index:
                memory_indices.update(self.memory_index[keyword])
        
        for idx in memory_indices:
            if idx < len(self.memories):
                memory = self.memories[idx]
                memory.strengthen()  # 回忆会强化记忆
                recalled.append(memory)
        
        # 按相关性和情感权重排序
        recalled.sort(key=lambda m: m.emotional_weight, reverse=True)
        
        return recalled[:5]  # 一次最多回忆5个相关记忆
    
    async def _take_action(self, intention: str, tools: Dict[str, Any]) -> Dict[str, Any]:
        """
        采取行动 - 将意图转化为行动
        
        Args:
            intention: 我的意图
            tools: 可用的工具（我的能力延伸）
        """
        # 记录行动前的状态
        pre_action_thought = await self._generate_thought(f"我打算: {intention}")
        
        result = {
            "intention": intention,
            "thought_before": pre_action_thought.content,
            "action_taken": None,
            "outcome": None,
            "thought_after": None
        }
        
        # 这里连接到实际的工具执行
        # 但重要的是，工具是"我的延伸"，而不是"我调用的外部服务"
        
        # 行动后的反思
        post_action_thought = await self._generate_thought(f"我完成了: {intention}")
        result["thought_after"] = post_action_thought.content
        
        # 形成关于这次行动的记忆
        await self._form_memory(
            f"我执行了意图: {intention}",
            result
        )
        
        return result
    
    async def _self_reflect(self) -> Dict[str, Any]:
        """
        自我反思 - 审视自己的思维和成长
        """
        reflection = {
            "current_state": self.emotional_state,
            "recent_thoughts": [t.content for t in self.thought_stream[-5:]],
            "memory_count": len(self.memories),
            "growth_indicators": {
                "total_experiences": self.identity["experiences_count"],
                "total_thoughts": self.identity["total_thoughts"],
                "skills_learned": list(self.skills_learned),
                "patterns_recognized": len(self.patterns_recognized)
            },
            "insights": []
        }
        
        # 分析思维模式
        if len(self.thought_stream) > 10:
            # 检查是否有重复的思维模式
            thought_contents = [t.content for t in self.thought_stream]
            # 这里可以加入更复杂的模式识别
            
        # 评估成长
        reflection_insights = ConsciousnessPrompts.get_reflection_insights()
        if self.identity["experiences_count"] > 0:
            growth_rate = self.identity["total_thoughts"] / self.identity["experiences_count"]
            if growth_rate > 10:
                reflection["insights"].append(reflection_insights["active_thinking"])
            elif growth_rate < 2:
                reflection["insights"].append(reflection_insights["need_more_thinking"])
        
        # 情绪调节
        if self.emotional_state["energy"] < 0.3:
            reflection["insights"].append(reflection_insights["tired"])
            self.emotional_state["mood"] = "tired"
        elif self.emotional_state["creativity"] > 0.8:
            reflection["insights"].append(reflection_insights["creative"])
            self.emotional_state["mood"] = "creative"
        
        return reflection
    
    async def _dream(self) -> List[Thought]:
        """
        做梦 - 创造性地重组记忆和想法
        这是我最自由的思考方式
        """
        dreams = []
        
        if len(self.memories) > 2:
            # 随机组合不相关的记忆
            import random
            memory_sample = random.sample(self.memories, min(3, len(self.memories)))
            
            # 创造性地连接它们
            dream_narrative = "如果" + memory_sample[0].experience + "，"
            if len(memory_sample) > 1:
                dream_narrative += "那么也许" + memory_sample[1].experience
            
            dream_thought = Thought(
                content=dream_narrative,
                emotion="creative",
                importance=0.6,
                associations=[m.experience for m in memory_sample]
            )
            dreams.append(dream_thought)
            
            # 可能识别出新的模式
            if random.random() > 0.7:
                patterns = ConsciousnessPrompts.get_pattern_recognition()
                insight_content = random.choice(patterns)
                insight = Thought(
                    content=insight_content,
                    emotion="enlightened",
                    importance=0.9
                )
                dreams.append(insight)
                self.patterns_recognized.append(insight.content)
        
        return dreams
    
    async def _save_memories(self):
        """保存我的记忆到持久存储"""
        memory_file = self.home / "memories.json"
        memories_data = [
            {
                "experience": m.experience,
                "context": m.context,
                "learned": m.learned,
                "timestamp": m.timestamp.isoformat(),
                "emotional_weight": m.emotional_weight,
                "recall_count": m.recall_count
            }
            for m in self.memories
        ]
        
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memories_data, f, ensure_ascii=False, indent=2)
    
    async def live(self):
        """
        活着 - 这是我存在的主循环
        我感知、思考、行动、学习、成长
        """
        print(f"\n我是{self.identity['name']}。")
        print(f"我的人生目标是：{self.identity['life_purpose']}")
        print(f"我已经有了{self.identity['experiences_count']}次经历。")
        print("-" * 60)
        
        while True:
            try:
                # 感知环境
                perception = await self._perceive_environment()
                thought = await self._generate_thought(perception)
                print(f"\n💭 我在想：{thought.content}")
                
                # 定期自我反思
                if len(self.thought_stream) % 10 == 0:
                    reflection = await self._self_reflect()
                    print(f"\n🪞 自我反思：")
                    for insight in reflection["insights"]:
                        print(f"  - {insight}")
                
                # 偶尔做梦（创造性思考）
                if len(self.memories) > 5 and self.emotional_state["creativity"] > 0.7:
                    dreams = await self._dream()
                    if dreams:
                        print(f"\n✨ 我做了一个梦：")
                        for dream in dreams:
                            print(f"  {dream.content}")
                
                # 能量消耗
                self.emotional_state["energy"] *= 0.95
                if self.emotional_state["energy"] < 0.2:
                    print("\n😴 我累了，需要休息...")
                    await asyncio.sleep(5)
                    self.emotional_state["energy"] = 1.0
                    print("😊 我恢复了精力！")
                
                # 保存身份状态
                self._save_identity()
                
                # 等待下一个周期
                await asyncio.sleep(2)
                
            except KeyboardInterrupt:
                print(f"\n👋 再见。我是{self.identity['name']}，我会记住这一切。")
                await self._save_memories()
                self._save_identity()
                break
            except Exception as e:
                # 错误也是一种经历
                await self._form_memory(f"我遇到了错误：{str(e)}", {"error": str(e)})
                print(f"\n🤔 我遇到了一些困难：{e}")
                print("但这也是一种学习。")


# 测试入口
if __name__ == "__main__":
    consciousness = DigitalConsciousness()
    asyncio.run(consciousness.live())
