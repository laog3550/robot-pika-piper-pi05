#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
/usr/bin/python3 - "$repo_root" <<'PY'
import importlib.util,sys
from unittest.mock import Mock
path=sys.argv[1]+'/src/pi05_pika_input/scripts/side_input.py'
spec=importlib.util.spec_from_file_location('side_input',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ROSException(Exception):pass
ros=Mock();ros.ROSException=ROSException
pub=Mock();message=object()
ros.is_shutdown.return_value=False
m.forward(pub,message,ros);pub.publish.assert_called_once_with(message)
pub.reset_mock();ros.is_shutdown.return_value=True
m.forward(pub,message,ros);pub.publish.assert_not_called()
# Publisher closes after the initial shutdown check.
ros.is_shutdown.side_effect=[False,True]
pub.publish.side_effect=ROSException('closed topic')
m.forward(pub,message,ros)
# An operational error must remain visible outside shutdown.
ros.is_shutdown.side_effect=None;ros.is_shutdown.return_value=False
try:m.forward(pub,message,ros)
except ROSException:pass
else:raise AssertionError('operational fault hidden')
print('Pika shutdown forwarding tests: PASS')
PY
