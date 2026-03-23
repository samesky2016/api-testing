# 🧪 Integration Testing Skill

> Claude Code API 集成测试技能 · v0.9.0

自动读取 API 文档（Knife4j / Swagger2 / OpenAPI3 / Markdown），生成测试用例、执行真实 HTTP 请求、留存完整佐证，输出 Markdown + HTML 双格式报告。

---

## 目录

- [概述](#概述)
- [安装到 Claude 项目](#安装到-claude-项目)
- [仓库结构与运行时路径映射](#仓库结构与运行时路径映射)
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
| 🧪 三类用例自动生成 | `happy_path`（有效等价类）、`boundary`（边界值）、`error`（无效等价类），内置 BVA 三点法 |
| 🔗 路径参数自动填充 | 解析 `parameters[in=path]`，将 `/api/books/{id}` 自动替换为 `/api/books/1`，消除字面量路径 404 |
| 📐 JSONPath 断言 | 支持 `[?(@.field==value)]` 过滤表达式，可对列表响应做动态字段断言 |
| 🛡️ 合规留痕 | 每条用例写入完整 HTTP Trace（含 `curl` 复现命令），FAIL 时自动记录 `fail_reason`、完整出入参 |
| ⏱️ 超时保护 | `--request-timeout` 控制单请求超时，`--suite-timeout` 控制整套截止时间，超时后自动生成当前报告 |
| 📊 五份报告产物 | `report.md` · `report.html` · `BugList.md` · `audit-summary.md` · `results.json` |

---

## 安装到 Claude 项目

如果你的 Claude 项目根目录是 `/home/claude/gbhu/AIMedAssistant_0322/AIMedAssistant`，推荐按下面的目标结构安装：

```text
/home/claude/gbhu/AIMedAssistant_0322/AIMedAssistant/
└── .claude/
    ├── commands/
    │   └── api-testing.md            # /api-testing 斜杠命令
    ├── agents/
    │   └── integration-testing.md    # @integration-testing agent 定义
    └── skills/
        └── api-testing/
            ├── SKILL.md              # 技能索引（allowed-tools / invocation）
            ├── scripts/
            │   ├── discover_cases.py
            │   ├── run_test.py
            │   ├── run_chain.py
            │   ├── gen_reports.py
            │   └── record.sh
            ├── assets/
            │   └── http_client.py
            ├── references/
            │   ├── integration-testing.md
            │   ├── audit-trail.md
            │   └── case-generation.md
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

## 仓库结构与运行时路径映射

本仓库中的源码布局如下：

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

复制到 Claude 项目后，对应运行时路径为：

| 仓库源码路径 | Claude 项目运行时路径 |
|-------------|----------------------|
| `commands/api-testing.md` | `.claude/commands/api-testing.md` |
| `agents/integration-testing.md` | `.claude/agents/integration-testing.md` |
| `skills/api-testing/...` | `.claude/skills/api-testing/...` |

这意味着：

- 在本仓库里维护文档和脚本时，使用 `commands/`、`agents/`、`skills/api-testing/` 相对路径。
- 在你的 Claude 项目里实际安装和运行时，使用 `.claude/commands/`、`.claude/agents/`、`.claude/skills/` 路径。

---

## 快速开始

在 Claude Code 对话框中输入以下命令之一：

```bash
# 最简调用：自动推断 API 地址，扫描项目代码生成用例
/api-testing http://localhost:8080 --generate-all

# 指定 Knife4j 服务（推荐，服务运行时）
/api-testing http://localhost:8080 --knife4j-url http://localhost:8080 --generate-all

# 有认证 token 时（内部业务系统建议同时加 --force-auth）
/api-testing http://localhost:8080 --knife4j-url http://localhost:8080   --knife4j-token "Bearer eyJ..." --force-auth --generate-all

# 使用本地 Swagger 文件
/api-testing http://localhost:8080 --api-doc docs/test/test-data/swagger.json --generate-all

# 自然语言触发
帮我对 http://localhost:8080 做一次接口测试
```

执行完成后，产物写入：

```text
docs/test/test-reports/{TIMESTAMP}/
├── report.html        ← 推荐查看
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
| `--knife4j-url <url>` | Knife4j 服务地址，HTTP 实时拉取文档，自动遍历多分组（优先级高于 `--api-doc`） | — |
| `--knife4j-token <token>` | Knife4j 认证 Token，支持 `Bearer xxx` 或 `Basic xxx` | — |
| `--api-doc <file>` | 本地文档路径，支持 Knife4j 导出 JSON / Swagger2 / OpenAPI3 / Markdown | — |
| `--cases <file>` | 用户提供用例文件（JSON/YAML），优先级最高，原样执行 | — |
| `--generate-all` | 开启三类用例自动生成（`happy_path` / `boundary` / `error`） | 关闭 |
| `--force-auth` | 强制所有业务接口标记为 `requires_auth=true`，当 Swagger 文档未声明 security scheme 时建议传入 | 关闭 |
| `--model <sonnet\|haiku>` | 执行模型，`sonnet` 适合复杂项目，`haiku` 速度更快 | `sonnet` |
| `--suite-timeout <秒>` | 整套测试超时上限，超时后停止并生成当前报告 | `300` |

---

## 用例来源优先级

当多种参数同时传入时，按以下优先级选择：

```text
P1（最高）  --cases 文件          用户手工编写的精确用例，原样使用
P2a         --knife4j-url         HTTP 实时拉取，推荐生产环境
P2b         --api-doc JSON/YAML   Knife4j 导出 / Swagger2 / OpenAPI3 离线文件
P2c         --api-doc Markdown    Markdown 格式 API 文档，正则解析路由
P3（兜底）  Controller 代码扫描   无文档时扫描 Java / TypeScript / Python 路由注解
            ⚠ 降级时输出明确警告，提示提供文档以获得更精确的用例
```

---

## 用例自动生成

开启 `--generate-all` 后，每个端点自动生成以下类别用例：

| 类别 | 触发条件 | 预期状态码 | 设计依据 |
|------|----------|-----------|---------|
| `happy_path` | 所有端点 | 接口 responses 中最小 2xx | 有效等价类，所有必填字段填入合法值 |
| `boundary`（空/零） | POST / PUT / PATCH | 有 schema → `400`；无 schema → `200` | 字符串→`""`，数字→`0`，数组→`[]` |
| `boundary`（超上限） | 含整数字段的 schema | `400` | BVA：int32 上界 + 1（`2147483648`） |
| `boundary`（特殊字符） | 含字符串字段的 schema | 与 happy_path 相同 | `!@#$%^&*()` 等特殊输入 |
| `error`（缺失必填） | POST / PUT / PATCH | `400` | 无效等价类：发送空 body `{}` |
| `error`（类型不匹配） | POST / PUT / PATCH | `400` | 无效等价类：数字字段传 `"not_a_number"` |

### 自定义用例文件格式（`--cases`）

```json
[
  {
    "seq": 1,
    "tc_id": "TC-001",
    "name": "获取图书详情 - 正常场景",
    "priority": "P1",
    "category": "happy_path",
    "method": "GET",
    "path": "/api/books/1",
    "expected_status": 200,
    "body": null,
    "asserts": [
      { "path": ".id",    "type": "exists" },
      { "path": ".title", "type": "exists" }
    ],
    "requires_auth": false
  }
]
```

### 优先级说明

| 优先级 | 含义 |
|--------|------|
| `P0` | 认证接口、核心 CRUD，必须 100% 覆盖 |
| `P1` | 主要业务接口，正常场景 |
| `P2` | 边界条件、错误码、等价类扩展 |

---

## 断言引擎

### 支持的断言类型

| `type` | 说明 | 示例 |
|--------|------|------|
| `exists` | 字段存在性检查 | `{ "path": ".id", "type": "exists" }` |
| `not_exists` | 字段不存在检查 | `{ "path": ".error", "type": "not_exists" }` |
| `eq` | 精确值匹配 | `{ "path": ".status", "type": "eq", "expected": "active" }` |
| `contains` | 字段值包含子串 | `{ "path": ".message", "type": "contains", "expected": "成功" }` |
| JSONPath 过滤 | 列表动态过滤 | `{ "path": "[?(@.id==1)].name", "type": "exists" }` |

### JSONPath 过滤语法

支持对列表响应做动态过滤断言，格式：`[?(@.field 操作符 value)]`

```json
{ "path": "[?(@.id==1)].name", "type": "exists" }
{ "path": "[?(@.name contains Alice)].email", "type": "exists" }
{ "path": ".items[?(@.val>=50)].id", "type": "exists" }
```

支持的操作符：`==` `!=` `contains` `>=` `<=` `>` `<`

---

## 执行机制

### 四步执行流程

```text
步骤 1  初始化留痕目录
        bash .claude/skills/api-testing/scripts/record.sh init

步骤 2  发现 / 生成测试用例
        python3 .claude/skills/api-testing/scripts/discover_cases.py . --api-doc <文档> --generate-all

步骤 3  逐用例执行（真实 HTTP 请求，禁止 mock）
        python3 .claude/skills/api-testing/scripts/run_test.py <参数> --request-timeout 10 --suite-deadline <时间戳>

步骤 4  生成汇总报告
        bash .claude/skills/api-testing/scripts/record.sh all <REPORT_BASE> <TIMESTAMP> <API_URL>
```

### HTTP 执行器

`run_test.py` 自动选择执行器，也可通过环境变量强制指定：

| 执行器 | 触发条件 | 特点 |
|--------|---------|------|
| `curl` | `curl` 在 PATH 中（**首选**） | 稳定、自动生成 `curl_equivalent` 复现命令 |
| `http_client.py` | `requests` 库已安装（降级） | 纯 Python，无外部依赖 |

```bash
export TEST_EXECUTOR=curl
export TEST_EXECUTOR=http_client
```

### 有状态 API 的执行顺序

> ⚠️ 对于有数据库的真实 API，用例执行顺序至关重要。

推荐顺序：

```text
1. POST（创建资源，建立测试数据）
2. GET  （读取，验证创建结果）
3. PUT  （更新，修改已有数据）
4. boundary / error 用例
5. DELETE（最后清理，避免影响其他用例）
```

Agent 会自动从 POST 201 响应中捕获返回的 `id`，注入到后续需要该资源 ID 的用例中，避免误报 404。

### 超时控制

| 参数 | 控制粒度 | 行为 |
|------|---------|------|
| `--request-timeout <秒>` | 单条 HTTP 请求 | 默认 10 秒，超时后 `actual_status=0`，用例标记 FAIL |
| `--suite-deadline <时间戳>` | 整套测试（Unix 时间戳） | 到达后输出 `suite_timeout:true`，退出码 `2`，自动跳转报告生成 |
| `--suite-timeout <秒>` | 整套测试（秒数） | orchestrator 将秒数转换为 deadline 后传入，默认 300 秒 |

---

## 留痕与合规

### HTTP Trace 文件

每条用例在 `evidence/http-trace/` 生成一个 JSON 文件：

**命名规则：** `{SEQ}_{METHOD}_{path-slug}_{PASS|FAIL}.json`

### 敏感信息脱敏

| 字段 | 处理规则 |
|------|---------|
| `Authorization` token | 保留前 10 字符 + `***` |
| `password` / `secret` / `key` | 替换为 `[REDACTED]` |
| `Cookie` value | 替换为 `[REDACTED]` |

### 合规约束

- 所有计划内用例都应执行；依赖链中的技术性 `SKIP` 仍会在报告中被标记为需要修复。
- 不允许注册后长期 `UNTESTED` 的端点；无法访问的端点应在对话中说明原因。
- FAIL 用例必须记录失败原因、完整出入参和 `curl_equivalent`。
- 所有状态码和响应体必须来自真实 HTTP 请求，禁止 mock。

---

## 报告产物

### 五份产物说明

| 文件 | 格式 | 适用场景 | 关键内容 |
|------|------|---------|---------|
| `report.html` | HTML | 人工查阅（**推荐**） | 交互式，用例按类别分组，FAIL 内嵌出入参与 curl 命令 |
| `report.md` | Markdown | 文档存档 / Git 提交 | 覆盖矩阵、失败详情、接口列表 |
| `BugList.md` | Markdown | 缺陷管理 / 开发修复 | 仅含 FAIL 用例，完整请求体、响应体、复现命令 |
| `audit-summary.md` | Markdown | 审计 / 质量门禁 | 留痕文件索引、覆盖率、违规警告 |
| `results.json` | JSON | CI/CD 对接 / 自动化处理 | 结构化结果，含 `compliance` 字段 |

---

## 典型场景

### 场景一：Spring Boot + Knife4j 项目（推荐）

```bash
/api-testing http://localhost:8080   --knife4j-url http://localhost:8080   --generate-all
```

### 场景二：离线 Swagger / OpenAPI 文件

```bash
/api-testing http://localhost:8080   --api-doc docs/test/test-data/swagger.json   --generate-all
```

### 场景三：大型项目（500+ 用例）

```bash
/api-testing http://localhost:8080   --knife4j-url http://localhost:8080   --generate-all   --model sonnet   --suite-timeout 600
```

### 场景四：CI/CD 集成

```yaml
- name: Run Integration Tests
  run: |
    claude code --print       "/api-testing ${{ env.API_URL }}        --knife4j-url ${{ env.API_URL }}        --generate-all        --suite-timeout 300"
```

### 场景五：复用已有用例文件

```bash
/api-testing http://localhost:8080   --cases docs/test/test-cases/20260322_141808-cases.json
```

---

## 常见问题

### Q1：到底应该使用仓库路径还是 `.claude` 路径？

- 在本仓库维护源码时，使用 `skills/api-testing/...`、`agents/...`、`commands/...`。
- 在 Claude 项目中实际安装和运行时，使用 `.claude/skills/...`、`.claude/agents/...`、`.claude/commands/...`。

### Q2：`--knife4j-token` 传 `Bearer xxx` 还是裸 token？

命令参数可传 `Bearer xxx`；执行脚本前应剥离前缀，只把裸 token 传给 `run_test.py`。

### Q3：为什么报告里出现 `SKIP` 也算问题？

因为 `SKIP` 代表计划内链路未完整执行。技术上允许出现，但治理上仍应修复其上游依赖或测试数据。

### Q4：`integration-testing agent not found` 怎么办？

检查 `.claude/agents/integration-testing.md` 的 YAML frontmatter 是否完整，且文件已复制到目标 Claude 项目中。

### Q5：大量用例返回 401 怎么排查？

优先检查：

1. 是否传入了有效 `--knife4j-token`
2. Swagger / Knife4j 文档是否声明 security scheme
3. 未声明时是否追加了 `--force-auth`

---

## 版本历史

### v0.9.0

- 统一命令入口为 `/api-testing`，保留 `/integration-test` 作为历史兼容别名。
- 增补 `run_chain.py` 依赖链执行说明。
- 明确源码路径与 `.claude` 运行时路径映射。
- 修正文档安装示例，使其适配 `/home/claude/gbhu/AIMedAssistant_0322/AIMedAssistant` 这类 Claude 项目目录。
