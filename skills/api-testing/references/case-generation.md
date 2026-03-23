# 用例自动生成规范

> 本文档供 agent 在生成测试用例时参考。
> discover_cases.py 已内置三类用例生成逻辑，agent 按优先级调用即可。

---

## 三类用例生成策略

对每个 API 端点，`discover_cases.py` 在 `--generate-all` 模式下自动生成：

### 1. happy_path（正常场景）
- 所有必填字段填入有效数据
- 字符串 → `"test_value"`，整数 → `100`，布尔 → `true`，数组 → `["item1","item2"]`
- 预期：2xx 状态码，响应结构正确
- 优先级：继承端点优先级（P0/P1）

### 2. boundary（边界值）
- 字符串：空字符串 `""`
- 整数：`0` / `-1`
- 数组：空数组 `[]`
- 对象：空对象 `{}`
- 预期：接口应优雅处理或返回明确错误（200 或 400 均可接受）
- 优先级：P2

### 3. error（错误场景）—— 仅 POST / PUT / PATCH
- `missing_required`：缺失所有必填字段，body 为空 `{}`，预期 400
- `invalid_type`：数字字段传字符串 `"not_a_number"`，其余字段传 `null`，预期 400
- 优先级：P2

---

## 测试数据速查表

| 字段类型 | 有效值 | 边界值 | 无效值 |
|---------|--------|--------|--------|
| string  | `"test_value"` | `""` / 1000字符 | `null` / 数字 |
| integer | `100` | `0` / `-1` | `"not_a_number"` |
| boolean | `true` | — | `null` / `"true"` |
| array   | `["a","b"]` | `[]` | `null` |
| object  | 完整结构体 | `{}` | `null` |

---

## 调用方式

```bash
# 从 API 文档生成全部三类用例
python3 .claude/skills/api-testing/scripts/discover_cases.py . \
  --api-doc docs/test/test-data/<文档> \
  --generate-all > "$CASES_FILE"

# 仅生成正常场景（默认行为）
python3 .claude/skills/api-testing/scripts/discover_cases.py . \
  --api-doc docs/test/test-data/<文档> > "$CASES_FILE"
```

---

## 输出用例格式示例

```json
[
  {
    "seq": 1, "tc_id": "TC-001",
    "name": "POST /api/users - 正常场景",
    "priority": "P1", "category": "happy_path",
    "method": "POST", "path": "/api/users",
    "expected_status": 201,
    "body": {"email": "test@example.com", "name": "Test User"},
    "asserts": [{"path": ".id", "type": "exists"}],
    "requires_auth": false, "source": "apidoc"
  },
  {
    "seq": 2, "tc_id": "TC-002",
    "name": "POST /api/users - 边界值",
    "priority": "P2", "category": "boundary",
    "method": "POST", "path": "/api/users",
    "expected_status": 200,
    "body": {"email": "", "name": ""},
    "asserts": [], "requires_auth": false, "source": "apidoc"
  },
  {
    "seq": 3, "tc_id": "TC-003",
    "name": "POST /api/users - 缺失必填字段",
    "priority": "P2", "category": "error",
    "method": "POST", "path": "/api/users",
    "expected_status": 400,
    "body": {}, "asserts": [], "requires_auth": false, "source": "apidoc"
  }
]
```

---

## Knife4j 专项支持

### 支持的接入方式

| 方式 | 参数 | 适用场景 |
|------|------|----------|
| HTTP 实时拉取 | `--knife4j-url http://host:port` | 服务运行中，推荐首选 |
| 导出文件解析 | `--api-doc <knife4j-export>.json` | 离线/CI 环境 |
| 标准 Swagger2 YAML/JSON | `--api-doc swagger.yaml` | 通用 |
| 标准 OpenAPI3 JSON/YAML | `--api-doc openapi.json` | 通用 |

### Knife4j 扩展字段处理

| 扩展字段 | 作用 | 写入位置 |
|---------|------|---------|
| `x-knife4j-info.ignore` | 跳过该接口 | 自动过滤，不生成用例 |
| `x-knife4j-info.author` | 接口作者 | `metadata.author` |
| `x-order` | 接口排序 | `metadata.x_order` |
| `x-author` | 接口作者（旧版） | `metadata.author` |

### 多分组（微服务聚合）

Knife4j 聚合网关场景下，`/swagger-resources` 返回多个分组，`--knife4j-url` 会**自动遍历所有分组**并合并用例，每条用例的 `metadata.group` 标识所属分组。

### basePath / servers 路径前缀

- Swagger2 的 `basePath`（如 `/api/v1`）自动拼接到端点路径
- OpenAPI3 的 `servers[0].url` 路径部分自动提取并拼接
