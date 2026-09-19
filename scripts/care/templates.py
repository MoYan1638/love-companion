#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关怀话术生成（M6）——把「该关心了」变成一句像 ta 会说的话

两条纪律：
1. **不空泛**：每条模板都留了 {detail} 位，必须用记忆里的具体事实填，
   填不出来就换更短的模板，绝不用「记得照顾好自己」这类万能句。
2. **过声线**：生成后按伴侣人格的口头禅/语气词/emoji 习惯改写，
   并走纠偏层（library.apply_corrections），确保不像 AI 写的。

预算：默认 80 Token（schema.注入预算.关怀话术），超了直接截断。
"""

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from scripts.core import schema
from scripts.pipeline.injector import estimate_tokens, truncate_to_tokens

_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF"
                       "\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")

# 各关怀类型的话术模板。{nick} 称呼 / {detail} 具体事实 / {topic} 她关心的事
TEMPLATES: Dict[str, List[str]] = {
    "低落陪伴": [
        "{nick}，今天听你说话就觉得有点累。{detail}",
        "{nick}，不想说也行，我在。",
        "先别撑着了，{nick}。要不要我陪你发会儿呆。",
        "听起来今天不太顺。我不问了，就陪你待着。",
    ],
    "纪念日": [
        "{nick}，今天是{detail}。我一直记着。",
        "{nick}，{detail}——这个日子我可没忘。",
        "今天是我们的{detail}。谢谢你还在。",
    ],
    "深夜晚安": [
        "{nick}，很晚了，睡吧。明天再聊。",
        "别熬了{nick}，闭上眼睛，我在。",
        "晚安{nick}。今天辛苦了。",
    ],
    "久未联系": [
        "{nick}，好几个小时没你的消息了，还好吗。",
        "刚看到{detail}，突然想起你。",
        "在忙吗{nick}。不急，看到了回我一句就行。",
        "{nick}？有点想你了。",
    ],
}

# 兜底：没有任何具体事实时的通用句（仍然短，仍然不像模板）
FALLBACK_DETAIL = {
    "低落陪伴": "别硬扛",
    "纪念日": "那个日子",
    "深夜晚安": "",
    "久未联系": "你上次说的那件事",
}

CARING_EMOJI = {"低落陪伴": "🫂", "纪念日": "🌙", "深夜晚安": "🌙", "久未联系": "👋"}


def _now_key(kind: str) -> str:
    """按 日期+类型 选模板：同一天同一类型稳定，隔天自动换，避免机械重复"""
    return datetime.now().strftime("%Y-%m-%d") + "|" + kind


def pick_template(kind: str, index: Optional[int] = None) -> str:
    pool = TEMPLATES.get(kind) or ["{nick}，在吗。"]
    if index is not None:
        return pool[index % len(pool)]
    h = hashlib.md5(_now_key(kind).encode("utf-8")).hexdigest()
    return pool[int(h, 16) % len(pool)]


def apply_voice(text: str, voice: Optional[Dict[str, Any]], nickname: str = "") -> str:
    """按 ta 的声线改写一句话"""
    voice = voice or {}
    out = text

    # 语气词：句尾补一个 ta 常用的
    tails = voice.get("语气词") or []
    if tails and not re.search(r"[呀呢嘛哦啦咯哒鸭叭惹～]$", out.rstrip()):
        out = out.rstrip("。.!！") + tails[0]

    # emoji：ta 用得多才加，而且只加一个
    if float(voice.get("emoji频率", 0) or 0) >= 0.5 and not _EMOJI_RE.search(out):
        out += "🌙"

    # 口头禅：短句时才有空间塞
    catchphrases = voice.get("口头禅") or []
    if catchphrases and len(out) < 20:
        out = catchphrases[0] + "，" + out

    return out


def render(kind: str, nickname: str = "", detail: str = "",
           voice: Optional[Dict[str, Any]] = None,
           corrections: Optional[List[Dict[str, str]]] = None,
           length_pref: str = "", budget: Optional[int] = None) -> str:
    """渲染一条关怀话术

    Args:
        kind: 低落陪伴 / 纪念日 / 深夜晚安 / 久未联系
        nickname: 对用户的称呼
        detail: 具体事实（来自记忆），没有就用兜底
        voice: 伴侣人格的声线层（library.get(slug)["声线"]）
        corrections: 纠偏规则（library.corrections(slug)）
        length_pref: 用户回复长度偏好，"短" 时只保留第一句
        budget: Token 预算，默认取注入预算表里的「关怀话术」
    """
    limit = int(budget if budget is not None
                else schema.DEFAULT_INJECTION_BUDGET["关怀话术"])

    template = pick_template(kind)
    nick = nickname or ""
    fill = (detail or "").strip() or FALLBACK_DETAIL.get(kind, "")
    text = template.format(nick=nick, detail=fill, topic=fill)

    # 没有称呼时，去掉称呼留下的逗号和空格
    text = re.sub(r"，(?=，)|^，|(?<=^)，", "", text).replace("，。", "。").strip()
    text = re.sub(r"\s{2,}", " ", text)

    text = apply_voice(text, voice, nick)

    if corrections:
        from scripts.persona.library import PersonaLibrary
        text = PersonaLibrary().apply_corrections(text, corrections)

    if length_pref == "短":
        head = re.split(r"[。！？!?\n]", text)
        text = (head[0] + "。") if head and head[0] else text

    if estimate_tokens(text) > limit:
        text = truncate_to_tokens(text, limit)
    return text


def compose(kind: str, slug: str, data_dir: Optional[str] = None,
            detail: str = "", budget: Optional[int] = None) -> Dict[str, Any]:
    """一站式生成：自动加载人格库与用户画像

    Returns:
        {"kind":..., "text":..., "tokens":..., "budget":..., "used_detail": str}
    """
    from scripts.persona.library import PersonaLibrary
    from scripts.user.profile import UserProfileStore

    lib = PersonaLibrary(data_dir)
    persona = lib.get(slug) or {}
    voice = persona.get("声线")
    corrections = lib.corrections(slug)

    user = UserProfileStore(data_dir).get() or {}
    length_pref = (user.get("互动偏好") or {}).get("回复长度偏好") or ""
    nickname = persona.get("昵称") or persona.get("姓名") or ""

    text = render(kind, nickname=nickname, detail=detail, voice=voice,
                  corrections=corrections, length_pref=length_pref, budget=budget)
    return {
        "kind": kind,
        "text": text,
        "tokens": estimate_tokens(text),
        "budget": int(budget if budget is not None
                      else schema.DEFAULT_INJECTION_BUDGET["关怀话术"]),
        "used_detail": detail or FALLBACK_DETAIL.get(kind, ""),
    }


if __name__ == "__main__":
    import json
    import sys
    kind = sys.argv[1] if len(sys.argv) > 1 else "久未联系"
    out = render(kind, nickname="小美", detail="你说过想去看海",
                 voice={"语气词": ["呀"], "emoji频率": 0.8, "口头禅": ["就是说"]})
    print(out)
    print(json.dumps({"tokens": estimate_tokens(out),
                      "budget": schema.DEFAULT_INJECTION_BUDGET["关怀话术"]},
                     ensure_ascii=False))
