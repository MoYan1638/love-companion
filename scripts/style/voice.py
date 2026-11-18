#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交流语气控制器（M4）——恋人式短句、口语同步、深夜温柔模式、打字节奏模拟

强度四档：关闭 / 轻柔 / 标准 / 深度（可随场景自动切换）
设计：只做**形式层**改写（拆分/语气/节奏），不改写事实内容，
     配合 style/humanizer.py 的守门员一起用。

与其他层的一条硬边界（回复十条第 6 条）：**本层不生产断句标点**。
拆句、补语气词、加称呼都不补句号逗号，需要分隔时用空格。
真正的删标点由 style/typography.py 统一收口，这里只是不添乱。
"""

import re
from datetime import datetime
from typing import List, Optional

LEVELS = {"关闭": 0, "轻柔": 1, "标准": 2, "深度": 3}

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])")
_CLAUSE_SPLIT = re.compile(r"(?<=[，,])")
_SPACED = re.compile(r"[ \t]+")


def split_short(text: str, max_len: int = 12) -> List[str]:
    """把长回复拆成短句（模拟真人一句一句发）

    - 先按句末标点切
    - 文本已经过第 6 条（无断句标点、空格隔句）时，改按空格切
    - 仍过长的按逗号再切
    - **不补标点**：补句号等于把刚删掉的标点又加回来

    `max_len` 是日常目标，不是卡死的线：单个短句不超过 `max_len + 6` 就整句保留，
    为凑十字把一句十三四字腰斩反而难看（第 8 条的软硬双限，同 typography.py）。
    """
    text = (text or "").strip()
    if not text:
        return []
    hard = max_len + 6
    segs = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if len(segs) <= 1 and _SPACED.search(text):
        segs = [s for s in _SPACED.split(text) if s]

    pieces: List[str] = []
    for seg in segs:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= hard:
            pieces.append(seg)
            continue
        buf = ""
        for clause in _CLAUSE_SPLIT.split(seg):
            if not clause:
                continue
            if buf and len(buf) + len(clause) > max_len:
                pieces.append(_polish(buf))
                buf = clause
            else:
                buf += clause
        if buf:
            pieces.append(_polish(buf))
    return [p for p in pieces if p]


def _polish(seg: str) -> str:
    """切出来的片段直接返回，不补句号（第 6 条）"""
    return (seg or "").strip()


def is_night(hour: Optional[int] = None) -> bool:
    """深夜温柔模式判定（23:00–05:59）"""
    hour = datetime.now().hour if hour is None else hour
    return hour >= 23 or hour < 6


def shape(text: str, level: str = "标准", nickname: str = "",
          hour: Optional[int] = None) -> List[str]:
    """按强度档位改写为可逐条发送的短句列表

    Args:
        text: 原始回复
        level: 关闭 / 轻柔 / 标准 / 深度
        nickname: 对用户的称呼（来自人设），深度档会自然带上
        hour: 当前小时，用于深夜模式
    """
    intensity = LEVELS.get(level, 2)
    if intensity == 0 or not text:
        return [text] if text else []

    # 强度越高，一条越短（一句十字顶天是标准档的线，见 reply-rules 第 8 条）
    max_len = {1: 16, 2: 12, 3: 10}[intensity]
    night = is_night(hour)
    if night:
        max_len = int(max_len * 0.8)  # 深夜更短更柔

    pieces = split_short(text, max_len=max_len)

    if intensity >= 3:
        pieces = [_add_modal(p, nickname, night) for p in pieces]
    elif intensity >= 2 and night:
        pieces = [_soften(p) for p in pieces]

    # 收口：本层不生产断句标点，输入带进来的也不许漏出去
    # （拆句时逗号/句号会留在段尾，形状已经定了，这里只清外形。
    #   情绪句号在这里也清——那是写话层自己的决定，机械改写不留。）
    from scripts.style import typography  # 局部导入避免模块级循环依赖
    return [typography.strip_punct(p, keep_emotion_stop=False) for p in pieces]


def _add_modal(sentence: str, nickname: str = "", night: bool = False) -> str:
    """深度档：加语气词 / 称呼，让句子更像人在说话

    尾部的断句标点先清干净再加语气词，否则会拼出「辛苦啦，哦」这种
    半截标点（第 6 条留下的旧标点被新语气词顶在半空）。
    """
    s = sentence.rstrip("。！？!?，,、；;：:")
    if nickname and len(s) < 12 and nickname not in s:
        s = f"{nickname} {s}"
    if not re.search(r"[呀呢嘛哦啦~～]$", s):
        s = s + ("呀" if not night else "哦")
    tail = "～" if not night else "..."
    return s + tail


def _soften(sentence: str) -> str:
    """轻柔档（深夜）：语气放缓——去掉感叹，不添句号"""
    s = sentence.rstrip("。！？!?")
    s = s.replace("！", " ").replace("!", " ")
    return s.strip()


if __name__ == "__main__":
    import sys
    demo = sys.argv[1] if len(sys.argv) > 1 else (
        "今天辛苦啦，我听你说项目很紧，先别硬撑，喝口热水，早点休息，我在这儿陪着你。"
    )
    for lv in ("关闭", "轻柔", "标准", "深度"):
        print(f"[{lv}]")
        for line in shape(demo, level=lv, nickname="宝贝", hour=23):
            print("  " + line)
