#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
/usr/bin/python3 - "$repo_root" <<'PY'
import sys,json
sys.path.insert(0,sys.argv[1]+'/scripts')
from diagnose_pika_tracking import Stream,PoseMatch,duration
s=Stream(0.)
s.observe_pose((0.,0.,0.),(0.,0.,0.,1.),.01,'synthetic',.01,.01)
s.observe_status(False,.02)
s.observe_status(False,.04)
s.observe_status(True,.10)
s.observe_status(False,.15)
a=s.snapshot(.20,'static')
assert a['invalid_runs']==2 and a['inaccurate_samples']==3
assert a['longest_invalid_run_ms']==80
assert a['invalid_duration_observed_ms']==130
assert a['first_run_left_censored'] and a['last_run_right_censored']
assert 'first_position' not in json.dumps(a) and 'synthetic' not in json.dumps(a)
match=PoseMatch()
match.observe('raw',1,('fixture',),.1)
match.observe('relay',1,('fixture',),.102)
match.observe('relay',2,('fixture',),.2)
match.observe('raw',2,('different',),.202)
assert match.snapshot()['identical_pose_pairs']==1
assert match.snapshot()['different_pose_pairs']==1
for n in range(5002):match.observe('raw',n+3,('fixture',),.3)
assert len(match.pending['raw'])==5000 and match.evicted==2
assert duration('30')==30
for value in ('0','nan','inf','121'):
    try:duration(value)
    except Exception:pass
    else:raise AssertionError('invalid duration accepted')
print('Pika tracking diagnostic tests: PASS')
PY
if rg -n 'Publisher|Service|[.]publish[(]|[.]send(all|msg|to)?[(]|open[(]|set_param|subprocess|os[.]write' "$repo_root/scripts/diagnose_pika_tracking.py"; then
  printf '%s\n' 'diagnostic contains a write/control API' >&2
  exit 1
fi
