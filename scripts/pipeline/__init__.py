# -*- coding: utf-8 -*-
"""
离线管线 + 轻注入框架（M1 / 阶段1）

职责：
- 任务注册/调度/重试（纯本地文件队列，零外部依赖）
- 注入摘要生成与 Token 预算校验（超限截断/拒注）
- 与 SKILL.md 的运行时衔接约定：在线只读摘要，不读原始内容

状态：M1 已实现。
对外入口（直接按模块导入）：
    from scripts.pipeline.queue import TaskQueue      # 离线任务队列
    from scripts.pipeline.injector import Injector    # 在线轻注入器（预算硬约束）
    from scripts.pipeline.runner import run_idle, register  # 对话间隙调度
设计约束（红线）：
- 只依赖 Python 标准库，零外部依赖（Skill 分发的硬性要求）
- 重活全部离线完成，在线只注入摘要
- 单轮额外注入预算见 core/schema.py 的 DEFAULT_INJECTION_BUDGET
- 引用记忆/画像/人格必须可溯源，禁止编造
"""
