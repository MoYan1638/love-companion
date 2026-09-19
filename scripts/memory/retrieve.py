#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆多路检索（M2）——语义 + 时间 + 重要性 + 关系路径 → Top-3

语义部分用字符二元组重叠度（对中文友好、零依赖），
不做向量化是为了守住"只依赖标准库"的分发约束。
若后续确认可引入轻量向量库，可替换 _semantic_score 而不动其余逻辑。
"""

import math
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from scripts.pipeline.injector import estimate_tokens

_CJK = re.compile(r"[\u4e00-\u9fff]")
_PUNCT = re.compile(r"[，。！？、；：,.!?;:\s]+")

# 关系类记忆（共享事件 / 里程碑）额外加权 —— 这是"我们的故事"的核心
RELATIONAL_TYPES = ("共享事件", "里程碑")
RELATIONAL_BOOST = 1.35


def _tokens(text: str) -> List[str]:
    """中文按字、英文按词切分"""
    text = (text or "").lower()
    words = [w for w in _PUNCT.split(text) if w]
    out: List[str] = []
    for w in words:
        if _CJK.search(w):
            out.extend(list(w))               # 中文逐字
            out.extend(w[i:i + 2] for i in range(len(w) - 1))  # 二元组
        else:
            out.append(w)
    return out


def _semantic_score(query: str, content: str) -> float:
    """字符级重叠度 0–1"""
    q, c = set(_tokens(query)), set(_tokens(content))
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    return overlap / math.sqrt(len(q) * len(c))


def _recency_score(entry: Dict[str, Any], now: datetime) -> float:
    """时间衰减：越近期权重越高，30 天半衰"""
    stamp = entry.get("last_recalled_at") or entry.get("updated_at") or entry.get("created_at")
    try:
        last = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return 0.3
    days = max(0.0, (now - last).total_seconds() / 86400.0)
    return 0.5 ** (days / 30.0)


def score_entry(entry: Dict[str, Any], query: str, now: Optional[datetime] = None) -> float:
    """综合打分：语义 0.5 + 重要性 0.25 + 时间 0.15 + 关系路径 0.10"""
    now = now or datetime.now()
    semantic = _semantic_score(query, str(entry.get("content", "")))
    importance = float(entry.get("importance", 0.5))
    recency = _recency_score(entry, now)
    relational = 1.0 if entry.get("type") in RELATIONAL_TYPES else 0.4
    return (semantic * 0.5 + importance * 0.25 + recency * 0.15 + relational * 0.10) * (
        RELATIONAL_BOOST if entry.get("type") in RELATIONAL_TYPES else 1.0
    )


def top_k(entries: Iterable[Dict[str, Any]], query: str, k: int = 3,
          token_budget: int = 150, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """按综合分取 Top-K，并受 Token 预算约束

    Args:
        entries: 候选记忆
        query: 当前用户输入（或当前话题摘要）
        k: 最多取几条（方案要求 Top-3）
        token_budget: 注入预算（方案要求 <150）

    Returns:
        命中的记忆条目列表（含 _score 字段，便于调试与可解释面板）
    """
    now = now or datetime.now()
    scored = []
    for e in entries:
        s = score_entry(e, query, now)
        item = dict(e)
        item["_score"] = round(s, 4)
        scored.append(item)
    scored.sort(key=lambda x: x["_score"], reverse=True)

    picked: List[Dict[str, Any]] = []
    used = 0
    for item in scored:
        if len(picked) >= k:
            break
        cost = estimate_tokens(str(item.get("content", "")))
        if used + cost > token_budget:
            continue
        picked.append(item)
        used += cost
    return picked


def render(memories: List[Dict[str, Any]]) -> str:
    """渲染成可注入的简短文本（每条都带 id，便于追溯）"""
    return "；".join(f"#{m.get('id')} {m.get('content')}" for m in memories)


if __name__ == "__main__":
    import sys
    from scripts.memory.store import MemoryStore

    q = sys.argv[1] if len(sys.argv) > 1 else "今天很累"
    store = MemoryStore()
    hits = top_k(store.all(), q)
    print(render(hits) or "(无匹配记忆)")
    for h in hits:
        print(f"  #{h['id']} [{h['type']}] score={h['_score']} {h['content']}")
