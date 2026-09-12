cmake_minimum_required(VERSION 3.0.2)
project(pi05_control)

find_package(catkin REQUIRED COMPONENTS
  diagnostic_msgs
  rospy
  sensor_msgs
  std_msgs
  std_srvs
)

catkin_python_setup()

catkin_package(
  CATKIN_DEPENDS diagnostic_msgs rospy sensor_msgs std_msgs std_srvs
)

catkin_install_python(PROGRAMS
  scripts/arm_safety_filter_node.py
  scripts/dual_arm_safety_coordinator_node.py
  scripts/piper_readonly_feedback_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

if(CATKIN_ENABLE_TESTING)
  catkin_add_nosetests(test/test_safety_filter.py)
  catkin_add_nosetests(test/test_safety_filter_launch.py)
  catkin_add_nosetests(test/test_dual_arm_safety.py)
  catkin_add_nosetests(test/test_dual_arm_bringup_launch.py)
  catkin_add_nosetests(test/test_control_graph.py)
  catkin_add_nosetests(test/test_piper_feedback.py)
  catkin_add_nosetests(test/test_single_arm_driver_launch.py)
endif()
