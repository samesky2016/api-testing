#!/usr/bin/env python3
"""
discover_cases.py — 测试用例发现器

优先级：用户提供 > API文档（含Knife4j） > Controller扫描

用法:
  python3 discover_cases.py <project_root> [选项]

选项:
  --cases        <file>   用户提供的用例文件（JSON/YAML），优先级最高
  --api-doc      <file>   本地 API 文档（Markdown / Swagger2 JSON|YAML / OpenAPI3 JSON|YAML / Knife4j导出JSON）
  --knife4j-url  <url>    Knife4j 服务地址（如 http://localhost:8080），自动拉取所有分组文档
  --knife4j-token <token> Knife4j Basic认证或Bearer Token（可选）
  --generate-all          自动生成三类用例（happy_path / boundary / error）

输出: JSON 数组写到 stdout；进度/来源信息写到 stderr
"""

import json, os, re, sys, glob
from pathlib import Path

def eprint(*a): print(*a, file=sys.stderr)

def make_tc(seq, name, priority, method, path, expected_status,
            body=None, asserts=None, requires_auth=False, source='scan',
            category='happy_path', metadata=None, design_note=None,
            skip_reason=None):
    """
    构造单条测试用例。
    design_note : str  — 用例设计说明（等价类划分、边界值依据等）
    skip_reason : str  — 非空时标记该用例应跳过，并说明原因
    """
    tc = {
        'seq': seq, 'tc_id': f'TC-{seq:03d}', 'name': name,
        'priority': priority, 'category': category,
        'method': method, 'path': path,
        'expected_status': expected_status,
        'body': body, 'asserts': asserts or [],
        'requires_auth': requires_auth, 'source': source
    }
    if metadata:
        tc['metadata'] = metadata
    if design_note:
        tc['design_note'] = design_note
    if skip_reason:
        tc['skip_reason'] = skip_reason
    return tc

# ══════════════════════════════════════════════════════════════
# 等价类 & 边界值数据生成（注意事项④）
# ══════════════════════════════════════════════════════════════
#
# 等价类划分原则：
#   有效等价类（valid）  — 满足所有约束的典型值，预期接口正常处理
#   无效等价类（invalid）— 违反类型/格式约束，预期接口返回 4xx
#
# 边界值分析原则（基于 BVA 三点法）：
#   数字：min-1（下界-1） / min / min+1 / 典型中间值 / max-1 / max / max+1
#   字符串：空串（长度0边界） / 长度1 / 长度max / 长度max+1（超限）
#   数组：空数组（0元素边界） / 1元素 / 典型多元素
#   布尔：true / false（完整等价类覆盖）
#
# 每个字段类型对应的场景值表：
#   scenario: valid / boundary_min / boundary_max / invalid_type / missing / overflow

_TYPE_VALUES = {
    # (type_key): {scenario: value}
    'integer': {
        'valid':         100,
        'boundary_min':  0,          # 最小有效边界（通常为 0 或 1）
        'boundary_neg':  -1,         # 下界-1，常见无效值
        'boundary_max':  2147483647, # int32 上界
        'overflow':      2147483648, # int32 上界+1
        'invalid_type':  'not_a_number',
    },
    'number': {
        'valid':         3.14,
        'boundary_min':  0.0,
        'boundary_neg':  -0.01,
        'invalid_type':  'not_a_number',
    },
    'string': {
        'valid':         'test_value',
        'boundary_min':  '',          # 长度0边界
        'boundary_len1': 'a',         # 长度1边界
        'overflow':      'x' * 256,   # 超长字符串（常见限制边界）
        'special':       '!@#$%^&*()',  # 特殊字符等价类
        'invalid_type':  None,
    },
    'boolean': {
        'valid':         True,
        'valid_false':   False,        # 布尔另一个有效等价类
        'invalid_type':  'true',       # 字符串形式（无效等价类）
    },
    'array': {
        'valid':         ['item1', 'item2'],
        'boundary_min':  [],           # 空数组边界
        'boundary_one':  ['item1'],    # 单元素边界
        'invalid_type':  'not_an_array',
    },
    'object': {
        'valid':         {},
        'boundary_min':  {},
        'invalid_type':  'not_an_object',
    },
}

def _sample_value(field_type, scenario, fmt=None):
    """按场景取等价类/边界值样本，支持 format 感知"""
    ft = str(field_type).lower()

    # ── format 感知：优先按 format 生成符合格式规范的样本 ────────
    if fmt and scenario in ('valid',):
        fmt_lower = str(fmt).lower()
        if fmt_lower in ('phone', 'mobile'):
            return '13800138000'
        if fmt_lower == 'email':
            return 'test@example.com'
        if fmt_lower in ('date-time', 'datetime'):
            return '2024-01-01T00:00:00'
        if fmt_lower == 'date':
            return '2024-01-01'
        if fmt_lower in ('uri', 'url'):
            return 'http://example.com'
        if fmt_lower in ('uuid',):
            return '00000000-0000-0000-0000-000000000001'
        if fmt_lower in ('int64', 'int32'):
            return 1

    if ft in ('integer', 'int') or ('int' in ft and 'string' not in ft):
        t = _TYPE_VALUES['integer']
    elif ft in ('number', 'float', 'double'):
        t = _TYPE_VALUES['number']
    elif ft == 'boolean' or 'bool' in ft:
        t = _TYPE_VALUES['boolean']
    elif ft in ('array',) or 'list' in ft:
        t = _TYPE_VALUES['array']
    elif ft in ('object', 'dict') or 'object' in ft:
        t = _TYPE_VALUES['object']
    else:
        t = _TYPE_VALUES['string']

    # scenario 映射
    if scenario == 'valid':
        return t.get('valid', 'test_value')
    if scenario == 'boundary':
        return t.get('boundary_min', t.get('valid'))
    if scenario in ('invalid_type', 'invalid'):
        return t.get('invalid_type', None)
    return t.get(scenario, t.get('valid', 'test_value'))

def _build_body(schema, spec, scenario, depth=0):
    if depth > 4 or not isinstance(schema, dict):
        return None
    ref = schema.get('$ref', '')
    if ref:
        parts = ref.lstrip('#/').split('/')
        node = spec
        for p in parts:
            node = node.get(p, {}) if isinstance(node, dict) else {}
        return _build_body(node, spec, scenario, depth + 1)

    # allOf 合并
    if 'allOf' in schema:
        merged = {}
        for sub in schema['allOf']:
            sub_body = _build_body(sub, spec, scenario, depth + 1)
            if isinstance(sub_body, dict):
                merged.update(sub_body)
        return merged or None

    t = schema.get('type', 'object')

    # ── 顶层 array schema（POST body 直接是数组）─────────────
    # 不能把 {"type":"array","items":{...}} 当 object 传，必须生成实际数组
    if t == 'array':
        items_schema = schema.get('items', {})
        if scenario == 'boundary':
            return []
        if not items_schema:
            return [1, 2]
        item_val = _build_body(items_schema, spec, scenario, depth + 1)
        if item_val is None:
            item_val = _sample_value(items_schema.get('type', 'integer'), 'valid')
        return [item_val]

    # ── additionalProperties（Map<String,?> 类型）───────────
    # 不能把 schema 定义本身当 body 传，应生成示例 key-value
    if 'additionalProperties' in schema and 'properties' not in schema:
        val_schema = schema.get('additionalProperties', {})
        val_type   = val_schema.get('type', 'string') if isinstance(val_schema, dict) else 'string'
        return {'key': _sample_value(val_type, 'valid')}

    if 'example' in schema and scenario == 'valid':
        return schema['example']

    if t == 'object' or 'properties' in schema:
        props           = schema.get('properties', {})
        required_fields = schema.get('required', [])
        body = {}
        for k, v in list(props.items())[:10]:
            if scenario == 'missing_required':
                # 缺失必填字段等价类：只保留非必填字段
                if k not in required_fields:
                    body[k] = _sample_value(v.get('type', 'string'), 'valid', fmt=v.get('format'))
            elif scenario == 'invalid_type':
                # 无效类型等价类：每个字段传类型不匹配的值
                body[k] = _sample_value(v.get('type', 'string'), 'invalid_type', fmt=v.get('format'))
            else:
                # 数组字段：根据 items schema 推断元素类型
                if v.get('type') == 'array' and 'items' in v:
                    items = v['items']
                    if '$ref' in items:
                        # 引用类型数组：递归构造单个元素
                        item_val = _build_body(items, spec, scenario, depth + 1)
                        body[k] = [item_val] if item_val is not None else [1]
                    else:
                        item_type = items.get('type', 'integer')
                        item_val  = _sample_value(item_type, 'valid', fmt=items.get('format'))
                        body[k] = [] if scenario == 'boundary' else [item_val]
                else:
                    body[k] = _build_body(v, spec, scenario, depth + 1)
        return body or ({} if scenario == 'missing_required' else None)

    return _sample_value(t, scenario if scenario in ('valid', 'boundary') else 'invalid',
                         fmt=schema.get('format'))

def _design_note(category, method, schema_fields=None):
    """生成用例设计说明（等价类 / 边界值依据）"""
    notes = {
        'happy_path': (
            '有效等价类：所有必填字段取典型有效值，'
            '覆盖接口正常业务流程'
        ),
        'boundary': (
            '边界值分析（BVA）：'
            '字符串取空串(长度0边界)；'
            '数字取0(最小边界)；'
            '数组取[](空数组边界)；'
            '预期接口对边界输入的容错行为'
        ),
        'error': (
            '无效等价类：'
            + ('缺失必填字段（空body={}）预期400；' if 'missing' in (schema_fields or '') else '')
            + ('字段类型不匹配（数字传字符串等）预期400' if 'type' in (schema_fields or '') else
               '缺失必填字段或类型不匹配，预期400')
        ),
        'boundary_overflow': (
            '边界值分析：超出字段最大长度/最大值，预期接口拒绝或截断'
        ),
        'boundary_special': (
            '等价类扩展：特殊字符输入（!@#$等），验证接口转义/过滤行为'
        ),
    }
    base = notes.get(category, '用例设计说明待补充')
    if method in ('GET', 'DELETE') and category == 'boundary':
        base += '；GET/DELETE 边界值重点验证路径参数与查询参数的边界'
    return base

def generate_three_cases(seq_start, name_prefix, priority, method, path,
                          ok_status, body_schema, asserts, requires_auth,
                          source, spec=None, metadata=None):
    """
    为单个端点生成多类测试用例（注意事项④ 等价类 + 边界值覆盖）：
      happy_path         — 有效等价类，正常场景
      boundary           — 边界值（空/零/最小/最大）
      error/missing      — 无效等价类：缺失必填字段          （POST/PUT/PATCH）
      error/invalid_type — 无效等价类：类型不匹配            （POST/PUT/PATCH）
      boundary/overflow  — 边界值：字段超长/超上限           （POST/PUT/PATCH，有 schema 时）
      boundary/special   — 等价类扩展：特殊字符              （POST/PUT/PATCH，string 字段时）
    """
    cases, seq, spec = [], seq_start, spec or {}
    is_schema = isinstance(body_schema, dict) and (
        'properties' in body_schema or '$ref' in body_schema or 'allOf' in body_schema
        or body_schema.get('type') == 'array'          # 顶层数组 body
        or 'additionalProperties' in body_schema       # Map 类型 body
    )
    has_string_field = _has_type_in_schema(body_schema, spec, 'string') if body_schema else False
    has_int_field    = _has_type_in_schema(body_schema, spec, 'integer') if body_schema else False

    def resolve(scenario):
        """
        根据 scenario 构造请求体。
        is_schema=True  → 从 OpenAPI schema 生成字段值
        is_schema=False → 从示例 body dict 推断字段类型后生成
        scenario 分类：
          valid           — 有效值（happy_path）
          boundary        — 边界值（空串/零/空数组）
          missing_required— 缺失所有必填字段，返回空 {}
          invalid_type    — 类型不匹配（数字字段传字符串）
        """
        if body_schema is None:
            # 无任何 body 信息（GET/DELETE 等）
            if scenario in ('missing_required', 'invalid_type'):
                return {}
            return None
        if is_schema:
            return _build_body(body_schema, spec, scenario)
        if isinstance(body_schema, dict):
            # 文本文档解析到的示例 body，按字段类型降级
            if scenario == 'missing_required':
                # 缺失必填：发空 body
                return {}
            if scenario == 'invalid_type':
                # 类型不匹配：数字字段传字符串，字符串字段传数字
                result = {}
                for k, v in body_schema.items():
                    if isinstance(v, (int, float)):
                        result[k] = 'not_a_number'
                    elif isinstance(v, str):
                        result[k] = 12345
                    else:
                        result[k] = None
                return result
            if scenario == 'boundary':
                # 边界值：字符串→空串，数字→0，列表→[]，其他→None
                result = {}
                for k, v in body_schema.items():
                    if isinstance(v, str):   result[k] = ''
                    elif isinstance(v, bool):result[k] = False
                    elif isinstance(v, (int, float)): result[k] = 0
                    elif isinstance(v, list):result[k] = []
                    elif isinstance(v, dict):result[k] = {}
                    else: result[k] = None
                return result
            # valid / 其他 → 原始示例值
            return body_schema
        return body_schema

    # 判断是否为认证类接口（login/logout/auth/token 等）
    _auth_kw = {'login','logout','auth','token','register','signup','signin','password','credential'}
    is_auth_path = any(k in path.lower() for k in _auth_kw)

    # 判断 body 约束是否可知（is_schema 或有示例 body）
    has_body_constraint = is_schema or isinstance(body_schema, dict)

    # ── 1. 有效等价类：正常场景 ──────────────────────────────
    # GET/DELETE 无请求体（即使文本文档错误关联了 body 示例也忽略）
    happy_body = None if method in ('GET', 'DELETE', 'HEAD') else resolve('valid')
    cases.append(make_tc(
        seq, f'{name_prefix} - 正常场景', priority, method, path,
        ok_status, happy_body, asserts, requires_auth, source,
        'happy_path', metadata,
        design_note=_design_note('happy_path', method)
    ))
    seq += 1

    # ── 2. 边界值：空/零/最小边界 ────────────────────────────
    # 预期状态码策略：
    #   GET/DELETE 无请求体 → 200（路径/查询参数边界，服务应优雅处理）
    #   POST/PUT/PATCH auth路径（含 login/token 等）→ 401（空凭据=认证失败，语义正确）
    #   POST/PUT/PATCH 有 body 约束（schema 或示例 body）→ 400（空串/零违反字段约束）
    #   POST/PUT/PATCH 无 body 信息（仅 scan 来源）→ 200（无约束信息，宽松判断）
    if method in ('GET', 'DELETE', 'HEAD'):
        boundary_expected_status = 200
    elif method in ('POST', 'PUT', 'PATCH') and is_auth_path:
        boundary_expected_status = 401   # auth 接口空凭据 → 认证失败
    elif method in ('POST', 'PUT', 'PATCH') and has_body_constraint:
        boundary_expected_status = 400
    else:
        boundary_expected_status = 200
    # boundary body：GET/DELETE 无请求体
    boundary_body = None if method in ('GET', 'DELETE', 'HEAD') else resolve('boundary')
    cases.append(make_tc(
        seq, f'{name_prefix} - 边界值(空/零)', 'P2', method, path,
        boundary_expected_status, boundary_body, [],
        requires_auth, source,
        'boundary', metadata,
        design_note=_design_note('boundary', method)
    ))
    seq += 1

    if method in ('POST', 'PUT', 'PATCH'):
        # auth 路径的错误场景：缺失字段/类型错误 → 服务返回 401（凭据无效），不是 400
        error_expected_status = 401 if is_auth_path else 400

        # ── 3. 无效等价类：缺失必填字段 ─────────────────────
        cases.append(make_tc(
            seq, f'{name_prefix} - 缺失必填字段', 'P2', method, path,
            error_expected_status, resolve('missing_required') or {}, [], requires_auth, source,
            'error', metadata,
            design_note=_design_note('error', method, 'missing')
        ))
        seq += 1

        # ── 4. 无效等价类：类型不匹配 ────────────────────────
        cases.append(make_tc(
            seq, f'{name_prefix} - 无效数据类型', 'P2', method, path,
            error_expected_status, resolve('invalid_type') or {}, [], requires_auth, source,
            'error', metadata,
            design_note=_design_note('error', method, 'type')
        ))
        seq += 1

        # ── 5. 边界值：超长/超上限（有 schema 且含数字字段时）
        if is_schema and has_int_field:
            overflow_body = _build_body_overflow(body_schema, spec)
            if overflow_body:
                cases.append(make_tc(
                    seq, f'{name_prefix} - 边界值(超上限)', 'P2', method, path,
                    400, overflow_body, [], requires_auth, source,
                    'boundary', metadata,
                    design_note=_design_note('boundary_overflow', method)
                ))
                seq += 1

        # ── 6. 等价类扩展：特殊字符（含字符串字段时）────────
        if is_schema and has_string_field:
            special_body = _build_body_special(body_schema, spec)
            if special_body:
                # 特殊字符是合法字符串内容，接口应正常接受
                # 使用与 happy_path 相同的期望状态码
                cases.append(make_tc(
                    seq, f'{name_prefix} - 特殊字符输入', 'P2', method, path,
                    ok_status, special_body, [], requires_auth, source,
                    'boundary', metadata,
                    design_note=_design_note('boundary_special', method)
                ))
                seq += 1

    return cases, seq

def _has_type_in_schema(schema, spec, type_name, depth=0):
    """检查 schema 中是否存在指定类型的字段"""
    if depth > 3 or not isinstance(schema, dict):
        return False
    ref = schema.get('$ref', '')
    if ref:
        parts = ref.lstrip('#/').split('/')
        node  = spec
        for p in parts:
            node = node.get(p, {}) if isinstance(node, dict) else {}
        return _has_type_in_schema(node, spec, type_name, depth + 1)
    props = schema.get('properties', {})
    for v in props.values():
        if v.get('type', '') == type_name:
            return True
        if _has_type_in_schema(v, spec, type_name, depth + 1):
            return True
    return False

def _build_body_overflow(schema, spec, depth=0):
    """生成超上限边界值 body：数字字段取 int32 max+1，字符串取 256 字符"""
    if depth > 3 or not isinstance(schema, dict):
        return None
    ref = schema.get('$ref', '')
    if ref:
        parts = ref.lstrip('#/').split('/')
        node  = spec
        for p in parts:
            node = node.get(p, {}) if isinstance(node, dict) else {}
        return _build_body_overflow(node, spec, depth + 1)
    props = schema.get('properties', {})
    if not props:
        return None
    body = {}
    for k, v in list(props.items())[:10]:
        ft = v.get('type', 'string').lower()
        if ft in ('integer', 'int') or 'int' in ft:
            body[k] = _TYPE_VALUES['integer']['overflow']
        elif ft in ('number', 'float', 'double'):
            body[k] = _TYPE_VALUES['integer']['overflow']
        elif ft == 'string':
            body[k] = _TYPE_VALUES['string']['overflow']
        else:
            body[k] = _sample_value(ft, 'valid')
    return body or None

def _build_body_special(schema, spec, depth=0):
    """生成特殊字符等价类 body：字符串字段取特殊字符，其他字段取有效值"""
    if depth > 3 or not isinstance(schema, dict):
        return None
    ref = schema.get('$ref', '')
    if ref:
        parts = ref.lstrip('#/').split('/')
        node  = spec
        for p in parts:
            node = node.get(p, {}) if isinstance(node, dict) else {}
        return _build_body_special(node, spec, depth + 1)
    props = schema.get('properties', {})
    if not props:
        return None
    body = {}
    has_special = False
    for k, v in list(props.items())[:10]:
        ft = v.get('type', 'string').lower()
        if ft == 'string':
            body[k] = _TYPE_VALUES['string']['special']
            has_special = True
        else:
            body[k] = _sample_value(ft, 'valid')
    return body if has_special else None

# ══════════════════════════════════════════════════════════════
# 来源3：用户提供的用例文件
# ══════════════════════════════════════════════════════════════

def load_user_cases(path):
    text = open(path).read().strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            eprint(f'[discover] 来源=用户提供，用例数={len(data)}（{path}）')
            return _normalize_user_cases(data)
    except Exception:
        pass
    try:
        import yaml
        data = yaml.safe_load(text)
        if isinstance(data, list):
            eprint(f'[discover] 来源=用户提供(YAML)，用例数={len(data)}（{path}）')
            return _normalize_user_cases(data)
    except Exception:
        pass
    eprint(f'[discover] 警告：无法解析 {path}')
    return []

def _normalize_user_cases(raw):
    cases = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            continue
        method = (item.get('method') or 'GET').upper()
        path   = re.sub(r'https?://[^/]+', '', item.get('path') or item.get('url') or '/') or '/'
        cases.append(make_tc(
            i, item.get('name') or f'{method} {path}',
            item.get('priority', 'P0'), method, path,
            int(item.get('expected_status') or 200),
            item.get('body'), item.get('asserts') or [],
            bool(item.get('requires_auth')), 'user',
            item.get('category', 'happy_path'),
            item.get('metadata')
        ))
    return cases

# ══════════════════════════════════════════════════════════════
# Knife4j 专项支持
# ══════════════════════════════════════════════════════════════

def _http_get(url, headers=None, timeout=10):
    """简单 HTTP GET，优先用 urllib（零依赖）"""
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'HTTP {e.code} {url}')
    except Exception as e:
        raise RuntimeError(f'请求失败: {e}  URL={url}')

def _make_headers(token=None):
    h = {'Accept': 'application/json', 'User-Agent': 'api-testing/1.0'}
    if token:
        if token.startswith('Basic ') or token.startswith('Bearer '):
            h['Authorization'] = token
        else:
            h['Authorization'] = f'Bearer {token}'
    return h

def fetch_knife4j_groups(base_url, token=None):
    """
    从 Knife4j 服务拉取所有分组资源。
    返回列表：[{'name': '分组名', 'url': '/v2/api-docs?group=xxx', 'swaggerVersion': '2.0'}, ...]
    """
    base_url = base_url.rstrip('/')
    headers  = _make_headers(token)

    # 优先尝试 /swagger-resources（多分组）
    for endpoint in ('/swagger-resources', '/v3/api-docs', '/v2/api-docs'):
        try:
            raw = _http_get(base_url + endpoint, headers)
            data = json.loads(raw)
        except Exception as e:
            eprint(f'[knife4j] {endpoint} 不可用: {e}')
            continue

        # /swagger-resources 返回分组列表
        if isinstance(data, list) and data and 'url' in data[0]:
            eprint(f'[knife4j] 发现 {len(data)} 个文档分组（来自 /swagger-resources）')
            return [{'name': g.get('name', 'default'),
                     'url': g['url'],
                     'swaggerVersion': g.get('swaggerVersion', '2.0')} for g in data]

        # /v3/api-docs 或 /v2/api-docs 返回单个 spec
        if isinstance(data, dict) and 'paths' in data:
            eprint(f'[knife4j] 发现单分组文档（来自 {endpoint}）')
            ver = '3.0' if data.get('openapi', '').startswith('3') else '2.0'
            return [{'name': 'default', 'url': endpoint, 'swaggerVersion': ver, '_spec': data}]

    return []

def load_knife4j_cases(base_url, token=None, generate_all=False, force_auth=False):
    """
    从运行中的 Knife4j 服务拉取文档并生成用例。
    支持多分组（微服务聚合场景）。
    """
    base_url = base_url.rstrip('/')
    headers  = _make_headers(token)
    groups   = fetch_knife4j_groups(base_url, token)

    if not groups:
        eprint('[knife4j] 未找到任何文档分组，请检查服务是否启动或 URL 是否正确')
        return []

    all_cases, seq = [], 1

    for grp in groups:
        grp_name = grp['name']

        # 如果已预取到 spec，直接用；否则 HTTP 拉取
        if '_spec' in grp:
            spec = grp['_spec']
        else:
            grp_url = grp['url']
            full_url = base_url + grp_url if grp_url.startswith('/') else grp_url
            try:
                raw  = _http_get(full_url, headers)
                spec = json.loads(raw)
            except Exception as e:
                eprint(f'[knife4j] 拉取分组 [{grp_name}] 失败: {e}')
                continue

        eprint(f'[knife4j] 解析分组: {grp_name}  路径数={len(spec.get("paths", {}))}')
        cases, seq = _parse_knife4j_spec(spec, grp_name, seq, generate_all, force_auth=force_auth)
        all_cases.extend(cases)

    mode = '全量三类' if generate_all else '正常场景'
    eprint(f'[knife4j] 汇总: 分组={len(groups)} 用例={len(all_cases)} 模式={mode}')
    return all_cases

def _parse_knife4j_spec(spec, group_name, seq_start, generate_all, force_auth=False):
    """
    解析单个 Knife4j spec（Swagger2 或 OpenAPI3 均兼容）。
    额外处理 Knife4j 扩展字段：x-knife4j-info / x-order / x-author / x-knife4j-tag。
    """
    cases = []
    seq   = seq_start

    # basePath（Swagger2 专有，OpenAPI3 用 servers）
    base_path = spec.get('basePath', '').rstrip('/')
    if base_path in ('/', ''):
        base_path = ''

    # servers（OpenAPI3）
    servers = spec.get('servers', [])
    server_prefix = ''
    if servers:
        from urllib.parse import urlparse
        parsed = urlparse(servers[0].get('url', ''))
        server_prefix = parsed.path.rstrip('/')
        if server_prefix in ('', '/'):
            server_prefix = ''

    effective_prefix = base_path or server_prefix

    # 安全方案检测
    sec_defs = spec.get('securityDefinitions') or spec.get('components', {}).get('securitySchemes', {})
    has_global_auth = bool(sec_defs)

    # tag 描述映射（Knife4j 在 tags 列表里提供 x-order 等扩展）
    tag_descriptions = {}
    for tag in spec.get('tags', []):
        tag_name = tag.get('name', '')
        tag_descriptions[tag_name] = {
            'description': tag.get('description', ''),
            'x_order': tag.get('x-order', tag.get('x-knife4j-tag', {}).get('x-order', 999)),
        }

    for path, path_item in spec.get('paths', {}).items():
        if not isinstance(path_item, dict):
            continue

        # 拼接有效路径（处理 basePath/serverPrefix）
        effective_path = effective_prefix + path if effective_prefix else path

        for method, op in path_item.items():
            if method.lower() not in ('get', 'post', 'put', 'patch', 'delete', 'head', 'options'):
                continue
            if not isinstance(op, dict):
                continue
            method = method.upper()

            # ── Knife4j 扩展字段提取 ──────────────────────────────
            knife4j_info = op.get('x-knife4j-info', {}) or {}
            author       = (op.get('x-author') or
                            knife4j_info.get('author') or
                            op.get('x-knife4j-tag', {}).get('author', ''))
            order        = (op.get('x-order') or
                            knife4j_info.get('order') or
                            op.get('x-knife4j-order', 999))
            ignore       = op.get('x-knife4j-info', {}) and knife4j_info.get('ignore', False)

            # 跳过标记了 ignore 的接口
            if ignore:
                eprint(f'[knife4j] 跳过（x-knife4j-info.ignore=true）: {method} {path}')
                continue

            # ── 基本信息 ──────────────────────────────────────────
            tags     = op.get('tags', [])
            tag_name = tags[0] if tags else group_name
            summary  = op.get('summary') or op.get('operationId') or f'{method} {path}'
            desc     = op.get('description', '')

            # 优先级：认证/核心接口 P0，其余 P1
            auth_keywords = ('auth', 'login', 'logout', 'token', 'register', 'signin', 'signup')
            is_auth_path  = any(k in path.lower() or k in tag_name.lower() for k in auth_keywords)
            priority      = 'P0' if is_auth_path else 'P1'

            # 是否需要认证
            op_security   = op.get('security')
            requires_auth = (op_security is not None and op_security != []) or \
                            (has_global_auth and not is_auth_path)

            # force_auth 覆盖：当文档未声明 security scheme 时兜底
            # 传入 --force-auth 时，所有非登录接口强制标记为需要认证
            if force_auth and not is_auth_path:
                requires_auth = True

            # ── 路径参数替换 ──────────────────────────────────────
            # 将 /api/books/{id} → /api/books/1，避免字面量路径导致 404
            path_params = {}
            for param in op.get('parameters', []):
                if param.get('in') == 'path':
                    pname = param.get('name', '')
                    ptype = (param.get('type') or
                             param.get('schema', {}).get('type', 'integer'))
                    path_params[pname] = 1 if ptype in ('integer','number') else 'test'
            # 填充已知参数，兜底替换任何剩余 {xxx} 为 1
            filled_path = effective_path
            for k, v in path_params.items():
                filled_path = filled_path.replace('{' + k + '}', str(v))
            import re as _re2
            filled_path = _re2.sub(r'\{[^}]+\}', '1', filled_path)

            # ── 请求体 schema ─────────────────────────────────────
            body_schema = _extract_body_schema(op, spec)

            # ── 期望状态码 ────────────────────────────────────────
            responses  = op.get('responses', {})
            ok_codes   = [int(c) for c in responses
                          if str(c).startswith('2') and str(c).isdigit()]
            exp_status = min(ok_codes) if ok_codes else (201 if method == 'POST' else 200)

            # ── 断言（从响应 schema 提取字段存在性断言）────────────
            asserts = _extract_response_asserts(responses, exp_status, spec)

            # ── metadata（Knife4j 专有信息）────────────────────────
            metadata = {
                'group':   group_name,
                'tag':     tag_name,
                'summary': summary,
                'template_path': effective_path,   # 保留原始模板路径（含 {id}）
            }
            if desc:    metadata['description'] = desc
            if author:  metadata['author'] = author
            if order != 999: metadata['x_order'] = order

            # ── 生成用例 ──────────────────────────────────────────
            name_prefix = f'[{tag_name}] {summary}'
            if generate_all:
                new_cases, seq = generate_three_cases(
                    seq, name_prefix, priority, method, filled_path,
                    exp_status, body_schema, asserts, requires_auth,
                    'knife4j', spec, metadata
                )
                cases.extend(new_cases)
            else:
                body = _build_body(body_schema, spec, 'valid') if body_schema else None
                cases.append(make_tc(
                    seq, name_prefix, priority, method, filled_path,
                    exp_status, body, asserts, requires_auth, 'knife4j',
                    'happy_path', metadata
                ))
                seq += 1

    # ── 执行顺序排序 ──────────────────────────────────────────
    # POST(创建) -> GET(读取) -> PUT(更新) -> DELETE(删除)
    # 确保资源先创建再操作，DELETE 排最后，避免测试间数据依赖破坏
    method_order = {'POST':0,'GET':1,'PUT':2,'PATCH':2,'DELETE':3,'HEAD':4}
    cat_order    = {'happy_path':0,'boundary':1,'error':2}
    cases.sort(key=lambda c: (
        method_order.get(c['method'], 9),
        cat_order.get(c['category'], 9)
    ))
    # 重新分配连续 seq/tc_id
    for i, c in enumerate(cases, 1):
        c['seq']   = i
        c['tc_id'] = f'TC-{i:03d}'

    return cases, seq + len(cases)

def _extract_body_schema(op, spec):
    """提取请求体 schema（同时兼容 Swagger2 和 OpenAPI3）"""
    # OpenAPI3: requestBody
    rb = op.get('requestBody', {})
    if rb:
        content = rb.get('content', {})
        for mime in ('application/json', 'application/x-www-form-urlencoded',
                     'multipart/form-data'):
            schema = content.get(mime, {}).get('schema')
            if schema:
                return schema
        # fallback：取第一个 content type
        first = next(iter(content.values()), {})
        schema = first.get('schema')
        if schema:
            return schema

    # Swagger2: parameters[in=body]
    for param in op.get('parameters', []):
        if param.get('in') == 'body':
            return param.get('schema', {})

    # Swagger2: parameters[in=formData] → 构造 object schema
    form_params = [p for p in op.get('parameters', []) if p.get('in') == 'formData']
    if form_params:
        props = {}
        required = []
        for p in form_params:
            props[p['name']] = {'type': p.get('type', 'string'),
                                'description': p.get('description', '')}
            if p.get('required'):
                required.append(p['name'])
        return {'type': 'object', 'properties': props, 'required': required}

    return None

def _extract_response_asserts(responses, exp_status, spec):
    """从响应 schema 提取字段存在性断言。
    对于操作类接口（成功时 data=null 的 void 型返回），不生成 .data exists 断言，
    避免误判。判据：响应 schema 无 properties，或唯一属性为 code/message/data 且 data 无子 schema。
    """
    asserts = []
    resp = responses.get(str(exp_status)) or responses.get(exp_status, {})
    if not isinstance(resp, dict):
        return asserts
    # OpenAPI3
    content = resp.get('content', {})
    schema  = (content.get('application/json') or
               next(iter(content.values()), {})).get('schema', {})
    # Swagger2 fallback
    if not schema:
        schema = resp.get('schema', {})
    # 解引用
    if isinstance(schema, dict) and '$ref' in schema:
        parts = schema['$ref'].lstrip('#/').split('/')
        node  = spec
        for p in parts:
            node = node.get(p, {}) if isinstance(node, dict) else {}
        schema = node

    props = schema.get('properties', {}) if isinstance(schema, dict) else {}

    # ── 跳过 void 型操作接口的 .data 断言 ──────────────────────
    # 判据：props 只有 code/message/data（统一响应体），且 data 字段无 properties/items/allOf
    # 即 data 是原始类型或 null，操作类接口成功时 data 为 null，断言无意义
    wrapper_only = set(props.keys()) <= {'code', 'message', 'data', 'success', 'msg', 'result'}
    data_prop    = props.get('data', {})
    data_is_void = (not data_prop.get('properties') and
                    not data_prop.get('items') and
                    not data_prop.get('allOf') and
                    not data_prop.get('$ref'))
    if wrapper_only and data_is_void:
        # 操作类接口：只断言包装层 code 字段存在
        if 'code' in props:
            asserts.append({'path': '.code', 'type': 'exists'})
        return asserts

    # 正常数据接口：断言 data 内的字段（或顶层字段）
    # 若有 data 字段且 data 有子 schema，断言 data 下的字段
    if 'data' in props and (data_prop.get('properties') or data_prop.get('$ref') or data_prop.get('allOf')):
        # 解引用 data
        if data_prop.get('$ref'):
            ref_parts = data_prop['$ref'].lstrip('#/').split('/')
            node = spec
            for p in ref_parts:
                node = node.get(p, {}) if isinstance(node, dict) else {}
            data_prop = node
        data_props = data_prop.get('properties', {})
        for field in list(data_props.keys())[:3]:
            asserts.append({'path': f'.data.{field}', 'type': 'exists'})
        return asserts

    # fallback：断言顶层字段
    for field in list(props.keys())[:5]:
        asserts.append({'path': f'.{field}', 'type': 'exists'})
    return asserts

# ══════════════════════════════════════════════════════════════
# 来源2：本地 API 文档解析（Swagger / OpenAPI / Markdown / Knife4j导出JSON）
# ══════════════════════════════════════════════════════════════

def load_apidoc_cases(path, generate_all=False, force_auth=False):
    """
    自动识别文件格式：
    - Knife4j 导出的 JSON（含 x-knife4j-info 或 x-knife4j-tag 扩展字段）
    - OpenAPI3 JSON/YAML
    - Swagger2 JSON/YAML
    - Markdown / 纯文本
    """
    text = open(path, encoding='utf-8', errors='replace').read()
    ext  = Path(path).suffix.lower()

    # ── JSON 文件 ─────────────────────────────────────────────
    if ext == '.json':
        try:
            spec = json.loads(text)
            if 'paths' in spec:
                source_label = _detect_knife4j_label(spec)
                eprint(f'[discover] 格式={source_label}（{path}）')
                cases, _ = _parse_knife4j_spec(spec, 'local', 1, generate_all, force_auth=force_auth)
                mode = '全量三类' if generate_all else '正常场景'
                eprint(f'[discover] 来源=本地JSON，模式={mode}，用例数={len(cases)}')
                return cases
        except Exception as e:
            eprint(f'[discover] JSON 解析失败: {e}')

    # ── YAML 文件 ─────────────────────────────────────────────
    if ext in ('.yaml', '.yml'):
        try:
            import yaml
            spec = yaml.safe_load(text)
            if isinstance(spec, dict) and 'paths' in spec:
                source_label = _detect_knife4j_label(spec)
                eprint(f'[discover] 格式={source_label}（{path}）')
                cases, _ = _parse_knife4j_spec(spec, 'local', 1, generate_all)
                mode = '全量三类' if generate_all else '正常场景'
                eprint(f'[discover] 来源=本地YAML，模式={mode}，用例数={len(cases)}')
                return cases
        except Exception as e:
            eprint(f'[discover] YAML 解析失败: {e}')

    # ── Markdown / 纯文本 ─────────────────────────────────────
    return _parse_text_apidoc(text, path, generate_all)

def _detect_knife4j_label(spec):
    """检测 spec 来源标签（Knife4j / OpenAPI3 / Swagger2）"""
    # 检查是否含 Knife4j 扩展字段
    info = spec.get('info', {})
    has_knife4j = (
        'x-knife4j-info' in info or
        any('x-knife4j' in str(op) for ops in spec.get('paths', {}).values()
            if isinstance(ops, dict) for op in ops.values() if isinstance(op, dict))
    )
    if has_knife4j:
        return 'Knife4j增强文档'
    if spec.get('openapi', '').startswith('3'):
        return 'OpenAPI3'
    if spec.get('swagger', '').startswith('2'):
        return 'Swagger2'
    return '未知OpenAPI规范'

def _parse_text_apidoc(text, path, generate_all=False):
    cases, seq = [], 1
    pattern = re.compile(
        r'(?:^|\`|\*\*)\s*(GET|POST|PUT|PATCH|DELETE|HEAD)\s*\**\`?\s+(/[\w/\-\.{}\[\]]*)',
        re.IGNORECASE | re.MULTILINE
    )
    body_pattern = re.compile(r'```json\s*\n(.*?)\n```', re.DOTALL)
    body_examples = {}
    for m in body_pattern.finditer(text):
        try:
            body_examples[m.start()] = json.loads(m.group(1))
        except Exception:
            pass

    seen = set()
    for m in pattern.finditer(text):
        method, ep_path = m.group(1).upper(), m.group(2)
        key = f'{method}:{ep_path}'
        if key in seen:
            continue
        seen.add(key)
        start   = m.start()
        context = text[start:start + 500]
        body    = None
        nearest = None
        for pos, ex in body_examples.items():
            if start <= pos <= start + 500:
                if nearest is None or pos < nearest:
                    nearest, body = pos, ex
        priority   = 'P0' if any(k in ep_path.lower() for k in ('auth','login','logout','token','register')) else 'P1'
        code_m     = re.search(r'\b(200|201|204|400|401|403|404)\b', context)
        exp_status = int(code_m.group(1)) if code_m else (201 if method == 'POST' else 200)
        asserts    = []
        table_m    = re.search(r'\|([^\n]+)\|\n\|[-\s|:]+\|\n((?:\|[^\n]+\|\n?)+)', context)
        if table_m:
            for row in table_m.group(2).strip().splitlines():
                cells = [c.strip() for c in row.split('|') if c.strip()]
                if cells:
                    asserts.append({'path': f'.{cells[0]}', 'type': 'exists'})
        if generate_all:
            new_cases, seq = generate_three_cases(seq, f'{method} {ep_path}', priority,
                                                   method, ep_path, exp_status, body,
                                                   asserts, False, 'apidoc')
            cases.extend(new_cases)
        else:
            cases.append(make_tc(seq, f'{method} {ep_path}', priority,
                                 method, ep_path, exp_status, body, asserts, False, 'apidoc'))
            seq += 1
    mode = '全量三类' if generate_all else '正常场景'
    eprint(f'[discover] 来源=文本文档，模式={mode}，用例数={len(cases)}（{path}）')
    return cases

# ══════════════════════════════════════════════════════════════
# 来源1：Controller / Router 扫描
# ══════════════════════════════════════════════════════════════

AUTH_KEYWORDS = {'login','logout','auth','token','register','signup','signin','password'}

SCAN_PATTERNS = {
    'java_mapping': re.compile(
        r'@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?\"([^"]+)\"',
        re.IGNORECASE),
    'java_method_map': {'get':'GET','post':'POST','put':'PUT','patch':'PATCH','delete':'DELETE','request':'GET'},
    'java_class_ctrl': re.compile(r'@(RestController|Controller)'),
    'java_class_path': re.compile(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?\"([^\"]+)\"'),
    'ts_pattern':      re.compile(r'(?:router|app|this)\.(get|post|put|patch|delete)\s*\(\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE),
    'ts_decorator':    re.compile(r'@(Get|Post|Put|Patch|Delete)\s*\(\s*[\'"]([^\'"]*)[\'"]', re.IGNORECASE),
    'py_pattern':      re.compile(r'@(?:app|router|blueprint)\.(get|post|put|patch|delete)\s*\(\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE),
}

def scan_controllers(root, generate_all=False):
    root = Path(root)
    skip_dirs = {'node_modules','.git','dist','build','target','__pycache__',
                 'vendor','.gradle','.mvn','venv','.venv'}

    def glob_skip(pat):
        return [p for p in root.glob(pat) if not any(s in p.parts for s in skip_dirs)]

    seen, raw_eps = set(), []

    def add(method, ep_path):
        key = f'{method}:{ep_path}'
        if key not in seen:
            seen.add(key)
            raw_eps.append((method, ep_path))

    for f in glob_skip('**/*.java'):
        try: text = f.read_text(errors='ignore')
        except Exception: continue
        if not SCAN_PATTERNS['java_class_ctrl'].search(text): continue
        class_m = SCAN_PATTERNS['java_class_path'].search(text)
        base    = class_m.group(1).rstrip('/') if class_m else ''
        for m in SCAN_PATTERNS['java_mapping'].finditer(text):
            verb, sub = m.group(1).lower(), m.group(2)
            method = SCAN_PATTERNS['java_method_map'].get(verb, 'GET')
            ep_path = (sub if (sub.startswith('/') and (not base or sub.startswith(base)))
                       else (base.rstrip('/')+'/'+sub.lstrip('/') if base else '/'+sub.lstrip('/'))).replace('//', '/')
            add(method, ep_path)

    for pat_key in ('ts_pattern', 'ts_decorator'):
        pat = SCAN_PATTERNS[pat_key]
        for ext in ('**/*.ts', '**/*.js'):
            for f in glob_skip(ext):
                if not any(k in f.name.lower() for k in ('controller','router','route','handler')): continue
                try: text = f.read_text(errors='ignore')
                except Exception: continue
                for m in pat.finditer(text):
                    ep_path = m.group(2) if m.group(2).startswith('/') else '/'+m.group(2)
                    add(m.group(1).upper(), ep_path)

    for f in glob_skip('**/*.py'):
        if not any(k in f.name.lower() for k in ('router','route','view','handler','api','endpoint')): continue
        try: text = f.read_text(errors='ignore')
        except Exception: continue
        for m in SCAN_PATTERNS['py_pattern'].finditer(text):
            ep_path = m.group(2) if m.group(2).startswith('/') else '/'+m.group(2)
            add(m.group(1).upper(), ep_path)

    cases, seq = [], 1
    for method, ep_path in raw_eps:
        path_lower = ep_path.lower()
        is_auth    = any(k in path_lower for k in AUTH_KEYWORDS)
        priority   = 'P0' if is_auth else 'P1'
        body = None
        if method in ('POST', 'PUT', 'PATCH'):
            if 'login' in path_lower or 'auth' in path_lower:
                body = {'email': 'test@example.com', 'password': 'test123'}
            elif 'register' in path_lower or 'signup' in path_lower:
                body = {'email': 'test@example.com', 'password': 'test123', 'name': 'Test User'}
            else:
                body = {}
        exp_status = 201 if method == 'POST' else 200
        if generate_all:
            new_cases, seq = generate_three_cases(seq, f'{method} {ep_path}', priority,
                                                   method, ep_path, exp_status, body,
                                                   [], not is_auth, 'scan')
            cases.extend(new_cases)
        else:
            cases.append(make_tc(seq, f'{method} {ep_path}', priority, method, ep_path,
                                  exp_status, body, [], not is_auth, 'scan'))
            seq += 1
    mode = '全量三类' if generate_all else '正常场景'
    eprint(f'[discover] 来源=Controller扫描，模式={mode}，端点数={len(cases)}')
    return cases

# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description='测试用例发现器（支持 Knife4j）')
    parser.add_argument('project_root', help='项目根目录')
    parser.add_argument('--cases',          default=None,  help='用户提供的用例文件（JSON/YAML）')
    parser.add_argument('--api-doc',        default=None,  help='本地 API 文档文件（支持 Knife4j 导出 JSON）')
    parser.add_argument('--knife4j-url',    default=None,  help='Knife4j 服务地址（如 http://localhost:8080）')
    parser.add_argument('--knife4j-token',  default=None,  help='Knife4j 认证 Token（Bearer 或 Basic）')
    parser.add_argument('--force-auth',     action='store_true',
                        help='强制所有非登录接口设为 requires_auth=true（当 Swagger 文档未声明 security scheme 时使用）')
    parser.add_argument('--generate-all',   action='store_true',
                        help='自动生成三类用例（happy_path / boundary / error）')
    args = parser.parse_args()

    generate_all    = args.generate_all
    force_auth      = args.force_auth
    knife4j_url     = args.knife4j_url
    knife4j_token   = args.knife4j_token
    doc_f           = getattr(args, 'api_doc', None)

    # 确保 stderr 先于 stdout 落盘，避免 stderr 进度日志与 stdout JSON 在管道中交错
    import atexit
    atexit.register(sys.stderr.flush)

    # ── 优先级3：用户提供 ────────────────────────────────────
    if args.cases and os.path.exists(args.cases):
        cases = load_user_cases(args.cases)
        if cases:
            cases = _sort_cases_safe(cases)
            sys.stderr.flush()
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        return

    # ── 优先级2a：Knife4j HTTP 拉取 ─────────────────────────
    if knife4j_url:
        cases = load_knife4j_cases(knife4j_url, knife4j_token, generate_all, force_auth=force_auth)
        if cases:
            cases = _sort_cases_safe(cases)
            sys.stderr.flush()
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        return
        eprint('[discover] Knife4j HTTP 拉取失败，尝试本地文档')

    # ── 优先级2b：本地 API 文档（含 Knife4j 导出 JSON）──────
    if doc_f and os.path.exists(doc_f):
        cases = load_apidoc_cases(doc_f, generate_all, force_auth=force_auth)
        if cases:
            cases = _sort_cases_safe(cases)
            sys.stderr.flush()
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        return

    # ── 优先级1：Controller 扫描（兜底，有限制）───────────────
    eprint('[discover] ⚠️  警告：未检测到 API 文档，降级为 Controller 代码扫描。')
    eprint('[discover]    扫描结果仅包含路由路径，不含请求体结构、字段约束和响应模式。')
    eprint('[discover]    建议：提供 --knife4j-url 或 --api-doc 以获得更精确的用例。')
    cases = scan_controllers(args.project_root, generate_all)
    if cases:
        eprint(f'[discover]    扫描到 {len(cases)} 条用例（来源可信度：低）。')
        cases = _sort_cases_safe(cases)
        sys.stderr.flush()
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        return

    eprint('[discover] ❌ 未发现任何端点。Controller 扫描也未找到路由。')
    eprint('[discover]    请检查：')
    eprint('[discover]    1. 项目是否使用标准注解（@RestController / @GetMapping 等）')
    eprint('[discover]    2. 是否可提供 --api-doc <文档文件> 或 --knife4j-url <服务地址>')
    print('[]')

def _sort_cases_safe(cases):
    """
    对用例按执行安全顺序排序，防止 DELETE 先执行消耗数据导致后续 404。
    排序优先级（数值越小越先执行）：
      1. GET  happy_path  — 先读，不修改状态
      2. POST happy_path  — 创建数据，为后续提供依赖
      3. PUT  happy_path  — 更新已有数据
      4. GET/POST/PUT boundary/error — 边界和错误场景
      5. DELETE happy_path            — 删除操作最后
      6. DELETE boundary/error        — 最后执行
    """
    _method_order = {'GET': 0, 'POST': 1, 'PUT': 2, 'PATCH': 2,
                     'DELETE': 5, 'HEAD': 0, 'OPTIONS': 0}
    _cat_order    = {'happy_path': 0, 'boundary': 1, 'error': 2, 'jsonpath_demo': 0}

    def sort_key(tc):
        m   = tc.get('method', 'GET').upper()
        cat = tc.get('category', 'happy_path')
        mo  = _method_order.get(m, 3)
        co  = _cat_order.get(cat, 1)
        # DELETE 的优先级再细化：happy_path DELETE 在 boundary/error 之前
        if m == 'DELETE':
            mo = 5 if cat == 'happy_path' else 6
        return (mo + co, tc.get('seq', 0))

    # 重新分配 seq，保持路径分组内的相对顺序
    sorted_cases = sorted(cases, key=sort_key)
    for i, tc in enumerate(sorted_cases, 1):
        tc['seq'] = i
        tc['tc_id'] = f'TC-{i:03d}'
    return sorted_cases


if __name__ == '__main__':
    main()
