#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
趋势源注册表与故障转移（M7a）——借鉴 Agent-Reach 的「安装器 + 路由器」思路

诚实边界：本模块**不自己发网络请求**。小红书/B站/微博 都需要登录态或
JS 渲染，标准库抓不到，硬做只会得到一堆反爬页。所以这里只做两件事：
1. 按兴趣主题产出**抓取计划**（primary + fallback 链），交给上层
   Agent 的网络能力（如 Agent-Reach）去执行
2. 记录各源的成功/失败，失败多了自动把备用源顶上来（故障转移）

真正落地的提炼与注入在 store.py。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DATA_DIR = "~/.love-companion/data"
ENV_DATA_DIR = "LOVE_COMPANION_DATA_DIR"

# 平台 → 抓取规格。url 里的 {q} 是兴趣关键词占位符
PLATFORMS: Dict[str, Dict[str, Any]] = {
    "小红书": {
        "url": "https://www.xiaohongshu.com/search_result?keyword={q}",
        "hint": "需登录态，优先取笔记标题与高赞评论",
        "weight": 3,
    },
    "B站": {
        "url": "https://search.bilibili.com/all?keyword={q}",
        "hint": "取视频标题与热评，弹幕可作流行语来源",
        "weight": 3,
    },
    "微博": {
        "url": "https://s.weibo.com/weibo?q={q}",
        "hint": "热搜词最直接，注意去广告",
        "weight": 2,
    },
    "知乎": {
        "url": "https://www.zhihu.com/search?q={q}",
        "hint": "适合观点类话题，取其高赞回答的开头几句",
        "weight": 2,
    },
    "豆瓣": {
        "url": "https://www.douban.com/search?q={q}",
        "hint": "影视/书籍/音乐类话题质量最高",
        "weight": 1,
    },
    "RSS": {
        "url": "{q}",
        "hint": "用户自建订阅源，q 直接是 feed 地址",
        "weight": 1,
    },
}

# 话题类别 → 推荐平台顺序（primary 在前，之后是 fallback）
TOPIC_PLATFORMS: Dict[str, List[str]] = {
    "穿搭": ["小红书", "B站", "微博"],
    "美食": ["小红书", "B站", "微博"],
    "影视": ["豆瓣", "B站", "微博"],
    "游戏": ["B站", "微博", "知乎"],
    "音乐": ["B站", "豆瓣", "微博"],
    "科技": ["知乎", "B站", "微博"],
    "情感": ["小红书", "知乎", "微博"],
    "旅行": ["小红书", "B站", "豆瓣"],
}
DEFAULT_CHAIN = ["小红书", "B站", "微博", "知乎"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SourceRouter:
    """按兴趣主题产出抓取计划，并根据历史成败做故障转移"""

    def __init__(self, data_dir: Optional[str] = None):
        resolved = data_dir or os.environ.get(ENV_DATA_DIR) or DEFAULT_DATA_DIR
        self.data_dir = Path(os.path.expanduser(str(resolved)))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / "trend_sources.json"

    def _load(self) -> Dict[str, Any]:
        if not self.file.exists():
            return {}
        with open(self.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def health(self) -> Dict[str, Dict[str, int]]:
        """各源的成功/失败次数"""
        return self._load().get("health", {})

    def mark(self, platform: str, ok: bool) -> Dict[str, int]:
        """上报一次抓取结果"""
        data = self._load()
        h = data.setdefault("health", {}).setdefault(platform, {"ok": 0, "fail": 0})
        h["ok" if ok else "fail"] = int(h.get("ok" if ok else "fail", 0)) + 1
        h["ts"] = _now()
        self._save(data)
        return h

    def _score(self, platform: str) -> float:
        """排序分：基础权重 − 失败惩罚。失败越多排越后"""
        base = float(PLATFORMS.get(platform, {}).get("weight", 1))
        h = self.health().get(platform, {})
        ok = int(h.get("ok", 0))
        fail = int(h.get("fail", 0))
        penalty = fail / max(1, ok + fail)
        return round(base * (1.0 - penalty), 3)

    def plan(self, topic: str, keyword: Optional[str] = None) -> Dict[str, Any]:
        """产出抓取计划：按健康度排序的 primary + fallback 链"""
        q = keyword or topic
        chain = TOPIC_PLATFORMS.get(topic, DEFAULT_CHAIN)
        ordered = sorted(chain, key=lambda p: -self._score(p))
        specs = [{
            "platform": p,
            "url": PLATFORMS[p]["url"].format(q=q),
            "hint": PLATFORMS[p]["hint"],
            "score": self._score(p),
        } for p in ordered if p in PLATFORMS]
        return {
            "topic": topic,
            "keyword": q,
            "primary": specs[0]["platform"] if specs else None,
            "fallbacks": [s["platform"] for s in specs[1:]],
            "specs": specs,
        }

    def next_source(self, topic: str, tried: List[str]) -> Optional[Dict[str, Any]]:
        """当前源挂了，取下一个没试过的"""
        specs = self.plan(topic)["specs"]
        for s in specs:
            if s["platform"] not in tried:
                return s
        return None

    def reset(self) -> None:
        self._save({})


if __name__ == "__main__":
    import sys
    r = SourceRouter()
    topic = sys.argv[1] if len(sys.argv) > 1 else "美食"
    print(json.dumps(r.plan(topic), ensure_ascii=False, indent=2))
