cmake_minimum_required(VERSION 3.0.2)
project(pi05_data_collection)

find_package(catkin REQUIRED COMPONENTS
  cv_bridge
  rospy
  sensor_msgs
  std_msgs
  std_srvs
)

catkin_python_setup()
catkin_package(CATKIN_DEPENDS cv_bridge rospy sensor_msgs std_msgs std_srvs)

catkin_install_python(PROGRAMS
  scripts/collector_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

if(CATKIN_ENABLE_TESTING)
  catkin_add_nosetests(test/test_session.py)
endif()
