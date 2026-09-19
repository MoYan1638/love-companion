#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话间隙调度器（M1）——方案确认的触发方式：**对话间隙自动跑**

用法（由 Agent 在每轮回复后调用，或由系统任务定时调用）：
    python scripts/pipeline/runner.py --data-dir ~/.love-companion/data
    python scripts/pipeline/runner.py --max-tasks 5

设计约束：
- 单次调用有上限（默认 8 个任务），绝不让离线工作拖慢对话
- 每个任务可重试，超过次数进死信，不阻塞后续任务
- 只依赖标准库

新模块接入：
    from scripts.pipeline.runner import register

    @register("memory.extract")
    def handle(payload, ctx):
        ...        # ctx 提供 data_dir、queue 等
        return {...}   # 返回值写入 task["result"]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pipeline.queue import TaskQueue  # noqa: E402

# kind -> handler(payload, ctx) -> result
HANDLERS: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {}


def register(kind: str) -> Callable:
    """注册任务处理器"""
    def deco(fn: Callable) -> Callable:
        HANDLERS[kind] = fn
        return fn
    return deco


def run_idle(data_dir: Optional[str] = None, max_tasks: int = 8) -> Dict[str, Any]:
    """排空待执行任务（对话间隙调用）

    Returns:
        {"picked": n, "done": n, "failed": n, "skipped": n, "errors": [...]}
    """
    queue = TaskQueue(data_dir)
    ctx = {"data_dir": str(queue.data_dir), "queue": queue}
    report: Dict[str, Any] = {"picked": 0, "done": 0, "failed": 0, "skipped": 0, "errors": []}

    for task in queue.pending(limit=max_tasks):
        kind = task.get("kind")
        if kind not in HANDLERS:
            report["skipped"] += 1
            queue.fail(task["id"], f"未注册的任务类型：{kind}")
            continue
        claimed = queue.claim(task["id"])
        if not claimed:
            continue
        report["picked"] += 1
        try:
            result = HANDLERS[kind](claimed.get("payload") or {}, ctx)
            queue.complete(claimed["id"], result)
            report["done"] += 1
        except Exception as exc:  # noqa: BLE001 - 离线任务失败不得影响对话
            queue.fail(claimed["id"], f"{type(exc).__name__}: {exc}")
            report["failed"] += 1
            report["errors"].append(f"{kind}: {exc}")

    return report


# ==================== 内置任务 ====================

@register("memory.extract")
def _task_memory_extract(payload: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """从一段对话文本中无感采集记忆（离线，不占对话 Token）"""
    from scripts.memory.store import MemoryStore
    from scripts.memory.extract import extract_memories

    text = payload.get("text", "")
    if not text:
        return {"added": 0, "reason": "空文本"}
    store = MemoryStore(ctx["data_dir"])
    candidates = extract_memories(text, conversation_id=payload.get("conversation_id", ""))
    added = []
    for c in candidates:
        entry = store.add(
            content=c["content"],
            memory_type=c["type"],
            source=c.get("source", ""),
            importance=c.get("importance", 0.5),
            valence=c.get("valence", 0.0),
            conversation_id=payload.get("conversation_id", ""),
        )
        added.append(entry["id"])
    return {"added": len(added), "ids": added}


@register("memory.decay")
def _task_memory_decay(payload: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """长期记忆重要性衰减（每日一次即可）"""
    from scripts.memory.store import MemoryStore
    store = MemoryStore(ctx["data_dir"])
    changed = store.decay()
    return {"decayed": changed}


def main() -> int:
    parser = argparse.ArgumentParser(description="对话间隙离线任务调度")
    parser.add_argument("--data-dir", default=os.environ.get("LOVE_COMPANION_DATA_DIR", "~/.love-companion/data"))
    parser.add_argument("--max-tasks", type=int, default=8)
    parser.add_argument("--enqueue", nargs=2, metavar=("KIND", "PAYLOAD_JSON"),
                        help="入队一个任务，例：--enqueue memory.extract '{\"text\":\"我喜欢三分糖\"}'")
    args = parser.parse_args()

    if args.enqueue:
        kind, payload_raw = args.enqueue
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError as exc:
            print(f"payload 不是合法 JSON：{exc}")
            return 1
        task_id = TaskQueue(args.data_dir).enqueue(kind, payload)
        print(json.dumps({"enqueued": task_id}, ensure_ascii=False))
        return 0

    report = run_idle(args.data_dir, max_tasks=args.max_tasks)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
