#!/usr/bin/env python
"""
Paw 记忆系统 - Memory System v3

核心改动:
- 删除自动规则生成，只保留用户手动配置的规则
- 使用 RAG 检索完整对话记录，而非 LLM 判断摘要

架构:
├── Rules (永远注入，用户手动配置)
│   ├── 用户规则: ~/.paw/rules.yaml
│   └── 项目规范: {project}/.paw/conventions.yaml
│
└── Conversations (RAG 检索)
    └── ~/.paw/conversations/  # ChromaDB 向量数据库
"""

import os
import yaml
import json
import hashlib
import time
import sqlite3
import math
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

import aiohttp


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
# 对话存储（基于 ChromaDB）
# ============================================================

# 本地模型存储路径
LOCAL_MODEL_DIR = Path(__file__).parent / "models"


class LMStudioEmbeddingClient:
    def __init__(self, *, url: str, model: str, api_key: Optional[str] = None, timeout_s: float = 2.0):
        self.url = url
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def embed(self, text: str) -> List[float]:
        # 严格匹配 LM Studio 官方示例：
        # curl http://127.0.0.1:1234/v1/embeddings -H "Content-Type: application/json" -d '{"model":..., "input": ...}'
        headers = {"Content-Type": "application/json"}
        # LM Studio 本地默认无需 key，但保留兼容
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"model": self.model, "input": text}

        timeout = aiohttp.ClientTimeout(total=self.timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.url, headers=headers, json=payload) as resp:
                raw_text = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(f"embeddings 请求失败({resp.status}): {raw_text[:500]}")
                try:
                    data = json.loads(raw_text)
                except Exception as e:
                    raise RuntimeError(f"embeddings 返回不是 JSON: {e}; body={raw_text[:200]}")
                emb = (((data or {}).get("data") or [{}])[0]).get("embedding")
                if not isinstance(emb, list) or not emb:
                    raise RuntimeError(f"embeddings 返回格式异常: {str(data)[:200]}")
                return emb


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


class SQLiteConversationStore:
    def __init__(self, storage_path: Path, embedding_client: LMStudioEmbeddingClient):
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
        embed_text = f"用户: {user_message}"

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

        query_embedding = await self.embedding_client.embed(f"用户: {query}")

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

    def find_duplicates(self, threshold: float = 0.95) -> List[List[str]]:
        # 轻量后端先返回空，避免引入额外 O(n^2) 计算
        return []


class ConversationStore:
    """
    对话存储 - 使用 ChromaDB 进行向量检索
    
    存储粒度: 单轮对话（一问一答）
    检索方式: 用户输入 -> 向量相似度 -> 返回相关历史对话
    """
    
    def __init__(self, storage_path: Path, model_name: str = "all-MiniLM-L6-v2"):
        """
        初始化对话存储
        
        Args:
            storage_path: 存储路径
            model_name: sentence-transformers 模型名称
                       - all-MiniLM-L6-v2: 快速，英文为主
                       - paraphrase-multilingual-MiniLM-L12-v2: 多语言支持
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化 embedding 模型（优先从本地加载）
        self._model_name = model_name
        t0 = time.perf_counter()
        self._embedding_model = self._load_embedding_model(model_name)
        print(f"[Memory] embedding 模型加载耗时: {time.perf_counter() - t0:.2f}s")
        
        # 初始化 ChromaDB
        t1 = time.perf_counter()
        self.client = self._chromadb.PersistentClient(
            path=str(self.storage_path),
            settings=self._Settings(anonymized_telemetry=False)
        )
        
        # 获取或创建 collection
        self.collection = self.client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
        )

        print(f"[Memory] ChromaDB 初始化耗时: {time.perf_counter() - t1:.2f}s")
        
        print(f"[Memory] 对话存储已加载，当前记录数: {self.collection.count()}")
    
    def _load_embedding_model(self, model_name: str) -> "SentenceTransformer":
        """
        加载 embedding 模型
        
        优先从本地加载，避免每次启动都连接 HuggingFace
        首次使用时下载到项目本地 models/ 目录
        """
        local_path = LOCAL_MODEL_DIR / model_name
        
        # 优先从本地加载（离线模式）
        if local_path.exists():
            print(f"[Memory] 从本地加载模型: {local_path}")
            return self._SentenceTransformer(str(local_path), local_files_only=True)
        
        # 本地不存在，从网络下载并保存到本地
        print(f"[Memory] 首次使用，下载模型: {model_name}")
        print(f"[Memory] 模型将保存到: {local_path}")
        
        LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
        model = self._SentenceTransformer(model_name)
        model.save(str(local_path))
        
        print(f"[Memory] 模型已保存，下次启动将直接从本地加载")
        return model
    
    @property
    def embedding_model(self) -> "SentenceTransformer":
        """获取 embedding 模型"""
        if self._embedding_model is None:
            self._embedding_model = self._load_embedding_model(self._model_name)
        return self._embedding_model
    
    def _generate_id(self, content: str, timestamp: str) -> str:
        """生成唯一 ID"""
        hash_input = f"{timestamp}_{content[:100]}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    def add_conversation(self, 
                        user_message: str, 
                        assistant_message: str,
                        project: str = "",
                        metadata: Optional[Dict] = None) -> str:
        """
        添加一轮对话
        
        Args:
            user_message: 用户消息
            assistant_message: AI 回复
            project: 项目名称
            metadata: 额外元数据
            
        Returns:
            对话 ID
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 组合文本用于 embedding（主要基于用户问题检索）
        # 但存储完整对话用于上下文
        embed_text = f"用户: {user_message}"
        full_text = f"用户: {user_message}\nAI: {assistant_message}"
        
        # 生成 embedding
        embedding = self.embedding_model.encode(embed_text).tolist()
        
        # 生成 ID
        doc_id = self._generate_id(user_message, timestamp)
        
        # 准备元数据
        doc_metadata = {
            "project": project,
            "timestamp": timestamp,
            "user_message": user_message[:1000],  # 限制长度
            "assistant_message": assistant_message[:2000],
            **(metadata or {})
        }
        
        # 存入 ChromaDB
        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[full_text[:3000]],  # 完整对话，限制长度
            metadatas=[doc_metadata]
        )
        
        return doc_id
    
    def search(self, 
               query: str, 
               project: Optional[str] = None,
               n_results: int = 5,
               min_score: float = 0.3) -> List[Dict[str, Any]]:
        """
        检索相关对话
        
        Args:
            query: 查询文本
            project: 限定项目（可选）
            n_results: 返回数量
            min_score: 最低相似度阈值（0-1，越高越严格）
            
        Returns:
            相关对话列表
        """
        if self.collection.count() == 0:
            return []
        
        # 生成查询 embedding
        query_embedding = self.embedding_model.encode(f"用户: {query}").tolist()
        
        # 构建过滤条件
        where_filter = None
        if project:
            where_filter = {"project": project}
        
        # 检索
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self.collection.count()),
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        # 处理结果
        conversations = []
        if results and results['ids'] and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                # ChromaDB 返回的是距离，转换为相似度
                distance = results['distances'][0][i]
                similarity = 1 - distance  # 余弦距离转相似度
                
                if similarity >= min_score:
                    conversations.append({
                        "id": doc_id,
                        "similarity": round(similarity, 3),
                        "document": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i]
                    })
        
        return conversations
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_conversations": self.collection.count(),
            "storage_path": str(self.storage_path)
        }
    
    def list_all(self, 
                 project: Optional[str] = None,
                 limit: int = 100,
                 offset: int = 0) -> List[Dict[str, Any]]:
        """
        列出所有对话记录
        
        Args:
            project: 限定项目（可选）
            limit: 返回数量限制
            offset: 偏移量（用于分页）
            
        Returns:
            对话列表，按时间倒序
        """
        if self.collection.count() == 0:
            return []
        
        # 构建过滤条件
        where_filter = None
        if project:
            where_filter = {"project": project}
        
        # 获取所有记录
        results = self.collection.get(
            where=where_filter,
            include=["documents", "metadatas"]
        )
        
        # 组装结果
        conversations = []
        if results and results['ids']:
            for i, doc_id in enumerate(results['ids']):
                conversations.append({
                    "id": doc_id,
                    "document": results['documents'][i] if results['documents'] else "",
                    "metadata": results['metadatas'][i] if results['metadatas'] else {}
                })
        
        # 按时间倒序排序
        conversations.sort(
            key=lambda x: x.get('metadata', {}).get('timestamp', ''),
            reverse=True
        )
        
        # 分页
        return conversations[offset:offset + limit]
    
    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 ID 获取单条对话
        
        Args:
            doc_id: 对话 ID
            
        Returns:
            对话记录，不存在则返回 None
        """
        try:
            results = self.collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"]
            )
            
            if results and results['ids']:
                return {
                    "id": results['ids'][0],
                    "document": results['documents'][0] if results['documents'] else "",
                    "metadata": results['metadatas'][0] if results['metadatas'] else {}
                }
        except Exception:
            pass
        return None
    
    def delete(self, doc_id: str) -> bool:
        """
        删除单条对话
        
        Args:
            doc_id: 对话 ID
            
        Returns:
            是否删除成功
        """
        try:
            self.collection.delete(ids=[doc_id])
            return True
        except Exception:
            return False
    
    def delete_batch(self, doc_ids: List[str]) -> int:
        """
        批量删除对话
        
        Args:
            doc_ids: 对话 ID 列表
            
        Returns:
            成功删除的数量
        """
        if not doc_ids:
            return 0
        try:
            self.collection.delete(ids=doc_ids)
            return len(doc_ids)
        except Exception:
            return 0
    
    def find_duplicates(self, threshold: float = 0.95) -> List[List[str]]:
        """
        查找重复或高度相似的对话
        
        Args:
            threshold: 相似度阈值（0-1，越高越严格）
            
        Returns:
            重复组列表，每组包含相似对话的 ID
        """
        if self.collection.count() < 2:
            return []
        
        # 获取所有记录
        all_records = self.list_all(limit=1000)
        if len(all_records) < 2:
            return []
        
        # 提取用户消息用于比较
        messages = []
        for record in all_records:
            user_msg = record.get('metadata', {}).get('user_message', '')
            messages.append((record['id'], user_msg))
        
        # 简单的文本相似度检测（基于字符重叠）
        duplicate_groups = []
        seen = set()
        
        for i, (id1, msg1) in enumerate(messages):
            if id1 in seen or not msg1:
                continue
            
            group = [id1]
            for j, (id2, msg2) in enumerate(messages[i+1:], i+1):
                if id2 in seen or not msg2:
                    continue
                
                # 计算简单相似度（Jaccard）
                set1 = set(msg1)
                set2 = set(msg2)
                if not set1 or not set2:
                    continue
                similarity = len(set1 & set2) / len(set1 | set2)
                
                if similarity >= threshold:
                    group.append(id2)
                    seen.add(id2)
            
            if len(group) > 1:
                duplicate_groups.append(group)
                seen.add(id1)
        
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
# 记忆管理器 v3
# ============================================================

class MemoryManager:
    """
    记忆管理器 v3
    
    核心特性:
    1. Rules: 用户手动配置，永远注入
    2. Conversations: RAG 检索历史对话
    """
    
    def __init__(self, 
                 project_path: Path,
                 embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
                 embeddings_url: Optional[str] = None,
                 embeddings_model: Optional[str] = None,
                 embeddings_api_key: Optional[str] = None):
        """
        初始化记忆管理器
        
        Args:
            project_path: 当前项目路径
            embedding_model: embedding 模型名称
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
        if embeddings_url and embeddings_model:
            embedding_client = LMStudioEmbeddingClient(
                url=embeddings_url,
                model=embeddings_model,
                api_key=embeddings_api_key,
                timeout_s=2.0
            )
            self.conversation_store = SQLiteConversationStore(
                storage_path=conversations_dir,
                embedding_client=embedding_client
            )
        else:
            self.conversation_store = ConversationStore(
                storage_path=conversations_dir,
                model_name=embedding_model
            )
        
        # 初始化回忆管理器（生命值递减法）
        self.recall_manager = RecallManager(
            max_capacity=4000,  # 最大4000 tokens（约14条回忆）
            base_life=3,        # 基础生命值3轮
            decay_rate=1        # 每轮衰减1
        )
        
        # 当前检索到的相关对话（临时，用于兼容）
        self.recalled_conversations: List[Dict] = []
    
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
               project_only: bool = True) -> int:
        """
        回忆相关对话（RAG 检索 + 生命值管理）
        
        Args:
            query: 用户输入
            n_results: 返回数量
            min_score: 最低相似度
            project_only: 是否只检索当前项目
            
        Returns:
            新唤醒的记忆数量
        """
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
                           project_only: bool = True) -> int:
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
    
    def clear_recalled(self):
        """清空所有活跃记忆"""
        self.recall_manager.clear()
    
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
        return self.get_rules_prompt()


