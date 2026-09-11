#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checker="${repo_root}/scripts/check_pika_localization.py"

"${repo_root}/scripts/check_pika_localization.sh" --help >/dev/null

/usr/bin/python3 - "${checker}" <<'PY'
import importlib.util
import contextlib
import io
import math
import sys

path = sys.argv[1]
spec = importlib.util.spec_from_file_location("check_pika_localization", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

stats = module.LocalizationStats()
stats.observe_pose((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0), 1.0, "base")
stats.observe_pose((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0), 2.0, "base")
stats.observe_status(True)
rate, failures = module.evaluate(stats.snapshot(), 0.05, 30.0, 1)
assert rate == 40.0
assert failures == []

bad = module.LocalizationStats()
bad.observe_pose((math.nan, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), 2.0, "base")
bad.observe_pose((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), 1.0, "changed")
bad.observe_status(False)
_, failures = module.evaluate(bad.snapshot(), 1.0, 30.0, 2)
assert len(failures) == 6, failures

with contextlib.redirect_stderr(io.StringIO()):
    assert module.main(["--duration", "0"]) == module.EXIT_USAGE
assert module.ros_master_reachable("http://127.0.0.1:9") is False
print("Pika localization checker tests: PASS")
PY

if rg -n 'Publisher|Service|[.]publish[(]|[.]send(all|msg|to)?[(]|open[(]' "${checker}"; then
  echo "localization checker contains a write or ROS server API" >&2
  exit 1
fi
