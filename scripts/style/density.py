#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
密度校准层（M4.5）——把「去 AI 味」从黑名单升级为双向密度校准

设计理念（借鉴 dsh-fish-tone 的「按密度压，不按禁用」思路，按恋人场景定制）：

1. AI 味不是「AI 用了某个词」，而是「AI 把某些人类也用的东西的密度拉爆了，
   又把另一些人类高频的东西用少了」。
2. 所以这里做**双向**：
   - 结构腔「超了压」：不是X而是Y / 最…的是 / 破折号 / 三段并列 … 按真人密度给预算，
     超了才标记（破折号可安全改逗号，其余只报告，交给上层重写）。
   - 欠用词「少了补」：也/还（关系）、好像/应该/感觉/可能（留白）、根本/贼/巨（加强），
     这些 AI 明显欠用，按真人密度提示补回。
3. 与 humanizer.py 的分工（红线）：
   - humanizer.py = **硬红线**：身份露馅词（"作为AI"）、替用户断言情绪（"你一定很"）
     这些是性质问题，不是密度问题，必须禁用，不能软化成密度。
   - density.py = **软校准**：结构腔密度 + 微标记密度，超了压、少了补。
   两者独立运行，互不替代。

密度基线采用「通用 + 恋人」双层融合：
- 通用层：网络口语实测密度（B站评论 10 万条量出的 per1k，见 FRAMES / MARKS 注释）
- 恋人层：恋人对话专项词表（COMMON_LOVE / LOVE_MARKS），这些词在恋人场景是高频且正当的，
  不能拿通用密度一刀切；只有「密度失控」才提示收敛。

零外部依赖，只靠 Python 标准库。离线运行，不占主生成 Token。
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 一、结构腔（超了压）：通用口语实测密度
# per1k = 真人每千字出现次数。AI 普遍是这些数的 5~37 倍。
# ---------------------------------------------------------------------------

# tier 说明：
#   strict —— 基本只在长文里允许，短对话出现即偏高
#   soft   —— 每几百字允许一个，超了才压
FRAMES: List[Dict[str, Any]] = [
    {"id": "not-but",    "name": "不是X而是Y", "tier": "strict", "per1k": 0.06,
     "re": re.compile(r"不是[^。！？]{1,24}(?:，\s*(?:这|那|它|就)?是|而是)")},
    {"id": "most-de",    "name": "最…的是",    "tier": "strict", "per1k": 0.05,
     "re": re.compile(r"最[^，。]{1,8}的是")},
    {"id": "first-then", "name": "先…再…",    "tier": "strict", "per1k": 0.01,
     "re": re.compile(r"先[^，。]{1,10}再")},
    {"id": "notonly",    "name": "不仅…更",    "tier": "strict", "per1k": 0.01,
     "re": re.compile(r"不仅[^，。]{1,12}(?:更|还)")},
    {"id": "de-copula",  "name": "X的是Y",     "tier": "soft",   "per1k": 0.37,
     "re": re.compile(r"[^的，。！？]{1,8}的是[^，。]")},
    {"id": "triple",     "name": "三段并列",   "tier": "soft",   "per1k": 0.23,
     "re": re.compile(r"[^，。、]{2,8}、[^，。、]{2,8}、[^，。、]{2,8}")},
    {"id": "emdash",     "name": "破折号",     "tier": "soft",   "per1k": 0.22,
     "re": re.compile(r"——+|—"), "fix": "comma"},
    {"id": "yue",        "name": "越…越",      "tier": "soft",   "per1k": 0.16,
     "re": re.compile(r"越[^，。]{1,8}越")},
    {"id": "really",     "name": "真正/本质上", "tier": "soft",   "per1k": 0.17,
     "re": re.compile(r"(?:真正|本质上|归根结底)")},
    {"id": "roadmap",    "name": "首先/其次/综上", "tier": "soft", "per1k": 0.5,
     "re": re.compile(r"(?:首先|其次|综上所述|总而言之)")},
]

# ---------------------------------------------------------------------------
# 二、微标记（少了补）：AI 欠用的词
# human = 真人每千字出现次数，ai = AI 每千字出现次数（实测，AI 明显欠用）
# ---------------------------------------------------------------------------

MARKS: List[Dict[str, Any]] = [
    # 关系组：把对方拉进来
    {"ch": "也",   "kind": "relate",    "human": 3.40, "ai": 2.87},
    {"ch": "还",   "kind": "relate",    "human": 3.37, "ai": 3.22},
    # 留白组：AI 不猜，显得生硬
    {"ch": "好像", "kind": "hedge",     "human": 0.25, "ai": 0.09},
    {"ch": "应该", "kind": "hedge",     "human": 0.41, "ai": 0.08},
    {"ch": "感觉", "kind": "hedge",     "human": 0.70, "ai": 0.24},
    {"ch": "可能", "kind": "hedge",     "human": 0.53, "ai": 0.17},
    {"ch": "估计", "kind": "hedge",     "human": 0.07, "ai": 0.03},
    # 加强组：人激动会加词，AI 一个音量
    {"ch": "根本", "kind": "intensify", "human": 0.15, "ai": 0.03},
    {"ch": "特别", "kind": "intensify", "human": 0.17, "ai": 0.02},
    {"ch": "竟然", "kind": "intensify", "human": 0.07, "ai": 0.01},
    {"ch": "明明", "kind": "intensify", "human": 0.08, "ai": 0.02},
]

# ---------------------------------------------------------------------------
# 三、恋人场景专项层：这些词在恋人对话里高频且正当，不能拿通用密度一刀切
# 只有「密度失控」才提示收敛（比如一条消息连喊三个不同昵称）
# ---------------------------------------------------------------------------

# 恋人高频亲昵表达（每千字真人恋人对话的合理密度，远高于通用口语）
COMMON_LOVE: List[Dict[str, Any]] = [
    {"name": "昵称",     "words": ("宝宝", "宝贝", "亲爱的", "乖乖", "老婆", "老公", "小可爱"),
     "per1k": 4.0, "note": "恋人对话高频正当，但一条消息堆多个昵称即失控"},
    {"name": "亲亲抱抱", "words": ("抱抱", "亲亲", "摸摸", "贴贴", "蹭蹭"),
     "per1k": 2.0, "note": "亲昵动作，密度过高显得模板化"},
    {"name": "想你念你", "words": ("想你", "想你了", "好想你", "一直在想你"),
     "per1k": 1.5, "note": "高频但每句都说会假"},
    {"name": "爱称后缀", "words": ("嘛", "啦", "呀", "呢", "哦"),
     "per1k": 8.0, "note": "语气词，恋人场景本身高频，只拦「句句都挂」"},
]

# 恋人场景的「欠用」标记：真人恋人对话里高频、AI 恋人反而欠用的
LOVE_MARKS: List[Dict[str, Any]] = [
    {"ch": "陪你", "kind": "relate", "note": "把「我」和「你」绑在一起，AI 常只说事不说人"},
    {"ch": "心疼", "kind": "relate", "note": "情绪回应，AI 常给建议而非共情"},
    {"ch": "我猜", "kind": "hedge",  "note": "不确定时主动说，AI 习惯断言"},
    {"ch": "说真的", "kind": "relate", "note": "拉近距离，AI 缺这种口语锚点"},
]

_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def _count_chars(text: str) -> int:
    """数中文字符数（密度分母，只算汉字，标点空格不计）"""
    return len(_CJK_CHAR.findall(text or ""))


def _budget(frames: List[Dict[str, Any]], chars: int) -> Dict[str, int]:
    """一篇多长，就允许多少个结构腔"""
    out: Dict[str, int] = {}
    for f in frames:
        raw = (f["per1k"] * chars) / 1000.0
        if f["tier"] == "soft":
            out[f["id"]] = max(1 if chars >= 200 else 0, int(round(raw * 2)))
        else:
            out[f["id"]] = int(round(raw))
    return out


def scan_structures(text: str) -> List[Dict[str, Any]]:
    """扫描结构腔（超了压的那一半）"""
    src = text or ""
    rows: List[Dict[str, Any]] = []
    for f in FRAMES:
        spans = [m.group(0) for m in f["re"].finditer(src)]
        if spans:
            rows.append({"id": f["id"], "name": f["name"], "tier": f["tier"],
                         "count": len(spans), "spans": spans[:5]})
    return rows


def thin_structures(text: str, skip: Optional[callable] = None) -> Dict[str, Any]:
    """把超出预算的结构腔压下去。

    只有破折号会自动改成逗号；其余只报告，交给上层重写（不硬改语义）。
    skip(line) 返回 True 的行（代码块/路径/表格）整行不碰。
    """
    src = text or ""
    if _count_chars(src) < 80:
        return {"text": src, "thinned": 0, "over": []}

    lines = src.split("\n")
    keep = [not (skip and skip(l)) for l in lines]
    chars = _count_chars("".join(l for l, k in zip(lines, keep) if k))
    allow = _budget(FRAMES, chars)

    counts: Dict[str, int] = {}
    for i, line in enumerate(lines):
        if not keep[i]:
            continue
        for row in scan_structures(line):
            counts[row["id"]] = counts.get(row["id"], 0) + row["count"]

    over: List[Dict[str, Any]] = []
    thinned = 0
    for fid, cnt in counts.items():
        allowed = allow.get(fid, 0)
        if cnt <= allowed:
            continue
        f = next((x for x in FRAMES if x["id"] == fid), None)
        if f is None:
            continue
        over.append({"id": fid, "name": f["name"], "count": cnt, "allowed": allowed})
        if "fix" not in f:
            continue
        surplus = cnt - allowed
        for i, line in enumerate(lines):
            if surplus <= 0:
                break
            if not keep[i]:
                continue
            lines[i], n = f["re"].subn(
                lambda m: m.group(0).replace("——", "，").replace("—", "，").replace("、", "，"),
                line, count=surplus)
            surplus -= n
            thinned += n

    return {"text": "\n".join(lines), "thinned": thinned, "over": over}


def scan_marks(text: str) -> Dict[str, Any]:
    """扫描微标记密度（少了补的那一半），返回关系/留白/加强三组密度"""
    src = text or ""
    chars = max(1, _count_chars(src))
    relate = hedge = intensify = 0
    for m in MARKS:
        n = src.count(m["ch"])
        if m["kind"] == "relate":
            relate += n
        elif m["kind"] == "intensify":
            intensify += n
        else:
            hedge += n
    return {
        "chars": chars,
        "relate": round(relate / chars * 1000, 2),
        "hedge": round(hedge / chars * 1000, 2),
        "intensify": round(intensify / chars * 1000, 2),
        # 真人基线（每千字）
        "relate_line": 6.8,
        "hedge_line": 2.0,
        "intensify_line": 0.9,
    }


def scan_love(text: str) -> Dict[str, Any]:
    """恋人专项层：亲昵表达密度是否失控（高了收敛，低了补）"""
    src = text or ""
    chars = max(1, _count_chars(src))
    over: List[Dict[str, Any]] = []
    under: List[Dict[str, Any]] = []
    for item in COMMON_LOVE:
        n = sum(src.count(w) for w in item["words"])
        per1k = round(n / chars * 1000, 2)
        if per1k > item["per1k"] * 1.5:
            over.append({"name": item["name"], "count": n, "per1k": per1k,
                         "limit": item["per1k"], "note": item["note"]})
    for m in LOVE_MARKS:
        if m["ch"] not in src:
            under.append({"ch": m["ch"], "kind": m["kind"], "note": m["note"]})
    return {"over": over, "under": under}


def assess(text: str) -> Dict[str, Any]:
    """一站式密度评估：结构腔 + 微标记 + 恋人专项，返回给上层参考"""
    structs = scan_structures(text)
    marks = scan_marks(text)
    love = scan_love(text)

    # 综合建议：哪里超了、哪里缺了
    chars = max(1, _count_chars(text))
    allow = _budget(FRAMES, chars)
    over_structs = [s for s in structs if s["count"] > allow.get(s["id"], 0)]
    under_marks = [
        k for k, v, line in (
            ("relate", marks["relate"], marks["relate_line"]),
            ("hedge", marks["hedge"], marks["hedge_line"]),
            ("intensify", marks["intensify"], marks["intensify_line"]),
        ) if v < line * 0.5
    ]

    return {
        "structs": structs,
        "over_structs": over_structs,
        "marks": marks,
        "under_marks": under_marks,
        "love": love,
        "advice": {
            "压": [s["name"] for s in over_structs],
            "补": under_marks,
        },
    }


if __name__ == "__main__":
    import sys
    import json
    demo = sys.argv[1] if len(sys.argv) > 1 else (
        "首先，你需要明白情绪不是问题；其次，逃避也不是办法；最后，"
        "最关键的是一切都会好起来的，我会一直陪着你。"
    )
    print(json.dumps(assess(demo), ensure_ascii=False, indent=2))
