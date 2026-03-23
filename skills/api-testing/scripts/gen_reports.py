#!/usr/bin/env python3
"""
gen_reports.py  —  集成测试报告生成器（含 HTML 报告）
用法:
  python3 gen_reports.py summary  <assert_file> <coverage_file> <trace_dir> <out_md>     <timestamp> <api_url>
  python3 gen_reports.py report   <assert_file> <coverage_file> <trace_dir> <out_report>  <timestamp> <api_url>
  python3 gen_reports.py results  <assert_file> <coverage_file> <trace_dir> <out_json>   <timestamp>
  python3 gen_reports.py html     <assert_file> <coverage_file> <trace_dir> <out_html>   <timestamp> <api_url>
  python3 gen_reports.py all      <assert_file> <coverage_file> <trace_dir> <base_dir>   <timestamp> <api_url>
"""
import json, os, glob, sys
from datetime import datetime

def load(path):
    with open(path) as f: return json.load(f)

def traces(trace_dir):
    return sorted(glob.glob(os.path.join(trace_dir, '*.json')))

# ─── Markdown audit-summary ──────────────────────────────────

def _count_traces(tf):
    """统计 PASS / FAIL 数量（不再存在 SKIP）"""
    pc = sum(1 for f in tf if '_PASS.json' in f)
    fc = len(tf) - pc
    return pc, fc, 0   # sc 固定为 0

def _load_untested_endpoints(coverage_file):
    """
    提取 UNTESTED 端点列表。
    新规则：不允许任何 UNTESTED，每条均视为违规，报告中标红。
    """
    c = load(coverage_file)
    return [
        {
            'method':   ep['method'],
            'path':     ep['path'],
            'priority': ep['priority'],
            'reason':   '❌ 违规：该端点未被测试（所有注册端点必须执行）',
            'missing':  True,
        }
        for ep in c.get('endpoints', [])
        if ep.get('status') == 'UNTESTED'
    ]

def _load_skipped_cases(assert_file):
    """
    提取 SKIP 用例列表。
    新规则：不允许任何 SKIP，每条均视为违规。
    """
    a = load(assert_file)
    return [
        (d['id'], '❌ 违规：用例被跳过（所有用例必须执行）')
        for d in a.get('details', [])
        if d.get('skipped')
    ]

def _load_failed_cases_with_io(assert_file, trace_dir):
    """
    提取失败用例的完整出入参（注意事项②）。
    返回列表：[{tc_id, endpoint, req_body, resp_body, actual_status, fail_assertions}]
    """
    a        = load(assert_file)
    tf_map   = {}
    for path in traces(trace_dir):
        try:
            tr = load(path)
            tc_id = 'TC-' + str(tr['seq']).zfill(3)
            tf_map[tc_id] = tr
        except Exception:
            pass

    result = []
    for d in a.get('details', []):
        if d.get('skipped'):
            continue
        fail_as = [x for x in d.get('assertions', []) if x.get('result') == 'FAIL']
        if not fail_as:
            continue
        tc_id = d['id']
        tr    = tf_map.get(tc_id, {})
        req   = tr.get('request', {})
        resp  = tr.get('response', {})
        # 优先从 failure_detail 取，其次从 request/response 取
        fd    = tr.get('failure_detail', {})
        result.append({
            'tc_id':          tc_id,
            'endpoint':       d.get('endpoint', ''),
            'req_body':       fd.get('request_body',  req.get('body')),
            'resp_body':      fd.get('response_body', resp.get('body')),
            'actual_status':  fd.get('actual_status', resp.get('status_code')),
            'curl_equivalent': req.get('curl_equivalent', ''),
            'fail_assertions': fail_as,
        })
    return result

def cmd_summary(assert_file, coverage_file, trace_dir, out_md, timestamp, api_url):
    a = load(assert_file); c = load(coverage_file)
    tf = traces(trace_dir)
    pc, fc, sc = _count_traces(tf)
    s  = c['summary']
    skipped  = _load_skipped_cases(assert_file)
    untested = _load_untested_endpoints(coverage_file)
    # 新规则：UNTESTED 和 SKIP 均为违规，不区分是否有原因
    missing_untested = untested
    missing_skip     = skipped

    rows = [
        '# 集成测试留痕摘要', '',
        '**执行时间**: ' + timestamp + '  **后端**: ' + api_url, '',
        '> 合规声明：所有测试结果来自真实 HTTP 请求，禁止 mock 数据（compliance.no_mock=true）', '',
    ]
    if missing_untested or missing_skip:
        rows += ['> ❌ **违规警告**：存在 UNTESTED 端点或 SKIP 用例，所有用例必须执行，请立即修复', '']

    rows += [
        '## 📊 执行概览', '', '| 指标 | 数值 |', '|------|------|',
        *['| ' + k + ' | ' + v + ' |' for k, v in [
            ('发现端点数',          str(s['total_endpoints'])),
            ('测试用例数',          str(len(tf))),
            ('通过 / 失败',         f'{pc} / {fc}'),
            ('断言总数',            str(a['total_assertions'])),
            ('断言通过率',          a['pass_rate']),
            ('接口覆盖率',          s['coverage_rate']),
            ('P0 覆盖率',           s['p0_coverage']),
            ('P1 覆盖率',           s['p1_coverage']),
        ]], '',
        '## 🔍 留痕文件索引', '', '| 文件 | 说明 |', '|------|------|',
        *['| evidence/http-trace/' + os.path.basename(f) + ' | HTTP 请求响应 |' for f in tf],
        '| evidence/assertions/assertions-detail.json | 断言明细 (' + str(a['total_assertions']) + ' 条) |',
        '| evidence/coverage/api-coverage.json | 接口覆盖矩阵 (' + str(s['total_endpoints']) + ' 个端点) |',
        '| BugList.md | Bug 清单（FAIL 用例汇总） |', '',
    ]
    failures = [e for e in c['endpoints'] if e['last_result'] == 'FAIL']
    if failures:
        rows += ['## ❌ 失败端点', '', '| 端点 | 失败次数 |', '|------|----------|',
                 *['| ' + e['method'] + ' ' + e['path'] + ' | ' + str(e['fail_count']) + ' |' for e in failures], '']
    if skipped:
        rows += ['## ❌ 违规：存在 SKIP 用例（所有用例必须执行）', '', '| 用例ID | 违规说明 |', '|--------|----------|',
                 *['| ' + tc_id + ' | ' + reason + ' |' for tc_id, reason in skipped], '']
    if untested:
        rows += ['## ❌ 违规：存在 UNTESTED 端点（所有注册端点必须执行）', '',
                 '| 端点 | 优先级 | 违规说明 |',
                 '|------|--------|----------|',
                 *['| ' + u['method'] + ' ' + u['path'] + ' | ' + u['priority'] + ' | ' + u['reason'] + ' |'
                   for u in untested], '']
    rows += ['## 🔗 佐证材料',
             '- http-trace/ (' + str(len(tf)) + ' 个文件)',
             '- evidence/assertions/assertions-detail.json',
             '- evidence/coverage/api-coverage.json']
    with open(out_md, 'w') as f: f.write('\n'.join(rows))
    print('[gen] audit-summary.md ->', out_md)

# ─── Markdown report ─────────────────────────────────────────

def cmd_report(assert_file, coverage_file, trace_dir, out_report, timestamp, api_url):
    a = load(assert_file); c = load(coverage_file)
    tf = traces(trace_dir)
    pc, fc, sc = _count_traces(tf)
    s  = c['summary']
    skipped       = _load_skipped_cases(assert_file)
    failed_detail = _load_failed_cases_with_io(assert_file, trace_dir)
    untested      = _load_untested_endpoints(coverage_file)
    # 新规则：所有 UNTESTED/SKIP 均为违规
    missing_untested = untested
    missing_skip     = skipped

    rows = [
        '# 集成测试报告', '',
        '**执行时间**: ' + timestamp + '  **后端**: ' + api_url, '',
        '> 合规声明：所有测试结果来自真实 HTTP 请求，禁止 mock 数据（compliance.no_mock=true）', '',
    ]
    if missing_untested or missing_skip:
        rows += ['> ❌ **违规警告**：存在 UNTESTED 端点或 SKIP 用例，所有用例必须执行，请立即修复', '']

    rows += [
        '## 执行摘要', '', '| 指标 | 数值 |', '|------|------|',
        *['| ' + k + ' | ' + v + ' |' for k, v in [
            ('测试端点数',         str(s['total_endpoints'])),
            ('测试用例数',         str(len(tf))),
            ('通过 / 失败', f'{pc} / {fc}'),
            ('接口覆盖率',         s['coverage_rate']),
            ('P0 覆盖率',          s['p0_coverage']),
            ('断言总数',           str(a['total_assertions'])),
            ('断言通过率',         a['pass_rate']),
            ('佐证目录',           'evidence/ (详见 audit-summary.md)'),
        ]], '',
        '## API 覆盖矩阵', '', '| 端点 | 方法 | 优先级 | 状态 | 通过 | 失败 |', '|------|------|--------|------|------|------|',
        *['| ' + ep['path'] + ' | ' + ep['method'] + ' | ' + ep['priority'] + ' | ' +
          ('✅' if ep['last_result']=='PASS' else '❌' if ep['last_result']=='FAIL' else '⬜') +
          ' ' + ep['status'] + ' | ' + str(ep['pass_count']) + ' | ' + str(ep['fail_count']) + ' |'
          for ep in c['endpoints']],
        '', '## ❌ 失败用例详情（含完整出入参）',
    ]
    # 注意事项②：失败用例展示完整出入参
    if failed_detail:
        for fd in failed_detail:
            rows += [
                '', f'### {fd["tc_id"]} — {fd["endpoint"]}', '',
                f'**实际状态码**: `{fd["actual_status"]}`', '',
            ]
            if fd['req_body'] is not None:
                rows += ['**请求体**:', '```json',
                         json.dumps(fd['req_body'], ensure_ascii=False, indent=2),
                         '```', '']
            if fd['resp_body'] is not None:
                resp_str = (json.dumps(fd['resp_body'], ensure_ascii=False, indent=2)
                            if isinstance(fd['resp_body'], (dict, list))
                            else str(fd['resp_body'])[:800])
                rows += ['**响应体**:', '```json', resp_str, '```', '']
            if fd['curl_equivalent']:
                rows += ['**可复现命令**:', '```bash', fd['curl_equivalent'], '```', '']
            rows += ['**失败断言**:', '']
            for x in fd['fail_assertions']:
                rows += [
                    f'- ❌ **{x.get("description", "")}**',
                    f'  - 预期: `{x.get("expected", "")}`  实际: `{x.get("actual", "")}`',
                    f'  - 原因: {x.get("message") or "值不匹配"}',
                ]
    else:
        rows += ['', '所有断言均通过。']

    # 注意事项③：跳过用例及原因
    if skipped:
        rows += ['', '## ❌ 违规：存在 SKIP 用例（所有用例必须执行）', '',
                 '| 用例ID | 违规说明 |', '|--------|----------|',
                 *['| ' + tc_id + ' | ' + reason + ' |' for tc_id, reason in skipped], '']

    rows += ['', '## ❌ 违规：存在 UNTESTED 端点（所有注册端点必须执行）']
    if untested:
        rows += ['', '| 端点 | 方法 | 优先级 | 违规说明 |',
                 '|------|------|--------|----------|',
                 *['| ' + u['path'] + ' | ' + u['method'] + ' | ' + u['priority'] + ' | ' + u['reason'] + ' |'
                   for u in untested]]
    else:
        rows += ['', '所有已发现端点均已测试。']
    with open(out_report, 'w') as f: f.write('\n'.join(rows))
    print('[gen] report.md ->', out_report)

# ─── JSON results ────────────────────────────────────────────

def cmd_results(assert_file, coverage_file, trace_dir, out_json, timestamp):
    a = load(assert_file); c = load(coverage_file)
    tf = traces(trace_dir)
    pc, fc, _ = _count_traces(tf)
    total_ms = 0
    tests    = []
    for path in tf:
        tr      = load(path)
        tc_id   = 'TC-' + str(tr['seq']).zfill(3)
        ms      = tr.get('duration_ms') or 0
        total_ms += ms
        tc_data = next((d for d in a['details'] if d['id'] == tc_id), {})
        asrts   = tc_data.get('assertions', [])
        result  = tr.get('result', 'UNKNOWN')
        entry = {
            'id':       tc_id,
            'name':     tr['test_case'],
            'endpoint': tr['request']['method'] + ' ' + tr['request']['url'],
            'priority': tr['priority'],
            'status':   result,
            'executor': tr.get('executor', '-'),
            'duration_ms':         ms,
            'assertions_passed':   sum(1 for x in asrts if x.get('result') == 'PASS'),
            'assertions_failed':   sum(1 for x in asrts if x.get('result') == 'FAIL'),
            'compliance':          tr.get('compliance', {}),
            'evidence_links': {
                'http_trace':  'evidence/http-trace/' + os.path.basename(path),
                'assertions':  'evidence/assertions/assertions-detail.json'
            }
        }
        # SKIP 不再被允许，如出现 SKIP 记为违规
        if result == 'SKIP':
            entry['violation'] = '违规：用例被跳过，所有用例必须执行'
        # 注意事项②：失败时附完整出入参
        if result == 'FAIL':
            fd = tr.get('failure_detail', {})
            entry['failure_detail'] = {
                'request_body':  fd.get('request_body',  tr['request'].get('body')),
                'response_body': fd.get('response_body', tr['response'].get('body')),
                'actual_status': fd.get('actual_status', tr['response'].get('status_code')),
                'curl_equivalent': tr['request'].get('curl_equivalent', ''),
            }
        tests.append(entry)

    s = c['summary']
    out = {
        'generated_at': timestamp,
        'compliance': {'no_mock': True, 'source': 'real_http_requests'},
        'summary': {
            'total':    len(tf),
            'passed':   pc,
            'failed':   fc,
            'duration_ms':          total_ms,
            'coverage_rate':        s['coverage_rate'],
            'p0_coverage':          s['p0_coverage'],
            'assertion_pass_rate':  a['pass_rate'],
        },
        'tests': tests
    }
    os.makedirs(os.path.dirname(out_json) or '.', exist_ok=True)
    with open(out_json, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('[gen] results.json ->', out_json)

# ─── HTML report（新增）─────────────────────────────────────

def cmd_html(assert_file, coverage_file, trace_dir, out_html, timestamp, api_url):
    a = load(assert_file); c = load(coverage_file)
    tf = traces(trace_dir)
    pc, fc, sc = _count_traces(tf)
    s         = c['summary']
    pass_rate = round(pc / (pc + fc) * 100, 1) if (pc + fc) > 0 else 0
    bug_count = fc   # FAIL 数 = Bug 数
    skipped_cases   = _load_skipped_cases(assert_file)
    failed_with_io  = {fd['tc_id']: fd for fd in _load_failed_cases_with_io(assert_file, trace_dir)}
    untested_eps    = _load_untested_endpoints(coverage_file)
    # 新规则：有任何 UNTESTED 或 SKIP 均为违规
    missing_any     = bool(untested_eps) or bool(skipped_cases)

    # ── 从 trace 读取完整信息 ────────────────────────────────
    trace_data = []
    for path in tf:
        tr      = load(path)
        tc_id   = 'TC-' + str(tr['seq']).zfill(3)
        tc_data = next((d for d in a['details'] if d['id'] == tc_id), {})
        name    = tr.get('test_case', '')
        result  = tr.get('result', 'UNKNOWN')

        # 推断 category（结果只有 PASS / FAIL）
        if '边界值' in name or '超上限' in name or '特殊字符' in name:
            cat = 'boundary'
        elif '缺失' in name or '无效' in name or '错误' in name:
            cat = 'error'
        else:
            cat = 'happy_path'

        trace_data.append({
            'tc_id':       tc_id,
            'name':        name,
            'method':      tr['request']['method'],
            'path':        tr['request']['url'],
            'priority':    tr.get('priority', 'P1'),
            'category':    cat,
            'result':      result,
            'status_code': tr['response']['status_code'],
            'duration_ms': tr.get('duration_ms', 0),
            'executor':    tr.get('executor', '-'),
            'assertions':  tc_data.get('assertions', []),
            'design_note': '',
            'req_body':    tr['request'].get('body'),
            'resp_body':   tr['response'].get('body'),
            'curl':        tr['request'].get('curl_equivalent', ''),
            'fd':          failed_with_io.get(tc_id, {}),
        })

    # ── 覆盖矩阵行 ──────────────────────────────────────────
    coverage_rows = ''
    for ep in c['endpoints']:
        icon    = '✅' if ep['last_result'] == 'PASS' else ('❌' if ep['last_result'] == 'FAIL' else '⬜')
        pri_cls = 'badge-p0' if ep['priority'] == 'P0' else ('badge-p1' if ep['priority'] == 'P1' else 'badge-p2')
        is_untested = ep.get('status') == 'UNTESTED'
        status_cell = f'{icon} {ep["status"]}'
        if is_untested:
            status_cell += ' — <span class="reason-missing">❌ 违规：该端点未被测试，所有端点必须执行</span>'
        coverage_rows += f'''
        <tr class="{'untested-missing-row' if is_untested else ''}">
          <td><code>{ep['method']}</code></td>
          <td>{ep['path']}</td>
          <td><span class="badge {pri_cls}">{ep['priority']}</span></td>
          <td>{status_cell}</td>
          <td class="num">{ep['pass_count']}</td>
          <td class="num">{ep['fail_count']}</td>
        </tr>'''

    # ── 用例详情行（按 category 分组） ──────────────────────
    cat_label = {
        'happy_path': '✅ 正常场景（有效等价类）',
        'boundary':   '⚠️ 边界值 / 等价类扩展',
        'error':      '❌ 错误场景（无效等价类）',
    }
    cat_order = ['happy_path', 'boundary', 'error']
    grouped   = {k: [] for k in cat_order}
    for td in trace_data:
        grouped.setdefault(td['category'], []).append(td)

    detail_rows = ''
    for cat in cat_order:
        tds = grouped.get(cat, [])
        if not tds:
            continue
        cat_pass = sum(1 for t in tds if t['result'] == 'PASS')
        label    = cat_label.get(cat, cat)
        summary  = f'{cat_pass}/{len(tds)} 通过'
        detail_rows += f'<tr class="group-header"><td colspan="8">{label} — {summary}</td></tr>\n'

        for td in tds:
            result  = td['result']
            is_fail = (result == 'FAIL')

            r_cls     = 'pass-row' if result == 'PASS' else 'fail-row'
            badge_cls = 'badge-pass' if result == 'PASS' else 'badge-fail'
            badge     = f'<span class="badge {badge_cls}">{result}</span>'
            pri_cls   = 'badge-p0' if td['priority'] == 'P0' else ('badge-p1' if td['priority'] == 'P1' else 'badge-p2')

            # 断言统计列
            a_pass  = sum(1 for x in td['assertions'] if x.get('result') == 'PASS')
            a_total = len(td['assertions'])
            a_cell  = f'{a_pass}/{a_total}' if a_total else '-'

            # 失败断言提示
            fail_tips = ''
            for x in td['assertions']:
                if x.get('result') == 'FAIL':
                    fail_tips += (f'<div class="fail-tip">✗ {x.get("description","")} | '
                                  f'预期: {x.get("expected","")} 实际: {x.get("actual","")}</div>')

            # 失败出入参展开块
            io_block = ''
            if is_fail and td['fd']:
                fd        = td['fd']
                req_json  = (json.dumps(fd.get('req_body'), ensure_ascii=False, indent=2)
                             if fd.get('req_body') is not None else '无')
                resp_raw  = fd.get('resp_body')
                resp_json = (json.dumps(resp_raw, ensure_ascii=False, indent=2)
                             if isinstance(resp_raw, (dict, list))
                             else str(resp_raw)[:600] if resp_raw else '无')
                curl_cmd  = fd.get('curl_equivalent', '') or td['curl']
                fail_rsn  = fd.get('fail_reason', '断言不匹配，详见 assertions')
                io_block  = f'''
                <details class="io-detail">
                  <summary>📋 失败原因：{fail_rsn}（actual_status={fd.get("actual_status", "?")}）</summary>
                  <div class="io-section"><strong>请求体</strong><pre>{req_json}</pre></div>
                  <div class="io-section"><strong>响应体</strong><pre>{resp_json}</pre></div>
                  {'<div class="io-section"><strong>可复现命令</strong><pre>' + curl_cmd + '</pre></div>' if curl_cmd else ''}
                </details>'''

            detail_rows += f'''
        <tr class="{r_cls}">
          <td>{td['tc_id']}</td>
          <td>{td['name']}</td>
          <td><span class="badge {pri_cls}">{td['priority']}</span></td>
          <td><code>{td['method']}</code></td>
          <td class="num">{td['status_code']}</td>
          <td class="num">{td['duration_ms']} ms</td>
          <td class="num">{a_cell}</td>
          <td>{badge}{fail_tips}{io_block}</td>
        </tr>\n'''

    # ── SKIP 违规区块（理论上不应出现） ──────────────────────
    skip_section = ''
    if skipped_cases:
        skip_rows = ''.join(
            f'<tr class="untested-missing-row"><td>{tc_id}</td><td>{reason}</td></tr>'
            for tc_id, reason in skipped_cases
        )
        skip_section = f'''
    <h2 class="section-title fail">❌ 违规：存在 SKIP 用例（所有用例必须执行）</h2>
    <table><thead><tr><th>用例ID</th><th>违规说明</th></tr></thead>
    <tbody>{skip_rows}</tbody></table>'''

    # ── 失败端点汇总 ─────────────────────────────────────────
    failures = [e for e in c['endpoints'] if e['last_result'] == 'FAIL']
    fail_section = ''
    if failures:
        fail_rows = ''.join(
            f'<tr><td><code>{e["method"]}</code></td><td>{e["path"]}</td>'
            f'<td class="num">{e["fail_count"]}</td></tr>'
            for e in failures
        )
        fail_section = f'''
    <h2 class="section-title fail">❌ 失败端点</h2>
    <table><thead><tr><th>方法</th><th>路径</th><th class="num">失败次数</th></tr></thead>
    <tbody>{fail_rows}</tbody></table>'''

    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>集成测试报告 — {api_url}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
         background: #f7f8fa; color: #222; font-size: 14px; line-height: 1.6; }}
  header {{ background: #1e2230; color: #fff; padding: 24px 32px; }}
  header h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 4px; }}
  header p {{ color: #8a9bb5; font-size: 13px; }}
  .compliance-bar {{ background: #1a3a2a; color: #4ade80; font-size: 12px;
                     padding: 6px 32px; letter-spacing: .02em; }}
  main {{ max-width: 1280px; margin: 24px auto; padding: 0 24px; }}
  .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
                    gap: 12px; margin-bottom: 28px; }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px 20px; }}
  .card .label {{ font-size: 12px; color: #7b8496; margin-bottom: 6px; }}
  .card .value {{ font-size: 26px; font-weight: 700; }}
  .card.pass .value {{ color: #16a34a; }}
  .card.fail .value {{ color: #dc2626; }}
  .card.skip .value {{ color: #d97706; }}
  .card.info .value {{ color: #2563eb; }}
  .section-title {{ font-size: 16px; font-weight: 600; margin: 28px 0 12px;
                    padding-left: 10px; border-left: 3px solid #6366f1; }}
  .section-title.fail {{ border-color: #dc2626; }}
  .section-title.skip {{ border-color: #d97706; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;
           margin-bottom: 24px; font-size: 13px; }}
  thead th {{ background: #f1f3f8; padding: 10px 14px; text-align: left;
              font-weight: 600; color: #444; border-bottom: 1px solid #e5e7eb; }}
  tbody td {{ padding: 9px 14px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  .group-header td {{ background: #eef0f8; font-weight: 600; color: #3b3f5c;
                      font-size: 13px; padding: 8px 14px; }}
  .pass-row {{ background: #f0fdf4; }}
  .fail-row {{ background: #fef2f2; }}
  .skip-row {{ background: #fffbeb; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  code {{ background: #f1f3f8; padding: 1px 6px; border-radius: 4px;
          font-size: 12px; font-family: "SF Mono", monospace; }}
  pre  {{ background: #f8f9fb; border: 1px solid #e5e7eb; border-radius: 6px;
          padding: 10px 12px; font-size: 12px; font-family: "SF Mono", monospace;
          white-space: pre-wrap; word-break: break-all; max-height: 300px;
          overflow-y: auto; margin: 6px 0; }}
  .badge {{ display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 20px; }}
  .badge-pass {{ background: #dcfce7; color: #166534; }}
  .badge-fail {{ background: #fee2e2; color: #991b1b; }}
  .badge-skip {{ background: #fef3c7; color: #92400e; }}
  .badge-p0   {{ background: #fef9c3; color: #854d0e; }}
  .badge-p1   {{ background: #dbeafe; color: #1e40af; }}
  .badge-p2   {{ background: #f3f4f6; color: #6b7280; }}
  .fail-tip   {{ font-size: 11px; color: #b91c1c; margin-top: 3px;
                 padding: 2px 6px; background: #fff1f1; border-radius: 4px; }}
  .skip-note  {{ font-size: 11px; color: #92400e; margin-top: 3px;
                 padding: 2px 6px; background: #fef3c7; border-radius: 4px; }}
  .progress-bar {{ height: 8px; background: #e5e7eb; border-radius: 4px;
                   overflow: hidden; margin: 6px 0; }}
  .progress-bar .fill {{ height: 100%; background: #16a34a; border-radius: 4px; }}
  .progress-bar .fill.warn   {{ background: #f59e0b; }}
  .progress-bar .fill.danger {{ background: #dc2626; }}
  /* 违规高亮：无原因的 UNTESTED / SKIP 行 */
  .untested-missing-row td, .skip-missing-row td {{ background: #fff7ed !important; }}
  .reason-missing {{ font-size: 11px; color: #b45309; background: #fef3c7;
                     padding: 1px 6px; border-radius: 4px; font-weight: 600; }}
  .reason-ok {{ font-size: 11px; color: #065f46; background: #d1fae5;
                padding: 1px 6px; border-radius: 4px; }}
  /* 合规警告横幅 */
  .compliance-warn {{ background: #fef3c7; border-left: 4px solid #f59e0b;
                      padding: 10px 20px; margin-bottom: 20px; font-size: 13px;
                      color: #92400e; border-radius: 0 6px 6px 0; }}
  details.io-detail {{ margin-top: 6px; }}
  details.io-detail summary {{ cursor: pointer; font-size: 11px; color: #2563eb;
                                padding: 3px 6px; background: #eff6ff; border-radius: 4px;
                                display: inline-block; }}
  .io-section {{ margin-top: 6px; }}
  .io-section strong {{ font-size: 11px; color: #555; }}
</style>
</head>
<body>
<header>
  <h1>🧪 集成测试报告</h1>
  <p>后端: {api_url} &nbsp;|&nbsp; 执行时间: {timestamp} &nbsp;|&nbsp; 生成: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</header>
<div class="compliance-bar">✅ 合规声明：所有测试结果来自真实 HTTP 请求，禁止 mock 数据（compliance.no_mock=true）</div>
{'<div class="compliance-warn">❌ <strong>违规警告</strong>：存在 UNTESTED 端点或 SKIP 用例，所有用例必须执行，请立即修复（高亮行为违规项）</div>' if missing_any else ''}
<main>

  <div class="summary-cards">
    <div class="card"><div class="label">测试用例</div><div class="value">{len(tf)}</div></div>
    <div class="card pass"><div class="label">通过</div><div class="value">{pc}</div></div>
    <div class="card fail"><div class="label">失败</div><div class="value">{fc}</div></div>
    <div class="card {'fail' if bug_count > 0 else 'pass'}">
      <div class="label">Bug 数</div>
      <div class="value">{bug_count}</div>
      {'<div style="font-size:11px;margin-top:4px"><a href="BugList.md" style="color:inherit">查看 BugList.md →</a></div>' if bug_count > 0 else ''}
    </div>
    <div class="card info"><div class="label">通过率</div><div class="value">{pass_rate}%</div>
      <div class="progress-bar"><div class="fill{'warn' if pass_rate < 80 else ('danger' if pass_rate < 60 else '')}"
           style="width:{pass_rate}%"></div></div></div>
    <div class="card info"><div class="label">接口覆盖率</div><div class="value">{s['coverage_rate']}</div></div>
    <div class="card info"><div class="label">P0 覆盖率</div><div class="value">{s['p0_coverage']}</div></div>
    <div class="card info"><div class="label">断言通过率</div><div class="value">{a['pass_rate']}</div></div>
  </div>

  <h2 class="section-title">📋 API 覆盖矩阵</h2>
  <table>
    <thead><tr><th>方法</th><th>路径</th><th>优先级</th><th>状态</th><th class="num">通过</th><th class="num">失败</th></tr></thead>
    <tbody>{coverage_rows}</tbody>
  </table>

  {fail_section}

  {skip_section}

  <h2 class="section-title">🔬 用例详情（含等价类/边界值分组）</h2>
  <table>
    <thead><tr>
      <th>ID</th><th>用例名称</th><th>优先级</th><th>方法</th>
      <th class="num">状态码</th><th class="num">耗时</th><th class="num">断言</th><th>结果</th>
    </tr></thead>
    <tbody>{detail_rows}</tbody>
  </table>

</main>
</body>
</html>'''

    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    print('[gen] report.html ->', out_html)

# ─── BugList ─────────────────────────────────────────────────

def _bug_severity(fc):
    """
    从失败类型和端点优先级推断 Bug 严重等级。
    P0 端点 + 状态码失败  → 严重 (Critical)
    状态码失败 / actual=0 → 高 (High)
    字段断言失败           → 中 (Medium)
    其他                  → 低 (Low)
    """
    actual  = fc.get('actual_status', 0)
    fail_as = fc.get('fail_assertions', [])
    types   = {a.get('type') for a in fail_as}

    if actual == 0:
        return '🔴 严重 (Critical)', '网络错误或超时，接口完全不可达'
    if 'status_code' in types:
        return '🟠 高 (High)', '状态码与预期不符，接口返回异常'
    if 'json_field' in types:
        return '🟡 中 (Medium)', '响应字段断言失败，返回数据不符合预期'
    return '🔵 低 (Low)', '其他断言失败'

def _build_bug_title(endpoint, first_fail, fc):
    """从端点信息和首条失败断言提炼 Bug 标题"""
    actual_status = fc.get('actual_status', 0)
    if actual_status == 0:
        return f'{endpoint} — 请求失败（网络错误或超时）'
    if first_fail.get('type') == 'status_code':
        expected = first_fail.get('expected', '?')
        return f'{endpoint} — 状态码异常（预期 {expected}，实际 {actual_status}）'
    if first_fail.get('type') == 'json_field':
        desc = first_fail.get('description', '')
        return f'{endpoint} — 响应字段断言失败（{desc}）'
    return f'{endpoint} — 测试失败（HTTP {actual_status}）'

def _build_error_info(fc):
    """将所有失败断言整理为错误信息列表"""
    lines   = []
    fail_as = fc.get('fail_assertions', [])
    for a in fail_as:
        a_type = a.get('type', '')
        desc   = a.get('description', '')
        exp    = a.get('expected', '')
        act    = a.get('actual', '')
        msg    = a.get('message', '') or ''
        if a_type == 'status_code':
            lines.append(f'- ❌ **状态码不符**：预期 `{exp}`，实际 `{act}`'
                         + (f'（{msg}）' if msg else ''))
        elif a_type == 'json_field':
            lines.append(f'- ❌ **{desc}**：预期 `{exp}`，实际 `{act}`')
        else:
            lines.append(f'- ❌ {desc}：预期 `{exp}`，实际 `{act}`')
    if not lines:
        lines.append('- ❌ 断言执行失败，详见 trace 文件')
    return lines

def cmd_buglist(assert_file, coverage_file, trace_dir, out_buglist, timestamp, api_url):
    """
    生成 BugList.md。
    每条 Bug 包含：Bug编号 / 严重等级 / 标题 / 错误信息 / 对应用例编号
                   实际状态码 / 请求体 / 响应体 / curl 复现命令
    """
    failed_cases = _load_failed_cases_with_io(assert_file, trace_dir)

    # ── 无 Bug ───────────────────────────────────────────────
    if not failed_cases:
        content = '\n'.join([
            '# Bug 清单', '',
            f'**生成时间**: {timestamp}  **后端**: {api_url}', '',
            '> ✅ 本次测试未发现 Bug，所有用例均通过。',
        ])
        with open(out_buglist, 'w', encoding='utf-8') as f:
            f.write(content)
        print('[gen] BugList.md ->', out_buglist, '(无 Bug)')
        return 0

    total = len(failed_cases)

    # ── 索引表 ───────────────────────────────────────────────
    index_rows = ['| Bug编号 | 严重等级 | 标题 | 对应用例 |',
                  '|---------|----------|------|----------|']

    # ── 详情区块 ─────────────────────────────────────────────
    detail_blocks = []

    for idx, fc in enumerate(failed_cases, 1):
        bug_id   = f'BUG-{idx:03d}'
        tc_id    = fc['tc_id']
        endpoint = fc.get('endpoint', '')

        fail_as    = fc.get('fail_assertions', [])
        first_fail = fail_as[0] if fail_as else {}

        title            = _build_bug_title(endpoint, first_fail, fc)
        severity, sev_desc = _bug_severity(fc)
        error_lines      = _build_error_info(fc)

        # 从 trace 的 failure_detail 取 fail_reason
        a_obj = load(assert_file)
        tr_map = {}
        for tpath in traces(trace_dir):
            try:
                tr = load(tpath)
                key = 'TC-' + str(tr['seq']).zfill(3)
                tr_map[key] = tr
            except Exception:
                pass
        tr      = tr_map.get(tc_id, {})
        tc_name = tr.get('test_case', tc_id)
        fd_raw  = tr.get('failure_detail', {})
        fail_reason = (fd_raw.get('fail_reason')
                       or (error_lines[0].lstrip('- ❌ ') if error_lines else '断言失败'))

        # 索引行
        index_rows.append(
            f'| [{bug_id}](#{bug_id.lower()}) | {severity} | {title} | `{tc_id}` |'
        )

        # 详情块
        req_body  = fc.get('req_body')
        resp_body = fc.get('resp_body')
        curl_cmd  = fc.get('curl_equivalent', '')

        req_section = []
        if req_body is not None:
            req_str = (json.dumps(req_body, ensure_ascii=False, indent=2)
                       if isinstance(req_body, (dict, list)) else str(req_body))
            req_section = ['', '**请求体**', '', '```json', req_str, '```']

        resp_section = []
        if resp_body is not None:
            resp_str = (json.dumps(resp_body, ensure_ascii=False, indent=2)
                        if isinstance(resp_body, (dict, list))
                        else str(resp_body)[:1000])
            resp_section = ['', '**响应体**', '', '```json', resp_str, '```']

        curl_section = []
        if curl_cmd:
            curl_section = ['', '**复现命令**', '', '```bash', curl_cmd, '```']

        block = [
            f'## {bug_id}', '',
            '| 字段 | 内容 |',
            '|------|------|',
            f'| **Bug 编号** | `{bug_id}` |',
            f'| **严重等级** | {severity} |',
            f'| **标题** | {title} |',
            f'| **对应用例** | `{tc_id}` — {tc_name} |',
            f'| **接口** | `{endpoint}` |',
            f'| **实际状态码** | `{fc.get("actual_status", "?")}` |',
            f'| **错误原因** | {fail_reason} |',
            '',
            '**错误信息**', '',
            *error_lines,
            *req_section,
            *resp_section,
            *curl_section,
            '', '---', '',
        ]
        detail_blocks.append(block)

    # ── 组装完整文档 ─────────────────────────────────────────
    rows = [
        '# Bug 清单', '',
        f'**生成时间**: {timestamp}  **后端**: {api_url}', '',
        f'> 本次测试共发现 **{total}** 个 Bug。',
        '', '---', '',
        '## 索引', '',
        *index_rows,
        '', '---', '',
        '## 详情', '',
    ]
    for block in detail_blocks:
        rows.extend(block)

    with open(out_buglist, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows))
    print(f'[gen] BugList.md -> {out_buglist} ({total} 个 Bug)')
    return total


# ─── all（一次生成全部报告）─────────────────────────────────

def cmd_all(assert_file, coverage_file, trace_dir, base_dir, timestamp, api_url):
    os.makedirs(base_dir, exist_ok=True)
    cmd_summary(assert_file, coverage_file, trace_dir,
                os.path.join(base_dir, 'audit-summary.md'), timestamp, api_url)
    cmd_report(assert_file, coverage_file, trace_dir,
               os.path.join(base_dir, 'report.md'), timestamp, api_url)
    out_json = os.path.join(base_dir, 'results.json')
    cmd_results(assert_file, coverage_file, trace_dir, out_json, timestamp)
    cmd_html(assert_file, coverage_file, trace_dir,
             os.path.join(base_dir, 'report.html'), timestamp, api_url)
    bug_count = cmd_buglist(assert_file, coverage_file, trace_dir,
                            os.path.join(base_dir, 'BugList.md'), timestamp, api_url)

    r      = load(out_json)
    c_data = load(coverage_file)
    s      = r['summary']

    # 统计违规项
    untested_all = _load_untested_endpoints(coverage_file)
    skipped_all  = _load_skipped_cases(assert_file)
    missing_untested = untested_all
    missing_skip     = skipped_all

    print('SUMMARY: 端点={ep} 用例={total} 通过={passed} 失败={failed} Bug数={bugs} '
          'P0覆盖={p0} 断言通过率={apr}'.format(
        ep=c_data['summary']['total_endpoints'],
        total=s['total'], passed=s['passed'], failed=s['failed'],
        bugs=bug_count,
        p0=s['p0_coverage'], apr=s['assertion_pass_rate']
    ))
    print('FILES: ' + base_dir + '/report.md | report.html | audit-summary.md | results.json | BugList.md')

    if missing_untested:
        print(f'[ERROR] {len(missing_untested)} 个端点 UNTESTED（违规：所有注册端点必须执行）：'
              + ', '.join(u["method"] + " " + u["path"] for u in missing_untested),
              file=sys.stderr)
    if missing_skip:
        print(f'[ERROR] {len(missing_skip)} 个用例 SKIP（违规：所有用例必须执行）：'
              + ', '.join(tid for tid, _ in missing_skip),
              file=sys.stderr)

# ─── 入口 ────────────────────────────────────────────────────

if __name__ == '__main__':
    subcmd = sys.argv[1]
    if   subcmd == 'summary': cmd_summary(*sys.argv[2:])
    elif subcmd == 'report':  cmd_report(*sys.argv[2:])
    elif subcmd == 'results': cmd_results(*sys.argv[2:])
    elif subcmd == 'html':    cmd_html(*sys.argv[2:])
    elif subcmd == 'buglist': cmd_buglist(*sys.argv[2:])
    elif subcmd == 'all':     cmd_all(*sys.argv[2:])
    else: print('unknown command:', subcmd); sys.exit(1)
