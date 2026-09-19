#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆存储（M2）——6 类记忆的持久化与管理

兼容约定（重要）：
写入的记忆条目是 **v1 结构的超集**（保留 id / content / created_at），
因此 v1 的 manager.py 依然能正常读取，升级无损、可回退。

数据主权（方案红线 4）：
- delete(id)         单条删除
- delete_keyword(kw) 按关键词删除
- delete_conversation(cid) 遗忘某段关系
- export()           批量导出
- clear()            一键清除
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.core import schema

DEFAULT_DATA_DIR = "~/.love-companion/data"
ENV_DATA_DIR = "LOVE_COMPANION_DATA_DIR"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class MemoryStore:
    """六类记忆的本地存储"""

    def __init__(self, data_dir: Optional[str] = None):
        resolved = data_dir or os.environ.get(ENV_DATA_DIR) or DEFAULT_DATA_DIR
        self.data_dir = Path(os.path.expanduser(str(resolved)))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / "memory.json"

    # ---------- IO ----------

    def _load(self) -> List[Dict[str, Any]]:
        if not self.file.exists():
            return []
        with open(self.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    def _save(self, memories: List[Dict[str, Any]]) -> None:
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)

    def all(self) -> List[Dict[str, Any]]:
        """返回已规范化为 v2 结构的全部记忆"""
        return [schema.normalize_memory_entry(m, entry_id=i)
                for i, m in enumerate(self._load(), 1)]

    # ---------- 增 ----------

    def add(self, content: str, memory_type: str = "事实", source: str = "",
            importance: float = 0.5, valence: float = 0.0,
            conversation_id: str = "") -> Dict[str, Any]:
        """新增一条记忆（自动去重：同 type 同 content 只保留一条并刷新时间）"""
        memories = self.all()
        for m in memories:
            if m.get("type") == memory_type and m.get("content") == content.strip():
                m["updated_at"] = _now()
                m["importance"] = max(float(m.get("importance", 0.5)), importance)
                for i, old in enumerate(memories, 1):
                    old["id"] = i
                self._save(memories)
                return m

        entry = schema.memory_entry(
            content=content.strip(), memory_type=memory_type, source=source,
            importance=importance, valence=valence, conversation_id=conversation_id,
        )
        entry["id"] = len(memories) + 1
        memories.append(entry)
        for i, m in enumerate(memories, 1):
            m["id"] = i
        self._save(memories)
        return entry

    # ---------- 查 ----------

    def get(self, memory_id: int) -> Optional[Dict[str, Any]]:
        for m in self.all():
            if m.get("id") == memory_id:
                return m
        return None

    def by_type(self, memory_type: str) -> List[Dict[str, Any]]:
        return [m for m in self.all() if m.get("type") == memory_type]

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        kw = (keyword or "").lower()
        return [m for m in self.all() if kw in str(m.get("content", "")).lower()]

    # ---------- 删（数据主权） ----------

    def delete(self, memory_id: int) -> bool:
        memories = self.all()
        left = [m for m in memories if m.get("id") != memory_id]
        if len(left) == len(memories):
            return False
        for i, m in enumerate(left, 1):
            m["id"] = i
        self._save(left)
        return True

    def delete_keyword(self, keyword: str) -> int:
        kw = (keyword or "").lower()
        memories = self.all()
        left = [m for m in memories if kw not in str(m.get("content", "")).lower()]
        removed = len(memories) - len(left)
        for i, m in enumerate(left, 1):
            m["id"] = i
        self._save(left)
        return removed

    def delete_conversation(self, conversation_id: str) -> int:
        """遗忘某段关系：整段会话产生的记忆一次性清除"""
        return self._delete_by_field("conversation_id", conversation_id)

    def _delete_by_field(self, field: str, value: Any) -> int:
        memories = self.all()
        left = [m for m in memories if m.get(field) != value]
        removed = len(memories) - len(left)
        for i, m in enumerate(left, 1):
            m["id"] = i
        self._save(left)
        return removed

    def clear(self) -> int:
        count = len(self.all())
        self._save([])
        return count

    def export(self) -> str:
        return json.dumps(self.all(), ensure_ascii=False, indent=2)

    # ---------- 召回与衰减 ----------

    def recall(self, memory_ids: List[int]) -> None:
        """标记被注入上下文的记忆：召回计数 +1，重要性回升"""
        if not memory_ids:
            return
        memories = self.all()
        boost = schema.DEFAULT_DECAY["recall_boost"]
        ceiling = schema.DEFAULT_DECAY["max_importance"]
        for m in memories:
            if m.get("id") in memory_ids:
                m["recall_count"] = int(m.get("recall_count", 0)) + 1
                m["importance"] = min(ceiling, float(m.get("importance", 0.5)) + boost)
                m["last_recalled_at"] = _now()
        self._save(memories)

    def decay(self, now: Optional[datetime] = None) -> int:
        """长期记忆重要性按半衰期衰减，返回被衰减的条数"""
        now = now or datetime.now()
        half_life = schema.DEFAULT_DECAY["half_life_days"]
        floor = schema.DEFAULT_DECAY["min_importance"]
        memories = self.all()
        changed = 0
        for m in memories:
            updated = m.get("updated_at") or m.get("created_at")
            try:
                last = datetime.fromisoformat(str(updated))
            except (TypeError, ValueError):
                continue
            days = max(0.0, (now - last).total_seconds() / 86400.0)
            if days < 1:
                continue
            factor = 0.5 ** (days / half_life)
            new_imp = max(floor, float(m.get("importance", 0.5)) * factor)
            if abs(new_imp - float(m.get("importance", 0.5))) > 1e-6:
                m["importance"] = round(new_imp, 4)
                changed += 1
        if changed:
            self._save(memories)
        return changed

    # ---------- 统计 ----------

    def stats(self) -> Dict[str, Any]:
        memories = self.all()
        by_type: Dict[str, int] = {}
        for m in memories:
            t = m.get("type", "?")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total": len(memories),
            "by_type": by_type,
            "avg_importance": round(
                sum(float(m.get("importance", 0)) for m in memories) / len(memories), 3
            ) if memories else 0.0,
        }


if __name__ == "__main__":
    import sys
    store = MemoryStore()
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        for m in store.all():
            print(f"#{m['id']} [{m['type']}] {m['content']} (重要度 {m['importance']})")
    else:
        print(json.dumps(store.stats(), ensure_ascii=False))
