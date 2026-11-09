#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Token 估算。

预算必须在发请求之前算出来，而服务端只在请求之后才告诉我们真实用量，
所以这里只能估算。旧的"字符数除以 4"对中文低估约三倍，导致预算形同虚设。

做法：中日韩字符按 1 字 1 token，其余按 4 字符 1 token；整体再乘以一个
由真实 usage 校准出来的系数。校准只在拿到服务端用量时发生，拿不到就
维持启发式值，不会假装精确。
"""

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List

_CJK = re.compile(
    "[　-〿㐀-䶿一-鿿＀-￯぀-ヿ가-힯]"
)


@dataclass
class TokenCounter:
    # 真实 token 数与字符启发式结果的比例，1.0 表示相信启发式
    scale: float = 1.0
    samples: int = 0

    def raw(self, text: str) -> int:
        """未经校准的字符启发式结果。"""
        if not text:
            return 0
        cjk = len(_CJK.findall(text))
        other = len(text) - cjk
        return cjk + math.ceil(other / 4)

    def count(self, text: str) -> int:
        return max(0, int(self.raw(text) * self.scale))

    def calibrate(self, raw_total: int, prompt_tokens: int) -> None:
        """用服务端返回的 prompt_tokens 修正系数。"""
        if raw_total <= 0 or prompt_tokens <= 0:
            return
        observed = prompt_tokens / raw_total
        if self.samples == 0:
            self.scale = observed
        else:
            self.scale = self.scale * 0.7 + observed * 0.3
        # 单个样本可能受工具 schema、缓存等因素影响，限制修正幅度
        self.scale = min(max(self.scale, 0.4), 3.0)
        self.samples += 1


# 单进程应用共用一个计数器：校准来源（模型请求）与使用方（预算、状态栏）
# 是同一份会话上下文，分开维护只会让两边数字不一致。
DEFAULT_COUNTER = TokenCounter()


def count_text(text: str) -> int:
    return DEFAULT_COUNTER.count(text)


def count_json(value: Any) -> int:
    if not value:
        return 0
    return DEFAULT_COUNTER.count(json.dumps(value, ensure_ascii=False))


def count_messages(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += count_text(content)
        elif isinstance(content, list):
            total += count_json(content)
        total += count_json(message.get("tool_calls"))
    return total


def count_messages_raw(messages: List[Dict[str, Any]]) -> int:
    """未经校准的基础估算。

    校准本身要用它做分母；如果用已校准的结果去校准，系数会自我强化，
    一旦遇到一次异常用量就永久跑偏。
    """
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += DEFAULT_COUNTER.raw(content)
        elif isinstance(content, list):
            total += DEFAULT_COUNTER.raw(json.dumps(content, ensure_ascii=False))
        tool_calls = message.get("tool_calls")
        if tool_calls:
            total += DEFAULT_COUNTER.raw(json.dumps(tool_calls, ensure_ascii=False))
    return total
