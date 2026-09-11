cmake_minimum_required(VERSION 3.0.2)
project(pi05_control)

find_package(catkin REQUIRED COMPONENTS
  rospy
  sensor_msgs
  std_srvs
)

catkin_python_setup()

catkin_package(
  CATKIN_DEPENDS rospy sensor_msgs std_srvs
)

catkin_install_python(PROGRAMS
  scripts/piper_readonly_feedback_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

if(CATKIN_ENABLE_TESTING)
  catkin_add_nosetests(test/test_piper_feedback.py)
  catkin_add_nosetests(test/test_single_arm_driver_launch.py)
endif()
