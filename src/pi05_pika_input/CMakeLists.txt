cmake_minimum_required(VERSION 3.0.2)
project(pi05_pika_input)
find_package(catkin REQUIRED COMPONENTS rospy geometry_msgs std_msgs)
catkin_package(CATKIN_DEPENDS rospy geometry_msgs std_msgs)
catkin_install_python(PROGRAMS scripts/safe_locator.py scripts/side_input.py scripts/gripper_input.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
install(DIRECTORY launch DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
