#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排版层（回复规约的第 6、8 条）——把「写好的话」变成「能发出去的消息」

这一层与前面三道守门的分工（红线，互不替代）：

- humanizer.py 判「这一条像不像 AI 写的」——性质问题
- density.py   判「用词密度像不像真人」——密度问题
- dialogue.py  判「几条连起来像不像两个人在说话」——多轮形态问题
- 本文件       判「外形对不对」——排版问题：有没有标点、一条是不是太长

前三个都在**评价**，这一层**动手改**。改的只有外形，不碰一个字的意思：

1. **不带句号逗号，用空格隔开**（第 6 条）
   聊天窗里「我在。你说。」像写作文；「我在 你说」才是打字。
   去掉的是**断句标点**：。，、；：！？ 及英文对应。
   保留的是**语气零件**：省略号（…留有白）、括号（补白）、引号书名号（引用原话）、
   破折号（转折）。把省略号也删掉，留白就没了，句子会变得又硬又平。

2. **一句别太长**（第 8 条）
   「控篇幅」不是少说话，是**一句话别长**：当代年轻人的亲密对话里一条十字顶天，
   说得多就多发几条，不把三句塞进一条。超过上限就断开，优先在空格处断
   （那是上一句的断点），其次硬切。四十字一条读起来像通知，不像聊天。

3. **短回应可以带一个句号**（第 6 条的例外）
   「哦哦。」「嗯嗯。」「呃。」——有人习惯在极短回应末尾点一个句号，
   那是语气（收得干净、有点冷淡），不是作文感。默认**不加**，要加靠设置开。

设计原则：
- **只改外形，不改语义**：删标点不改字，断句不改顺序
- **可开关**：有人就喜欢带标点打字，`回复风格.无标点 = False` 时只做长度控制
- **可回退**：改完给出 audit，告诉上层「改了什么」，不是静默篡改
- 零依赖、纯函数、不落盘

用法：

    from scripts.style import typography
    typography.format_reply("我在。你说。")        # ['我在 你说']
    typography.audit("我在。你说。")                # {'punct': 2, 'longest': 5, ...}

    # 命令行（Agent 发送前可直接跑）
    python scripts/style/typography.py "我在。你说。"
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 断句标点：这些是「作文感」的来源，聊天里一律换成空格
TERMINAL = "。，、；：！？,.;:!?"

# 语气零件：删了语义会变，必须保留
KEEP = "…—（）()「」“”‘’《》〈〉～~·"

# 一条消息的字数上限：一句十字顶天，留两字余量给语气词和 emoji
DEFAULT_MAX_CHARS = 12

# 短回应：整条不超过这么多字、且只有一个末尾句号时，可以选择保留那个句号
# 定在 3 是有意的：「哦哦。」「嗯嗯。」「呃。」「好的。」都是语气词级别；
# 「我知道了。」这类完整回应带句号会显得冷硬，不放进去。
SHORT_REPLY_MAX = 3
_SHORT_STOP = re.compile(r"^([^。，、；：！？,.;:!?\s]{1,%d})。$" % SHORT_REPLY_MAX)


def strip_punct(text: str, keep_short_stop: bool = False) -> str:
    """去掉断句标点，用空格隔开（第 6 条）

    `keep_short_stop=True` 时保留「哦哦。」「嗯嗯。」这类**短回应的末尾句号**——
    那是语气不是断句，删了会变成「哦哦」，冷淡的分寸差一点。
    只认「整条 ≤4 字 + 只有一个末尾句号」，多一个字或句中还有标点就不算。

    >>> strip_punct("我在。你说。")
    '我在 你说'
    >>> strip_punct("不是。算了。")
    '不是 算了'
    >>> strip_punct("哦哦。", keep_short_stop=True)
    '哦哦。'
    >>> strip_punct("哦哦。", keep_short_stop=False)
    '哦哦'
    """
    src = (text or "").strip()
    if not src:
        return ""
    if keep_short_stop and _SHORT_STOP.match(src):
        return src
    out = "".join(" " if ch in TERMINAL else ch for ch in src)
    out = out.replace("\r", " ").replace("\n", " ")
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip(" \t")


def split_by_length(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> List[str]:
    """按长度切条，优先在空格处断（第 8 条）

    空格是上一步留下的断点，在那里断开最不破坏语气；
    单个词就超长时只能硬切，否则会产出一条永远发不出去的消息。
    """
    src = (text or "").strip()
    if not src:
        return []
    if max_chars <= 0:
        return [src]
    parts: List[str] = []
    cur = ""
    for word in src.split():
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= max_chars:
            cur = f"{cur} {word}"
        else:
            parts.append(cur)
            cur = word
        if len(cur) > max_chars:
            pieces = _hard_split(cur, max_chars)
            parts.extend(pieces[:-1])
            cur = pieces[-1]
    if cur:
        parts.append(cur)
    return [p for p in parts if p]


def _hard_split(word: str, max_chars: int) -> List[str]:
    """没有空格可断时只能硬切，但**两段以内就均分**

    13 字上限 12，硬切会剩一个孤零零的单字（12+1），读起来像手滑。
    均分成 7+6 才是人能发出去的样子。
    """
    out: List[str] = []
    rest = word
    while len(rest) > max_chars:
        if len(rest) <= max_chars * 2:
            mid = (len(rest) + 1) // 2
            out.append(rest[:mid])
            rest = rest[mid:]
            break
        out.append(rest[:max_chars])
        rest = rest[max_chars:]
    if rest:
        out.append(rest)
    return out


def audit(text: str, max_chars: int = DEFAULT_MAX_CHARS,
          keep_short_stop: bool = False) -> Dict[str, Any]:
    """体检：这条回复还差哪几条规矩（只报 6、8 两条，其余是语义层，机械判不了）

    第 8 条判的是「原文一条有多长」，不是断条后有多长——断条是补救手段，
    需要补救就说明这一条本来就不该这么长。
    """
    src = (text or "").strip()
    if keep_short_stop and _SHORT_STOP.match(src):
        punct = []
    else:
        punct = [ch for ch in src if ch in TERMINAL]
    flat = strip_punct(src, keep_short_stop=keep_short_stop).rstrip("。")
    chunks = split_by_length(flat, max_chars)
    longest = max((len(c) for c in chunks), default=0)
    issues: List[str] = []
    if punct:
        issues.append(f"带了 {len(punct)} 处断句标点（第 6 条）")
    if len(flat) > max_chars:
        issues.append(
            f"整条 {len(flat)} 字，超过 {max_chars}，会断成 {len(chunks)} 条（第 8 条）")
    return {
        "ok": not issues,
        "issues": issues,
        "punct": len(punct),
        "chars": len(flat),
        "longest": longest,
        "parts": len(chunks),
    }


def style_config(data_dir: Optional[str] = None) -> Dict[str, Any]:
    """读 `回复风格` 设置；读不到就用默认值，绝不抛异常打断发送"""
    cfg = {"无标点": True, "单条字数上限": DEFAULT_MAX_CHARS,
           "短回应句号": False}
    try:
        from scripts.core import settings as core_settings
        got = (core_settings.load(data_dir) or {}).get("回复风格") or {}
        if isinstance(got, dict):
            cfg.update({k: v for k, v in got.items() if k in cfg})
    except Exception:  # noqa: BLE001
        pass
    try:
        cfg["单条字数上限"] = int(cfg["单条字数上限"])
    except (TypeError, ValueError):
        cfg["单条字数上限"] = DEFAULT_MAX_CHARS
    return cfg


def format_reply(text: str, no_punct: Optional[bool] = None,
                 max_chars: Optional[int] = None,
                 short_stop: Optional[bool] = None,
                 data_dir: Optional[str] = None) -> List[str]:
    """一条回复 → 若干条可发送消息

    `no_punct` / `max_chars` / `short_stop` 传 None 时读设置；显式传值则以此为准
    （测试与临时覆盖用）。
    """
    cfg = style_config(data_dir)
    if no_punct is None:
        no_punct = bool(cfg["无标点"])
    if max_chars is None:
        max_chars = cfg["单条字数上限"]
    if short_stop is None:
        short_stop = bool(cfg["短回应句号"])
    src = (strip_punct(text, keep_short_stop=short_stop) if no_punct
           else re.sub(r"\s+", " ", (text or "")).strip())
    return split_by_length(src, max_chars)


def main(argv: List[str]) -> int:
    text = " ".join(argv[1:]) if len(argv) > 1 else ""
    if not text:
        print(json.dumps({"error": "用法: typography.py \"<回复正文>\""},
                         ensure_ascii=False))
        return 2
    print(json.dumps({"messages": format_reply(text), "audit": audit(text)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
