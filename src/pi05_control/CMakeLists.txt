cmake_minimum_required(VERSION 3.0.2)
project(pi05_control)

find_package(catkin REQUIRED COMPONENTS
  rospy
  sensor_msgs
  std_srvs
)

catkin_package(
  CATKIN_DEPENDS rospy sensor_msgs std_srvs
)

# Add migrated Python nodes here with catkin_install_python once implemented.
