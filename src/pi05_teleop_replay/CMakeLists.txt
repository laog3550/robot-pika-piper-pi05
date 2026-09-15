cmake_minimum_required(VERSION 3.0.2)
project(pi05_teleop_replay)
find_package(catkin REQUIRED)
catkin_package()
catkin_install_python(PROGRAMS scripts/replay_component.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(DIRECTORY launch DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
