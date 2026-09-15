cmake_minimum_required(VERSION 3.0.2)
project(pi05_left_teleop)
find_package(catkin REQUIRED)
catkin_package()
catkin_install_python(PROGRAMS scripts/component.py scripts/supervisor.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(FILES scripts/safety_gate.py DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(DIRECTORY launch DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
