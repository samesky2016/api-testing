#!/usr/bin/env python3
"""
run_test.py — 执行单个测试用例并完整留痕

规则：
  · 所有用例必须执行，不存在 SKIP。
  · 执行结果只有 PASS 或 FAIL，FAIL 时自动记录完整出入参。
  · 所有响应来自真实请求，禁止 mock（compliance.no_mock=true）。

执行器自动选择：curl（优先）→ http_client.py（降级）→ 报错
  环境变量 TEST_EXECUTOR=curl|http_client 可强制指定

用法:
  python3 run_test.py <evidence_dir> <seq> <tc_id> <priority> <method> <url> \
    <expected_status> <req_json_str> <assert_fields_json> [token]

输出: 单行 JSON，包含 result(PASS|FAIL)/status/duration_ms/executor/assertions
      FAIL 时额外含 failure_detail{request_body, response_body, actual_status, curl_equivalent}
留痕: 写入 evidence_dir/http-trace/ 并更新 assertions-detail.json
"""

import json, os, sys, time, re
from datetime import datetime, timezone
from pathlib import Path

# ══════════════════════════════════════════════════════════════
# 执行器检测
# ══════════════════════════════════════════════════════════════

def _curl_available():
    import subprocess
    try:
        return subprocess.run(['curl', '--version'], capture_output=True, timeout=3).returncode == 0
    except Exception:
        return False

def _http_client_available():
    try:
        import requests  # noqa
        return True
    except ImportError:
        return False

def _resolve_executor():
    forced = os.environ.get('TEST_EXECUTOR', '').lower()
    if forced in ('curl', 'http_client'):
        return forced
    if _curl_available():
        return 'curl'
    if _http_client_available():
        return 'http_client'
    raise RuntimeError(
        '未找到可用执行器：\n'
        '  · curl 未安装或不在 PATH 中\n'
        '  · requests 库未安装（pip install requests）\n'
        '请安装其中一个，或设置环境变量 TEST_EXECUTOR=curl|http_client'
    )

# ══════════════════════════════════════════════════════════════
# curl 执行器
# ══════════════════════════════════════════════════════════════

def _run_curl(method, url, req_body, token, seq, timeout=10):
    import subprocess
    req_file  = f'/tmp/req_{seq:03d}.json'
    resp_file = f'/tmp/resp_{seq:03d}.txt'

    if req_body is not None:
        with open(req_file, 'w', encoding='utf-8') as f:
            json.dump(req_body, f, ensure_ascii=False)

    cmd = [
        'curl', '-s', '-o', resp_file, '-w', '%{http_code}',
        '-X', method, url,
        '-H', 'Content-Type: application/json',
        '--max-time', str(timeout), '--connect-timeout', '5',
    ]
    if token and token != '-':
        # 兼容两种传入格式：
        # 1. "Bearer eyJ..."  → 直接用
        # 2. "eyJ..."         → 自动补 Bearer 前缀
        auth_header = token if token.lower().startswith('bearer ') else f'Bearer {token}'
        cmd += ['-H', f'Authorization: {auth_header}']
    if req_body is not None:
        cmd += ['-d', f'@{req_file}']

    curl_str = ' '.join(
        f"'{a}'" if any(c in a for c in (' ', '{', '}', '"')) else a for a in cmd
    )

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        duration_ms   = int((time.time() - t0) * 1000)
        actual_status = int(proc.stdout.strip() or '0')
    except subprocess.TimeoutExpired:
        duration_ms, actual_status = int((time.time() - t0) * 1000), 0
        with open(resp_file, 'w') as f:
            f.write(json.dumps({'error': 'curl timeout', 'fail_reason': '请求超时，接口未在规定时间内响应'}))
    except Exception as e:
        duration_ms, actual_status = int((time.time() - t0) * 1000), 0
        with open(resp_file, 'w') as f:
            f.write(json.dumps({'error': str(e), 'fail_reason': f'curl执行异常: {e}'}))

    try:
        raw = open(resp_file, encoding='utf-8', errors='replace').read()
        resp_body = json.loads(raw)
    except Exception:
        resp_body = open(resp_file, encoding='utf-8', errors='replace').read() \
                    if os.path.exists(resp_file) else None

    return actual_status, resp_body, curl_str, duration_ms

# ══════════════════════════════════════════════════════════════
# http_client 执行器
# ══════════════════════════════════════════════════════════════

def _run_http_client(method, url, req_body, token, seq, timeout=10):
    _assets = Path(__file__).parent.parent / 'assets' / 'http_client.py'
    _mod    = None
    if _assets.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location('http_client', str(_assets))
        _mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)

    headers = {'Content-Type': 'application/json'}
    if token and token != '-':
        auth_header = token if token.lower().startswith('bearer ') else f'Bearer {token}'
        headers['Authorization'] = auth_header

    curl_parts = ['curl', '-s', '-X', method, f"'{url}'",
                  "-H 'Content-Type: application/json'"]
    if token and token != '-':
        auth_header = token if token.lower().startswith('bearer ') else f'Bearer {token}'
        curl_parts.append(f"-H 'Authorization: {auth_header}'")
    if req_body is not None:
        body_str = json.dumps(req_body, ensure_ascii=False)
        curl_parts.append(f"-d '{body_str}'")
    curl_str = ' '.join(curl_parts)

    t0 = time.time()
    actual_status, resp_body = 0, None
    try:
        if _mod:
            client = _mod.HTTPClient(
                headers={k: v for k, v in headers.items() if k != 'Content-Type'},
                timeout=(5, timeout)
            )
            fn_map = {
                'GET':    lambda: client.get(url),
                'POST':   lambda: client.post(url, data=req_body),
                'PUT':    lambda: client.put(url, data=req_body),
                'DELETE': lambda: client.delete(url),
                'PATCH':  lambda: client.post(url, data=req_body),
            }
            fn = fn_map.get(method.upper())
            if fn is None:
                raise ValueError(f'http_client 不支持 {method}，请切换 curl 执行器')
            resp = fn()
            actual_status = resp.status_code
            try:    resp_body = resp.json()
            except: resp_body = resp.text[:2000] if resp.text else None
            client.close()
        else:
            import requests as rlib
            resp = rlib.request(method.upper(), url, json=req_body,
                                headers=headers, timeout=timeout)
            actual_status = resp.status_code
            try:    resp_body = resp.json()
            except: resp_body = resp.text[:2000] if resp.text else None
    except Exception as e:
        resp_body = {'error': str(e), 'fail_reason': f'http_client执行异常: {e}'}

    duration_ms = int((time.time() - t0) * 1000)
    return actual_status, resp_body, curl_str, duration_ms

# ══════════════════════════════════════════════════════════════
# 断言引擎
# ══════════════════════════════════════════════════════════════

def _get_nested(obj, path):
    """
    支持两种路径格式：
    1. 简单点分路径：.field.subfield.0
    2. JSONPath 过滤表达式：[?(@.field==value)] 或 [?(@.field contains value)]
       例：.items[?(@.id==1)].name  /  .list[?(@.type contains "admin")]
    """
    if not path:
        return obj
    path = path.lstrip('.')

    # ── JSONPath 过滤表达式解析 ───────────────────────────────
    filter_re = re.compile(r'^([^[]*)\[\?\(@\.(\w+)\s*(==|!=|contains|>=|<=|>|<)\s*["\']?([^"\')\]]*)["\']?\)\](.*)$')
    m = filter_re.match(path)
    if m:
        prefix, field, op, val_str, suffix = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        # 先解析前缀路径
        parent = _get_nested(obj, prefix) if prefix else obj
        if not isinstance(parent, list):
            return None
        # 过滤列表
        matched = []
        for item in parent:
            if not isinstance(item, dict):
                continue
            item_val = item.get(field)
            item_str = str(item_val) if item_val is not None else ''
            # 类型尝试转换
            try:
                item_num = float(item_val) if item_val is not None else None
                val_num  = float(val_str)
            except (TypeError, ValueError):
                item_num, val_num = None, None

            if op == '==' and (item_str == val_str or item_num == val_num):
                matched.append(item)
            elif op == '!=' and item_str != val_str:
                matched.append(item)
            elif op == 'contains' and val_str.lower() in item_str.lower():
                matched.append(item)
            elif op == '>=' and item_num is not None and item_num >= val_num:
                matched.append(item)
            elif op == '<=' and item_num is not None and item_num <= val_num:
                matched.append(item)
            elif op == '>' and item_num is not None and item_num > val_num:
                matched.append(item)
            elif op == '<' and item_num is not None and item_num < val_num:
                matched.append(item)

        if not matched:
            return None
        # 若有后缀路径，对第一个匹配项继续解析
        if suffix:
            return _get_nested(matched[0], suffix.lstrip('.'))
        return matched  # 返回列表供 exists 断言使用

    # ── 简单点分路径（原逻辑）────────────────────────────────
    parts = [p for p in path.split('.') if p]
    cur = obj
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and p.isdigit():
            idx = int(p)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
    return cur

def _is_unified_wrapper(resp_body):
    """检测是否为统一响应体格式 {code, message, data}"""
    if not isinstance(resp_body, dict):
        return False
    keys = set(resp_body.keys())
    # 至少包含 code + (message 或 data 或 msg)
    return 'code' in keys and bool(keys & {'message', 'data', 'msg', 'result'})

def _run_assertions(expected_status, actual_status, resp_body, assert_fields):
    assertions = []

    # ── HTTP 状态码断言（兜底）────────────────────────────────
    # 对于统一响应体 API（所有接口均返回 HTTP 200），只要 HTTP 不是 0/401/403/5xx
    # 就不以 HTTP 状态码作为主判断，改用 body.code
    http_exp = int(expected_status)
    is_wrapper = _is_unified_wrapper(resp_body) and actual_status == 200

    if is_wrapper:
        # ── 统一响应体模式：以 body.code 为主断言 ────────────
        body_code = resp_body.get('code', 200)
        body_msg  = resp_body.get('message', resp_body.get('msg', ''))

        # 期望 2xx → body.code 应为 200（业务成功）
        # 期望 4xx  → body.code 应非 200（业务被拒绝）
        if 200 <= http_exp < 300:
            ok = (body_code == 200)
            desc = f'业务成功（body.code=200）'
            exp_str = '200'
            fail_msg = None if ok else f'body.code={body_code}，msg={body_msg}'
        else:
            ok = (body_code != 200)
            desc = f'业务被拒绝（body.code≠200，期望校验拒绝）'
            exp_str = '≠200'
            fail_msg = None if ok else f'body.code={body_code}（服务端未校验，应拒绝请求）'

        assertions.append({
            'type':        'body_code',
            'description': desc,
            'expected':    exp_str,
            'actual':      str(body_code),
            'result':      'PASS' if ok else 'FAIL',
            'message':     fail_msg
        })
    else:
        # ── 标准模式：以 HTTP 状态码为主断言 ─────────────────
        status_ok = (actual_status == http_exp)
        assertions.append({
            'type':        'status_code',
            'description': f'状态码为 {http_exp}',
            'expected':    str(http_exp),
            'actual':      str(actual_status),
            'result':      'PASS' if status_ok else 'FAIL',
            'message':     None if status_ok else (
                f'实际返回 {actual_status}' +
                (f'（网络/超时错误）' if actual_status == 0 else '')
            )
        })

    for af in assert_fields:
        field_path   = af.get('path', '')
        expected_val = str(af.get('expected', ''))
        check_type   = af.get('type', 'eq')
        actual_val   = _get_nested(resp_body, field_path) if isinstance(resp_body, (dict, list)) else None
        actual_str   = str(actual_val) if actual_val is not None else 'null'

        if check_type == 'exists':
            ok, desc, ev = actual_val is not None, f'字段 {field_path} 存在', 'exists'
        elif check_type == 'not_exists':
            ok, desc, ev = actual_val is None, f'字段 {field_path} 不存在', 'not_exists'
        elif check_type == 'contains':
            ok, desc, ev = expected_val in actual_str, f'字段 {field_path} 包含 {expected_val}', expected_val
        else:
            ok, desc, ev = (actual_str == expected_val), f'字段 {field_path} = {expected_val}', expected_val

        assertions.append({
            'type':        'json_field',
            'description': desc,
            'expected':    ev,
            'actual':      actual_str,
            'result':      'PASS' if ok else 'FAIL',
            'message':     None
        })

    return assertions

# ══════════════════════════════════════════════════════════════
# 合规标记
# ══════════════════════════════════════════════════════════════

def _mock_guard(executor):
    return {
        'no_mock':       True,
        'executor':      executor,
        'source':        'real_http_request',
        'skip_allowed':  False,   # 本版本不允许 SKIP
        'untested_allowed': False  # 本版本不允许 UNTESTED
    }

# ══════════════════════════════════════════════════════════════
# 留痕写入
# ══════════════════════════════════════════════════════════════

def _write_trace(trace_dir, seq, tc_id, priority, method, url,
                 req_body, resp_body, actual_status, duration_ms,
                 curl_str, executor, overall, now):
    slug = re.sub(r'https?://[^/]*', '', url).replace('/', '-').strip('-').lower()
    trace_path = os.path.join(trace_dir, f'{seq:03d}_{method}_{slug}_{overall}.json')

    trace = {
        'seq':         seq,
        'test_case':   tc_id,
        'priority':    priority,
        'executed_at': now,
        'duration_ms': duration_ms,
        'result':      overall,
        'executor':    executor,
        'compliance':  _mock_guard(executor),
        'request': {
            'method':          method,
            'url':             url,
            'body':            req_body,
            'curl_equivalent': curl_str,
        },
        'response': {
            'status_code': actual_status,
            'body':        resp_body,
        },
        'error': None,
    }

    # FAIL 时附加完整出入参摘要，方便快速定位失败原因
    if overall == 'FAIL':
        fail_reason = None
        # 尝试从响应体提取 fail_reason 字段
        if isinstance(resp_body, dict):
            fail_reason = resp_body.get('fail_reason') or resp_body.get('error')
        if actual_status == 0:
            fail_reason = fail_reason or '网络错误或请求超时（actual_status=0）'
        # 把第一条 FAIL 断言的消息附在 fail_reason 里，方便 agent 直接读
        if not fail_reason or fail_reason == '断言不匹配，详见 assertions':
            for a in assertions:
                if a['result'] == 'FAIL' and a.get('message'):
                    fail_reason = a['message']
                    break

        trace['failure_detail'] = {
            'fail_reason':   fail_reason or '断言不匹配，详见 assertions',
            'request_body':  req_body,
            'response_body': resp_body,
            'actual_status': actual_status,
            'note':          '完整出入参已保留，禁止 mock 替换（compliance.no_mock=true）'
        }

    _save(trace_path, trace)
    return trace_path

def _write_assertions(assert_file, tc_id, method, url, assertions):
    ad = _load(assert_file)
    tc_entry = next((x for x in ad['details'] if x.get('id') == tc_id), None)
    if tc_entry is None:
        tc_entry = {'id': tc_id, 'endpoint': f'{method} {url}', 'assertions': []}
        ad['details'].append(tc_entry)
    for a in assertions:
        ad['total_assertions'] += 1
        if a['result'] == 'PASS':
            ad['passed'] += 1
        else:
            ad['failed'] += 1
        tc_entry['assertions'].append({
            'id': 'A' + str(ad['total_assertions']).zfill(3),
            **a
        })
    n = ad['total_assertions']
    ad['pass_rate'] = f"{round(ad['passed'] / n * 100, 1)}%" if n else '0%'
    _save(assert_file, ad)

def _load(path):
    with open(path, encoding='utf-8') as f: return json.load(f)

def _save(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ══════════════════════════════════════════════════════════════
# 主执行函数
# ══════════════════════════════════════════════════════════════

def run(evidence_dir, seq, tc_id, priority, method, url,
        expected_status, req_json_str, assert_fields_json, token=None,
        request_timeout=10):

    trace_dir   = os.path.join(evidence_dir, 'http-trace')
    assert_file = os.path.join(evidence_dir, 'assertions', 'assertions-detail.json')
    os.makedirs(trace_dir, exist_ok=True)

    req_body      = None if req_json_str in ('null', '', None) else json.loads(req_json_str)
    assert_fields = json.loads(assert_fields_json) if assert_fields_json not in ('[]', '', None) else []
    now           = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    # 选择执行器（所有用例必须执行，无 SKIP 路径）
    try:
        executor = _resolve_executor()
    except RuntimeError as e:
        print(json.dumps({'tc_id': tc_id, 'result': 'ERROR', 'error': str(e)},
                         ensure_ascii=False))
        sys.exit(1)

    # 发送真实请求（禁止 mock），透传 request_timeout
    if executor == 'curl':
        actual_status, resp_body, curl_str, duration_ms = _run_curl(
            method, url, req_body, token, seq, timeout=request_timeout)
    else:
        actual_status, resp_body, curl_str, duration_ms = _run_http_client(
            method, url, req_body, token, seq, timeout=request_timeout)

    # 断言
    assertions = _run_assertions(expected_status, actual_status, resp_body, assert_fields)
    overall    = 'PASS' if all(a['result'] == 'PASS' for a in assertions) else 'FAIL'

    # 留痕（FAIL 时写完整出入参）
    trace_path = _write_trace(
        trace_dir, seq, tc_id, priority, method, url,
        req_body, resp_body, actual_status, duration_ms,
        curl_str, executor, overall, now
    )
    _write_assertions(assert_file, tc_id, method, url, assertions)

    # 输出摘要
    summary = {
        'tc_id':           tc_id,
        'result':          overall,
        'executor':        executor,
        'status':          actual_status,
        'expected_status': int(expected_status),
        'duration_ms':     duration_ms,
        'assertions':      [{'desc': a['description'], 'r': a['result']} for a in assertions],
        'trace':           trace_path,
    }
    if overall == 'FAIL':
        # FAIL 时在摘要中也携带出入参，供 agent 在对话中直接报告
        fd = {}
        if isinstance(resp_body, dict):
            fd['fail_reason'] = resp_body.get('fail_reason') or resp_body.get('error')
        if actual_status == 0:
            fd['fail_reason'] = fd.get('fail_reason') or '网络错误或请求超时'
        summary['failure_detail'] = {
            'fail_reason':   fd.get('fail_reason') or '断言不匹配，详见 assertions',
            'request_body':  req_body,
            'response_body': resp_body if not isinstance(resp_body, str) else resp_body[:500],
            'actual_status': actual_status,
        }

    print(json.dumps(summary, ensure_ascii=False))
    return overall

# ══════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='执行单个测试用例（所有用例必须执行，不允许 SKIP）')
    parser.add_argument('evidence_dir')
    parser.add_argument('seq',              type=int)
    parser.add_argument('tc_id')
    parser.add_argument('priority')
    parser.add_argument('method')
    parser.add_argument('url')
    parser.add_argument('expected_status')
    parser.add_argument('req_json_str')
    parser.add_argument('assert_fields_json')
    parser.add_argument('token',            nargs='?', default=None)
    parser.add_argument('--request-timeout', type=int, default=10,
                        help='单个 HTTP 请求超时秒数（默认 10）')
    parser.add_argument('--suite-deadline',  type=float, default=None,
                        help='套件截止时间戳（unix epoch），由 orchestrator 传入；'
                             '超过则输出 {"suite_timeout": true} 并以退出码 2 终止')
    args = parser.parse_args()

    # 套件超时检测：若当前时间已超过截止时间戳，直接退出，不执行请求
    if args.suite_deadline is not None and time.time() > args.suite_deadline:
        print(json.dumps({
            'tc_id':         args.tc_id,
            'result':        'SUITE_TIMEOUT',
            'suite_timeout': True,
            'message':       f'套件超时，{args.tc_id} 未执行',
        }, ensure_ascii=False))
        sys.exit(2)

    run(
        args.evidence_dir, args.seq, args.tc_id, args.priority,
        args.method, args.url, args.expected_status,
        args.req_json_str, args.assert_fields_json,
        args.token,
        request_timeout=args.request_timeout,
    )
