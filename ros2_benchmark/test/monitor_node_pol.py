# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import os
import unittest

import launch
from launch.actions import ExecuteProcess
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
import launch_testing.actions

import rclpy

from ros2_benchmark.utils.ros2_utility import ClientUtility
from ros2_benchmark_interfaces.srv import StartMonitoring


def generate_test_description():
    """Initialize test nodes and generate test description."""
    dir_path = os.path.dirname(os.path.realpath(__file__))
    rosbag_path = os.path.join(dir_path, 'pol.bag')

    monitor_node0 = ComposableNode(
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        name='MonitorNode0',
        parameters=[{
            'monitor_data_format': 'sensor_msgs/msg/Image',
            'monitor_index': 0
        }],
        remappings=[
            ('output', '/image'),
        ],
    )

    monitor_node1 = ComposableNode(
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        name='MonitorNode1',
        parameters=[{
            'monitor_data_format': 'sensor_msgs/msg/CameraInfo',
            'monitor_index': 1
        }],
        remappings=[
            ('output', '/camera_info'),
        ],
    )

    monitor_container = ComposableNodeContainer(
        package='rclcpp_components',
        name='monitor_container',
        namespace='',
        executable='component_container_mt',
        composable_node_descriptions=[monitor_node0, monitor_node1],
        output='screen'
    )

    # Play rosbag for the monitor node to receive messages
    rosbag_play = ExecuteProcess(
        cmd=['ros2', 'bag', 'play', rosbag_path],
        output='screen')

    return launch.LaunchDescription([
        rosbag_play,
        monitor_container,
        launch_testing.actions.ReadyToTest()
    ])


class TestMonitorNode(unittest.TestCase):
    """An unit test class for MonitorNode."""

    def test_monitor_node_services(self):
        """Test services hosted in MonitorNode."""
        SERVICE_SETUP_TIMEOUT_SEC = 5
        SERVICE_TIMEOUT_SEC = 20
        SERVICE_FUTURE_TIMEOUT_SEC = 25

        # Create a test ROS node
        rclpy.init()
        node = rclpy.create_node('test_node')

        # Create a start_monitoring0 service client
        start_monitoring_client0 = ClientUtility.create_service_client_blocking(
            node, StartMonitoring, 'start_monitoring0', SERVICE_SETUP_TIMEOUT_SEC)
        self.assertIsNotNone(start_monitoring_client0)

        # Create a start_monitoring1 service client
        start_monitoring_client1 = ClientUtility.create_service_client_blocking(
            node, StartMonitoring, 'start_monitoring1', SERVICE_SETUP_TIMEOUT_SEC)
        self.assertIsNotNone(start_monitoring_client1)

        # Send a request to the start_monitoring0 service
        start_monitoring_request = StartMonitoring.Request()
        start_monitoring_request.timeout = SERVICE_TIMEOUT_SEC
        start_monitoring_request.message_count = 1
        start_monitoring_future0 = start_monitoring_client0.call_async(
            start_monitoring_request)

        # Send a request to the start_monitoring1 service
        start_monitoring_future1 = start_monitoring_client1.call_async(
            start_monitoring_request)

        # Wait for the response from the start_monitoring0 service
        start_monitoring_response0 = ClientUtility.get_service_response_from_future_blocking(
            node, start_monitoring_future0, SERVICE_FUTURE_TIMEOUT_SEC)
        self.assertIsNotNone(start_monitoring_response0)
        node.get_logger().info('Received response from the start_monitoring0 service:')
        node.get_logger().info(str(start_monitoring_response0))

        # Wait for the response from the start_monitoring1 service
        start_monitoring_response1 = ClientUtility.get_service_response_from_future_blocking(
            node, start_monitoring_future1, SERVICE_FUTURE_TIMEOUT_SEC)
        self.assertIsNotNone(start_monitoring_response1)
        node.get_logger().info('Received response from the start_monitoring1 service:')
        node.get_logger().info(str(start_monitoring_response1))
