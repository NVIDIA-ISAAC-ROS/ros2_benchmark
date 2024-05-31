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

import os
import time
import unittest

import launch
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
import launch_testing.actions

import rclpy

from ros2_benchmark.utils.ros2_utility import ClientUtility
from ros2_benchmark_interfaces.srv import SetData, StartLoading, StopLoading

DIR_PATH = os.path.dirname(os.path.realpath(__file__))
ROSBAG_PATH = os.path.join(DIR_PATH, 'pol.bag/pol.bag_0.db3')


def generate_test_description():
    """Initialize test nodes and generate test description."""
    data_loader_node = ComposableNode(
        package='ros2_benchmark',
        plugin='ros2_benchmark::DataLoaderNode',
        name='DataLoaderNode',
    )

    data_loader_container = ComposableNodeContainer(
        package='rclcpp_components',
        name='data_loader_container',
        namespace='',
        executable='component_container_mt',
        composable_node_descriptions=[data_loader_node],
        output='screen'
    )

    return launch.LaunchDescription([
        data_loader_container,
        launch_testing.actions.ReadyToTest()
    ])


class TestDataLoaderNode(unittest.TestCase):
    """An unit test class for DataLoaderNode."""

    def test_data_loader_node_services(self):
        """Test services hosted in DataLoaderNode."""
        SERVICE_SETUP_TIMEOUT_SEC = 5
        SERVICE_FUTURE_TIMEOUT_SEC = 25

        # Create a test ROS node
        rclpy.init()
        node = rclpy.create_node('test_node')

        # Create a set_data service client
        set_data_client = ClientUtility.create_service_client_blocking(
            node, SetData, 'set_data', SERVICE_SETUP_TIMEOUT_SEC)
        self.assertIsNotNone(set_data_client)

        # Create a start_loading service client
        start_loading_client = ClientUtility.create_service_client_blocking(
            node, StartLoading, 'start_loading', SERVICE_SETUP_TIMEOUT_SEC)
        self.assertIsNotNone(start_loading_client)

        # Create a stop_loading service client
        stop_loading_client = ClientUtility.create_service_client_blocking(
            node, StopLoading, 'stop_loading', SERVICE_SETUP_TIMEOUT_SEC)
        self.assertIsNotNone(stop_loading_client)

        # Send a request to the set_data service
        set_data_request = SetData.Request()
        set_data_request.data_path = ROSBAG_PATH
        set_data_future = set_data_client.call_async(
            set_data_request)

        # Wait for the response from the start_recording service
        set_data_response = ClientUtility.get_service_response_from_future_blocking(
            node, set_data_future, SERVICE_FUTURE_TIMEOUT_SEC)
        self.assertIsNotNone(set_data_response)
        self.assertTrue(set_data_response.success)

        # Send a request to the start_loading service
        start_loading_request = StartLoading.Request()
        start_loading_future = start_loading_client.call_async(
            start_loading_request)

        time.sleep(1)

        # Send a request to the stop_loading service
        stop_loading_request = StopLoading.Request()
        stop_loading_future = stop_loading_client.call_async(
            stop_loading_request)

        # Wait for the response from the start_recording service
        start_loading_response = ClientUtility.get_service_response_from_future_blocking(
            node, start_loading_future, SERVICE_FUTURE_TIMEOUT_SEC)
        self.assertIsNotNone(start_loading_response)
        node.get_logger().info('Received response from the start_loading service:')
        node.get_logger().info(str(start_loading_response))

        # Wait for the response from the start_recording service
        stop_loading_response = ClientUtility.get_service_response_from_future_blocking(
            node, stop_loading_future, SERVICE_FUTURE_TIMEOUT_SEC)
        self.assertIsNotNone(stop_loading_response)
        node.get_logger().info('Received response from the stop_loading service.')
