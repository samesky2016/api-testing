#!/usr/bin/env bash
# record.sh - 集成测试留痕脚本
# 规则：所有用例必须执行，不允许 UNTESTED（端点注册后必须被测试）
# 需预设 EVIDENCE_DIR 环境变量
# 命令: init | register-endpoint | trace | assert | cover | summary | report | results | html | buglist | all

# 兼容性：pipefail 是 bash 特性，/bin/sh 不支持。
# 检测 bash 后再启用；sh 降级执行时跳过，不影响功能。
set -eu
[ -n "${BASH_VERSION:-}" ] && set -o pipefail || true
BASE="${EVIDENCE_DIR:?需要设置 EVIDENCE_DIR}"
TRACE_DIR="$BASE/http-trace"
ASSERT_FILE="$BASE/assertions/assertions-detail.json"
COVERAGE_FILE="$BASE/coverage/api-coverage.json"
SCRIPTS_DIR="$(dirname "$0")"
cmd="${1:-}"

if [[ "$cmd" == "init" ]]; then
  mkdir -p "$TRACE_DIR" "$BASE/assertions" "$BASE/coverage"
  NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo '{"generated_at":"'"$NOW"'","total_assertions":0,"passed":0,"failed":0,"pass_rate":"0%","details":[]}' > "$ASSERT_FILE"
  echo '{"generated_at":"'"$NOW"'","summary":{"total_endpoints":0,"tested":0,"untested":0,"coverage_rate":"0%","p0_coverage":"0%","p1_coverage":"0%"},"endpoints":[]}' > "$COVERAGE_FILE"
  echo "[record] 初始化: $BASE"

elif [[ "$cmd" == "register-endpoint" ]]; then
  # register-endpoint <METHOD> <PATH> <PRIORITY>
  # 注：所有注册的端点必须在本次测试中被 cover，不允许保持 UNTESTED 状态
  python3 -c "
import json
with open('$COVERAGE_FILE') as f: d = json.load(f)
d['endpoints'].append({'method':'$2','path':'$3','priority':'$4',
    'status':'UNTESTED','test_cases':[],'pass_count':0,'fail_count':0,'last_result':None})
d['summary']['total_endpoints'] = len(d['endpoints'])
d['summary']['untested'] = sum(1 for e in d['endpoints'] if e['status']=='UNTESTED')
with open('$COVERAGE_FILE','w') as f: json.dump(d,f,ensure_ascii=False)
"
  echo "[record] 注册: $2 $3 ($4)"

elif [[ "$cmd" == "trace" ]]; then
  # [已废弃] trace 子命令在 v0.9 起由 run_test.py 内部直接写入留痕，
  # record.sh trace 不再被主流程调用。保留仅供向后兼容，将在 v1.0 移除。
  echo "[record] ⚠️  trace 子命令已废弃（v0.9+），留痕由 run_test.py 直接处理。" >&2
  # 原有逻辑保留，不实际执行写入，直接返回
  exit 0

elif [[ "$cmd" == "assert" ]]; then
  # assert <TC_ID> <ENDPOINT> <TYPE> <DESC> <EXPECTED> <ACTUAL> <r> [MSG]
  PYFILE=$(mktemp /tmp/ra_XXXXXX.py)
  cat > "$PYFILE" << 'PYEOF'
import json, sys
af,tc,ep,tp,desc,exp,act,res = sys.argv[1:9]
msg = sys.argv[9] if len(sys.argv)>9 else ""
with open(af) as f: d = json.load(f)
t = next((x for x in d['details'] if x.get('id')==tc), None)
if t is None:
    t = {'id':tc,'endpoint':ep,'assertions':[]}; d['details'].append(t)
t['assertions'].append({'id':'A'+str(d['total_assertions']+1).zfill(3),'type':tp,'description':desc,
  'expected':exp,'actual':act,'result':res,'message':msg or None})
d['total_assertions']+=1
if res=='PASS': d['passed']+=1
else: d['failed']+=1
n=d['total_assertions']; d['pass_rate']=str(round(d['passed']/n*100,1))+'%' if n else '0%'
with open(af,'w') as f: json.dump(d,f,ensure_ascii=False,indent=2)
PYEOF
  python3 "$PYFILE" "$ASSERT_FILE" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "${9:-}"
  rm -f "$PYFILE"
  echo "[record] 断言 $8: $4 - $5"

elif [[ "$cmd" == "cover" ]]; then
  # cover <METHOD> <PATH> <TC_NAME> <r>
  PYFILE=$(mktemp /tmp/rc_XXXXXX.py)
  cat > "$PYFILE" << 'PYEOF'
import json, sys
cf,meth,path,tc,res = sys.argv[1:6]
with open(cf) as f: d = json.load(f)
for ep in d['endpoints']:
    if ep['method']==meth and ep['path']==path:
        ep['status']='TESTED'; ep['test_cases'].append(tc)
        if res=='PASS': ep['pass_count']+=1
        else: ep['fail_count']+=1
        ep['last_result']=res; break
t=len(d['endpoints']); te=[e for e in d['endpoints'] if e['status']=='TESTED']
p0=[e for e in d['endpoints'] if e['priority']=='P0']
p0t=[e for e in p0 if e['status']=='TESTED']
p1=[e for e in d['endpoints'] if e['priority']=='P1']
p1t=[e for e in p1 if e['status']=='TESTED']
s=d['summary']; s['tested']=len(te); s['untested']=t-len(te)
s['coverage_rate']=str(round(len(te)/t*100,1))+'%' if t else '0%'
s['p0_coverage']=str(round(len(p0t)/len(p0)*100,1))+'%' if p0 else 'N/A'
s['p1_coverage']=str(round(len(p1t)/len(p1)*100,1))+'%' if p1 else 'N/A'
with open(cf,'w') as f: json.dump(d,f,ensure_ascii=False,indent=2)
PYEOF
  python3 "$PYFILE" "$COVERAGE_FILE" "$2" "$3" "$4" "$5"
  rm -f "$PYFILE"
  echo "[record] 覆盖: $2 $3 → $5"

elif [[ "$cmd" == "summary" ]]; then
  python3 "$SCRIPTS_DIR/gen_reports.py" summary "$ASSERT_FILE" "$COVERAGE_FILE" "$TRACE_DIR" "$2" "$3" "$4"

elif [[ "$cmd" == "report" ]]; then
  python3 "$SCRIPTS_DIR/gen_reports.py" report "$ASSERT_FILE" "$COVERAGE_FILE" "$TRACE_DIR" "$2/report.md" "$3" "$4"

elif [[ "$cmd" == "results" ]]; then
  python3 "$SCRIPTS_DIR/gen_reports.py" results "$ASSERT_FILE" "$COVERAGE_FILE" "$TRACE_DIR" "$2/results.json" "$3"

elif [[ "$cmd" == "html" ]]; then
  python3 "$SCRIPTS_DIR/gen_reports.py" html "$ASSERT_FILE" "$COVERAGE_FILE" "$TRACE_DIR" "$2/report.html" "$3" "$4"

elif [[ "$cmd" == "buglist" ]]; then
  # buglist <BASE_DIR> <TIMESTAMP> <API_URL> — 单独生成 BugList.md
  python3 "$SCRIPTS_DIR/gen_reports.py" buglist "$ASSERT_FILE" "$COVERAGE_FILE" "$TRACE_DIR" "$2/BugList.md" "$3" "$4"

elif [[ "$cmd" == "all" ]]; then
  # all <BASE_DIR> <TIMESTAMP> <API_URL> — 生成全部报告（report.md/html/audit-summary/results.json/BugList.md）
  python3 "$SCRIPTS_DIR/gen_reports.py" all "$ASSERT_FILE" "$COVERAGE_FILE" "$TRACE_DIR" "$2" "$3" "$4"

else
  echo "用法: record.sh <init|register-endpoint|assert|cover|summary|report|results|html|buglist|all>"
  echo "      [已废弃: trace — 由 run_test.py 内部处理，v1.0 将移除]"
  exit 1
fi
