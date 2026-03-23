---
description: "对当前项目执行 API 集成测试并生成留痕报告（MD + HTML）。用法: /api-testing [API地址] [--knife4j-url URL] [--knife4j-token TOKEN] [--cases 用例文件] [--api-doc 文档文件] [--generate-all] [--force-auth] [--model sonnet|haiku] [--suite-timeout 秒]"
---

你是 orchestrator，直接执行集成测试（无需 delegate）。
完整流程和目录规范见源码文件 `agents/integration-testing.md`；安装到 Claude 项目后，对应路径为 `.claude/agents/integration-testing.md`。

> 兼容性说明：当前仓库的正式命令名为 `/api-testing`，如历史环境仍保留 `/integration-test`，可视为旧别名。

**参数解析**：
- `TIMESTAMP=$(date +%Y%m%d_%H%M%S)`
- `API_URL`：取命令第一个非 `--` 参数，或自动推断
- `--knife4j-url <url>`：直接从 Knife4j 服务拉取文档（自动发现多分组，优先于 `--api-doc`）
- `--knife4j-token <token>`：Knife4j 认证 Token（Bearer 或 Basic，可选）
  - **必须同时存入 `AUTH_TOKEN` 变量**，步骤 3 执行用例时使用
  - **必须自动追加 `--force-auth`**，确保业务接口标记为 `requires_auth=true`
- `--cases <file>`：用例文件（优先级最高，默认在 `docs/test/test-data/` 下查找）
- `--api-doc <file>`：本地 API 文档（Knife4j 导出 JSON / OpenAPI3 / Swagger2 / Markdown）
- `--generate-all`：从文档自动生成三类用例（`happy_path` / `boundary` / `error`）
- `--force-auth`：强制所有业务接口标记为 `requires_auth=true`（文档无 security scheme 时必传）
- `--model <sonnet|haiku>`：指定执行模型，默认 `sonnet`（复杂项目建议 `sonnet`）
- `--suite-timeout <秒>`：整套测试超时上限（默认 `300` 秒），超时后停止剩余用例并生成报告

所有产物写入 `docs/test/` 目录规范，摘要数字从步骤 4 的 stdout 读取，**全程不得读取报告文件内容**。
