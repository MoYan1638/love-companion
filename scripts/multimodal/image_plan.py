#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多模态陪伴（M7b）——主动发图的「时机 + 风格 + 衔接」

诚实边界：本模块**不生成图片**。它产出的是一份配图规格（风格参数 + 提示词 +
图文衔接话术），真正出图交给上层的图像生成能力。这样既保持零外部依赖，
又不把「发什么图」的审美决策甩给模型临场发挥。

三件事：
1. 时机：该不该发图（冷却 / 每日上限 / 深夜降饱和 / 用户关了就不发）
2. 风格：从人格与情绪推导色调、光线、构图、元素，确保「像 ta 会发的图」
3. 衔接：图前一句话，避免聊着聊着突然甩一张图（图文交织）
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.core import schema
from scripts.pipeline.injector import estimate_tokens, truncate_to_tokens

DEFAULT_DATA_DIR = "~/.love-companion/data"
ENV_DATA_DIR = "LOVE_COMPANION_DATA_DIR"

DEFAULT_CONFIG: Dict[str, Any] = {
    "开关": True,
    "冷却消息数": 6,     # 两张图之间至少隔这么多轮
    "每日上限": 3,
    "深夜起始": 22,
}

# 情绪 → 视觉基调
MOOD_TONE: Dict[str, Dict[str, str]] = {
    "低落": {"色调": "低饱和暖灰", "光线": "柔和散射光", "氛围": "安静、不喧哗"},
    "疲惫": {"色调": "米白与浅咖", "光线": "黄昏侧光", "氛围": "松弛、可以靠一会儿"},
    "开心": {"色调": "明亮清透", "光线": "正午自然光", "氛围": "轻快、有一点跳脱"},
    "想念": {"色调": "蓝紫渐变", "光线": "窗边微光", "氛围": "私密、只给你看"},
    "日常": {"色调": "自然本色", "光线": "日常室内光", "氛围": "随手拍的真实感"},
    "纪念": {"色调": "复古暖黄", "光线": "烛光或串灯", "氛围": "有仪式感但不过度"},
}

# 价值观 → 构图与元素
VALUE_ELEMENTS: Dict[str, Dict[str, str]] = {
    "浪漫": {"构图": "近景、留白", "元素": "花、日落、手写卡片"},
    "自由": {"构图": "远景、开阔地平线", "元素": "公路、天空、车窗"},
    "家庭": {"构图": "中景、生活场景", "元素": "餐桌、毛毯、猫"},
    "成长": {"构图": "桌面俯拍", "元素": "书、咖啡、笔记本"},
    "健康": {"构图": "自然光全身或半身", "元素": "晨跑、绿植、水杯"},
    "旅行": {"构图": "广角风景", "元素": "山、海、陌生街角"},
}

# 图文衔接话术：按情绪给一句，避免「给你看张图」这种突兀句式
CAPTIONS: Dict[str, List[str]] = {
    "低落": ["刚看到这个，想到你了。", "不用回，就看看。"],
    "疲惫": ["给你留了个位置。", "今天就到这儿吧，看看这个。"],
    "开心": ["这个我第一反应就想发给你。", "你看这个像不像我们那天说的。"],
    "想念": ["刚路过的时候拍的，想给你看。", "有点想你，就发了。"],
    "日常": ["随手拍的。", "今天这个还挺好看的。"],
    "纪念": ["我记得今天。", "这个日子，给你留了一张。"],
}

_IMAGE_BUDGET = 40      # 图文衔接话术的 Token 上限（从关怀/人格余量里出）


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None


class ImagePlanner:
    """主动发图决策"""

    def __init__(self, data_dir: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        resolved = data_dir or os.environ.get(ENV_DATA_DIR) or DEFAULT_DATA_DIR
        self.data_dir = Path(os.path.expanduser(str(resolved)))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / "multimodal.json"
        self.config = dict(DEFAULT_CONFIG)
        if config:
            self.config.update(config)

    # ---------- 状态 ----------

    def _load(self) -> Dict[str, Any]:
        if not self.file.exists():
            return {"history": [], "turns_since_last": 99}
        with open(self.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"history": [], "turns_since_last": 99}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def tick(self, sent: bool) -> None:
        """每轮对话调用：sent=True 表示这轮发了图，计数归零"""
        data = self._load()
        data["turns_since_last"] = 0 if sent else int(data.get("turns_since_last", 99)) + 1
        self._save(data)

    def today_count(self, now: Optional[datetime] = None) -> int:
        now = now or datetime.now()
        today = now.strftime("%Y-%m-%d")
        return sum(1 for h in self._load().get("history", [])
                   if str(h.get("ts", "")).startswith(today))

    def mark_sent(self, kind: str, caption: str, now: Optional[datetime] = None) -> None:
        data = self._load()
        data.setdefault("history", []).append({
            "ts": (now or datetime.now()).isoformat(timespec="seconds"),
            "kind": kind, "caption": caption})
        data["history"] = data["history"][-100:]
        data["turns_since_last"] = 0
        self._save(data)

    # ---------- 时机 ----------

    def gate(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """该不该发图"""
        now = now or datetime.now()
        if not self.config.get("开关", True):
            return {"ok": False, "reason": "发图开关已关闭"}
        if self.today_count(now) >= int(self.config["每日上限"]):
            return {"ok": False, "reason": f"今日发图已达上限（{self.config['每日上限']}）"}
        if int(self._load().get("turns_since_last", 99)) < int(self.config["冷却消息数"]):
            return {"ok": False, "reason": "距离上一张图太近，会显得刻意"}
        return {"ok": True, "reason": ""}

    # ---------- 风格 ----------

    def style_for(self, persona: Optional[Dict[str, Any]], mood: str = "日常",
                  now: Optional[datetime] = None) -> Dict[str, str]:
        """从人格与情绪推导配图风格，确保「像 ta 会发的图」"""
        now = now or datetime.now()
        persona = persona or {}
        tone = dict(MOOD_TONE.get(mood, MOOD_TONE["日常"]))

        values = (persona.get("思维") or {}).get("价值观") or []
        composition, elements = "中景、平视", "生活细节"
        for v in values:
            if v in VALUE_ELEMENTS:
                composition = VALUE_ELEMENTS[v]["构图"]
                elements = VALUE_ELEMENTS[v]["元素"]
                break

        if now.hour >= int(self.config["深夜起始"]):
            tone["色调"] = "夜色低饱和"
            tone["光线"] = "台灯或街灯"
            elements = "窗、夜景、暖色小灯"

        return {"色调": tone["色调"], "光线": tone["光线"], "氛围": tone["氛围"],
                "构图": composition, "元素": elements}

    # ---------- 衔接 ----------

    def caption(self, mood: str = "日常", voice: Optional[Dict[str, Any]] = None,
                corrections: Optional[List[Dict[str, str]]] = None) -> str:
        """图前一句话，走声线改写与纠偏"""
        pool = CAPTIONS.get(mood) or CAPTIONS["日常"]
        idx = datetime.now().day % len(pool)
        text = pool[idx]

        voice = voice or {}
        tails = voice.get("语气词") or []
        if tails and not text.rstrip().endswith(tuple("呀呢嘛哦啦咯哒～")):
            text = text.rstrip("。") + tails[0] + "。"
        if float(voice.get("emoji频率", 0) or 0) >= 0.5:
            text = text.rstrip("。") + " 📷"

        if corrections:
            from scripts.persona.library import PersonaLibrary
            text = PersonaLibrary().apply_corrections(text, corrections)

        return truncate_to_tokens(text, _IMAGE_BUDGET)

    # ---------- 汇总 ----------

    def plan(self, slug: str, mood: str = "日常", now: Optional[datetime] = None,
             data_dir: Optional[str] = None) -> Dict[str, Any]:
        """一站式产出配图计划

        Returns:
            {"should": bool, "reason": str, "mood": str, "style": {...},
             "caption": str, "prompt_hint": str, "tokens": int}
        """
        now = now or datetime.now()
        g = self.gate(now)
        if not g["ok"]:
            return {"should": False, "reason": g["reason"], "mood": mood}

        from scripts.persona.library import PersonaLibrary
        lib = PersonaLibrary(data_dir or str(self.data_dir))
        persona = lib.get(slug) or {}
        voice = persona.get("声线")
        style = self.style_for(persona, mood, now)
        text = self.caption(mood, voice, lib.corrections(slug))

        hint = (f"{style['构图']}，{style['元素']}，{style['色调']}，"
                f"{style['光线']}，氛围{style['氛围']}，写实摄影感，不做过度修饰")
        return {
            "should": True, "reason": "", "mood": mood, "style": style,
            "caption": text, "prompt_hint": hint, "tokens": estimate_tokens(text),
        }

    def reset(self) -> None:
        self._save({"history": [], "turns_since_last": 99})


if __name__ == "__main__":
    import sys
    p = ImagePlanner()
    mood = sys.argv[1] if len(sys.argv) > 1 else "想念"
    print(json.dumps(p.plan("美美", mood=mood), ensure_ascii=False, indent=2))
