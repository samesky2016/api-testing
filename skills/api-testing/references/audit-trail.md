# 留痕规范（字段语义参考）

> 此文档仅供 Agent 在需要理解字段含义时按需查阅。
> **留痕文件的实际写入由 `record.sh` 脚本处理**，无需手动构造 JSON。

---

## 文件职责速查

| 文件 | 由 record.sh 哪个命令写入 | 说明 |
|------|--------------------------|------|
| `evidence/http-trace/{seq}_{METHOD}_{slug}_{PASS\|FAIL}.json` | `trace` | 单个请求的完整请求+响应 |
| `evidence/assertions/assertions-detail.json` | `assert` | 所有断言逐条累积 |
| `evidence/coverage/api-coverage.json` | `register-endpoint` + `cover` | 端点发现与覆盖矩阵 |
| `audit-summary.md` | `summary` | 可观测索引，自动生成 |

---

## 断言类型（type 字段枚举）

| type | 用途 |
|------|------|
| `status_code` | HTTP 状态码 |
| `json_field` | 响应体字段值匹配 |
| `json_field_exists` | 字段存在性 |
| `response_time` | 响应耗时（ms），超 2000 为 FAIL |
| `header_value` | 响应头值 |
| `body_contains` | 响应体包含字符串 |

---

## 敏感信息脱敏规则

| 字段 | 处理 |
|------|------|
| Authorization token | 保留前 10 字符 + `***` |
| password / secret / key | 替换为 `[REDACTED]` |
| Cookie value | 替换为 `[REDACTED]` |

---

## 优先级定义

| 优先级 | 含义 |
|--------|------|
| P0 | 认证接口、核心 CRUD，必须 100% 覆盖 |
| P1 | 数据校验、权限控制 |
| P2 | 边界条件、错误码，按时间覆盖 |
