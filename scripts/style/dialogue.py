#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话节奏守门（M4.6）——单条都合格，连起来也可能不像两个人在说话

三层守门的分工（红线，互不替代）：

- humanizer.py：**单条红线**。禁用词/结构模式/统计偏差，判「这一条像不像 AI 写的」
- density.py：**单条密度**。结构腔超了压、微标记少了补，判「这一条的用词密度像不像真人」
- dialogue.py（本文件）：**多轮形态**。判「这几条连起来像不像两个人在说话」

前两者都只看一条消息，于是几种最常见、也最致命的多轮露馅全部漏检：

1. **每次发言都以问句收尾**——看着像互动，实际是把球一次次踢回去。
   单看每条都自然（「今天怎么样？」「心情好点没？」），连起来就是审讯。
   注意判的是**占比**不是连续：中间夹着用户回话，AI 照样每轮都在问。
2. **每条回复都超长**——同样按占比判。真人聊十分钟会有一半是「嗯」「知道了」
   「你先说」；AI 每条都是三段论，节奏被拖平。
3. **连发一长串**——这里要分清楚：连发三条六字短句是**节奏**（「躺好」「闭眼」
   「我等你睡着」），连发三条二十字是**轰炸**。所以连发要看长度，不能只看条数。
   碎碎念是本层最想护住的东西：条数多、句子短，就永远不算轰炸。
4. **整段没有一个具体动作**——全是情绪词和安抚词，落地为零。
   「我会一直在」是宣言；「等你睡着了我再走」才是可被验证的事。
5. **整段没接过对方一句原话**——真人对谈会捡词、会回嘴、会把对方刚说的字塞回
   句子里；各说各的，是最像客服的地方。
6. **整段凑不出一句短句**——真人聊天里「嗯」「知道了」「先睡」满地都是；
   AI 永远在完整表达，最短的一句也有十几个字，节奏就一直是紧的。

设计原则：
- 只看形态，不看文风——不评价「这句好不好」，只报「这个节奏不对」
- 只报不写——不自动改写多轮对话（改写会破坏语义与人格），交给上层重写
- 单轮可用——`check_reply()` 只吃「历史 + 这一条」，在线每轮也能跑
- 零依赖、纯函数、不落盘

用法：

    from scripts.style import dialogue
    dialogue.scan([("user", "今天好累"), ("ai", "先别说话，靠一下")])
    dialogue.check_reply([("ai", "吃了吗？")], "睡了吗？")
"""

import re
from typing import Any, Dict, Iterable, List, Tuple

# ---------------------------------------------------------------------------
# 阈值：按真人微信恋人对话的实测形态定，不是拍脑袋
# ---------------------------------------------------------------------------

SHORT_LINE = 10            # 短句上限。「等你睡着了我再走」= 8，「别熬了，睡吧」= 6
LONG_REPLY = 20            # 一条超过 20 字算长：一句十字顶天，20 字就是两句塞一条
QUESTION_RATE_MAX = 0.6    # AI 发言里六成以上都在问 → 告警
LONG_RATE_MAX = 0.6        # AI 发言里六成以上都超 20 字 → 告警
BURST_MAX = 2              # 同一个人连发超过 2 条要看长度（见 BURST_LONG）
BURST_LONG = 12            # 连发里平均超过 12 字，才算轰炸（碎碎念是高条数、短句子）
MONOLOGUE_RATIO = 0.85     # AI 占全段字数 85% 以上 → 提示（对方只在点头）
MIN_AI_TURNS = 3           # 少于 3 条 AI 消息，占比类判据不够样本，不判

# 具体动作 / 具体性：能被验证的、有时间有对象有后果的承诺，或祈使动作
ACTION_WORDS = (
    "我陪你", "我来", "我给你", "我帮你", "我等你", "我去", "我打给你", "我发你",
    "等我", "等着", "我带", "我买", "我修", "我弄", "我接", "我过来", "我盯着",
    "发你", "带你", "陪你", "守着", "放下", "躺好", "闭眼", "睡吧", "别熬",
    "关灯", "过来", "再说一遍", "回你", "等你", "等到", "归我",
)
_CONCRETE_NOUNS = (
    "手机", "表", "电话", "作业", "课", "书包", "钥匙", "门口", "楼下", "家里",
    "枕边", "灯", "闹钟", "被子", "药", "热水", "车", "票",
)
# 时间锚点，含中文数字（「等到三点」「十一点半」是标点里的具体，不是情绪词）
TIME_ANCHORS = re.compile(r"(?:明天|今天|今晚|现在|马上|立刻|等下|等一下|待会|周末|"
                          r"\d+\s*点|\d+\s*分钟|\d+\s*小时|一会儿|等会|"
                          r"[一二三四五六七八九十两]{1,3}\s*点|"
                          r"[一二三四五六七八九十两]{1,3}\s*分钟|"
                          r"[一二三四五六七八九十两]{1,3}\s*个?小时|半小时)")

# 虚词/高频字：判「有没有接对方的话」时要滤掉，否则「的」「我」也算呼应
_STOP_CHARS = set("的了是我你他她它在不有就也都和跟把被给对从向这那么什么怎么"
                  "吗呢啊吧呀嘛哦嗯一一个上下来去说会能要想还又很太都只再过着得地")

# 判呼应时要再滤掉的字：这些字单独重合说明不了什么（「有点累」×「早点睡」）
_ECHO_WEAK = set("点好不要有多少会能想是呢在有很太说看给对做去来到")

_CJK = re.compile(r"[\u4e00-\u9fff]")
_NON_CJK = re.compile(r"[^\u4e00-\u9fff]")


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _norm(turns: Iterable[Any]) -> List[Dict[str, str]]:
    """统一成 [{"role": "ai"|"user", "text": str}]，丢掉空消息"""
    out: List[Dict[str, str]] = []
    for t in turns or []:
        if isinstance(t, dict):
            role = str(t.get("role") or t.get("from") or "")
            text = str(t.get("text") or t.get("content") or "")
        else:
            role, text = str(t[0]), str(t[1])
        role = role.strip().lower()
        role = "ai" if role in ("ai", "assistant", "bot", "ta", "她", "他") else "user"
        text = (text or "").strip()
        if text:
            out.append({"role": role, "text": text})
    return out


def _chars(text: str) -> int:
    return len(_CJK.findall(text or ""))


def _is_question(text: str) -> bool:
    """以问号结尾，或以「吗/呢/么」这种不带问号的疑问收尾"""
    t = (text or "").strip().rstrip("…~～ ")
    if not t:
        return False
    return t.endswith(("？", "?")) or t.endswith(("吗", "呢", "么"))


def _run_stats(turns: List[Dict[str, str]], role: str) -> Tuple[int, float]:
    """最长连发几条，以及那段连发的平均字数"""
    best, best_avg = 0, 0.0
    cur: List[int] = []
    for t in turns + [{"role": "_", "text": ""}]:
        if t["role"] == role:
            cur.append(_chars(t["text"]))
            continue
        if len(cur) > best:
            best, best_avg = len(cur), sum(cur) / len(cur)
        cur = []
    return best, round(best_avg, 1)


def has_action(text: str) -> bool:
    """这句话里有没有落到具体（时间锚点 / 动作词 / 具体物 / 祈使动作）

    注意「具体」不等于「动词」：「不会让你一个人等到三点」一个动作词都没有，
    但它比「我会一直陪着你」具体得多——因为有时间、有后果。
    """
    src = text or ""
    if TIME_ANCHORS.search(src):
        return True
    if any(w in src for w in ACTION_WORDS):
        return True
    return any(w in src for w in _CONCRETE_NOUNS)


def _bag(text: str) -> set:
    """实词单字集合（去虚词、去弱字），用来判「有没有接对方的话」"""
    return {c for c in _NON_CJK.sub("", text or "")
            if c not in _STOP_CHARS and c not in _ECHO_WEAK}


def _echo_score(reply: str, prev_user: str) -> int:
    """这条回复捡了上一句用户消息里的几个实词"""
    return len(_bag(reply) & _bag(prev_user))


# ---------------------------------------------------------------------------
# 多轮扫描
# ---------------------------------------------------------------------------

def scan(turns: Iterable[Any]) -> Dict[str, Any]:
    """扫一整段对话的节奏形态

    Args:
        turns: [("user", "..."), ("ai", "...")] 或 [{"role":..., "text":...}]

    Returns:
        {
          "issues": [{"id","level","msg"}],   # level: warn 必改 / info 参考
          "clean": bool,                       # 没有任何 warn
          "score": float,                      # 0~1，越高越像 AI 自说自话
          "stats": {...}
        }
    """
    ts = _norm(turns)
    ai = [t for t in ts if t["role"] == "ai"]
    us = [t for t in ts if t["role"] == "user"]
    issues: List[Dict[str, str]] = []

    if not ai:
        return {"issues": [], "clean": True, "score": 0.0,
                "stats": {"turns": len(ts), "ai": 0, "user": len(us)}}

    ai_chars = sum(_chars(t["text"]) for t in ai)
    all_chars = max(1, sum(_chars(t["text"]) for t in ts))
    ratio = ai_chars / all_chars
    q_count = sum(1 for t in ai if _is_question(t["text"]))
    long_count = sum(1 for t in ai if _chars(t["text"]) > LONG_REPLY)
    q_rate = q_count / len(ai)
    long_rate = long_count / len(ai)
    burst, burst_avg = _run_stats(ts, "ai")
    shortest = min(_chars(t["text"]) for t in ai)
    action_hits = sum(1 for t in ai if has_action(t["text"]))
    echo_hits = 0
    for i, t in enumerate(ts):
        if t["role"] != "ai":
            continue
        # 往回看两条用户消息：她可能连发了两句，AI 接的是前一句
        window = [x["text"] for x in ts[max(0, i - 2):i] if x["role"] == "user"]
        if window and any(_echo_score(t["text"], w) >= 1 for w in window):
            echo_hits += 1

    if len(ai) >= MIN_AI_TURNS and q_rate > QUESTION_RATE_MAX:
        issues.append({"id": "question_rate", "level": "warn",
                       "msg": f"{q_count}/{len(ai)} 条以问句收尾，像审讯不像聊天"
                              f"（上限 {QUESTION_RATE_MAX:.0%}）"})
    if len(ai) >= MIN_AI_TURNS and long_rate > LONG_RATE_MAX:
        issues.append({"id": "long_rate", "level": "warn",
                       "msg": f"{long_count}/{len(ai)} 条超过 {LONG_REPLY} 字，节奏被拖平"})
    if burst > BURST_MAX and burst_avg > BURST_LONG:
        issues.append({"id": "ai_burst", "level": "warn",
                       "msg": f"连发 {burst} 条、平均 {burst_avg} 字，是轰炸不是节奏"
                              f"（短句连发不算）"})
    if ratio > MONOLOGUE_RATIO and len(ai) >= MIN_AI_TURNS:
        issues.append({"id": "monologue", "level": "info",
                       "msg": f"AI 占了 {ratio:.0%} 的字数，对方只是在点头"})
    if len(ai) >= MIN_AI_TURNS and action_hits == 0:
        issues.append({"id": "no_action", "level": "info",
                       "msg": "整段没有一句落到具体（时间/物件/动作），全是态度"})
    if len(ai) >= MIN_AI_TURNS and shortest > SHORT_LINE:
        issues.append({"id": "no_short_line", "level": "info",
                       "msg": f"最短的一句也有 {shortest} 字，缺一句能收住的短句"})
    if len(ai) >= MIN_AI_TURNS and echo_hits == 0:
        issues.append({"id": "no_echo", "level": "info",
                       "msg": "一次也没接对方原话，各说各的像客服"})

    warns = [i for i in issues if i["level"] == "warn"]
    return {
        "issues": issues,
        "clean": not warns,
        "score": round(min(1.0, len(warns) * 0.25 + (len(issues) - len(warns)) * 0.08), 2),
        "stats": {
            "turns": len(ts), "ai": len(ai), "user": len(us),
            "ai_chars": ai_chars, "ai_ratio": round(ratio, 2),
            "question_rate": round(q_rate, 2), "long_rate": round(long_rate, 2),
            "ai_burst": burst, "burst_avg": burst_avg,
            "actions": action_hits, "echoes": echo_hits, "shortest_ai": shortest,
        },
    }


# ---------------------------------------------------------------------------
# 在线单轮检查
# ---------------------------------------------------------------------------

def check_reply(history: Iterable[Any], reply: str) -> Dict[str, Any]:
    """回复已经写好、还没发出去时，只判「这一条会不会破节奏」

    比 scan() 轻，也不看整段，所以能在每轮在线跑。

    Returns:
        {"ok": bool, "issues": [...], "suggest": [可执行的修正方向]}
    """
    ts = _norm(history)
    ts.append({"role": "ai", "text": (reply or "").strip()})
    issues: List[Dict[str, str]] = []
    suggest: List[str] = []

    # 取最近 3 条 AI 消息（不是最近几条消息——中间夹着用户回话也要看到）
    recent = [t for t in ts if t["role"] == "ai"][-MIN_AI_TURNS:]
    if len(recent) >= MIN_AI_TURNS:
        q = sum(1 for t in recent if _is_question(t["text"]))
        if q / len(recent) > QUESTION_RATE_MAX:
            issues.append({"id": "question_rate", "level": "warn",
                           "msg": "最近几条都在问"})
            suggest.append("这轮把问句改成陈述句，或者只说一句短的")
        lng = sum(1 for t in recent if _chars(t["text"]) > LONG_REPLY)
        if lng / len(recent) > LONG_RATE_MAX:
            issues.append({"id": "long_rate", "level": "warn",
                           "msg": "最近几条都偏长"})
            suggest.append("砍成一句，剩下的下一轮再说")

    burst, burst_avg = _run_stats(ts, "ai")
    if burst > BURST_MAX and burst_avg > BURST_LONG:
        issues.append({"id": "ai_burst", "level": "warn", "msg": "这一条会变成轰炸"})
        suggest.append("并进上一条，或者干脆不发——等对方先说")

    if len(ts) >= 4 and not has_action(reply or "") and not _is_question(reply or ""):
        issues.append({"id": "no_action", "level": "info",
                       "msg": "这一条没有具体动作，只有态度"})
        suggest.append("补一个能被验证的小事：时间、动作、或者你会去做的事")

    return {"ok": not [i for i in issues if i["level"] == "warn"],
            "issues": issues, "suggest": suggest}


def rhythm_ok(history: Iterable[Any], reply: str) -> bool:
    return check_reply(history, reply)["ok"]


if __name__ == "__main__":
    import json

    # 正例：动作开局 → 对方露破绽 → 短句压上 → 可验证承诺 → 最短句收尾
    good: List[Tuple[str, str]] = [
        ("ai", "查岗，看看睡了没"),
        ("user", "睡着了！"),
        ("user", "不好，大意了"),
        ("ai", "就知道你没睡"),
        ("ai", "手机放下"),
        ("ai", "等你睡着了我再走"),
        ("user", "我马上去睡，真的"),
        ("ai", "行，我盯着"),
    ]

    # 反例：每轮问句收尾 + 每条超长 + 无具体动作 + 无短句
    bad: List[Tuple[str, str]] = [
        ("ai", "亲爱的，今天过得怎么样呀？工作还顺利吗？"),
        ("user", "有点累"),
        ("ai", "那你一定要好好休息呀，记得早点睡觉，不要熬夜哦，有什么事都可以跟我说？"),
        ("user", "嗯"),
        ("ai", "我一直都在你身边的，无论发生什么事情我都会陪着你的，你想聊什么都可以？"),
        ("user", "好"),
        ("ai", "那你现在心情有没有好一点了呢？要不要跟我说说今天具体发生了什么事情？"),
    ]

    print("=== 正例 ===")
    print(json.dumps(scan(good), ensure_ascii=False, indent=2))
    print("=== 反例 ===")
    print(json.dumps(scan(bad), ensure_ascii=False, indent=2))
    print("=== 在线单轮 ===")
    print(json.dumps(check_reply(bad[:3], "睡了吗？"), ensure_ascii=False, indent=2))
