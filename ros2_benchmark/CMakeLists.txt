# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2023-2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.5)
project(ros2_benchmark)

# Default to C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Default to Release build
if(NOT CMAKE_BUILD_TYPE OR CMAKE_BUILD_TYPE STREQUAL "")
  set(CMAKE_BUILD_TYPE "Release" CACHE STRING "" FORCE)
endif()
message( STATUS "CMAKE_BUILD_TYPE: ${CMAKE_BUILD_TYPE}" )

find_package(ament_cmake_auto REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)

ament_auto_find_build_dependencies()

ament_python_install_package(${PROJECT_NAME})

# OpenSSL library
find_package(OpenSSL REQUIRED)

###################################
#          Dataloader Node        #
###################################
ament_auto_add_library(data_loader_node SHARED
    src/data_loader_node.cpp
)
target_compile_definitions(data_loader_node
  PRIVATE "COMPOSITION_BUILDING_DLL"
)
target_link_libraries(data_loader_node OpenSSL::Crypto)
rclcpp_components_register_nodes(data_loader_node "ros2_benchmark::DataLoaderNode")
set(node_plugins "${node_plugins}ros2_benchmark::DataLoaderNode;$<TARGET_FILE:data_loader_node>\n")

###################################
#          Playback Node          #
###################################
ament_auto_add_library(playback_node SHARED
    src/playback_node.cpp
)
target_compile_definitions(playback_node
  PRIVATE "COMPOSITION_BUILDING_DLL"
)
rclcpp_components_register_nodes(playback_node "ros2_benchmark::PlaybackNode")
set(node_plugins "${node_plugins}ros2_benchmark::PlaybackNode;$<TARGET_FILE:playback_node>\n")

###################################
#          Monitor Node           #
###################################
ament_auto_add_library(monitor_node SHARED
    src/monitor_node.cpp
)
target_compile_definitions(monitor_node
  PRIVATE "COMPOSITION_BUILDING_DLL"
)
rclcpp_components_register_nodes(monitor_node "ros2_benchmark::MonitorNode")
set(node_plugins "${node_plugins}ros2_benchmark::MonitorNode;$<TARGET_FILE:monitor_node>\n")


if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)

  ament_lint_auto_find_test_dependencies()


  # The FindPythonInterp and FindPythonLibs modules are removed
  if(POLICY CMP0148)
    cmake_policy(SET CMP0148 OLD)
  endif()

  find_package(launch_testing_ament_cmake REQUIRED)
  add_launch_test(test/data_loader_node_pol.py TIMEOUT "60")
  add_launch_test(test/monitor_node_pol.py TIMEOUT "60")
  add_launch_test(test/playback_node_pol.py TIMEOUT "60")
endif()


# Embed versioning information into installed files
ament_index_get_resource(ISAAC_ROS_COMMON_CMAKE_PATH isaac_ros_common_cmake_path isaac_ros_common)
include("${ISAAC_ROS_COMMON_CMAKE_PATH}/isaac_ros_common-version-info.cmake")
generate_version_info(${PROJECT_NAME})

ament_auto_package(INSTALL_TO_SHARE ../scripts)
