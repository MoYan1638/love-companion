# -*- coding: utf-8 -*-
"""
伴侣人格克隆（M3a / 阶段3）+ 双向人格镜像（M5 / 阶段5）

模块划分（参考 crush-skills / yourself-skill 的 tools/ + prompts/ 分层）：
- parser.py    素材解析：微信/QQ/社媒/纯文本 → 统一语料（含隐私脱敏与素材指纹）
- extract.py   三层提取：声线 / 思维 / 性格 + 5 层人格模型编译
- library.py   人格库：CRUD、增量 merge、纠偏层、版本回滚、在线摘要编译
- mirror.py    双向人格镜像：关系阶段、共鸣、演化建模、一致性自检、元认知反馈

状态：M3a + M5 已实现（2026-09）。

设计约束（红线）：
- 只依赖 Python 标准库，零外部依赖（Skill 分发的硬性要求）
- 重活全部离线完成，在线只注入 library.compile_summary 压出来的摘要
- 单轮额外注入预算见 core/schema.py 的 DEFAULT_INJECTION_BUDGET（人格指令 100）
- 人格必须可溯源到素材指纹，禁止凭空生成（真实性零容忍）
"""
