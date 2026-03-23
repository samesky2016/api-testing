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

Integration Testing Skill 是面向 Claude Code 的 API 集成测试自动化技能，通过 `/api-testing` 斜杠命令或 `@integration-testing` agent 调用；`/integration-test` 视为兼容旧别名。

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
git clone <repo> /your-project
cp -r /your-project/skills /your-project/commands /your-project/agents <target-project>/
```

### 2. 安装后校验

```
.
├── commands/
│   └── api-testing.md           # /api-testing 斜杠命令
├── agents/
│   └── integration-testing.md   # @integration-testing agent 定义
└── skills/
    └── api-testing/
        ├── SKILL.md             # 技能索引（allowed-tools / invocation）
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

### 复制到 `.claude` 后的实际调用示例

下表同时展示“源码仓库里的维护视角”和“复制到 Claude 项目后的运行时视角”：

| 场景 | 源码仓库示例 | Claude 运行时示例 |
|------|--------------|-------------------|
| 查看命令入口 | `commands/api-testing.md` | `.claude/commands/api-testing.md` |
| 查看 agent 规则 | `agents/integration-testing.md` | `.claude/agents/integration-testing.md` |
| 发现用例 | `skills/api-testing/scripts/discover_cases.py`（源码维护位置） | `python3 .claude/skills/api-testing/scripts/discover_cases.py . --api-doc docs/test/test-data/swagger.json --generate-all` |
| 依赖链执行 | `skills/api-testing/scripts/run_chain.py`（源码维护位置） | `python3 .claude/skills/api-testing/scripts/run_chain.py "$CASES_FILE" "$EVIDENCE_DIR" "$API_URL" "$AUTH_TOKEN" --request-timeout 10 --suite-timeout 600` |
| 生成报告 | `skills/api-testing/scripts/record.sh`（源码维护位置） | `bash .claude/skills/api-testing/scripts/record.sh all "$BASE_DIR" "$TIMESTAMP" "$API_URL"` |

> 说明：源码仓库中的 `skills/api-testing/scripts/...` 适合查看与维护；真正执行 `run_chain.py`、`run_test.py`、`record.sh` 时，应以 Claude 项目中的 `.claude/skills/api-testing/scripts/...` 运行时路径为准。

---

## 快速开始

在 Claude Code 对话框中输入以下命令之一：

```bash
# 最简调用：自动推断 API 地址，扫描项目代码生成用例
/api-testing http://localhost:8080 --generate-all

# 指定 Knife4j 服务（推荐，服务运行时）
/api-testing http://localhost:8080 --knife4j-url http://localhost:8080 --generate-all

# 有认证 token 时（内部业务系统必须加 --force-auth）
/api-testing http://localhost:8080 --knife4j-url http://localhost:8080 \
  --knife4j-token "Bearer eyJ..." --force-auth --generate-all

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
        bash skills/api-testing/scripts/record.sh init

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

### 合规约束（不可违反）

> 违反任意一条，测试结果无效。

**① 所有用例必须执行**
原则上发现多少用例执行多少。`run_test.py` 已移除显式 `--skip` 路径；若依赖链执行中因前置失败出现技术性 `SKIP`，报告仍会将其标记为违规并提示修复。若接口不可达，`actual_status=0`，断言强制 FAIL，如实记录。

**② 不允许 UNTESTED**
注册的端点必须全部被 `cover`，否则报告标红为违规并向 stderr 输出 `[ERROR]`。  
若某端点由环境限制确实无法访问，**不注册该端点**，在对话中说明原因。

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
# 服务运行中，直接从 Knife4j 实时拉取所有分组
/api-testing http://localhost:8080 \
  --knife4j-url http://localhost:8080 \
  --generate-all

# 带认证的 Knife4j
/api-testing http://localhost:8080 \
  --knife4j-url http://localhost:8080 \
  --knife4j-token "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  --generate-all
```

### 场景二：离线 Swagger / OpenAPI 文件

```bash
# Swagger2 JSON
/api-testing http://localhost:8080 \
  --api-doc docs/test/test-data/swagger.json \
  --generate-all

# OpenAPI3 YAML
/api-testing http://localhost:8080 \
  --api-doc docs/test/test-data/openapi.yaml \
  --generate-all
```

### 场景三：大型项目（500+ 用例）

```bash
# 升级到 sonnet 模型，延长超时至 600 秒
/api-testing http://localhost:8080 \
  --knife4j-url http://localhost:8080 \
  --generate-all \
  --model sonnet \
  --suite-timeout 600
```

### 场景四：CI/CD 集成

```yaml
- name: Run Integration Tests
  run: |
    claude code --print \
      "/api-testing ${{ env.API_URL }} \
       --knife4j-url ${{ env.API_URL }} \
       --generate-all \
       --suite-timeout 300"

- name: Check Results
  run: |
    FAILED=$(jq .summary.failed docs/test/test-reports/*/results.json | tail -1)
    if [ "$FAILED" -gt "0" ]; then
      echo "❌ 存在 $FAILED 条 FAIL 用例"
      cat docs/test/test-reports/*/BugList.md
      exit 1
    fi
```

### 场景五：复用已有用例文件

```bash
# 跳过发现阶段，直接执行上次生成的用例
/api-testing http://localhost:8080 \
  --cases docs/test/test-cases/20260322_141808-cases.json
```

### 场景六：Markdown API 文档

```bash
/api-testing http://localhost:8080 \
  --api-doc docs/api.md \
  --generate-all
```

Markdown 文档中的接口格式（技能可自动识别）：

````markdown
## `GET /users/1`
获取单个用户，响应 200

## `POST /posts`
创建文章，请求体：
```json
{"title": "foo", "body": "bar", "userId": 1}
```
响应 201
````

---

## 常见问题

### Q1：到底应该使用仓库路径还是 `.claude` 路径？

检查 `agents/integration-testing.md` 的 YAML frontmatter 是否完整，必须同时有开头和结尾的 `---`：

### Q2：`--knife4j-token` 传 `Bearer xxx` 还是裸 token？

命令参数既可传裸 token，也可传 `Bearer xxx`；`run_test.py` 会兼容这两种格式。若需要在 `discover_cases.py` 和 `run_chain.py` 间复用同一个变量，推荐统一保存为裸 token，再在请求 Knife4j 文档时按需补 `Bearer ` 前缀。

### Q3：为什么报告里出现 `SKIP` 也算问题？

因为 `SKIP` 代表计划内链路未完整执行。技术上允许出现，但治理上仍应修复其上游依赖或测试数据。

### Q4：`integration-testing agent not found` 怎么办？

---

**Q: 大量用例 FAIL，原因是"图书/订单不存在"（404）**

执行顺序问题。正确做法：

```
1. 先执行 POST 创建资源（建立测试数据）
2. 再执行 GET / PUT 操作已有资源
3. 最后执行 DELETE（避免影响后续用例）
```

Agent 会自动捕获 POST 201 响应中的 `id` 并注入后续用例，需确保 POST happy_path 用例排在前面。

---

**Q: 大量用例返回 401，实际状态 got=401**

两种原因：
- **`--force-auth` 未传**：Swagger 文档未声明 security scheme，接口被标为 `requires_auth=false`，步骤3不携带 token → 加上 `--force-auth`
- **token 已过期**：重新登录获取新 token 后传入 `--knife4j-token`

正确调用方式：
```bash
/api-testing http://... --knife4j-url http://... \
  --knife4j-token "Bearer eyJ..." \
  --force-auth \
  --generate-all
```

---

**Q: `boundary POST` 期望 400，实际返回 200 或 201**

两种情况：

- **服务端校验缺失（真实 Bug）**：服务未对空字段/零值做校验，该 FAIL 是有效测试发现
- **用例预期不合理**：该接口本身允许空字段，可在自定义用例文件中调整 `expected_status`

---

**Q: 所有用例 FAIL，`actual_status=0`**

服务不可达。检查：

```bash
# 确认服务已启动
curl -v http://localhost:8080/health

# 检查端口占用
lsof -i :8080
```

---

**Q: 套件提前停止，提示"超时中断"**

增大 `--suite-timeout` 参数，或分批测试：

```bash
# 延长到 10 分钟
/api-testing http://localhost:8080 --generate-all --suite-timeout 600
```

---

**Q: 如何只测试部分接口**

优先检查：

```bash
/api-testing http://localhost:8080 \
  --cases docs/test/test-data/my-cases.json
```

---

## 版本历史

### v0.9.0（当前）

**v0.9.0 新增（本轮）**
- `run_chain.py`：带依赖链的测试用例执行器，支持 CREATE→READ→UPDATE→DELETE 全链路
- 用例格式新增 `depends_on`（前置依赖）、`capture`（响应ID捕获）、`path_template`（动态路径）
- 依赖失败时允许技术性 SKIP（附原因），但报告中仍按违规提示，避免静默遗漏
- 修复 `Bearer Bearer xxx` 双重前缀问题（步骤1加 `${RAW_TOKEN#Bearer }` 去前缀）
- 修复 `SUITE_DEADLINE` 在 heredoc 中展开异常导致 1 条即超时
- 修复重跑复用旧 TIMESTAMP 导致报告统计虚高



**新增**
- 路径参数自动填充：`{id}` → `1`，消除字面量路径 404
- JSONPath 过滤断言：`[?(@.field==value)]` 等操作符
- 套件超时控制：`--suite-deadline`（Unix 时间戳），超时退出码 `2`
- `--request-timeout` 参数：可配置单请求超时秒数
- `--force-auth` 参数：强制所有业务接口标记为 `requires_auth=true`，解决 Swagger 未声明 security scheme 时 token 不传的问题
- Controller 扫描降级时输出明确警告，引导用户提供文档
- 执行顺序与测试数据约定章节（POST→GET→PUT→DELETE 原则）

**优化**
- `boundary` 预期状态码：POST/PUT/PATCH 含 body 约束时改为 `400`（此前为宽松 `200`）
- `error` 用例 `missing_required` body 固定为 `{}`（此前可能错误传入有效 body）
- GET/DELETE 用例 body 强制为 `null`（此前可能受其他端点 body 示例污染）
- Agent 模型升级至 `claude-sonnet-4-6`
- `record.sh` `trace` 子命令标注废弃（留痕已由 `run_test.py` 内部处理）
- `_build_body`：顶层 `array` schema 和 `additionalProperties` schema 现在生成正确的请求体，而非将 schema 定义本身当 body 传
- `_sample_value`：新增 `format` 感知（phone/email/date/date-time/uri/uuid），生成符合格式规范的样本值
- `_build_body` 属性迭代：数组字段按 `items.type` 推断元素类型，不再硬编码 `["item1","item2"]`
- `_extract_response_asserts`：识别统一响应体 void 型（data=null 的操作接口），自动改为断言 `.code exists`，避免 `.data exists` 误判

**修复**
- `discover_cases.py` 第 361 行 `expected_status` 未定义（`NameError`），导致 Swagger2/OpenAPI3 JSON 文档解析崩溃（B5）
- `generate_three_cases` 中 `resolve()` 对非 schema 文档的 `boundary`/`error` 场景返回错误 body（B6）
- `is_schema` 判断扩展至顶层 array/additionalProperties，使其正确走 `_build_body` 路径而非兜底

### v0.8.x

基础版本：Knife4j 多分组支持、三类用例生成、留痕合规约束（no_mock / 禁止 SKIP / 禁止 UNTESTED）、交互式 HTML 报告。

---

## 目录结构参考

```
docs/test/
├── test-cases/
│   └── {TIMESTAMP}-cases.json       # 用例文件（可复用于下次执行）
└── test-reports/
    └── {TIMESTAMP}/
        ├── report.md                # Markdown 汇总报告
        ├── report.html              # 交互式 HTML 报告（推荐）
        ├── BugList.md               # Bug 清单（含完整出入参和 curl 命令）
        ├── audit-summary.md         # 留痕摘要与佐证文件索引
        ├── results.json             # 结构化结果（CI/CD 对接）
        └── evidence/
            ├── http-trace/          # 每条用例完整 HTTP Trace JSON
            ├── assertions/
            │   └── assertions-detail.json   # 断言明细累积文件
            └── coverage/
                └── api-coverage.json        # 接口覆盖矩阵
```

---

- 统一命令入口为 `/api-testing`，保留 `/integration-test` 作为历史兼容别名。
- 增补 `run_chain.py` 依赖链执行说明。
- 明确源码路径与 `.claude` 运行时路径映射。
- 修正文档安装示例，使其适配 `/home/claude/gbhu/AIMedAssistant_0322/AIMedAssistant` 这类 Claude 项目目录。
