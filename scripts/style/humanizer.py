#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Humanizer 守门员（M4）——AI 写作特征检测，离线运行，不占主生成 Token

三层黑名单：
- L1 硬性禁用词：一眼 AI 腔的固定搭配，命中即必须重写
- L2 结构模式：AI 偏爱的组织方式（三段式、逐条罗列、破折号堆砌）
- L3 风格偏差：统计层面的不自然（句长失衡、emoji 过量、语气词缺失）

检测结果供 style/voice.py 改写，或返回给上层让模型重写。
"""

import re
from typing import Any, Dict, List

# L1：硬性禁用词（出现即判为 AI 腔）
L1_WORDS: List[str] = [
    "首先", "其次", "再次", "最后", "综上所述", "总而言之", "总的来说",
    "值得注意的是", "不难看出", "显而易见", "众所周知",
    "在当今社会", "随着.*的发展", "让我们", "让我们一起",
    "作为一个AI", "作为一个人工智能", "我是AI", "我希望这能帮到你",
    "如果你有任何问题", "欢迎随时", "希望我的回答", "以上就是",
    "事实上", "从某种程度上", "在一定程度上", "需要注意的是",
]

# L2：结构模式（正则）
L2_PATTERNS: List[tuple] = [
    ("三段式罗列", re.compile(r"(?:^|[。；;\n])\s*(?:首先|第一|其一).{0,40}(?:其次|第二|其二).{0,40}(?:最后|第三|其三)")),
    ("逐条编号", re.compile(r"(?:^|\n)\s*(?:\d+[.、)]|[一二三四五六七八九十]+[、.])")),
    ("破折号堆砌", re.compile(r"——[^。！？]{0,30}——")),
    ("括号补充说明过多", re.compile(r"（[^）]{6,}）")),
    ("排比堆砌", re.compile(r"(?:[^，。！？]{4,10}，){3,}")),
    ("每段以连接词开头", re.compile(r"(?:^|[。！？\n])\s*(?:此外|另外|而且|并且|因此|所以|然而|不过)")),
]

_CJK_PUNCT = re.compile(r"[。！？!?；;]")
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
_MODAL = ("呀", "呢", "嘛", "哦", "啦", "~", "～")


def scan(text: str) -> Dict[str, Any]:
    """检测一段回复的 AI 写作特征"""
    text = text or ""
    hits_l1 = [w for w in L1_WORDS if re.search(w, text)]
    hits_l2 = [name for name, pat in L2_PATTERNS if pat.search(text)]

    sentences = [s for s in _CJK_PUNCT.split(text) if s.strip()]
    avg_len = (sum(len(s) for s in sentences) / len(sentences)) if sentences else 0
    emoji_count = len(_EMOJI.findall(text))
    modal_count = sum(text.count(m) for m in _MODAL)

    l3: List[str] = []
    if sentences and avg_len > 45:
        l3.append(f"句子过长（平均 {avg_len:.0f} 字）")
    if emoji_count > 3:
        l3.append(f"emoji 过多（{emoji_count} 个）")
    if len(text) >= 20 and modal_count == 0:
        l3.append("缺少语气词，像书面说明")
    if text.count("，") > len(sentences) * 3:
        l3.append("逗号密度过高，长句堆砌")

    # 综合评分：命中越多越"AI"
    score = min(1.0, len(hits_l1) * 0.25 + len(hits_l2) * 0.2 + len(l3) * 0.12)
    return {
        "l1": hits_l1, "l2": hits_l2, "l3": l3,
        "score": round(score, 2),
        "clean": not hits_l1 and not hits_l2 and not l3,
        "stats": {"sentences": len(sentences), "avg_len": round(avg_len, 1),
                  "emoji": emoji_count, "modal": modal_count},
    }


def is_clean(text: str) -> bool:
    return scan(text)["clean"]


if __name__ == "__main__":
    import sys
    demo = sys.argv[1] if len(sys.argv) > 1 else (
        "首先，你需要理解自己的情绪；其次，可以尝试深呼吸；最后，保持规律作息。"
    )
    import json
    print(json.dumps(scan(demo), ensure_ascii=False, indent=2))
