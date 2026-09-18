# Love Companion v2 架构设计（M0）

> 依据：《LoveCompanion_开发与优化交接方案》
> 里程碑拆解见：`../love-companion-v2-里程碑拆解.md`（工作区根目录）
> 状态：M0 骨架已落地，模块实现按里程碑推进

---

## 一、形态与边界

**仍是 Skill 包**，不是独立应用。这一点决定了所有架构选择：

| 维度 | 约束 |
|---|---|
| 分发 | SKILL.md + references/ + scripts/ 的文件集合，ClawHub / SkillHub / 虾评分发渠道不变 |
| 依赖 | **只依赖 Python 标准库**，零第三方库（用户装不上，也不能要求装） |
| 存储 | 本地文件，沿用 `~/.love-companion/data/`（可用 `LOVE_COMPANION_DATA_DIR` 覆盖） |
| 执行 | 离线管线由宿主机（Agent 框架 / 系统任务）触发；在线只读取离线产物 |
| 兼容 | v1 的 8 套人设、`/恋人…` 指令、manager.py API、数据目录全部保留 |

---

## 二、核心原则（红线，贯穿所有模块）

1. **离线重处理、在线轻注入**——特征提取、记忆抽取、人格编译、网页抓取、Humanizer 改写全部后台完成，原始内容绝不进对话
2. **单轮额外系统开销 ≤ 300–500 Token**
3. **真实性零容忍**——注入的每条记忆 / 人设特征 / 画像必须可溯源（条目 id + 原文），禁止编造
4. **隐私优先**——采集经隐私过滤，支持单条删除、批量导出、一键清除

---

## 三、在线 / 离线边界

```
┌─────────────── 离线（重活，不占对话 Token）───────────────┐
│ pipeline/   任务队列：注册 · 调度 · 重试 · 落盘          │
│ memory/     无感采集 → 六类记忆 → 检索索引               │
│ persona/    素材摄取 → 三层提取 → 人格库 → 编译人格摘要   │
│ user/       流式采集 → 两级分析 → User Persona → 相处指南 │
│ style/      Humanizer 三层黑名单校验（后处理）            │
│ trends/     抓取 → 解析 → 流行语/热点提炼                │
└────────────────────────┬───────────────────────────────┘
                         │ 产出「注入摘要」（短文本 + Token 计数）
                         ▼
┌─────────────── 在线（轻注入）────────────────────────────┐
│ SKILL.md 运行时读取摘要 → 拼进 System Prompt             │
│ 预算：相处指南<200 · 记忆Top-3<150 · 人格指令<100       │
│       趋势<50 · 关怀话术<80    合计 ≤500 Token           │
└──────────────────────────────────────────────────────────┘
```

Token 预算定义与校验入口：`scripts/core/schema.py::DEFAULT_INJECTION_BUDGET`。
注入前统一走 `pipeline/` 的注入器做计数与超限时截断/拒注——**预算不是建议值，是硬约束**。

---

## 四、目录结构

```
love-companion/
├── SKILL.md                  # 技能主文件（v1 指令体系 + v2 轻注入策略）
├── README.md
├── LICENSE
├── references/               # 人设预设（唯一数据源）、指令手册、教程
├── docs/
│   └── architecture.md       # 本文件
├── tests/
│   └── test_manager.py       # 回归测试：v1 能力 + v2 schema/迁移
└── scripts/
    ├── manager.py            # v1 配置与记忆管理（保留，向后兼容）
    ├── core/
    │   └── schema.py         # v2 数据 schema：记忆/画像/人格库/设置
    ├── migrate/
    │   └── migrate_v1.py     # v1→v2 数据迁移（自带备份，无损可回退）
    ├── pipeline/             # M1 离线管线 + 注入器
    ├── memory/               # M2 记忆系统
    ├── persona/              # M3a 伴侣人格克隆
    ├── user/                 # M3b 恋人式用户理解
    ├── style/                # M4 交流语气 + Humanizer 守门
    ├── care/                 # M6 主动关怀
    ├── trends/               # M7a 趋势感知
    ├── multimodal/           # M7b 多模态
    └── panel/                # M7c 控制与安全感
```

---

## 五、数据 schema（v2.0）

定义：`scripts/core/schema.py`。要点：

- **6 类记忆**：事实 / 偏好 / 里程碑 / 共享事件 / 情绪 / 人设特征
- **记忆条目字段**：`id · type · content · source · importance · valence · recall_count ·
  created_at · updated_at · last_recalled_at · conversation_id · schema_version`
- **v2 是 v1 的超集**：v1 条目只有 `id/content/created_at`，v2 完整保留并追加元数据 →
  v1 的 `manager.py` 可直接读取 v2 数据，升级无损、可回退（测试里有断言覆盖）
- **User Persona**：沟通风格 / 大五 / 依恋类型 / 情绪模式 / 互动偏好（均带置信度）
- **克隆人格**：声线 / 思维 / 性格 三层 + 关系面（M5 填充）+ 版本
- **衰减参数**：重要性半衰期 30 天、每次召回 +0.05、下限 0.05

---

## 六、迁移策略

`python scripts/migrate/migrate_v1.py --data-dir ~/.love-companion/data`

1. 整目录备份到 `backup_v1_<时间戳>/`
2. `memory.json` 条目补齐为 v2 结构（content 一字不改）
3. 缺失则生成 `settings.json`
4. **不删除任何原文件**；出问题用备份覆盖即可回退
5. `--dry-run` 可先预演，不落盘

---

## 七、里程碑映射

| 模块 | 里程碑 | 方案阶段 | 优先级 |
|---|---|---|---|
| pipeline/ | M1 | 阶段 1 | P0 |
| memory/ | M2 | 阶段 2 | P0 |
| persona/ | M3a | 阶段 3 | P0 |
| user/ | M3b | 阶段 4 | P0 |
| style/ | M4 | 阶段 6 | P0 |
| （融合：persona × user） | M5 | 阶段 5 | P0 |
| care/ | M6 | 阶段 7 | P0 |
| trends/ multimodal/ panel/ | M7 | 阶段 8/9/10 | P1 |

---

## 八、待拍板的技术决策（影响 M2 起的实现）

1. 记忆语义检索选型：TF-IDF（零依赖）vs sqlite-vec / faiss
2. 依恋 / 情绪识别：规则引擎 vs 本地小模型
3. 开源依赖接入方式：crush-cupid / yourself-skill / Agent-Reach 拿源码改造，还是按理念自研
4. 多模态图片来源（AI 生成 / 图库）与 IM 通道发图能力
5. 离线管线触发方式：定时任务 vs 对话间隙

---

## 九、测试

`python tests/test_manager.py`

覆盖范围：预设解析（8 套与文档逐字段一致）、2 号称呼回归、缓存隔离、坏 JSON 报错定位、
方案与记忆 CRUD、CLI 冒烟、v2 schema 校验、注入预算红线、**v1→v2 迁移无损与向下兼容**。
全程使用临时数据目录，不触碰用户真实数据。
