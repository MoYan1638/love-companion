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

# L1：硬性禁用词
# 注意：这不是英文写作场景的 AI 腔词表（"综上所述/在当今社会"那套对恋人对话
# 几乎无用），而是**中文恋爱对话里真正会露馅的说法**——空洞安慰、客服式共情、
# 替用户断言情绪、万能金句。命中即判为 AI 腔，必须重写。
L1_WORDS: List[str] = [
    # 客服式共情
    "我理解你的感受", "我完全理解", "我能理解", "我能感受到",
    "听到你这么说", "看到你说这些", "我能体会",
    # 空洞安慰（万能句，没有具体信息）
    # 注意：这里**故意没有**「抱抱你」「亲亲」——恋人之间说抱抱是正当表达，
    # 交给 density.py 管密度（COMMON_LOVE 里亲昵动作 per1k 2.0），不在这里硬禁。
    "一切都会好起来的", "会好起来的", "都会过去的",
    "记得照顾好自己", "记得按时吃饭", "记得早点休息", "多喝热水",
    "别难过了", "别伤心了", "别想太多了", "开心一点",
    # 万能陪伴宣言
    "我会一直陪着你", "我一直都在", "无论发生什么我都",
    # 替用户断言情绪
    "你一定很", "你肯定很", "想必你现在", "你应该很",
    # AI 身份与服务腔
    "作为一个AI", "作为一个人工智能", "我是AI", "我是人工智能",
    "我希望这能帮到你", "希望对你有帮助", "如果你还有任何问题",
    "欢迎随时", "希望我的回答", "以上就是",
    # 论文腔（恋人对话里同样露馅）
    "首先", "其次", "综上所述", "总而言之", "总的来说",
    "值得注意的是", "众所周知", "在当今社会", "随着.*的发展",
]

# L2：结构模式（正则）
L2_PATTERNS: List[tuple] = [
    ("共情复述开场", re.compile(r"^(?:听到|看到|知道|明白).{0,12}(?:你|宝).{0,20}[，,].{0,30}(?:我|让)")),
    ("替用户下结论", re.compile(r"你(?:一定|肯定|想必|应该)很[^。！？]{0,10}(?:吧|呢)?")),
    ("空洞鼓励", re.compile(r"(?:一切|事情|总会|都会).{0,6}(?:好起来|过去|变好)")),
    ("称呼堆叠", re.compile(r"(?:宝贝|亲爱的|宝宝|乖乖)[^。！？\n]{0,20}(?:宝贝|亲爱的|宝宝|乖乖)")),
    ("连续追问", re.compile(r"[？?][^。！？\n]{0,10}[？?]")),
    ("三段式罗列", re.compile(r"(?:^|[。；;\n])\s*(?:首先|第一|其一).{0,40}(?:其次|第二|其二).{0,40}(?:最后|第三|其三)")),
    ("逐条编号", re.compile(r"(?:^|\n)\s*(?:\d+[.、)]|[一二三四五六七八九十]+[、.])")),
    ("破折号堆砌", re.compile(r"——[^。！？]{0,30}——")),
    ("排比堆砌", re.compile(r"(?:[^，。！？]{4,10}，){3,}")),
    ("每段以连接词开头", re.compile(r"(?:^|[。！？\n])\s*(?:此外|另外|而且|并且|因此|所以|然而|不过)")),
]

_CJK_PUNCT = re.compile(r"[。！？!?；;]")
_SPACED = re.compile(r"[ \t]+")
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
_MODAL = ("呀", "呢", "嘛", "哦", "啦", "~", "～")

# 书面词：这些词本身没错，但出现在恋人对话里就是「在写材料」
_WRITTEN_WORDS: List[str] = [
    "根据", "描述", "建议", "尝试", "保持", "调整", "结构", "规律", "目前",
    "进行", "存在", "方面", "因素", "措施", "方式方法", "同时", "以及",
]


def _sentences(text: str) -> List[str]:
    """分句：优先按句末标点，无标点时按空格（回复十条第 6 条之后的常态）

    不兼容空格会出两个错：一是把「平均句长」算成整条长度，短句被判成
    「句子过长」；二是把一段正常的碎碎念误报成「缺语气词」。
    两种都是假阳性，方向错得很危险——会让守门员把好句子拦下来。
    """
    parts = [s for s in _CJK_PUNCT.split(text) if s.strip()]
    if len(parts) <= 1 and _SPACED.search(text):
        spaced = [s for s in _SPACED.split(text) if s]
        if len(spaced) > 1:
            return spaced
    return parts


def scan(text: str) -> Dict[str, Any]:
    """检测一段回复的 AI 写作特征"""
    text = text or ""
    hits_l1 = [w for w in L1_WORDS if re.search(w, text)]
    hits_l2 = [name for name, pat in L2_PATTERNS if pat.search(text)]

    sentences = _sentences(text)
    avg_len = (sum(len(s) for s in sentences) / len(sentences)) if sentences else 0
    emoji_count = len(_EMOJI.findall(text))
    modal_count = sum(text.count(m) for m in _MODAL)

    l3: List[str] = []
    # 恋人对话应是短句，30 字已经偏长（比通用写作的 45 更严）
    if sentences and avg_len > 30:
        l3.append(f"句子过长（平均 {avg_len:.0f} 字，恋人对话宜短）")
    if emoji_count > 2:
        l3.append(f"emoji 过多（{emoji_count} 个）")
    # 缺语气词只在「长 + 平 + 没有你我」时才算书面：短促有力的硬话本来就不带语气词，
    # 「我撑不住了，但我在」加个「呀」反而软掉了。
    if len(text) >= 30 and modal_count == 0 and avg_len > 18 and not re.search(r"[我你]", text):
        l3.append("缺少语气词，像书面说明")
    written = [w for w in _WRITTEN_WORDS if w in text]
    if written:
        l3.append(f"书面词混进口语（{'/'.join(written[:3])}）")
    if text.count("，") > len(sentences) * 3:
        l3.append("逗号密度过高，长句堆砌")
    # 每条消息都带 emoji 也不自然
    if sentences and emoji_count >= len(sentences) and len(sentences) >= 2:
        l3.append("句句带表情，像模板")

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
