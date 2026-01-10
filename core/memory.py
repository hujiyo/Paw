#!/usr/bin/env python
"""
Paw 记忆系统 - Memory System v4

核心改动 (v4):
- 移除本地 llama-cpp embedding，改用外部 API
- 支持 Ollama / LM Studio 等本地服务，也支持远程 API
- 记忆系统默认关闭，用户可在设置中启用

架构:
├── Rules (永远注入，用户手动配置)
│   ├── 用户规则: ~/.paw/rules.yaml
│   └── 项目规范: {project}/.paw/conventions.yaml
│
└── Conversations (RAG 检索，需启用记忆系统)
    └── ~/.paw/conversations/  # SQLite 向量数据库
"""

import os
import yaml
import json
import hashlib
import sqlite3
import math
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


EMBED_MAX_LEN = 2048

# 默认的本地 embedding 服务 URL
DEFAULT_EMBEDDING_URLS = {
    "ollama": "http://localhost:11434/api/embeddings",
    "lm_studio": "http://localhost:1234/v1/embeddings",
}


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class Rules:
    """规则/习惯（永远注入，用户手动配置）"""
    user_rules: List[str] = field(default_factory=list)
    project_conventions: List[str] = field(default_factory=list)
    project_name: str = ""
    project_type: str = ""
    project_description: str = ""


@dataclass
class ConversationChunk:
    """对话片段"""
    id: str                    # 唯一标识
    project: str               # 项目名
    timestamp: str             # 时间戳
    user_message: str          # 用户消息
    assistant_message: str     # AI 回复
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# 外部 Embedding API 客户端
# ============================================================

class ExternalEmbeddingClient:
    """
    外部 Embedding API 客户端
    
    支持:
    - Ollama: http://localhost:11434/api/embeddings
    - LM Studio: http://localhost:1234/v1/embeddings  
    - OpenAI 兼容 API: https://api.xxx.com/v1/embeddings
    """

    def __init__(self, *, 
                 api_url: str,
                 api_key: str = "",
                 model: str = "",
                 timeout: int = 30):
        """
        初始化 Embedding 客户端
        
        Args:
            api_url: API 地址
            api_key: API 密钥（本地服务可留空）
            model: 模型名称（如 nomic-embed-text、text-embedding-ada-002 等）
            timeout: 请求超时时间（秒）
        """
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._is_ollama = "11434" in api_url or "/api/embeddings" in api_url
        
    def _embed_sync(self, text: str) -> List[float]:
        """同步 embedding（用于初始化时预计算向量）"""
        import requests
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Ollama 和 OpenAI 兼容 API 请求格式不同
        if self._is_ollama:
            payload = {
                "model": self.model,
                "prompt": text
            }
        else:
            payload = {
                "model": self.model,
                "input": text
            }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            # 解析响应
            if self._is_ollama:
                # Ollama 格式: {"embedding": [...]}
                embedding = data.get("embedding", [])
            else:
                # OpenAI 兼容格式: {"data": [{"embedding": [...]}]}
                embedding = data.get("data", [{}])[0].get("embedding", [])
            
            if not embedding:
                raise RuntimeError(f"Embedding 结果为空: {data}")
            return embedding
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Embedding API 请求失败: {e}")

    async def embed(self, text: str) -> List[float]:
        """异步 embedding"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Ollama 和 OpenAI 兼容 API 请求格式不同
        if self._is_ollama:
            payload = {
                "model": self.model,
                "prompt": text
            }
        else:
            payload = {
                "model": self.model,
                "input": text
            }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    # 解析响应
                    if self._is_ollama:
                        embedding = data.get("embedding", [])
                    else:
                        embedding = data.get("data", [{}])[0].get("embedding", [])
                    
                    if not embedding:
                        raise RuntimeError(f"Embedding 结果为空: {data}")
                    return embedding
                    
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Embedding API 请求失败: {e}")


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom == 0.0:
        return 0.0
    return dot / denom


# ============================================================
# 回忆意图判断（RAG 触发机制）
# ============================================================

# B 文本：描述"回忆型问题"的语义特征
# 其 embedding 向量用作判断用户输入是否需要回忆历史的锚点，这个值禁止修改！已经经过内测效果非常好了！
_RECALL_INTENT_TEXT = """这个问题需要调取我们曾经对话中的具体信息才能回答，即答案在当前对话上下文内是找不到的，可能是用户曾经和我的对话记录。它不是一个可以独立解答的新问题，而是在延续昨天/过去的讨论主题或引用早已交流过的内容。用户正在回忆、确认或复用历史对话中的某个细节、结论或概念。问题的前提是"我们之前提到过"或"根据先前的讨论"，答案存在于过往的交流记录中，而非实时查询或通用知识。"""

# 默认配置
_DEFAULT_RECALL_THRESHOLD = 0.35  # 意图判断阈值


class SQLiteConversationStore:
    def __init__(self, storage_path: Path, embedding_client: ExternalEmbeddingClient):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "conversations.sqlite3"
        self.embedding_client = embedding_client
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    project TEXT,
                    timestamp TEXT,
                    user_message TEXT,
                    assistant_message TEXT,
                    embedding_json TEXT,
                    metadata_json TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)")

    def _generate_id(self, content: str, timestamp: str) -> str:
        hash_input = f"{timestamp}_{content[:100]}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    async def add_conversation(self,
                               user_message: str,
                               assistant_message: str,
                               project: str = "",
                               metadata: Optional[Dict] = None) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        embed_text = f"用户: {user_message[:EMBED_MAX_LEN]}"

        embedding = await self.embedding_client.embed(embed_text)
        doc_id = self._generate_id(user_message, timestamp)
        doc_metadata = {
            "project": project,
            "timestamp": timestamp,
            "user_message": user_message[:1000],
            "assistant_message": assistant_message[:2000],
            **(metadata or {})
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO conversations
                (id, project, timestamp, user_message, assistant_message, embedding_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    project,
                    timestamp,
                    user_message[:1000],
                    assistant_message[:2000],
                    json.dumps(embedding, ensure_ascii=False),
                    json.dumps(doc_metadata, ensure_ascii=False)
                )
            )
        return doc_id

    async def search(self,
                     query: str,
                     project: Optional[str] = None,
                     n_results: int = 5,
                     min_score: float = 0.3) -> List[Dict[str, Any]]:
        if not query:
            return []

        query_embedding = await self.embedding_client.embed(f"用户: {query[:EMBED_MAX_LEN]}")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if project:
                rows = conn.execute(
                    "SELECT id, project, timestamp, user_message, assistant_message, embedding_json, metadata_json FROM conversations WHERE project = ?",
                    (project,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, project, timestamp, user_message, assistant_message, embedding_json, metadata_json FROM conversations"
                ).fetchall()

        scored: List[Dict[str, Any]] = []
        for r in rows:
            try:
                emb = json.loads(r["embedding_json"] or "[]")
            except Exception:
                emb = []
            sim = _cosine_similarity(query_embedding, emb)
            if sim >= min_score:
                try:
                    meta = json.loads(r["metadata_json"] or "{}")
                except Exception:
                    meta = {}
                scored.append({
                    "id": r["id"],
                    "similarity": round(sim, 3),
                    "document": f"用户: {r['user_message']}\nAI: {r['assistant_message']}",
                    "metadata": meta
                })

        scored.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
        return scored[: max(1, n_results)]

    def get_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(1) FROM conversations").fetchone()
            total = int(row[0]) if row else 0
        return {"total_conversations": total, "storage_path": str(self.db_path)}

    def list_all(self, project: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if project:
                rows = conn.execute(
                    """
                    SELECT id, project, timestamp, user_message, assistant_message, metadata_json
                    FROM conversations
                    WHERE project = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (project, limit, offset)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, project, timestamp, user_message, assistant_message, metadata_json
                    FROM conversations
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset)
                ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                meta = json.loads(r["metadata_json"] or "{}")
            except Exception:
                meta = {}
            out.append({
                "id": r["id"],
                "similarity": 1.0,
                "document": f"用户: {r['user_message']}\nAI: {r['assistant_message']}",
                "metadata": meta
            })
        return out

    def delete(self, doc_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("DELETE FROM conversations WHERE id = ?", (doc_id,))
                return cur.rowcount > 0
        except Exception:
            return False

    def delete_batch(self, doc_ids: List[str]) -> int:
        if not doc_ids:
            return 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.executemany("DELETE FROM conversations WHERE id = ?", [(i,) for i in doc_ids])
                return cur.rowcount or 0
        except Exception:
            return 0

    def find_duplicates(self, threshold: float = 0.95, max_records: int = 800) -> List[List[str]]:
        """
        查找内容高度重复的记忆，按项目和 embedding 余弦相似度分组。
        
        Args:
            threshold: 相似度阈值，达到或超过该值的两条记录视为重复
            max_records: 为了避免 O(n^2) 开销设置的硬上限，超过则只检查最新 max_records 条
        
        Returns:
            每个元素是一组重复记录的 ID（长度>1）
        """
        duplicate_groups: List[List[str]] = []
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, project, embedding_json
                FROM conversations
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (max_records,)
            ).fetchall()
        
        if len(rows) < 2:
            return []
        
        # 先按项目拆分，减少跨项目比较
        entries_by_project: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            try:
                emb = json.loads(row["embedding_json"] or "[]")
            except Exception:
                emb = []
            if not emb:
                continue
            project_key = row["project"] or ""
            entries_by_project.setdefault(project_key, []).append({
                "id": row["id"],
                "embedding": emb,
            })
        
        for project_entries in entries_by_project.values():
            n = len(project_entries)
            if n < 2:
                continue
            
            parent = list(range(n))
            
            def find(idx: int) -> int:
                while parent[idx] != idx:
                    parent[idx] = parent[parent[idx]]
                    idx = parent[idx]
                return idx
            
            def union(a: int, b: int) -> None:
                pa, pb = find(a), find(b)
                if pa != pb:
                    parent[pb] = pa
            
            for i in range(n):
                emb_i = project_entries[i]["embedding"]
                for j in range(i + 1, n):
                    emb_j = project_entries[j]["embedding"]
                    if _cosine_similarity(emb_i, emb_j) >= threshold:
                        union(i, j)
            
            grouped: Dict[int, List[str]] = {}
            for idx in range(n):
                root = find(idx)
                grouped.setdefault(root, []).append(project_entries[idx]["id"])
            
            for group_ids in grouped.values():
                if len(group_ids) > 1:
                    duplicate_groups.append(group_ids)
        
        return duplicate_groups

# ============================================================
# 回忆管理器 - 生命值递减法
# ============================================================

@dataclass
class ActiveRecall:
    """活跃的回忆片段"""
    doc_id: str           # 记忆ID
    content: str          # 格式化的回忆内容
    life: int             # 生命值
    tokens: int           # 估算的token数
    similarity: float     # 相似度分数
    timestamp: str = ""   # 时间戳，用于排序

class RecallManager:
    """
    回忆管理器 - 生命值递减法
    
    核心机制:
    - 被唤醒的记忆获得生命值
    - 每轮对话所有记忆生命值衰减
    - 生命值归零的记忆被移除（但可再次唤醒）
    - 容量控制衰减/增益速度
    """
    
    def __init__(self, 
                 max_capacity: int = 2000,      # 最大容量（tokens）
                 base_life: int = 3,            # 基础生命值
                 decay_rate: int = 1):          # 基础衰减速率
        self.max_capacity = max_capacity
        self.base_life = base_life
        self.decay_rate = decay_rate
        
        # 活跃的回忆 {doc_id: ActiveRecall}
        self.active_recalls: Dict[str, ActiveRecall] = {}
    
    @property
    def current_tokens(self) -> int:
        """当前已使用的token数"""
        return sum(r.tokens for r in self.active_recalls.values())
    
    @property
    def capacity_ratio(self) -> float:
        """容量使用率 (0-1)"""
        return self.current_tokens / self.max_capacity if self.max_capacity > 0 else 0
    
    def _estimate_tokens(self, text: str) -> int:
        """估算token数"""
        return len(text) // 2  # 简单估算：中文约2字符/token
    
    def _calculate_life_gain(self, similarity: float) -> int:
        """计算生命值增益
        
        - 相似度越高，增益越大
        - 容量越空，增益越大
        """
        # 基础增益 = base_life * 相似度加成
        base = self.base_life
        similarity_bonus = int(similarity * 2)  # 0.8相似度 -> +1
        
        # 容量加成：容量越空，加成越高
        capacity_bonus = int((1 - self.capacity_ratio) * 2)
        
        return base + similarity_bonus + capacity_bonus
    
    def _calculate_decay(self) -> int:
        """计算衰减值
        
        - 容量越满，衰减越快
        """
        # 基础衰减
        base = self.decay_rate
        
        # 容量惩罚：超过50%容量后加速衰减
        if self.capacity_ratio > 0.5:
            capacity_penalty = int((self.capacity_ratio - 0.5) * 4)
            return base + capacity_penalty
        
        return base
    
    def awaken(self, doc_id: str, content: str, similarity: float, timestamp: str = "") -> bool:
        """唤醒一条记忆
        
        Args:
            doc_id: 记忆ID
            content: 格式化的回忆内容
            similarity: 相似度分数
            timestamp: 时间戳，用于按时间排序
            
        Returns:
            是否为新唤醒（True）或已存在（False）
        """
        life_gain = self._calculate_life_gain(similarity)
        
        if doc_id in self.active_recalls:
            # 已存在，增加生命值
            self.active_recalls[doc_id].life += life_gain
            self.active_recalls[doc_id].similarity = max(
                self.active_recalls[doc_id].similarity, 
                similarity
            )
            return False
        else:
            # 新唤醒
            tokens = self._estimate_tokens(content)
            self.active_recalls[doc_id] = ActiveRecall(
                doc_id=doc_id,
                content=content,
                life=life_gain,
                tokens=tokens,
                similarity=similarity,
                timestamp=timestamp
            )
            return True
    
    def tick(self) -> List[str]:
        """每轮对话调用，衰减所有记忆的生命值
        
        Returns:
            被移除的记忆ID列表
        """
        decay = self._calculate_decay()
        removed = []
        
        for doc_id in list(self.active_recalls.keys()):
            self.active_recalls[doc_id].life -= decay
            if self.active_recalls[doc_id].life <= 0:
                del self.active_recalls[doc_id]
                removed.append(doc_id)
        
        return removed
    
    def get_active_prompt(self) -> str:
        """生成当前活跃记忆的提示词"""
        if not self.active_recalls:
            return ""
        
        # 按时间顺序排序（旧的在前，新的在后）
        sorted_recalls = sorted(
            self.active_recalls.values(),
            key=lambda r: r.timestamp
        )
        
        lines = ["<recall>", "以下是与当前话题相关的历史对话片段（按时间排序，各片段相互独立）："]
        for i, recall in enumerate(sorted_recalls, 1):
            lines.append(f"--- 片段 {i} ---")
            lines.append(recall.content)
        lines.append("--- 历史回忆结束 ---")
        lines.append("</recall>")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_count": len(self.active_recalls),
            "current_tokens": self.current_tokens,
            "max_capacity": self.max_capacity,
            "capacity_ratio": f"{self.capacity_ratio:.1%}",
            "recalls": [
                {"id": r.doc_id[:8], "life": r.life, "tokens": r.tokens}
                for r in self.active_recalls.values()
            ]
        }
    
    def clear(self):
        """清空所有活跃记忆"""
        self.active_recalls.clear()


# ============================================================
# 记忆管理
# ============================================================

class MemoryManager:
    """
    记忆管理
    
    核心特性:
    1. Rules: 用户手动配置，永远注入
    2. Conversations: RAG 检索历史对话（需启用记忆系统）
    """
    
    def __init__(self, 
                 project_path: Path,
                 embedding_url: str = "",
                 embedding_key: str = "",
                 embedding_model: str = ""):
        """
        初始化记忆管理器
        
        Args:
            project_path: 当前项目路径
            embedding_url: Embedding API 地址
            embedding_key: Embedding API 密钥（本地服务可留空）
            embedding_model: Embedding 模型名称
        """
        self.project_path = Path(project_path)
        
        # 存储路径
        self.user_dir = Path.home() / ".paw"
        self.project_dir = self.project_path / ".paw"
        
        # 确保目录存在
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件路径
        self.user_rules_file = self.user_dir / "rules.yaml"
        self.project_conventions_file = self.project_dir / "conventions.yaml"
        
        # 加载规则
        self.rules = self._load_rules()
        
        # 初始化对话存储
        conversations_dir = self.user_dir / "conversations"
        self.embedding_client = ExternalEmbeddingClient(
            api_url=embedding_url,
            api_key=embedding_key,
            model=embedding_model,
        )
        self.conversation_store = SQLiteConversationStore(
            storage_path=conversations_dir,
            embedding_client=self.embedding_client
        )
        
        # 初始化回忆管理器（生命值递减法）
        self.recall_manager = RecallManager(
            max_capacity=4000,  # 最大4000 tokens（约14条回忆）
            base_life=3,        # 基础生命值3轮
            decay_rate=1        # 每轮衰减1
        )

        # 加载回忆意图判断配置
        self._load_recall_config()

        # 预计算"回忆意图"锚点向量 B
        self._recall_intent_vector: List[float] = []
        self._init_recall_intent_vector()

    # ==================== 回忆意图判断配置 ====================

    def _load_recall_config(self):
        """加载回忆相关配置（从项目根目录的 config.yaml）"""
        import os
        config_path = self.project_path / "config.yaml"
        self._recall_enabled = True
        self._recall_threshold = _DEFAULT_RECALL_THRESHOLD

        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                recall_config = config.get('recall', {})
                self._recall_enabled = recall_config.get('enabled', True)
                self._recall_threshold = recall_config.get('threshold', _DEFAULT_RECALL_THRESHOLD)
            except Exception as e:
                print(f"[Memory] 加载 recall 配置失败: {e}")

    def _init_recall_intent_vector(self):
        """预计算'回忆意图'锚点向量 B"""
        if not self._recall_enabled:
            return
        try:
            # 使用同步方法预计算（初始化时可以接受阻塞）
            self._recall_intent_vector = self.embedding_client._embed_sync(_RECALL_INTENT_TEXT)
            print(f"[Memory] 回忆意图锚点向量已预计算 (阈值: {self._recall_threshold})")
        except Exception as e:
            print(f"[Memory] 预计算回忆意图向量失败: {e}")
            self._recall_enabled = False

    def _should_recall(self, query: str, context: str = "") -> tuple[bool, float]:
        """
        判断用户输入是否需要回忆历史

        原理：将用户问题和近期上下文一起 embedding，判断是否需要检索历史记忆。
        如果问题在当前上下文中已有答案（如"那个函数"刚刚讨论过），则不需要回忆。

        Args:
            query: 用户输入
            context: 近期对话上下文（最多 16K 字符）

        Returns:
            (是否需要回忆, 相似度分数)
        """
        if not self._recall_enabled or not self._recall_intent_vector:
            # 未启用或向量未初始化，默认进行回忆（保持向后兼容）
            return True, 1.0

        try:
            # 构建 embedding 文本：上下文 + 用户问题
            # 限制上下文长度，避免超出 embedding 模型限制
            max_context_len = 14000  # 为用户问题预留空间
            if context and len(context) > max_context_len:
                context = context[-max_context_len:]  # 取最近的部分
            
            if context:
                embed_text = f"对话上下文:\n{context}\n\n用户新问题: {query}"
            else:
                embed_text = query
            
            query_vector = self.embedding_client._embed_sync(embed_text)
            similarity = _cosine_similarity(query_vector, self._recall_intent_vector)
            should = similarity >= self._recall_threshold
            return should, similarity
        except Exception as e:
            print(f"[Memory] 意图判断失败: {e}")
            return True, 1.0  # 出错时默认进行回忆
    
    # ==================== 规则加载 ====================
    
    def _load_rules(self) -> Rules:
        """加载规则（用户规则 + 项目规范）"""
        rules = Rules(project_name=self.project_path.name)
        
        # 加载用户规则
        if self.user_rules_file.exists():
            try:
                with open(self.user_rules_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                rules.user_rules = data.get('rules', [])
            except Exception as e:
                print(f"[Memory] 加载用户规则失败: {e}")
        
        # 加载项目规范
        if self.project_conventions_file.exists():
            try:
                with open(self.project_conventions_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                rules.project_conventions = data.get('conventions', [])
                rules.project_type = data.get('type', '')
                rules.project_description = data.get('description', '')
            except Exception as e:
                print(f"[Memory] 加载项目规范失败: {e}")
        
        return rules
    
    def reload_rules(self):
        """重新加载规则"""
        self.rules = self._load_rules()
    
    # ==================== 规则保存 ====================
    
    def save_user_rules(self):
        """保存用户规则"""
        data = {'rules': self.rules.user_rules}
        with open(self.user_rules_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    
    def save_project_conventions(self):
        """保存项目规范"""
        data = {
            'conventions': self.rules.project_conventions,
            'type': self.rules.project_type,
            'description': self.rules.project_description
        }
        with open(self.project_conventions_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    
    # ==================== 规则管理 ====================
    
    def add_user_rule(self, rule: str) -> bool:
        """添加用户规则"""
        if rule and rule not in self.rules.user_rules:
            self.rules.user_rules.append(rule)
            self.save_user_rules()
            return True
        return False
    
    def remove_user_rule(self, rule: str) -> bool:
        """删除用户规则"""
        if rule in self.rules.user_rules:
            self.rules.user_rules.remove(rule)
            self.save_user_rules()
            return True
        return False
    
    def add_project_convention(self, convention: str) -> bool:
        """添加项目约定"""
        if convention and convention not in self.rules.project_conventions:
            self.rules.project_conventions.append(convention)
            self.save_project_conventions()
            return True
        return False
    
    def remove_project_convention(self, convention: str) -> bool:
        """删除项目约定"""
        if convention in self.rules.project_conventions:
            self.rules.project_conventions.remove(convention)
            self.save_project_conventions()
            return True
        return False
    
    # ==================== 规则注入 ====================
    
    def get_rules_prompt(self) -> str:
        """生成规则提示词（永远注入到 system prompt）"""
        sections = []
        
        # 用户规则
        if self.rules.user_rules:
            lines = ["## 用户规则"]
            for rule in self.rules.user_rules:
                lines.append(f"- {rule}")
            sections.append("\n".join(lines))
        
        # 项目规范
        if self.rules.project_conventions:
            lines = [f"## 项目规范 ({self.rules.project_name})"]
            if self.rules.project_type:
                lines.append(f"- 类型: {self.rules.project_type}")
            if self.rules.project_description:
                lines.append(f"- 描述: {self.rules.project_description}")
            lines.append("- 约定:")
            for conv in self.rules.project_conventions:
                lines.append(f"  - {conv}")
            sections.append("\n".join(lines))
        
        if not sections:
            return ""
        
        return "\n".join([
            "# 规则与习惯 (RULES)",
            "<rules>",
            *sections,
            "</rules>"
        ])
    
    # ==================== 对话存储 ====================
    
    def save_conversation(self, 
                         user_message: str, 
                         assistant_message: str,
                         metadata: Optional[Dict] = None) -> str:
        """
        保存一轮对话
        
        Args:
            user_message: 用户消息
            assistant_message: AI 回复
            metadata: 额外元数据
            
        Returns:
            对话 ID
        """
        if hasattr(self.conversation_store, "add_conversation") and asyncio.iscoroutinefunction(getattr(self.conversation_store, "add_conversation")):
            raise RuntimeError("SQLiteConversationStore 需要异步保存，请调用 save_conversation_async")
        return self.conversation_store.add_conversation(
            user_message=user_message,
            assistant_message=assistant_message,
            project=self.project_path.name,
            metadata=metadata
        )

    async def save_conversation_async(self,
                                     user_message: str,
                                     assistant_message: str,
                                     metadata: Optional[Dict] = None) -> str:
        if asyncio.iscoroutinefunction(getattr(self.conversation_store, "add_conversation", None)):
            return await self.conversation_store.add_conversation(
                user_message=user_message,
                assistant_message=assistant_message,
                project=self.project_path.name,
                metadata=metadata
            )
        return self.save_conversation(user_message, assistant_message, metadata)
    
    # ==================== 记忆回忆（生命值递减法）====================

    def recall(self,
               query: str,
               n_results: int = 3,
               min_score: float = 0.35,
               project_only: bool = True,
               context: str = "") -> int:
        """
        回忆相关对话（意图判断 + RAG 检索 + 生命值管理）

        Args:
            query: 用户输入
            n_results: 返回数量
            min_score: 最低相似度
            project_only: 是否只检索当前项目
            context: 近期对话上下文（用于意图判断，最多 16K 字符）

        Returns:
            新唤醒的记忆数量
        """
        # 意图判断：结合上下文判断用户输入是否需要回忆历史
        should_recall, intent_score = self._should_recall(query, context)
        if not should_recall:
            # 不需要回忆，跳过 RAG 检索
            print(f"[Memory] 意图判断: 跳过回忆 (相似度: {intent_score:.3f} < 阈值: {self._recall_threshold})")
            return 0
        print(f"[Memory] 意图判断: 触发回忆 (相似度: {intent_score:.3f})")

        project = self.project_path.name if project_only else None

        # RAG 检索
        if asyncio.iscoroutinefunction(getattr(self.conversation_store, "search", None)):
            raise RuntimeError("SQLiteConversationStore 需要异步检索，请调用 recall_async")
        results = self.conversation_store.search(
            query=query,
            project=project,
            n_results=n_results,
            min_score=min_score
        )

        # 唤醒记忆（加入生命值系统）
        new_count = 0
        for conv in results:
            doc_id = conv.get('id', '')
            similarity = conv.get('similarity', 0.5)

            # 格式化回忆内容
            meta = conv.get('metadata', {})
            timestamp = meta.get('timestamp', '')
            user_msg = meta.get('user_message', '')[:200]
            assistant_msg = meta.get('assistant_message', '')[:300]
            content = f"[{timestamp[:10]}] 用户问: {user_msg}\n我答: {assistant_msg}{'...' if len(meta.get('assistant_message', '')) > 300 else ''}"

            # 唤醒（传入时间戳用于排序）
            if self.recall_manager.awaken(doc_id, content, similarity, timestamp):
                new_count += 1

        return new_count

    async def recall_async(self,
                           query: str,
                           n_results: int = 3,
                           min_score: float = 0.35,
                           project_only: bool = True,
                           context: str = "") -> int:
        """
        异步版本：回忆相关对话（意图判断 + RAG 检索 + 生命值管理）
        
        Args:
            query: 用户输入
            n_results: 返回数量
            min_score: 最低相似度
            project_only: 是否只检索当前项目
            context: 近期对话上下文（用于意图判断，最多 16K 字符）
        """
        # 意图判断：结合上下文判断用户输入是否需要回忆历史
        should_recall, intent_score = self._should_recall(query, context)
        if not should_recall:
            # 不需要回忆，跳过 RAG 检索
            print(f"[Memory] 意图判断: 跳过回忆 (相似度: {intent_score:.3f} < 阈值: {self._recall_threshold})")
            return 0
        print(f"[Memory] 意图判断: 触发回忆 (相似度: {intent_score:.3f})")

        project = self.project_path.name if project_only else None
        if asyncio.iscoroutinefunction(getattr(self.conversation_store, "search", None)):
            results = await self.conversation_store.search(
                query=query,
                project=project,
                n_results=n_results,
                min_score=min_score
            )
        else:
            results = self.conversation_store.search(
                query=query,
                project=project,
                n_results=n_results,
                min_score=min_score
            )

        new_count = 0
        for conv in results:
            doc_id = conv.get('id', '')
            similarity = conv.get('similarity', 0.5)
            meta = conv.get('metadata', {})
            timestamp = meta.get('timestamp', '')
            user_msg = meta.get('user_message', '')[:200]
            assistant_msg = meta.get('assistant_message', '')[:300]
            content = f"[{timestamp[:10]}] 用户问: {user_msg}\n我答: {assistant_msg}{'...' if len(meta.get('assistant_message', '')) > 300 else ''}"
            if self.recall_manager.awaken(doc_id, content, similarity, timestamp):
                new_count += 1
        return new_count
    
    def tick_recall(self) -> List[str]:
        """每轮对话后调用，衰减记忆生命值
        
        Returns:
            被遗忘的记忆ID列表
        """
        return self.recall_manager.tick()
    
    def get_recalled_prompt(self) -> str:
        """生成当前活跃记忆的提示词 - 作为独立的 assistant 消息块
        
        使用生命值递减法管理的活跃记忆。
        
        使用方式（OpenAI API）:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": recalled_prompt},  # 独立块
                # LLM 继续生成正常回复，不会模仿 <recall> 格式
            ]
        """
        return self.recall_manager.get_active_prompt()
    
    # ==================== 统计信息 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "rules": {
                "user_rules_count": len(self.rules.user_rules),
                "project_conventions_count": len(self.rules.project_conventions)
            },
            "conversations": self.conversation_store.get_stats(),
            "recall": self.recall_manager.get_stats()
        }
    
    # ==================== 兼容旧接口 ====================
    
    def get_memory_prompt(self) -> str:
        """兼容旧接口"""
        return self.get_rules_prompt() #规则注入


