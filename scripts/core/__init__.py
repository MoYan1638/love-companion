# -*- coding: utf-8 -*-
"""Love Companion v2 - 数据 Schema 定义

对外入口：scripts/core/schema.py
约束：只依赖标准库，零外部依赖（Skill 分发的硬性要求）。
"""

# ---------------------------------------------------------------- 控制台兜底
# Windows 的 cmd / PowerShell 默认代码页 936（GBK），而人设、记忆、注入文本里
# 出现 emoji 是常态（"口头禅": ["好呀😊"]）。一旦 print 到 GBK 终端就会抛
# UnicodeEncodeError，用户看到的是 traceback 而不是结果。
#
# 只在该流确实是中文窄编码时才介入（错误处理改 replace，**不动编码**）：
# 能显示的照旧显示，显示不了的变成「?」，不崩。UTF-8 环境下完全不碰 stdout，
# 避免影响把本包当库调用的宿主程序。
import sys as _sys

_NARROW_ENCODINGS = {"gbk", "cp936", "gb2312", "cp18030", "gb18030"}

for _stream in (_sys.stdout, _sys.stderr):
    try:
        if (_stream.encoding or "").lower() in _NARROW_ENCODINGS:
            _stream.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001  非文本流 / 老版本 Python 直接跳过
        pass
del _stream

from .schema import (  # noqa: F401
    SCHEMA_VERSION,
    MEMORY_TYPES,
    DEFAULT_INJECTION_BUDGET,
    DEFAULT_DECAY,
    VALENCE_RANGE,
    memory_entry,
    normalize_memory_entry,
    validate_memory,
    is_v1_memory_entry,
    user_persona_template,
    cloned_persona_template,
    settings_template,
)
from .storage import read_json, write_json  # noqa: F401

__all__ = [
    "SCHEMA_VERSION", "MEMORY_TYPES", "DEFAULT_INJECTION_BUDGET", "DEFAULT_DECAY",
    "VALENCE_RANGE", "memory_entry", "normalize_memory_entry", "validate_memory",
    "is_v1_memory_entry", "user_persona_template", "cloned_persona_template",
    "settings_template", "read_json", "write_json",
]
