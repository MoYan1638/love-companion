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

3. **认真收住的那一句可以留一个句号**（第 6 条的情绪例外）
   「哦哦。」「嗯嗯。」这类极短回应的句号是冷淡的语气；「没事。」「嗯对。」「算了。」
   这类**认真收住的短句**末尾那个句号是情绪——安抚、下定论、道歉的时候，
   点一下收住，比空着更像真人。判定：整条除了末尾一个句号没有别的断句标点。
   日常闲聊还是全空格；句号是**情绪开关**，不是默认格式。

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

# 一条消息的字数目标：一句十字顶天，留两字余量给语气词和 emoji。
# 这是**日常的常态，不是卡死的线**——有时话多一点，十几字也能接受；
# 超过硬上限（DEFAULT_HARD_MAX）才真的必须拆。
DEFAULT_MAX_CHARS = 12
DEFAULT_HARD_MAX = 20

# 短回应：整条不超过这么多字、且只有一个末尾句号时，可以选择保留那个句号
# 定在 3 是有意的：「哦哦。」「嗯嗯。」「呃。」「好的。」都是语气词级别；
# 「我知道了。」这类完整回应带句号会显得冷硬，不放进去。
SHORT_REPLY_MAX = 3
_SHORT_STOP = re.compile(r"^([^。，、；：！？,.;:!?\s]{1,%d})。$" % SHORT_REPLY_MAX)

# 情绪句号：整条**只有末尾一个句号**、句中没有别的断句标点时，那个句号
# 可以是语气不是断句——「没事。」「嗯对。」「算了。」这种认真收住的一句。
# 句中还有标点（「我在。你说。」「没事的，我没怪你」）就不算，照常清。
def _emotion_stop(src: str) -> bool:
    if not src.endswith("。"):
        return False
    body = src[:-1]
    return bool(body) and not any(ch in TERMINAL for ch in body)


# 情绪段落：走心长段的逗号是叙述不是断句——「没事的，我没怪你」硬拆成空格短句反而怪。
# 这个例外**默认关**：逗号比句号常见得多，默认留会被习惯带标点的写法掏空第 6 条；
# 由写话层认定「这一段是认真长段」时显式传 keep_commas=True（或开设置 情绪逗号）。
COMMA = "，,"


def strip_punct(text: str, keep_short_stop: bool = False,
                keep_emotion_stop: bool = True,
                keep_commas: bool = False) -> str:
    """去掉断句标点，用空格隔开（第 6 条）

    `keep_short_stop=True` 时额外保留「哦哦。」「嗯嗯。」这类**极短回应的末尾句号**。
    `keep_emotion_stop=True`（默认开）时保留「没事。」「嗯对。」「算了。」这类
    **认真收住的短句**的末尾句号——那是情绪开关，不是断句；日常闲聊本来就不带，
    所以保留它不会破坏无标点的常态，反而是把写话那一层特意点的句号留住。
    句中还有别的断句标点就不算，照常清空格。
    `keep_commas=True` 时连逗号也留——那是**认真长段**的叙述，
    「没事的，我没怪你」拆成空格短句反而怪；默认关，写话层显式传。

    >>> strip_punct("我在。你说。")
    '我在 你说'
    >>> strip_punct("不是。算了。")
    '不是 算了'
    >>> strip_punct("没事。")
    '没事。'
    >>> strip_punct("没事。", keep_emotion_stop=False)
    '没事'
    >>> strip_punct("没事的，我没怪你", keep_commas=True)
    '没事的，我没怪你'
    >>> strip_punct("哦哦。", keep_short_stop=True)
    '哦哦。'
    """
    src = (text or "").strip()
    if not src:
        return ""
    if keep_emotion_stop and _emotion_stop(src):
        return src
    if keep_short_stop and _SHORT_STOP.match(src):
        return src
    out = "".join(" " if (ch in TERMINAL and not (keep_commas and ch in COMMA))
                  else ch for ch in src)
    out = out.replace("\r", " ").replace("\n", " ")
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip(" \t")


def split_by_length(text: str, max_chars: int = DEFAULT_MAX_CHARS,
                    hard_max: int = DEFAULT_HARD_MAX) -> List[str]:
    """按长度切条，优先在空格处断（第 8 条）

    `max_chars` 是**合并目标**：把空格隔开的短句往一条里装，装到十二字左右为止。
    `hard_max` 是**真的上限**：单个短句只要不超过它就整句保留，不为凑十字
    把一句话腰斩——日常聊天一般十来字，但有时一句十三四个字也是自然的，
    切成两半反而难看。超过 hard_max 才硬切。
    """
    src = (text or "").strip()
    if not src:
        return []
    if max_chars <= 0:
        return [src]
    if hard_max < max_chars:
        hard_max = max_chars
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
        if len(cur) > hard_max:
            pieces = _hard_split(cur, max_chars)
            parts.extend(pieces[:-1])
            cur = pieces[-1]
    if cur:
        parts.append(cur)
    return [p for p in parts if p]


def _hard_split(word: str, max_chars: int) -> List[str]:
    """没有空格可断时只能硬切，但**两段以内就均分**

    二十一字上限十二，硬切会剩一个孤零零的九字尾，读起来像手滑。
    均分成 11+10 才是人能发出去的样子。
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


def _pack_comma_text(src: str, max_chars: int,
                     hard_max: int) -> List[str]:
    """认真长段：逗号留在原地，按逗号归拢到十二字左右一条

    「科三跟科二不一样，科二是固定的，科三是几条完全不一样的路线随机抽的」
    → ['科三跟科二不一样，科二是固定的', '科三是几条完全不一样的路线随机抽的']。
    逗号不能丢（丢了叙述感就没了），但单条仍守硬上限——
    单个分句超了就硬切，两段以内均分，跟空格版同一个手感。
    """
    clauses = [c.strip() for c in re.split(r"[，,]", src) if c.strip()]
    if not clauses:
        return []
    parts: List[str] = []
    cur = ""
    for c in clauses:
        if not cur:
            cur = c
        elif len(cur) + 1 + len(c) <= max_chars:
            cur = f"{cur}，{c}"
        else:
            parts.append(cur)
            cur = c
        if len(cur) > hard_max:
            pieces = _hard_split(cur, max_chars)
            parts.extend(pieces[:-1])
            cur = pieces[-1]
    if cur:
        parts.append(cur)
    return [p for p in parts if p]


def audit(text: str, max_chars: int = DEFAULT_MAX_CHARS,
          hard_max: int = DEFAULT_HARD_MAX,
          keep_short_stop: bool = False,
          keep_emotion_stop: bool = True,
          keep_commas: bool = False) -> Dict[str, Any]:
    """体检：这条回复还差哪几条规矩（只报 6、8 两条，其余是语义层，机械判不了）

    第 8 条判的是「原文一条有多长」，不是断条后有多长——断条是补救手段，
    需要补救就说明这一条本来就不该这么长。

    超过目标但没过硬上限的，记进 `notes` 提醒一下，不算违规——
    日常十条里九条是短句，偶尔一条长点，卡死会显得像机器人。

    「没事。」这种只有一个末尾句号的也不算违规，记 note：那是情绪开关，
    认真收住的一句可以留；但日常不该带，所以留了要被提醒一句「别每条都带」。

    `keep_commas=True` 时逗号不算违规，记 note：认真长段的叙述随它去，
    但说完那段要回到短句空格，别变成新常态。
    """
    src = (text or "").strip()
    emotion = keep_emotion_stop and _emotion_stop(src)
    punct = [ch for ch in src if ch in TERMINAL]
    if keep_commas:
        punct = [ch for ch in punct if ch not in COMMA]
    if (keep_short_stop and _SHORT_STOP.match(src)) or emotion:
        punct = []
    flat = strip_punct(src, keep_short_stop=keep_short_stop,
                       keep_emotion_stop=keep_emotion_stop,
                       keep_commas=keep_commas).rstrip("。")
    chunks = (_pack_comma_text(flat, max_chars, hard_max)
              if keep_commas and any(ch in COMMA for ch in flat)
              else split_by_length(flat, max_chars, hard_max=hard_max))
    longest = max((len(c) for c in chunks), default=0)
    issues: List[str] = []
    notes: List[str] = []
    if punct:
        issues.append(f"带了 {len(punct)} 处断句标点（第 6 条）")
    elif emotion:
        notes.append("末尾留了一个句号：认真收住的一句可以，日常闲聊别带")
    elif keep_commas and any(ch in COMMA for ch in flat):
        notes.append("逗号留在认真长段里了：说完这段回到短句空格，别变成新常态")
    if len(flat) > hard_max:
        issues.append(
            f"整条 {len(flat)} 字，超过硬上限 {hard_max}，会断成 {len(chunks)} 条（第 8 条）")
    elif len(flat) > max_chars:
        notes.append(
            f"整条 {len(flat)} 字，比日常的 {max_chars} 略长；偶尔可以，别每条都这样")
    return {
        "ok": not issues,
        "issues": issues,
        "notes": notes,
        "punct": len(punct),
        "chars": len(flat),
        "longest": longest,
        "parts": len(chunks),
    }


def style_config(data_dir: Optional[str] = None) -> Dict[str, Any]:
    """读 `回复风格` 设置；读不到就用默认值，绝不抛异常打断发送"""
    cfg = {"无标点": True, "单条字数上限": DEFAULT_MAX_CHARS,
           "单条硬上限": DEFAULT_HARD_MAX, "短回应句号": False, "情绪句号": True,
           "情绪逗号": False}
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
                 hard_max: Optional[int] = None,
                 short_stop: Optional[bool] = None,
                 emotion_stop: Optional[bool] = None,
                 keep_commas: Optional[bool] = None,
                 data_dir: Optional[str] = None) -> List[str]:
    """一条回复 → 若干条可发送消息

    `no_punct` / `max_chars` / `hard_max` / `short_stop` / `emotion_stop` /
    `keep_commas` 传 None 时读设置；显式传值则以此为准（测试与临时覆盖用）。
    认真长段（走心解释）传 keep_commas=True：逗号留在原位，按逗号归拢断条。
    """
    cfg = style_config(data_dir)
    if no_punct is None:
        no_punct = bool(cfg["无标点"])
    if max_chars is None:
        max_chars = cfg["单条字数上限"]
    if hard_max is None:
        hard_max = cfg["单条硬上限"]
    if short_stop is None:
        short_stop = bool(cfg["短回应句号"])
    if emotion_stop is None:
        emotion_stop = bool(cfg["情绪句号"])
    if keep_commas is None:
        keep_commas = bool(cfg["情绪逗号"])
    src = (strip_punct(text, keep_short_stop=short_stop,
                       keep_emotion_stop=emotion_stop,
                       keep_commas=keep_commas) if no_punct
           else re.sub(r"\s+", " ", (text or "")).strip())
    if keep_commas and any(ch in COMMA for ch in src):
        return _pack_comma_text(src, max_chars, hard_max)
    return split_by_length(src, max_chars, hard_max=hard_max)


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
