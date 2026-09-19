#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三层人格提取（M3a）——声线 / 思维 / 性格

参考 crush-skills 的 persona_analyzer：蒸馏靠 LLM 按模板跑，Python 负责
**可复现的统计特征提取**，两者合并后写入人格库。这样即使没有 LLM，
规则层也能给出一份可用的人格；有 LLM 时规则结果作为事实底座，防止编造。

方案 3.3 三层：
- 声线：用词习惯、口头禅、句式、语气词、标点、emoji、平均句长
- 思维：决策逻辑、关注顺序、价值观
- 性格：情绪反应模式、亲密度基线、冲突应对

红线：只依赖标准库；不做任何超出语料的推断（置信度随语料量给出）。
"""

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence

from scripts.core import schema

# ---------------- 词表 ----------------

# 常见虚词/高频无信息词，用于口头禅与关键词去噪
STOPWORDS = set("""
的 了 是 我 你 他 她 它 我们 你们 他们 在 有 就 不 也 都 很 到 说 要 去 会 着 没 看 好 自己 这 那
什么 怎么 为什么 一个 这个 那个 可以 因为 所以 但是 然后 还有 就是 一下 一点 现在 时候 知道 觉得
吗 呢 吧 啊 哦 嗯 呀 啦 嘛 呗 咯 哒 鸭 惹 叭 唉 嘿 嗯嗯 哈哈 哈哈哈
""".split())

# 句尾语气词（声线特征）
MODAL_TAILS = ("呀", "呢", "嘛", "哦", "啦", "咯", "哒", "鸭", "惹", "叭", "嘛", "呗", "咯", "哈", "滴", "咯")

# emoji / 颜文字粗略范围
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF"
    "\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)

VALUE_KEYWORDS: Dict[str, Sequence[str]] = {
    "家庭": ("家人", "爸妈", "妈妈", "爸爸", "回家", "家里", "孩子", "小孩", "结婚"),
    "事业": ("工作", "加班", "项目", "升职", "老板", "同事", "业绩", "KPI", "面试", "开会"),
    "自由": ("自由", "旅行", "说走就走", "不被束缚", "辞职", "gap", "裸辞"),
    "成长": ("学习", "看书", "课程", "成长", "进步", "复盘", "考研", "证书", "读书"),
    "健康": ("健身", "跑步", "早睡", "体检", "身体", "养生", "熬夜", "生病", "头疼"),
    "金钱": ("钱", "存款", "房价", "理财", "基金", "省钱", "工资", "房租", "报销"),
    "朋友": ("朋友", "闺蜜", "兄弟", "聚会", "社交", "饭局"),
    "浪漫": ("惊喜", "仪式感", "花", "礼物", "纪念日", "浪漫", "电影", "日落", "海"),
}

EMO_POSITIVE = ("开心", "高兴", "喜欢", "爱", "哈哈", "笑", "期待", "幸福", "舒服", "棒",
                "惊喜", "感动", "甜", "治愈", "喜欢死", "绝了")
EMO_NEGATIVE = ("难过", "伤心", "累", "烦", "生气", "崩溃", "焦虑", "压力", "emo", "难受",
                "委屈", "失望", "孤独", "emo了", "内耗", "失眠", "哭")

CONFLICT_STYLES: Dict[str, Sequence[str]] = {
    "回避": ("算了", "随便", "无所谓", "不想说", "别问了", "都行", "没事"),
    "妥协": ("好吧", "听你的", "那行", "我改", "对不起", "是我的问题", "我错了"),
    "对抗": ("凭什么", "不管", "我就是", "非要", "你错了", "离谱", "过分"),
    "冷战": ("嗯。", "哦。", "知道了", "随便你", "……"),
}

DECISION_STYLES: Dict[str, Sequence[str]] = {
    "直觉型": ("感觉", "直觉", "就是觉得", "想都不用想", "第一反应"),
    "权衡型": ("考虑", "权衡", "利弊", "再想想", "比较一下", "分析", "评估"),
    "依赖型": ("你定", "你说", "听你的", "帮我决定", "都可以", "随便"),
    "果断型": ("就这样", "定了", "马上", "直接", "不用想", "立刻"),
}

INTIMATE_TERMS = ("宝贝", "宝宝", "亲爱的", "老婆", "老公", "想你", "爱你", "亲亲",
                  "抱抱", "么么", "晚安", "好想", "喜欢你")

_CJK = re.compile(r"[\u4e00-\u9fff]")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")


def _texts(corpus: Sequence[Dict[str, Any]]) -> List[str]:
    return [str(u.get("text", "")) for u in corpus]


def _count_hits(texts: Iterable[str], keywords: Iterable[str]) -> int:
    blob = "\n".join(texts)
    return sum(blob.count(k) for k in keywords)


def _ngrams(texts: Iterable[str], n_range: Sequence[int] = (2, 3, 4),
            min_count: int = 3, top_k: int = 8) -> List[str]:
    """高频连续短语（口头禅候选）

    先按长度降序取，再剔除「被更长且同频短语包含」的短片段，
    避免同时输出「真的」和「真的假的」这种重复。
    """
    counter: Counter = Counter()
    for t in texts:
        for run in _CJK_RUN.findall(t):
            for n in n_range:
                for i in range(len(run) - n + 1):
                    g = run[i:i + n]
                    if g in STOPWORDS:
                        continue
                    counter[g] += 1
    ranked = [(g, c) for g, c in counter.items() if c >= min_count]
    ranked.sort(key=lambda kv: (-kv[1], -len(kv[0])))
    picked: List[str] = []
    for g, c in ranked:
        if any(g in p for p in picked):
            continue
        picked.append(g)
        if len(picked) >= top_k:
            break
    return picked


# ---------------- 第一层：声线 ----------------

def extract_voice(corpus: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """声线层：ta 说话的样子"""
    texts = _texts(corpus)
    if not texts:
        return {"用词习惯": [], "口头禅": [], "句式": "", "语气词": [], "标点习惯": "",
                "emoji频率": 0.0, "平均句长": 0.0, "置信度": 0.0}

    lens = [len(t) for t in texts]
    avg_len = sum(lens) / len(lens)

    modal = Counter()
    for t in texts:
        tail = t.rstrip()
        for m in MODAL_TAILS:
            if tail.endswith(m):
                modal[m] += 1
                break

    emoji_hits = sum(len(EMOJI_RE.findall(t)) for t in texts)
    punct = Counter()
    for t in texts:
        punct["!！"] += t.count("!") + t.count("！")
        punct["?？"] += t.count("?") + t.count("？")
        punct["~～"] += t.count("~") + t.count("～")
        punct["…"] += t.count("…") + t.count("...")
        punct["。"] += t.count("。")
    top_punct = [p for p, _ in punct.most_common(2) if punct[p] > 0]

    # 句式画像：短句连发 / 长句叙述 / 爱提问 / 爱感叹
    short_ratio = sum(1 for l in lens if l <= 12) / len(lens)
    q_ratio = sum(1 for t in texts if t.rstrip().endswith(("?", "？"))) / len(texts)
    ex_ratio = sum(1 for t in texts if t.rstrip().endswith(("!", "！"))) / len(texts)
    if short_ratio >= 0.6:
        shape = "短句连发，一条消息一句话"
    elif avg_len >= 40:
        shape = "长句叙述，喜欢把话说完整"
    else:
        shape = "长短交替，按话题切换"
    if q_ratio >= 0.25:
        shape += "；爱反问和追问"
    if ex_ratio >= 0.25:
        shape += "；情绪到位时用感叹"

    # 用词习惯：高频实词（非虚词、长度≥2）
    words: Counter = Counter()
    for t in texts:
        for run in _CJK_RUN.findall(t):
            for n in (2, 3):
                for i in range(len(run) - n + 1):
                    g = run[i:i + n]
                    if g not in STOPWORDS:
                        words[g] += 1
    habit = [w for w, c in words.most_common(30) if c >= max(3, len(texts) // 20)][:6]

    confidence = min(1.0, len(texts) / 200.0)
    return {
        "用词习惯": habit,
        "口头禅": _ngrams(texts),
        "句式": shape,
        "语气词": [m for m, _ in modal.most_common(5)],
        "标点习惯": "、".join(top_punct) if top_punct else "少用标点",
        "emoji频率": round(emoji_hits / len(texts), 3),
        "平均句长": round(avg_len, 1),
        "置信度": round(confidence, 2),
    }


# ---------------- 第二层：思维 ----------------

def extract_thinking(corpus: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """思维层：ta 怎么想事"""
    texts = _texts(corpus)
    if not texts:
        return {"决策逻辑": "未知", "关注顺序": [], "价值观": [], "置信度": 0.0}

    values = [(k, _count_hits(texts, kws)) for k, kws in VALUE_KEYWORDS.items()]
    values.sort(key=lambda kv: -kv[1])
    top_values = [k for k, c in values if c > 0][:4]

    decisions = [(k, _count_hits(texts, kws)) for k, kws in DECISION_STYLES.items()]
    decisions.sort(key=lambda kv: -kv[1])
    decision = decisions[0][0] if decisions and decisions[0][1] > 0 else "混合型"

    # 关注顺序：高频内容词（去掉口头禅后剩下的高频词，近似「常聊什么」）
    focus: Counter = Counter()
    for t in texts:
        for run in _CJK_RUN.findall(t):
            for n in (2, 3):
                for i in range(len(run) - n + 1):
                    g = run[i:i + n]
                    if g not in STOPWORDS:
                        focus[g] += 1
    focus_order = [w for w, c in focus.most_common(60) if c >= max(3, len(texts) // 20)][:8]

    confidence = min(1.0, len(texts) / 300.0)
    return {
        "决策逻辑": decision,
        "关注顺序": focus_order,
        "价值观": top_values,
        "置信度": round(confidence, 2),
    }


# ---------------- 第三层：性格 ----------------

def extract_character(corpus: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """性格层：ta 的情绪与亲密度"""
    texts = _texts(corpus)
    if not texts:
        return {"情绪反应模式": "未知", "亲密度基线": 0.5, "冲突应对": "未知",
                "情绪效价": 0.0, "置信度": 0.0}

    pos = _count_hits(texts, EMO_POSITIVE)
    neg = _count_hits(texts, EMO_NEGATIVE)
    total = pos + neg
    valence = (pos - neg) / total if total else 0.0

    if total == 0:
        mode = "情绪表达克制，少直接表态"
    elif neg > pos * 1.5:
        mode = "负面情绪外放，难受了会直接说"
    elif pos > neg * 1.5:
        mode = "正面情绪外放，开心就藏不住"
    else:
        mode = "正负情绪都表达，比较真实"

    conflicts = [(k, _count_hits(texts, kws)) for k, kws in CONFLICT_STYLES.items()]
    conflicts.sort(key=lambda kv: -kv[1])
    conflict = conflicts[0][0] if conflicts and conflicts[0][1] > 0 else "就事论事"

    intimate = _count_hits(texts, INTIMATE_TERMS)
    baseline = min(1.0, 0.2 + intimate / max(10.0, len(texts)) * 2.0)

    confidence = min(1.0, len(texts) / 300.0)
    return {
        "情绪反应模式": mode,
        "亲密度基线": round(baseline, 2),
        "冲突应对": conflict,
        "情绪效价": round(valence, 2),
        "置信度": round(confidence, 2),
    }


# ---------------- 合装 ----------------

def extract_persona(corpus: Sequence[Dict[str, Any]], name: str = "",
                    nickname: str = "", source_prints: Optional[List[str]] = None
                    ) -> Dict[str, Any]:
    """三层提取合装为一条伴侣人格（schema.cloned_persona_template 结构）"""
    persona = schema.cloned_persona_template(name)
    persona["昵称"] = nickname
    persona["声线"] = extract_voice(corpus)
    persona["思维"] = extract_thinking(corpus)
    persona["性格"] = extract_character(corpus)
    persona["语料量"] = len(corpus)
    if source_prints:
        persona["来源素材"] = list(source_prints)
    return persona


# ---------------- 5 层人格模型（在线注入用） ----------------

def build_layers(persona: Dict[str, Any]) -> Dict[str, Any]:
    """把三层提取结果编译成 crush-skills 的 5 层人格模型

    硬规则 → 身份 → 说话风格 → 情感模式 → 人际行为
    这是「在线注入」时真正生效的形态，编译后由 library.compile_summary 压到预算内。
    """
    voice = persona.get("声线", {}) or {}
    think = persona.get("思维", {}) or {}
    char = persona.get("性格", {}) or {}

    hard_rules = ["不许编造没发生过的事", "不许替对方做决定"]
    if char.get("冲突应对") == "冷战":
        hard_rules.append("冲突时不追问、不逼答，给台阶")
    if float(voice.get("emoji频率", 0)) >= 0.5:
        hard_rules.append("适当带表情，但每轮不超过两个")

    identity = persona.get("姓名") or persona.get("昵称") or "ta"
    vals = think.get("价值观") or []
    if vals:
        identity += f"；看重{'/'.join(vals[:3])}"

    style_parts = [voice.get("句式") or ""]
    if voice.get("口头禅"):
        style_parts.append("口头禅：" + "、".join(voice["口头禅"][:4]))
    if voice.get("语气词"):
        style_parts.append("句尾常用" + "、".join(voice["语气词"][:3]))
    if voice.get("标点习惯"):
        style_parts.append("标点：" + voice["标点习惯"])

    emotion = char.get("情绪反应模式") or ""
    if char.get("情绪效价") is not None:
        emotion += f"（效价 {char['情绪效价']}）"

    behavior = f"决策{think.get('决策逻辑', '未知')}；冲突时{char.get('冲突应对', '未知')}"
    if think.get("关注顺序"):
        behavior += "；常聊" + "、".join(think["关注顺序"][:4])

    return {
        "硬规则": hard_rules,
        "身份": identity,
        "说话风格": "；".join(p for p in style_parts if p),
        "情感模式": emotion,
        "人际行为": behavior,
    }


if __name__ == "__main__":
    import json
    from scripts.persona import parser
    demo = "\n".join([
        "小美: 在吗 想你了呀",
        "小美: 今天加班累死了 想吃点甜的～",
        "小美: 你定吧 我都行啦",
        "小美: 算了 不想说了",
        "小美: 宝贝晚安呀🌙",
        "小美: 我就是说我觉得这个挺好的嘛",
    ] * 4)
    corpus = parser.parse_text(demo)
    p = extract_persona(parser.only(corpus, "小美"), name="小美")
    print(json.dumps({"三层": p, "五层": build_layers(p)}, ensure_ascii=False, indent=2))
