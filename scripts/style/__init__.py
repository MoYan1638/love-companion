# -*- coding: utf-8 -*-
"""
交流语气 + Humanizer 守门（M4 / 阶段6）

职责：
- 短句拆分控制器（模拟真人打字节奏）
- 口语化与情绪同步（语气词/标点/emoji 频率）
- Humanizer 三层黑名单：L1 禁用词 / L2 结构模式 / L3 风格偏差（硬红线）
- Density 密度校准：结构腔「超了压」+ 微标记「少了补」（软校准，双向）
- 强度四档：关闭/轻柔/标准/深度

状态：M4 已实现；M4.5 密度校准已实现。
对外入口：
    from scripts.style.voice import shape, split_short, is_night  # 短句/四档强度/深夜模式
    from scripts.style.humanizer import scan, is_clean             # L1/L2/L3 守门（离线，硬红线）
    from scripts.style.density import assess, thin_structures      # 密度校准（离线，软校准）
设计约束（红线）：
- 只依赖 Python 标准库，零外部依赖（Skill 分发的硬性要求）
- 重活全部离线完成，在线只注入摘要
- 单轮额外注入预算见 core/schema.py 的 DEFAULT_INJECTION_BUDGET
- 引用记忆/画像/人格必须可溯源，禁止编造
- humanizer 管「性质问题」（身份露馅、替用户断言情绪），density 管「密度问题」（结构腔超标、微标记欠用），两者不互相替代
"""
