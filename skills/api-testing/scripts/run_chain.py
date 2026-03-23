#!/usr/bin/env python3
"""
run_chain.py — 带依赖链的测试用例执行器

功能：
  1. 按依赖顺序执行用例（depends_on 指定的用例必须 PASS 才能执行后续）
  2. POST 成功后从响应体中捕获变量（capture.var / capture.path）
  3. 将捕获的变量动态注入后续用例的路径和请求体（{{VAR}} 占位符）
  4. 执行顺序：CREATE → READ → UPDATE → boundary/error → DELETE
  5. 跳过依赖失败的用例（SKIP，记录原因）

用法：
  python3 run_chain.py \\
    <cases_file>   <evidence_dir>  <api_url>    <auth_token> \\
    [--request-timeout 10]  [--suite-timeout 600] \\
    [--batch-start 0]  [--batch-size 999]

输出：
  每条用例一行：✅/❌/⏭ {tc_id} {method} {path} exp={N} got={M} {dur}ms → {result}
  最后一行：SUMMARY: total={N} pass={P} fail={F} skip={S}
"""
import json, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

# ── CLI 参数 ──────────────────────────────────────────────────
import argparse
p = argparse.ArgumentParser()
p.add_argument('cases_file')
p.add_argument('evidence_dir')
p.add_argument('api_url')
p.add_argument('auth_token')
p.add_argument('--request-timeout', type=int, default=10)
p.add_argument('--suite-timeout',   type=int, default=600)
p.add_argument('--batch-start',     type=int, default=0)
p.add_argument('--batch-size',      type=int, default=9999)
args = p.parse_args()

CASES_FILE   = args.cases_file
EV           = args.evidence_dir
API_URL      = args.api_url.rstrip('/')
AUTH_TOKEN   = args.auth_token   # 裸 token（不含 Bearer）
DEADLINE     = int(time.time()) + args.suite_timeout
REQ_TIMEOUT  = args.request_timeout
BASH         = '/usr/bin/bash'

# ── 加载用例 ──────────────────────────────────────────────────
all_cases = json.load(open(CASES_FILE, encoding='utf-8'))
cases = all_cases[args.batch_start : args.batch_start + args.batch_size]

# ── 变量注册表（存放从响应中捕获的运行时 ID）─────────────────
# 格式：{"CASE_ID": 42, "USER_ID": 7, ...}
captured_vars: dict = {
    # TIMESTAMP 变量：执行时自动注入，用于唯一性字段（caseNo、username 等）
    'TIMESTAMP': datetime.now().strftime('%Y%m%d%H%M%S'),
    'RAND4': __import__('random').randint(1000, 9999),
}

def fill_template(text: str) -> str:
    """将 {{VAR}} 替换为 captured_vars 中的真实值"""
    if not text: return text
    for var, val in captured_vars.items():
        text = text.replace(f'{{{{{var}}}}}', str(val))
    return text

def fill_body(body):
    """递归替换 body 中的 {{VAR}} 占位符"""
    if body is None: return None
    if isinstance(body, str):  return fill_template(body)
    if isinstance(body, dict): return {k: fill_body(v) for k, v in body.items()}
    if isinstance(body, list): return [fill_body(i) for i in body]
    return body

def extract_from_resp(resp_body, path: str):
    """从响应体按点分路径提取值，支持 .data.id / .data / .id"""
    if resp_body is None: return None
    parts = [p for p in path.lstrip('.').split('.') if p]
    cur = resp_body
    for part in parts:
        if isinstance(cur, dict): cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit(): cur = cur[int(part)]
        else: return None
    return cur

# ── 执行顺序排列（CREATE → READ → UPDATE → bound/err → DELETE）──
ORDER_WEIGHT = {
    ('POST',   'happy_path'): 10,
    ('GET',    'happy_path'): 20,
    ('GET',    'boundary'):   21,
    ('PUT',    'happy_path'): 30,
    ('POST',   'happy_path'): 10,   # 带 capture 的 create 排最前
    ('POST',   'boundary'):   40,
    ('POST',   'error'):      41,
    ('PUT',    'boundary'):   31,
    ('PUT',    'error'):      32,
    ('DELETE', 'happy_path'): 90,
    ('DELETE', 'boundary'):   91,
}
def sort_key(c):
    base = ORDER_WEIGHT.get((c['method'], c['category']), 50)
    # 有 capture 的 create 用例排最前（weight 1）
    if c.get('capture'): base = 1
    # delete 排最后
    if c.get('_delete_last'): base = 99
    # depends_on 的用例按依赖链顺序
    return (base, c['seq'])

cases_sorted = sorted(cases, key=sort_key)

# ── 构建 depends_on 映射（tc_id → 是否已 PASS）────────────────
result_registry: dict = {}   # tc_id → "PASS" | "FAIL" | "SKIP"

# ── 统计 ──────────────────────────────────────────────────────
total = len(cases_sorted)
n_pass = n_fail = n_skip = 0

print(f"[run_chain] 共 {total} 条用例，已捕获变量: {list(captured_vars.keys())}")

for tc in cases_sorted:
    tc_id  = tc['tc_id']
    method = tc['method']
    cat    = tc.get('category', 'happy_path')

    # ── 套件超时检查 ──────────────────────────────────────────
    if time.time() > DEADLINE:
        print(f"⏸ [SUITE_TIMEOUT] 已超时，停止剩余用例")
        break

    # ── 依赖检查 ──────────────────────────────────────────────
    dep = tc.get('depends_on')
    if dep:
        dep_result = result_registry.get(dep, 'UNKNOWN')
        if dep_result != 'PASS':
            reason = f"依赖 {dep} 未 PASS（当前状态: {dep_result}）"
            print(f"  ⏭  {tc_id} {method} {tc['path']}  → SKIP（{reason}）")
            result_registry[tc_id] = 'SKIP'
            n_skip += 1
            continue

    # ── 路径填充（{{VAR}} → 真实 ID）─────────────────────────
    raw_path = tc.get('path_template') or tc['path']
    filled_path = fill_template(raw_path)

    # ── body 填充 ─────────────────────────────────────────────
    filled_body = fill_body(tc.get('body'))

    # ── token 注入 ────────────────────────────────────────────
    token_arg = AUTH_TOKEN if (tc.get('requires_auth') and AUTH_TOKEN) else '-'

    # ── 构造执行命令 ──────────────────────────────────────────
    url      = f"{API_URL}{filled_path}"
    body_str = json.dumps(filled_body, ensure_ascii=False) if filled_body is not None else 'null'
    asrt_str = json.dumps(tc.get('asserts', []), ensure_ascii=False)
    exp      = tc.get('expected_status', 200)

    cmd = (
        f"python3 .claude/skills/api-testing/scripts/run_test.py "
        f'"{EV}" {tc["seq"]} {tc_id} {tc.get("priority","P1")} {method} '
        f'"{url}" {exp} '
        f"'{body_str}' '{asrt_str}' '{token_arg}' "
        f"--request-timeout {REQ_TIMEOUT} --suite-deadline {DEADLINE}"
    )

    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if r.returncode == 2:
        print("⏸ [SUITE_TIMEOUT] run_test 返回超时退出码")
        break

    try:
        ro = json.loads(r.stdout.strip())
    except:
        ro = {'result': 'ERROR', 'status': 0, 'duration_ms': 0}

    res  = ro.get('result', 'ERROR')
    got  = ro.get('status', '?')
    dur  = ro.get('duration_ms', '?')
    auth_icon = '🔑' if tc.get('requires_auth') else '  '
    icon = '✅' if res == 'PASS' else '❌'
    print(f"  {icon} {auth_icon} {tc_id} {cat:12s} {method:6s} {filled_path:45s}  exp={exp:<3} got={got:<3} {dur}ms → {res}")

    if res == 'FAIL':
        fd = ro.get('failure_detail', {})
        print(f"       ↳ {fd.get('fail_reason', '断言不匹配')}")
        if str(got) == '401':
            print(f"       ⚠️  401：检查 AUTH_TOKEN（requires_auth={tc.get('requires_auth')}）")

    result_registry[tc_id] = res
    if res == 'PASS': n_pass += 1
    else: n_fail += 1

    # ── 变量捕获（POST 成功后提取 ID）────────────────────────
    cap = tc.get('capture')
    if cap and res == 'PASS' and method == 'POST':
        # 从 trace 文件读取响应体
        import glob
        resp_body = None
        pattern = f"{EV}/http-trace/{tc['seq']:03d}_POST_*_PASS.json"
        matches = glob.glob(pattern)
        if matches:
            try:
                trace = json.load(open(matches[0]))
                resp_body = trace.get('response', {}).get('body')
            except: pass

        val = None
        if resp_body:
            val = extract_from_resp(resp_body, cap['path'])
            if val is None:
                val = extract_from_resp(resp_body, cap.get('fallback_path', '.data'))

        if val is not None:
            captured_vars[cap['var']] = val
            print(f"       📌 捕获 {cap['var']} = {val}")
        else:
            print(f"       ⚠️  未能从响应中提取 {cap['var']}（路径: {cap['path']}）")
            print(f"       响应体: {str(resp_body)[:100]}")

    # ── 更新覆盖 ─────────────────────────────────────────────
    template_path = tc.get('metadata', {}).get('template_path', tc['path'])
    subprocess.run(
        f'{BASH} .claude/skills/api-testing/scripts/record.sh cover '
        f'{method} "{template_path}" "{tc.get("name","")}" {res}',
        shell=True, capture_output=True
    )

# ── 最终汇总 ──────────────────────────────────────────────────
exec_total = n_pass + n_fail + n_skip
print(f"\nSUMMARY: total={exec_total} pass={n_pass} fail={n_fail} skip={n_skip} "
      f"pass_rate={round(n_pass/max(exec_total,1)*100,1)}%")
print(f"CAPTURED_VARS: {json.dumps(captured_vars, ensure_ascii=False)}")
