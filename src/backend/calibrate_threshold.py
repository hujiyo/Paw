#!/usr/bin/env python
"""
Paw 记忆意图判断阈值推荐

根据用户配置的 Embedding API，自动计算最优阈值。

原理：
1. 预定义两类样本：
   - 正例：需要回忆历史的问题
   - 负例：不需要回忆的即时问题
2. 计算所有样本与"回忆意图锚点"的相似度
3. 找到最大化类间距离的阈值

用法：
    python calibrate_threshold.py [embedding_url] [embedding_model]
"""

import os
import sys
import math
import requests
import yaml
from pathlib import Path
from typing import List, Tuple

# 添加 core 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from memory import _RECALL_INTENT_TEXT as RECALL_INTENT_TEXT, DEFAULT_EMBEDDING_URLS


# ============================================================
# 测试样本
# ============================================================

# 样本格式: (query, context)
# context 为空字符串表示没有上下文

# 正例：需要回忆历史的问题（当前上下文中没有相关信息）
POSITIVE_SAMPLES = [
    # 无上下文，明确的回忆意图
    ("之前你说的那个函数叫什么名字？", ""),
    ("我们上次讨论的方案是什么来着？", ""),
    ("你之前提到的那个 bug 修好了吗？", ""),
    ("根据我们之前的讨论，下一步应该怎么做？", ""),
    ("你之前帮我写的那段代码能再发一下吗？", ""),
    ("我们上次说到哪了？", ""),
    ("还记得上次说的那个优化方案吗？", ""),
    ("之前推荐的那本书叫什么？", ""),
    # 有上下文，但上下文中没有相关信息（需要回忆更早的对话），且问题中有明确的回忆词
    ("之前说的那个 API 怎么调用？", "用户: 帮我翻译这句话\nAI: 翻译结果是..."),
    ("我们上次讨论的数据库设计怎么样了？", "用户: Git 怎么撤销提交\nAI: 你可以用 git reset..."),
    ("之前推荐的那本书叫什么？", "用户: 今天天气怎么样\nAI: 抱歉，我无法查询实时天气"),
    ("继续之前的话题", "用户: 什么是机器学习\nAI: 机器学习是..."),
]

# 负例：不需要回忆的问题
NEGATIVE_SAMPLES = [
    # 无上下文，即时问题
    ("今天天气怎么样？", ""),
    ("Python 怎么读取 JSON 文件？", ""),
    ("帮我写一个快速排序", ""),
    ("什么是机器学习？", ""),
    ("npm install 报错怎么办？", ""),
    ("解释一下 RESTful API", ""),
    ("推荐几本编程书", ""),
    ("写一个 Hello World", ""),
    # 有上下文，问题在上下文中已有答案（不需要回忆）
    ("那个函数怎么用？", "用户: 帮我写个处理字符串的函数\nAI: def process_string(s): return s.strip().lower()"),
    ("继续说", "用户: 解释 RESTful API\nAI: RESTful API 是一种架构风格，它使用 HTTP 方法..."),
    ("还有别的方法吗？", "用户: 怎么排序\nAI: 可以用 sorted() 或 list.sort()"),
    ("具体怎么写？", "用户: 怎么读取文件\nAI: 用 with open('file.txt', 'r') as f: content = f.read()"),
]


# ============================================================
# 工具函数
# ============================================================

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_config() -> dict:
    """加载 config.yaml"""
    config_path = SCRIPT_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def get_embedding_config(url: str = None, model: str = None) -> Tuple[str, str]:
    """获取 Embedding 配置"""
    config = load_config()
    memory_cfg = config.get('memory', {})
    
    embedding_url = url or memory_cfg.get('embedding_url', DEFAULT_EMBEDDING_URLS['ollama'])
    embedding_model = model or memory_cfg.get('embedding_model', 'nomic-embed-text')
    
    return embedding_url, embedding_model


def create_embed_function(url: str, model: str):
    """创建 embedding 函数"""
    is_ollama = "11434" in url or "/api/embeddings" in url
    
    def embed(text: str) -> List[float]:
        headers = {"Content-Type": "application/json"}
        
        if is_ollama:
            payload = {"model": model, "prompt": text}
        else:
            payload = {"model": model, "input": text}
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if is_ollama:
            return data.get("embedding", [])
        else:
            return data.get("data", [{}])[0].get("embedding", [])
    
    return embed


def print_distribution(name: str, scores: List[float], marker: str = "#"):
    """打印分布可视化"""
    min_s, max_s = min(scores), max(scores)
    avg_s = sum(scores) / len(scores)
    print(f"  {name}: {min_s:.3f} ~ {max_s:.3f} (avg {avg_s:.3f})")
    
    # 简单的直方图
    buckets = [0] * 10
    for s in scores:
        idx = min(int(s * 10), 9)
        buckets[idx] += 1
    
    max_count = max(buckets) if buckets else 1
    print("  分布: ", end="")
    for i, count in enumerate(buckets):
        bar_len = int(count / max_count * 5) if max_count > 0 else 0
        print(marker * bar_len + "." * (5 - bar_len), end=" ")
    print()
    print("        0.0       0.5       1.0")


# ============================================================
# 主函数
# ============================================================

def calibrate(embedding_url: str, embedding_model: str) -> Tuple[float, dict]:
    """
    执行校准
    
    Returns:
        (推荐阈值, 详细统计信息)
    """
    print(f"\n{'='*60}")
    print("Paw 记忆意图判断阈值校准工具")
    print(f"{'='*60}\n")
    
    print(f"[1/4] 连接 Embedding API...")
    print(f"  URL: {embedding_url}")
    print(f"  模型: {embedding_model}")
    
    embed = create_embed_function(embedding_url, embedding_model)
    
    # 测试连接
    try:
        test_result = embed("test")
        if not test_result:
            raise RuntimeError("Embedding 返回空结果")
        print(f"  ✓ 连接成功 (embedding 维度: {len(test_result)})")
    except Exception as e:
        raise RuntimeError(f"Embedding API 连接失败: {e}")
    
    print("\n[2/4] 计算锚点向量...")
    anchor_vector = embed(RECALL_INTENT_TEXT)
    
    print(f"[3/4] 计算样本相似度 ({len(POSITIVE_SAMPLES)} 正例 + {len(NEGATIVE_SAMPLES)} 负例)...")
    
    positive_scores = []
    negative_scores = []
    
    def build_embed_text(query: str, context: str) -> str:
        """构建用于 embedding 的文本（与 memory.py 中的逻辑一致）"""
        if context:
            return f"对话上下文:\n{context}\n\n用户新问题: {query}"
        return query
    
    print("\n  正例（需要回忆）:")
    for query, context in POSITIVE_SAMPLES:
        embed_text = build_embed_text(query, context)
        vec = embed(embed_text)
        score = cosine_similarity(vec, anchor_vector)
        positive_scores.append(score)
        status = "[v]" if score >= 0.35 else "[x]"
        ctx_indicator = " [有上下文]" if context else ""
        print(f"    {status} {score:.3f} | {query[:35]}{ctx_indicator}")
    
    print("\n  负例（即时问题/上下文已有答案）:")
    for query, context in NEGATIVE_SAMPLES:
        embed_text = build_embed_text(query, context)
        vec = embed(embed_text)
        score = cosine_similarity(vec, anchor_vector)
        negative_scores.append(score)
        status = "[v]" if score < 0.35 else "[x]"
        ctx_indicator = " [有上下文]" if context else ""
        print(f"    {status} {score:.3f} | {query[:35]}{ctx_indicator}")
    
    print("\n[4/4] 计算最优阈值...")
    
    # 统计信息
    pos_min, pos_max = min(positive_scores), max(positive_scores)
    pos_avg = sum(positive_scores) / len(positive_scores)
    neg_min, neg_max = min(negative_scores), max(negative_scores)
    neg_avg = sum(negative_scores) / len(negative_scores)
    
    # 计算最优阈值
    # 使用 4:6 权重，让阈值偏向正例（提高门槛，减少误触发）
    # 阈值 = 负例最大值 * 0.4 + 正例最小值 * 0.6
    recommended_threshold = neg_max * 0.4 + pos_min * 0.6
    
    # 计算分离度
    separation = pos_min - neg_max
    
    # 判断分离质量
    if separation > 0.1:
        quality = "优秀 [++]"
        quality_note = "两类样本分离良好，阈值可靠"
    elif separation > 0.05:
        quality = "良好 [+]"
        quality_note = "两类样本有一定分离，阈值较可靠"
    elif separation > 0:
        quality = "一般 [~]"
        quality_note = "两类样本分离较小，建议测试后微调"
    else:
        quality = "较差 [-]"
        quality_note = "两类样本存在重叠，该模型可能不太适合此任务"
        # 重叠时使用均值作为阈值
        recommended_threshold = (pos_avg + neg_avg) / 2
    
    stats = {
        "positive": {"min": pos_min, "max": pos_max, "avg": pos_avg, "scores": positive_scores},
        "negative": {"min": neg_min, "max": neg_max, "avg": neg_avg, "scores": negative_scores},
        "separation": separation,
        "quality": quality,
        "threshold": recommended_threshold,
    }
    
    # 输出结果
    print(f"\n{'='*60}")
    print("校准结果")
    print(f"{'='*60}\n")
    
    print("相似度分布:")
    print_distribution("需要回忆", positive_scores, "#")
    print_distribution("即时问题", negative_scores, "-")
    
    print(f"\n分离度: {separation:.3f} ({quality})")
    print(f"  └─ {quality_note}")
    
    print(f"\n+{'-'*40}+")
    print(f"|  推荐阈值: {recommended_threshold:.3f}".ljust(41) + " |")
    print(f"+{'-'*40}+")
    
    print(f"\n将以下配置添加到 config.yaml:")
    print(f"```yaml")
    print(f"recall:")
    print(f"  enabled: true")
    print(f"  threshold: {recommended_threshold:.2f}")
    print(f"```")
    
    return recommended_threshold, stats


def calibrate_api(embedding_url: str, embedding_model: str) -> dict:
    """
    API 调用版本，返回 JSON 格式结果
    
    Args:
        embedding_url: Embedding API 地址
        embedding_model: Embedding 模型名称
        
    Returns:
        dict: {"success": bool, "threshold": float, "quality": str, "error": str}
    """
    try:
        # 创建 embed 函数
        embed = create_embed_function(embedding_url, embedding_model)
        
        # 测试连接
        test_result = embed("test")
        if not test_result:
            return {"success": False, "error": "Embedding API 返回空结果"}
        
        # 计算锚点向量
        anchor_vector = embed(RECALL_INTENT_TEXT)
        
        # 计算样本相似度
        def build_embed_text(query: str, context: str) -> str:
            if context:
                return f"对话上下文:\n{context}\n\n用户新问题: {query}"
            return query
        
        positive_scores = []
        negative_scores = []
        
        for query, context in POSITIVE_SAMPLES:
            embed_text = build_embed_text(query, context)
            vec = embed(embed_text)
            score = cosine_similarity(vec, anchor_vector)
            positive_scores.append(score)
        
        for query, context in NEGATIVE_SAMPLES:
            embed_text = build_embed_text(query, context)
            vec = embed(embed_text)
            score = cosine_similarity(vec, anchor_vector)
            negative_scores.append(score)
        
        # 计算统计信息
        pos_min, pos_max = min(positive_scores), max(positive_scores)
        pos_avg = sum(positive_scores) / len(positive_scores)
        neg_min, neg_max = min(negative_scores), max(negative_scores)
        neg_avg = sum(negative_scores) / len(negative_scores)
        
        # 计算最优阈值
        recommended_threshold = neg_max * 0.4 + pos_min * 0.6
        
        # 计算分离度
        separation = pos_min - neg_max
        
        # 判断分离质量
        if separation > 0.1:
            quality = "优秀"
        elif separation > 0.05:
            quality = "良好"
        elif separation > 0:
            quality = "一般"
        else:
            quality = "较差"
            # 重叠时使用均值作为阈值
            recommended_threshold = (pos_avg + neg_avg) / 2
        
        return {
            "success": True,
            "threshold": round(recommended_threshold, 2),
            "quality": quality,
            "separation": round(separation, 3),
            "positive_range": f"{pos_min:.3f} ~ {pos_max:.3f}",
            "negative_range": f"{neg_min:.3f} ~ {neg_max:.3f}"
        }
        
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Embedding API 连接失败，请检查服务是否已启动"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Embedding API 请求超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    try:
        # 获取参数
        url_arg = sys.argv[1] if len(sys.argv) > 1 else None
        model_arg = sys.argv[2] if len(sys.argv) > 2 else None
        
        embedding_url, embedding_model = get_embedding_config(url_arg, model_arg)
        
        threshold, stats = calibrate(embedding_url, embedding_model)
        
        print(f"\n校准完成！")
        return 0
        
    except RuntimeError as e:
        print(f"\n错误: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\n已取消")
        return 1
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
