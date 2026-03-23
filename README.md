# 🧪 Integration Testing Skill

> Claude Code API 集成测试技能 · v0.9.0

自动读取 API 文档（Knife4j / Swagger2 / OpenAPI3 / Markdown），生成测试用例、执行真实 HTTP 请求、留存完整佐证，输出 Markdown + HTML 双格式报告。

---

## 目录

- [概述](#概述)
- [安装到 Claude 项目](#安装到-claude-项目)
- [仓库结构](#仓库结构)
- [快速开始](#快速开始)
- [参数说明](#参数说明)
- [用例来源优先级](#用例来源优先级)
- [用例自动生成](#用例自动生成)
- [断言引擎](#断言引擎)
- [执行机制](#执行机制)
- [留痕与合规](#留痕与合规)
- [报告产物](#报告产物)
- [典型场景](#典型场景)
- [常见问题](#常见问题)
- [版本历史](#版本历史)

---

## 概述

Integration Testing Skill 是面向 Claude Code 的 API 集成测试自动化技能，通过 `/api-testing` 斜杠命令或 `@integration-testing` agent 调用；`/integration-test` 仅作为历史兼容别名。

### 核心特性

| 特性 | 说明 |
|------|------|
| 📄 多文档格式 | Knife4j HTTP 实时拉取、Knife4j 导出 JSON、Swagger2/OpenAPI3 YAML/JSON、Markdown，支持微服务多分组聚合 |
| 🧪 三类用例自动生成 | `happy_path`、`boundary`、`error` 三类用例，内置 BVA 三点法 |
| 🔗 路径参数自动填充 | 自动将 `/api/books/{id}` 替换为 `/api/books/1`，避免字面量路径 404 |
| 📐 JSONPath 断言 | 支持 `[?(@.field==value)]` 过滤表达式，可对列表响应做动态断言 |
| 🛡️ 合规留痕 | 每条用例保留完整 HTTP Trace、断言明细和 `curl` 复现命令 |
| ⏱️ 超时保护 | 同时支持请求级超时与套件级超时 |
| 📊 五份报告产物 | `report.md`、`report.html`、`BugList.md`、`audit-summary.md`、`results.json` |

---

## 安装到 Claude 项目

如果你的 Claude 项目根目录是 `/home/claude/gbhu/AIMedAssistant_0322/AIMedAssistant`，推荐按下面的目标结构安装：

```text
/home/claude/gbhu/AIMedAssistant_0322/AIMedAssistant/
└── .claude/
    ├── agents/
    │   └── integration-testing.md
    ├── commands/
    │   └── api-testing.md
    └── skills/
        └── api-testing/
            ├── SKILL.md
            ├── scripts/
            ├── references/
            ├── assets/
            └── _meta.json
```

### 1. 从本仓库复制文件

```bash
PROJECT_ROOT=/home/claude/gbhu/AIMedAssistant_0322/AIMedAssistant
mkdir -p "$PROJECT_ROOT/.claude/skills" "$PROJECT_ROOT/.claude/agents" "$PROJECT_ROOT/.claude/commands"
cp -r skills/api-testing "$PROJECT_ROOT/.claude/skills/"
cp agents/integration-testing.md "$PROJECT_ROOT/.claude/agents/"
cp commands/api-testing.md "$PROJECT_ROOT/.claude/commands/"
```

### 2. 安装后校验

```bash
test -f "$PROJECT_ROOT/.claude/skills/api-testing/SKILL.md"
test -f "$PROJECT_ROOT/.claude/agents/integration-testing.md"
test -f "$PROJECT_ROOT/.claude/commands/api-testing.md"
```

### 3. 依赖要求

| 依赖 | 说明 |
|------|------|
| Python 3.8+ | 标准库即可，无需额外安装 |
| `curl` | 推荐，首选 HTTP 执行器 |
| `requests`（可选） | `pip install requests`，curl 不可用时的降级执行器 |
| Claude Code | 支持 `.claude/skills`、`.claude/agents`、`.claude/commands` |

---

## 仓库结构

本仓库中的源码布局如下；复制到 Claude 项目后，目标路径应映射到 `.claude/...`：

```text
.
├── commands/
│   └── api-testing.md
├── agents/
│   └── integration-testing.md
└── skills/
    └── api-testing/
        ├── SKILL.md
        ├── scripts/
        ├── assets/
        ├── references/
        └── _meta.json
```

在 Claude 项目中，对应运行时路径分别是：

- `.claude/commands/api-testing.md`
- `.claude/agents/integration-testing.md`
- `.claude/skills/api-testing/...`

---

## 快速开始

在 Claude Code 对话框中输入以下命令之一：

```bash
/api-testing http://localhost:8080 --generate-all

/api-testing http://localhost:8080 --knife4j-url http://localhost:8080 --generate-all

/api-testing http://localhost:8080 --knife4j-url http://localhost:8080 \
  --knife4j-token "Bearer eyJ..." --force-auth --generate-all

/api-testing http://localhost:8080 --api-doc docs/test/test-data/swagger.json --generate-all
```

执行完成后，产物写入：

```text
docs/test/test-reports/{TIMESTAMP}/
├── report.html
├── report.md
├── BugList.md
├── audit-summary.md
└── results.json
```

---

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `API_URL` | 被测服务地址（第一个非 `--` 参数） | `http://localhost:8080` |
| `--knife4j-url <url>` | Knife4j 服务地址，自动遍历多分组 | — |
| `--knife4j-token <token>` | Knife4j 认证 Token，支持 `Bearer xxx` 或 `Basic xxx` | — |
| `--api-doc <file>` | 本地文档路径，支持 Knife4j 导出 JSON / Swagger2 / OpenAPI3 / Markdown | — |
| `--cases <file>` | 用户提供用例文件（JSON/YAML），优先级最高 | — |
| `--generate-all` | 自动生成 `happy_path` / `boundary` / `error` 三类用例 | 关闭 |
| `--force-auth` | 强制业务接口标记为 `requires_auth=true` | 关闭 |
| `--model <sonnet\|haiku>` | 执行模型 | `sonnet` |
| `--suite-timeout <秒>` | 整套测试超时上限 | `300` |

---

## 用例来源优先级

```text
P1（最高）  --cases 文件
P2a         --knife4j-url
P2b         --api-doc JSON/YAML
P2c         --api-doc Markdown
P3（兜底）  Controller 代码扫描
```

---

## 用例自动生成

开启 `--generate-all` 后，每个端点自动生成：

- `happy_path`
- `boundary`
- `error`

支持通过 `--cases` 提供手工用例覆盖自动生成结果。

---

## 断言引擎

支持的断言类型：

- `exists`
- `not_exists`
- `eq`
- `contains`
- JSONPath 风格过滤

---

## 执行机制

- 推荐优先使用 `.claude/commands/api-testing.md` 作为公开入口。
- agent 实际执行规则见 `.claude/agents/integration-testing.md`。
- skill 参考与脚本位于 `.claude/skills/api-testing/`。
- 若使用源码仓库相对路径进行维护，则对应文件位于 `commands/`、`agents/`、`skills/api-testing/`。

---

## 留痕与合规

- 每次重跑必须生成新的 `TIMESTAMP`。
- 发现/生成用例时必须分离 stdout 与 stderr。
- 覆盖登记必须使用模板路径 `metadata.template_path`。
- 依赖链执行时允许技术性 `SKIP`，但报告层仍视为需要修复的异常状态。

---

## 报告产物

输出目录：`docs/test/test-reports/{TIMESTAMP}/`

- `report.md`
- `report.html`
- `BugList.md`
- `audit-summary.md`
- `results.json`

---

## 典型场景

- 基于 Knife4j / Swagger 对已有 REST API 做快速回归。
- 为交付验收生成完整测试证据链。
- 在缺乏手工 case 的情况下生成基础覆盖。

---

## 常见问题

### Q1：到底应该使用仓库路径还是 `.claude` 路径？

- 在本仓库维护源码时，使用 `skills/api-testing/...`、`agents/...`、`commands/...`。
- 在 Claude 项目中实际安装和运行时，使用 `.claude/skills/...`、`.claude/agents/...`、`.claude/commands/...`。

### Q2：`--knife4j-token` 传 `Bearer xxx` 还是裸 token？

命令参数可传 `Bearer xxx`；执行脚本前应剥离前缀，只把裸 token 传给 `run_test.py`。

### Q3：为什么报告里出现 `SKIP` 也算问题？

因为 `SKIP` 代表计划内链路未完整执行。技术上允许出现，但治理上仍应修复其上游依赖或测试数据。

---

## 版本历史

- `v0.9.0`：统一命令入口为 `/api-testing`，补充依赖链说明，明确源码路径与 `.claude` 运行时路径映射。
