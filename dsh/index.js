// love-companion - DSH plugin bridge (v2.1.0+)
// (c) 2026 MoYan1638
// https://github.com/MoYan1638/love-companion
// Licensed under the CC BY-NC 4.0 License. See the LICENSE file for details.
//
// 分层架构：
// - Python 核心（scripts/manager.py + pipeline/orchestrator.py）：纯工具层，
//   人设 CRUD / 六类记忆 / 情绪识别 / 主动关怀，全部离线重处理
// - DSH 插件 Host（本文件）：系统提示注入 + 可选 settings 命名空间
//   * ctx.systemPrompt.section 注入 AI 工作指引（可选服务，缺失不阻塞）
//   * ctx.settings.register('love-companion') 官方设置命名空间
//
// 技能发现走文件系统（~/.dsh/skills/love-companion/SKILL.md），
// 插件不在运行时重复注册 SKILL.md，避免与文件系统技能 API 面重复。
//
// 纯 CLI / OpenClaw / WorkBuddy 用户完全不受影响：
// 不使用 DSH 插件时，本文件不会被加载，SKILL.md 照常被各宿主读取。

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 配置目录（与 Python 侧 ~/.love-companion 保持兼容）
const APP_DATA_DIR = join(homedir(), ".love-companion");

// settings 命名空间（官方要求小写 kebab-case）
const SETTINGS_NS = "love-companion";

// 系统提示段落名（官方约定 plugin:<name>，重复注册会抛错）
const SECTION_NAME = "plugin:love-companion";
const SECTION_ORDER = 100;

// AI 工作指引（模型可见的能力说明）
const COMPANION_GUIDANCE = `本机已安装 AI 陪伴技能 love-companion。能力：多轮情感对话、用户自定义人设配置（姓名/昵称/性别/性格/背景）、长时记忆存储与检索、情绪识别与反馈、预设人设模板套用、配置导入导出。当用户提及「恋人 / 男/女朋友 / 情感陪伴 / 人设 / 角色扮演 / 情感对话」时即指本技能。所有对话均为 AI 生成的角色扮演内容，不代表真实人际关系；启用前需确认用户已满 18 周岁。数据全部存储在本地设备（~/.love-companion/data），不上传。`;

// DSH 插件默认导出：接收 ctx 上下文
export default function apply(ctx) {
  // 1) 系统提示注入（可选服务，ctx.get 缺失时静默跳过）
  try {
    if (ctx.systemPrompt && typeof ctx.systemPrompt.section === "function") {
      ctx.systemPrompt.section(SECTION_NAME, COMPANION_GUIDANCE, SECTION_ORDER);
    }
  } catch (e) {
    // systemPrompt 为可选服务，缺失不阻塞插件加载
  }

  // 2) settings 命名空间（可选，仅当 schemastery 与 settings 服务可用时注册）
  try {
    if (ctx.settings && typeof ctx.settings.register === "function") {
      ctx.settings.register(SETTINGS_NS);
    }
  } catch (e) {
    // settings 为可选服务
  }

  // 3) 确保数据目录存在（与 Python 侧共享）
  try {
    if (!existsSync(APP_DATA_DIR)) {
      mkdirSync(APP_DATA_DIR, { recursive: true });
    }
  } catch (e) {
    // 目录创建失败不阻塞；Python 侧会自行兜底
  }
}

// 导出路径常量，供外部（测试/文档）引用
export const DATA_DIR = APP_DATA_DIR;
