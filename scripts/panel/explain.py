#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可解释面板（M7c）——每条回复都能说清「我凭什么这么说」

方案红线 1（真实性零容忍）的可验证形态：注入上下文的每一段，都标注它
来自哪条记忆、哪个人格字段、哪个画像字段。用户点开就能看到依据，
觉得不对可以直接改（见 controls.py）。

记录只存**引用关系**（记忆 id + 字段路径），不存原文，避免二次留存隐私。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DATA_DIR = "~/.love-companion/data"
ENV_DATA_DIR = "LOVE_COMPANION_DATA_DIR"

# 各注入段的依据来源说明（人类可读）
SECTION_ORIGIN: Dict[str, str] = {
    "相处指南": "用户画像（user_persona.json）",
    "记忆片段": "记忆库（memory.json）",
    "人格指令": "伴侣人格库（personas/{slug}.json）",
    "趋势调味料": "趋势知识库（trends.json）",
    "关怀话术": "主动关怀触发（care.trigger）",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_evidence(sections: Dict[str, str], data_dir: Optional[str] = None,
                   slug: str = "") -> Dict[str, List[str]]:
    """为已注入的各段找出可追溯依据

    Returns:
        {"记忆片段": ["#3 用户喜欢三分糖奶茶", ...], "人格指令": ["声线.口头禅", ...], ...}
    """
    resolved = data_dir or os.environ.get(ENV_DATA_DIR) or "~/.love-companion/data"
    base = Path(os.path.expanduser(str(resolved)))
    evidence: Dict[str, List[str]] = {}

    if "记忆片段" in sections:
        try:
            from scripts.memory.store import MemoryStore
            memories = MemoryStore(str(base)).all()
        except Exception:  # noqa: BLE001 - 记忆库不可读不该让解释失败
            memories = []
        cites = []
        for m in memories:
            text = str(m.get("content", ""))
            if text and text in sections["记忆片段"]:
                cites.append(f"#{m.get('id')} {text}")
        evidence["记忆片段"] = cites or ["（未能匹配到具体条目）"]

    if "人格指令" in sections and slug:
        try:
            from scripts.persona.library import PersonaLibrary
            persona = PersonaLibrary(str(base)).get(slug) or {}
        except Exception:  # noqa: BLE001
            persona = {}
        cites = []
        for layer in ("声线", "思维", "性格"):
            for key, val in (persona.get(layer) or {}).items():
                if isinstance(val, str) and val and val in sections["人格指令"]:
                    cites.append(f"{layer}.{key}")
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and v and v in sections["人格指令"]:
                            cites.append(f"{layer}.{key}")
                            break
        evidence["人格指令"] = cites or ["（人格库无匹配字段）"]

    if "相处指南" in sections:
        evidence["相处指南"] = [SECTION_ORIGIN["相处指南"]]

    if "趋势调味料" in sections:
        evidence["趋势调味料"] = [SECTION_ORIGIN["趋势调味料"]]

    if "关怀话术" in sections:
        evidence["关怀话术"] = [SECTION_ORIGIN["关怀话术"]]

    return evidence


class ExplainPanel:
    """解释记录的存取与渲染"""

    def __init__(self, data_dir: Optional[str] = None):
        resolved = data_dir or os.environ.get(ENV_DATA_DIR) or DEFAULT_DATA_DIR
        self.data_dir = Path(os.path.expanduser(str(resolved)))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / "explanations.json"
        self.keep = 50

    def _load(self) -> List[Dict[str, Any]]:
        if not self.file.exists():
            return []
        with open(self.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def _save(self, entries: List[Dict[str, Any]]) -> None:
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(entries[-self.keep:], f, ensure_ascii=False, indent=2)

    def record(self, sections: Dict[str, str], evidence: Optional[Dict[str, List[str]]] = None,
               slug: str = "", reply: str = "") -> Dict[str, Any]:
        """记录一轮对话注入了什么、依据是什么"""
        entry = {
            "ts": _now(),
            "slug": slug,
            "sections": {k: v for k, v in sections.items() if v},
            "evidence": evidence if evidence is not None
            else build_evidence(sections, str(self.data_dir), slug),
            "reply_chars": len(reply or ""),     # 只记长度，不记原文（隐私）
        }
        entries = self._load()
        entries.append(entry)
        self._save(entries)
        return entry

    def latest(self, n: int = 5) -> List[Dict[str, Any]]:
        return self._load()[-n:]

    def render(self, entry: Dict[str, Any]) -> str:
        """渲染成人话"""
        lines = [f"【这轮为什么这么说】（{entry.get('ts', '')}）"]
        for section, text in (entry.get("sections") or {}).items():
            origin = SECTION_ORIGIN.get(section, "未知来源")
            cites = (entry.get("evidence") or {}).get(section) or []
            cite_text = "；".join(cites[:3])
            lines.append(f"- {section}：{text}")
            lines.append(f"  依据（{origin}）：{cite_text or '无'}")
        return "\n".join(lines)

    def render_latest(self) -> str:
        entries = self.latest(1)
        return self.render(entries[0]) if entries else "暂无解释记录"

    def clear(self) -> int:
        n = len(self._load())
        self._save([])
        return n


if __name__ == "__main__":
    p = ExplainPanel()
    print(p.render_latest())
