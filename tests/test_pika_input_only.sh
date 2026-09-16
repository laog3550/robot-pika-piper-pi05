#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
/usr/bin/python3 - "$repo_root" <<'PY'
import importlib.util
import pathlib
import sys
import xml.etree.ElementTree as ET
import types
from unittest.mock import Mock, patch
root = pathlib.Path(sys.argv[1])
package = root / 'src/pi05_pika_input'
spec = importlib.util.spec_from_file_location('safe_locator', package/'scripts/safe_locator.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
fake = {'pika_L_code':'fixture-left', 'pika_R_code':'fixture-right'}
assert module.mapping(fake, 'direct') == ('fixture-left', 'fixture-right')
assert module.mapping(fake, 'swapped') == ('fixture-right', 'fixture-left')
for env, order in (({},'direct'),(fake,'unverified'),({'pika_L_code':'same','pika_R_code':'same'},'direct')):
    try: module.mapping(env, order)
    except ValueError: pass
    else: raise AssertionError('unsafe mapping accepted')
# Exercise supervisor without launching hardware, checking argv and cleanup.
ros = types.ModuleType('rospy')
for name in ('init_node','set_param','delete_param','logerr','loginfo'):
    setattr(ros,name,Mock())
ros.get_name = Mock(return_value='/pi05/pika_input/safe_locator')
ros.get_param = Mock(return_value='swapped')
ros.is_shutdown = Mock(return_value=False)
ros.has_param = Mock(return_value=True)
graph = types.ModuleType('rosgraph')
graph.Master = Mock()
graph.Master.return_value.getSystemState.return_value = ([],[],[])
child = Mock()
child.poll.return_value = 0
with patch.dict(sys.modules, {'rospy':ros,'rosgraph':graph}), patch.dict(module.os.environ,fake), patch.object(module.subprocess,'Popen',return_value=child) as spawn:
    assert module.main() == 1
    argv = spawn.call_args[0][0]
    assert not any(value in ' '.join(argv) for value in fake.values())
    assert '__log:=/dev/null' in argv
    assert '/rosout:=/pi05/pika_input/suppressed_rosout' in argv
    assert ros.set_param.call_args_list[0].args[1] == 'fixture-right'
    assert ros.set_param.call_args_list[1].args[1] == 'fixture-left'
    # 映射方向必须被记录，但不得记录任何设备 code 值（mock 缺失该方法会在此暴露）
    assert ros.loginfo.call_count == 1, 'mapping direction must be logged exactly once'
    logged = ' '.join(str(arg) for arg in ros.loginfo.call_args[0])
    assert not any(value in logged for value in fake.values()), 'log must not contain handset codes'
    assert 'swapped' in logged, 'log must contain the applied mapping order'
    ros.delete_param.assert_called_once_with('/pi05/pika_input/safe_locator_backend')
graph.Master.return_value.getSystemState.return_value = ([('/pika_pose_l',['/existing'])],[],[])
with patch.dict(sys.modules, {'rospy':ros,'rosgraph':graph}), patch.dict(module.os.environ,fake), patch.object(module.subprocess,'Popen') as spawn:
    assert module.main() == 1
    spawn.assert_not_called()
graph.Master.return_value.getSystemState.return_value = ([],[],[('/left_arm/enable',['/left_arm/piper_driver'])])
with patch.dict(sys.modules, {'rospy':ros,'rosgraph':graph}), patch.dict(module.os.environ,fake), patch.object(module.subprocess,'Popen') as spawn:
    assert module.main() == 1
    spawn.assert_not_called()
for path in (package/'launch').glob('*.launch'):
    xml = ET.parse(path)
    for node in xml.findall('.//node'):
        assert node.attrib['pkg'] == 'pi05_pika_input'
        assert node.attrib['type'] in ('side_input.py','safe_locator.py')
    assert not xml.findall('.//remap')
    assert 'LHR-' not in path.read_text()
side = (package/'scripts/side_input.py').read_text()
assert 'Service' not in side and 'piper' not in side.lower()
assert 'O_RDWR' not in side and 'serial' not in side
print('Pika input-only mapping/static tests: PASS')
PY
