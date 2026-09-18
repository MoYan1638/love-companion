# -*- coding: utf-8 -*-
"""Love Companion v2 - 数据 Schema 定义

对外入口：scripts/core/schema.py
约束：只依赖标准库，零外部依赖（Skill 分发的硬性要求）。
"""

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

__all__ = [
    "SCHEMA_VERSION", "MEMORY_TYPES", "DEFAULT_INJECTION_BUDGET", "DEFAULT_DECAY",
    "VALENCE_RANGE", "memory_entry", "normalize_memory_entry", "validate_memory",
    "is_v1_memory_entry", "user_persona_template", "cloned_persona_template",
    "settings_template",
]
