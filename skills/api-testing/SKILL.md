---
name: api-testing
description: |
  API 集成测试技能。对 RESTful 服务执行完整集成测试，生成含留痕佐证的
  Markdown + HTML 报告。支持 Knife4j、Swagger2、OpenAPI3、Markdown 文档。
  当用户提到"接口测试"、"集成测试"、"API测试"、"运行测试"时自动触发。
  可通过 /api-testing 直接调用（兼容旧别名 /integration-test）。
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
invocation: auto
version: "0.9.0"
---

# Test Skills — 参考文档索引

集成测试技能内部参考文档，供 agent 按需按场景加载。源码仓库中使用 `skills/api-testing/...`；安装到 Claude 项目后，对应运行时路径为 `.claude/skills/api-testing/...`。

## 参考文档路由

| 场景 | 文件路径 |
|------|----------|
| 集成测试执行流程 | `skills/api-testing/references/integration-testing.md` |
| 留痕字段语义规范 | `skills/api-testing/references/audit-trail.md` |
| 用例自动生成规范 | `skills/api-testing/references/case-generation.md` |

## 脚本路由

| 功能 | 脚本 |
|------|------|
| 用例发现/生成 | `skills/api-testing/scripts/discover_cases.py` |
| 用例执行+留痕 | `skills/api-testing/scripts/run_test.py` |
| 报告生成 | `skills/api-testing/scripts/gen_reports.py` |
| 留痕编排 | `skills/api-testing/scripts/record.sh` |

## 使用说明

执行测试前，agent 应先读取 `references/integration-testing.md`（如需了解多语言框架示例）
和 `references/case-generation.md`（如需了解用例设计规范）。
所有留痕字段语义参见 `references/audit-trail.md`。

