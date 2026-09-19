#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在线轻注入器（M1）——方案红线 2 的执行者

职责：
1. 汇总各离线模块产出的「注入摘要」
2. 按优先级 + 总预算分配额度（core/schema.py::allocate_budget）
3. 逐段估算 Token，超支就截断，截不动就整段丢弃
4. 输出可直接拼进 System Prompt 的片段

铁律：总预算（默认 500 Token）是硬约束，不是建议值。
单模块上限只是"最多能给多少"，各模块上限之和 580 > 500，因此低优先模块会被压缩。
"""

import math
import re
from typing import Any, Dict, List, Optional

from scripts.core import schema

_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def estimate_tokens(text: str) -> int:
    """粗略估算 Token：CJK 约 1 字 1 token，其余按 4 字符 1 token

    刻意保守（宁可高估），避免超预算。
    """
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return int(math.ceil(cjk + other / 4.0))


def truncate_to_tokens(text: str, limit: int) -> str:
    """按 Token 预算截断（按字符近似，保留完整句子更好，此处保守按字数切）"""
    if estimate_tokens(text) <= limit:
        return text
    # 逐字符累加直到超预算
    acc, tokens = [], 0
    for ch in text:
        t = estimate_tokens(ch)
        if tokens + t > limit:
            break
        acc.append(ch)
        tokens += t
    return "".join(acc).rstrip("，,。、；; ")


class Injector:
    """注入摘要汇总与预算控制"""

    def __init__(self, total_budget: Optional[int] = None, sections: Optional[Dict[str, str]] = None):
        self.total_budget = int(
            total_budget if total_budget is not None else schema.DEFAULT_INJECTION_BUDGET["合计上限"]
        )
        self.sections: Dict[str, str] = dict(sections or {})

    def add(self, key: str, text: str) -> None:
        """添加一个注入段；key 需为预算表中的模块名"""
        if key not in schema.DEFAULT_INJECTION_BUDGET:
            raise KeyError(f"未登记的注入段 {key!r}，预算表只有：{list(schema.DEFAULT_INJECTION_BUDGET)}")
        self.sections[key] = text or ""

    def build(self) -> Dict[str, Any]:
        """按优先级分配预算并构建注入上下文

        Returns:
            {
              "sections": {模块: 实际注入文本},
              "tokens":   {模块: 估算 Token},
              "truncated": [被截断的模块],
              "dropped":   [被丢弃的模块],
              "total_tokens": 总估算 Token,
              "budget": 总预算,
            }
        """
        quota = schema.allocate_budget(self.total_budget)
        sections: Dict[str, str] = {}
        tokens: Dict[str, int] = {}
        truncated: List[str] = []
        dropped: List[str] = []

        for key in schema.INJECTION_PRIORITY:
            text = (self.sections.get(key) or "").strip()
            if not text:
                continue
            limit = quota.get(key, 0)
            if limit <= 0:
                dropped.append(key)
                continue
            used = estimate_tokens(text)
            if used > limit:
                text = truncate_to_tokens(text, limit)
                truncated.append(key)
                used = estimate_tokens(text)
            if not text:
                dropped.append(key)
                continue
            sections[key] = text
            tokens[key] = used

        return {
            "sections": sections,
            "tokens": tokens,
            "truncated": truncated,
            "dropped": dropped,
            "total_tokens": sum(tokens.values()),
            "budget": self.total_budget,
        }

    def render(self, title: str = "运行时上下文") -> str:
        """渲染成可拼进 System Prompt 的片段"""
        built = self.build()
        if not built["sections"]:
            return ""
        lines = [f"【{title}】"]
        for key in schema.INJECTION_PRIORITY:
            if key in built["sections"]:
                lines.append(f"- {key}：{built['sections'][key]}")
        return "\n".join(lines)


if __name__ == "__main__":
    import json

    inj = Injector()
    inj.add("人格指令", "你是温婉，温柔体贴，说话轻柔。" * 20)   # 故意超预算
    inj.add("记忆片段", "用户喜欢三分糖奶茶；生日 5 月 20 日")
    print(inj.render())
    print(json.dumps(inj.build(), ensure_ascii=False, indent=2))
