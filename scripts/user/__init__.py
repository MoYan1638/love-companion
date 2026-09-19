# -*- coding: utf-8 -*-
"""
恋人式用户理解（M3b / 阶段4）

职责：
- 流式采集：每轮输入经隐私过滤后入队
- 两级分析：每 5 条轻量提取 / 每 50 条深度画像
- User Persona：沟通风格/大五/依恋类型/情绪模式/互动偏好
- 相处指南编译（<200 Token）+ 反馈闭环

状态：M3b 已实现。
对外入口：
    from scripts.user.profile import UserProfileStore   # 流式采集 + 两级分析 + 反馈闭环
    from scripts.user.guide import compile_guide, infer_attachment  # 相处指南（<200 Token）
设计约束（红线）：
- 只依赖 Python 标准库，零外部依赖（Skill 分发的硬性要求）
- 重活全部离线完成，在线只注入摘要
- 单轮额外注入预算见 core/schema.py 的 DEFAULT_INJECTION_BUDGET
- 引用记忆/画像/人格必须可溯源，禁止编造
"""
