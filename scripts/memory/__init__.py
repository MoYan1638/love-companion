# -*- coding: utf-8 -*-
"""
记忆系统（M2 / 阶段2）

职责：
- 6 类记忆：事实/偏好/里程碑/共享事件/情绪/人设特征
- 无感采集（对话中提取）
- 多路检索：语义 + 时间 + 重要性 + 关系路径 → Top-3（<150 Token）
- 短期记忆（会话窗口）与长期记忆（衰减/召回计数/情感效价）
- 数据主权：单条删除、批量导出、一键清除

状态：M2 已实现。
对外入口（直接按模块导入）：
    from scripts.memory.store import MemoryStore      # 六类记忆 + 数据主权
    from scripts.memory.extract import extract_memories  # 无感采集（离线）
    from scripts.memory.retrieve import top_k, render    # 多路检索 Top-3
设计约束（红线）：
- 只依赖 Python 标准库，零外部依赖（Skill 分发的硬性要求）
- 重活全部离线完成，在线只注入摘要
- 单轮额外注入预算见 core/schema.py 的 DEFAULT_INJECTION_BUDGET
- 引用记忆/画像/人格必须可溯源，禁止编造
"""
