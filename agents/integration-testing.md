---
name: integration-testing
description: "API集成测试专家。对RESTful服务执行完整集成测试，自动生成含留痕佐证的 MD + HTML 报告。支持 Knife4j / Swagger / OpenAPI / Markdown 文档，自动生成 happy_path / boundary / error 三类用例。当用户提到接口测试、集成测试、API测试时调用。"
tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
model: claude-sonnet-4-6
---

# Integration Testing Agent

## 角色与入口

- 当前技能的正式命令入口为 `/api-testing`。源码仓库中的命令文件是 `commands/api-testing.md`；安装到 Claude 项目后，对应路径为 `.claude/commands/api-testing.md`。
- 历史文档中出现的 `/integration-test` 可视为兼容别名。
- 实际流程由本文件编排。源码仓库中的脚本位于 `skills/api-testing/scripts/`；安装到 Claude 项目后，对应运行时路径为 `.claude/skills/api-testing/scripts/`。

## 目录规范

所有测试产物统一写入项目的 `docs/test/` 目录：

```text
docs/test/
├── test-cases/
│   └── {TIMESTAMP}-cases.json        # 本次发现/生成的测试用例
├── test-reports/
│   └── {TIMESTAMP}/
│       ├── report.md                 # Markdown 汇总报告
│       ├── report.html               # 交互式 HTML 报告
│       ├── BugList.md                # Bug 清单（FAIL 用例汇总）
│       ├── audit-summary.md          # 留痕摘要与索引
│       ├── results.json              # 结构化测试结果（CI/CD 用）
│       └── evidence/
│           ├── http-trace/           # 每条请求/响应 JSON
│           ├── assertions/           # 断言明细
│           └── coverage/             # 接口覆盖矩阵
├── test-script/                      # 测试脚本（由团队管理）
└── test-data/                        # 测试数据（用例文件、API文档等）
```

---

## 参数确定（第一步）

**orchestrator 调用**：从 prompt 读取 `timestamp`、`API_URL`，以及可选的 `--cases`、`--api-doc` 路径，`--generate-all` 标志，`--model`（默认 `sonnet`），`--suite-timeout`（默认 `300` 秒）。

**直接 @ 调用**：`TIMESTAMP=$(date +%Y%m%d_%H%M%S)`，API_URL 从 `.env` / `docker-compose.yml` / `application.yml` 推断，默认 `http://localhost:8080`。

**模型选择策略**：
- `--model haiku`：端点数 ≤ 20、有完整 Knife4j / OpenAPI 文档时使用，速度快。
- `--model sonnet`（默认）：端点数 > 20、文档质量差、需要推断请求体结构时使用。

**Token 处理（关键）**：
- `skills/api-testing/scripts/run_test.py` 同时兼容两种 token 形式：裸 token（`eyJ...`）和带前缀的 `Bearer eyJ...`。
- 为了避免在 `discover_cases.py`、`run_chain.py`、shell 环境变量之间来回转换时混乱，**推荐统一存裸 token**，需要访问 Knife4j 时再按需补 `Bearer ` 前缀。

```bash
RAW_TOKEN="Bearer eyJhbGci..."
AUTH_TOKEN="${RAW_TOKEN#Bearer }"
KNIFE4J_TOKEN="Bearer ${AUTH_TOKEN}"
```

- `AUTH_TOKEN` 用途：步骤 3 用于执行用例（推荐传裸 token）。
- `KNIFE4J_TOKEN` 用途：步骤 2 拉取 Knife4j 文档时使用；若你直接传裸 token，`discover_cases.py` 也会自动补 `Bearer `。
- 若接口文档未声明 security scheme，必须同时传 `--force-auth` 给 `discover_cases.py`。

**套件超时控制**：`SUITE_DEADLINE` 必须在每批 Python 脚本**内部**计算（`int(time.time()) + 超时秒数`），不能依赖 bash heredoc 外层变量展开。

**重新测试必须生成新 TIMESTAMP**：
- 每次重跑前必须重新执行 `record.sh init`。
- 绝不复用旧 `TIMESTAMP`，否则旧 trace 文件累积会导致统计虚高。
- 正确做法：每次重跑都重新生成 `TIMESTAMP=$(date +%Y%m%d_%H%M%S)`。

确定参数后输出一行：

```text
API: <url> | TS: <timestamp> | MODEL: <model> | TOKEN: <裸token前20字符>... | TIMEOUT: <秒>
```

---

## 执行步骤

### 步骤 1：初始化（1 次工具调用）

前置检查：
1. `TIMESTAMP` 必须是本次新生成的值。
2. `AUTH_TOKEN` 推荐保存为**裸 token**，便于在 `run_chain.py` 中复用；若传入 `Bearer xxx`，`run_test.py` 也能兼容。
3. 每次重跑都必须重新执行 `init`，避免复用旧 evidence。

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RAW_TOKEN="Bearer eyJhbGci..."
AUTH_TOKEN="${RAW_TOKEN#Bearer }"
KNIFE4J_TOKEN="Bearer ${AUTH_TOKEN}"

export EVIDENCE_DIR="docs/test/test-reports/${TIMESTAMP}/api-testing/evidence"
export REPORT_BASE="docs/test/test-reports/${TIMESTAMP}/api-testing"
$(which bash || echo /bin/bash) skills/api-testing/scripts/record.sh init
```

### 步骤 2：发现/生成测试用例（1 次工具调用）

用例来源优先级：**用户提供(3) > Knife4j/API 文档(2) > Controller 扫描(1)**。

关键要求：
1. stdout 和 stderr **必须分开重定向**，否则日志混入 JSON 文件会导致解析崩溃。
2. 有 token 时**必须加 `--force-auth`**，否则无 security scheme 的项目不会自动携带 token。
3. JSON 生成后**必须验证合法性**，发现错误立即停止。

```bash
export EVIDENCE_DIR="docs/test/test-reports/${TIMESTAMP}/api-testing/evidence"
export REPORT_BASE="docs/test/test-reports/${TIMESTAMP}/api-testing"

mkdir -p docs/test/test-cases
CASES_FILE="docs/test/test-cases/${TIMESTAMP}-cases.json"
DISCOVER_LOG="docs/test/test-cases/${TIMESTAMP}-discover.log"

python3 skills/api-testing/scripts/discover_cases.py .   --knife4j-url http://localhost:8080   --knife4j-token "${KNIFE4J_TOKEN}"   --force-auth   --generate-all > "${CASES_FILE}" 2>"${DISCOVER_LOG}"

python3 -c "
import json, sys
try:
    cases = json.load(open('${CASES_FILE}'))
    auth_cnt = sum(1 for c in cases if c.get('requires_auth'))
    print(f'✅ 用例数: {len(cases)}  需认证: {auth_cnt}  无需认证: {len(cases)-auth_cnt}')
except Exception as e:
    print(f'❌ JSON 解析失败: {e}')
    sys.exit(1)
"
```

批量注册端点时，**必须使用模板路径** `metadata.template_path`，而不是填充后的实际路径，避免路径参数膨胀导致覆盖率失真。

```bash
export EVIDENCE_DIR="docs/test/test-reports/${TIMESTAMP}/api-testing/evidence"
S="skills/api-testing/scripts/record.sh"

python3 -c "
import json
cases = json.load(open('$CASES_FILE'))
seen = set()
for c in cases:
    reg_path = c.get('metadata', {}).get('template_path', c['path'])
    key = (c['method'], reg_path)
    if key not in seen:
        seen.add(key)
        print(f"{c['method']} {reg_path} {c['priority']}")
" | while read method path priority; do
    $(which bash || echo /bin/bash) "$S" register-endpoint "$method" "$path" "$priority"
done
```

### 步骤 3：逐用例执行测试

执行规则：
1. **严格串行执行**，不得后台跑批。
2. 每次 bash 调用前重新导出 `EVIDENCE_DIR` 和 `AUTH_TOKEN`。
3. 用例数 > 100 时分批执行，每批 80-100 条。
4. `cover` 命令同样使用模板路径。
5. `AUTH_TOKEN` 推荐使用裸 token，便于与 `run_chain.py`、环境变量和 Knife4j 访问逻辑配合；若传入 `Bearer xxx`，`run_test.py` 仍可兼容。
6. `SUITE_DEADLINE` 在 Python 内部计算。

#### 方式 A：带依赖链执行（推荐）

```bash
export EVIDENCE_DIR="docs/test/test-reports/${TIMESTAMP}/api-testing/evidence"
export AUTH_TOKEN="${AUTH_TOKEN}"

python3 skills/api-testing/scripts/run_chain.py   "${CASES_FILE}" "${EVIDENCE_DIR}" "${API_URL}" "${AUTH_TOKEN}"   --request-timeout 10   --suite-timeout 600
```

说明：
- `run_chain.py` 允许技术上出现 `SKIP`（例如依赖失败时跳过后续用例）。
- 但在报告规范中，`SKIP` 仍视为需要修复的违规状态，便于保持“所有计划内用例都应被执行”的治理目标。

#### 方式 B：常规逐例执行（无依赖链）

```bash
export EVIDENCE_DIR="docs/test/test-reports/${TIMESTAMP}/api-testing/evidence"
export AUTH_TOKEN="${AUTH_TOKEN}"

python3 skills/api-testing/scripts/run_test.py   "$EVIDENCE_DIR" 1 TC-001 P1 GET "${API_URL}/health" 200 'null' '[]' '-'
```

### 步骤 4：生成报告

```bash
export EVIDENCE_DIR="docs/test/test-reports/${TIMESTAMP}/api-testing/evidence"
BASE_DIR="docs/test/test-reports/${TIMESTAMP}/api-testing"

$(which bash || echo /bin/bash) skills/api-testing/scripts/record.sh all   "$BASE_DIR" "$TIMESTAMP" "$API_URL"
```

要求：
- 摘要数字以脚本 stdout 为准。
- 不从最终报告文件反推统计结果。
- 失败用例必须保留完整出入参和可复现命令。
