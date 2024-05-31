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
"""
Live benchmarking Realsense2 node.

The graph consists of the following:
- Graph under Test:
    1. Realsense2Camera: Realsense camera

Required:
- Packages:
    - Realsense2Camera
"""

import os

from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

from ros2_benchmark import ImageResolution
from ros2_benchmark import BasicPerformanceCalculator, BenchmarkMode
from ros2_benchmark import ROS2BenchmarkConfig, ROS2BenchmarkTest
from ros2_benchmark import MonitorPerformanceCalculatorsInfo

IMAGE_RESOLUTION = ImageResolution.VGA

def launch_setup(container_prefix, container_sigterm_timeout):
    """Generate launch description for live benchmarking Realsense2 camera."""
    # RealSense
    realsense_config_file_path = os.path.join(
        TestRealsense2Node.get_assets_root_path(),
        'configs', 'realsense.yaml')

    realsense_node = ComposableNode(
        name='Realsense2Camera',
        namespace=TestRealsense2Node.generate_namespace(),
        package='realsense2_camera',
        plugin='realsense2_camera::RealSenseNodeFactory',
        parameters=[realsense_config_file_path],
        remappings=[
            ('infra1/image_rect_raw', 'left/image_rect_raw_mono'),
            ('infra2/image_rect_raw', 'right/image_rect_raw_mono'),
            ('infra1/camera_info', 'left/camerainfo'),
            ('infra2/camera_info', 'right/camerainfo')
        ]
    )

    left_image_monitor_node = ComposableNode(
        name='LeftImageMonitorNode',
        namespace=TestRealsense2Node.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        parameters=[{
            'monitor_index': 0,
            'monitor_data_format': 'sensor_msgs/msg/Image',
        }],
        remappings=[('output', 'left/image_rect_raw_mono')]
    )

    right_image_monitor_node = ComposableNode(
        name='RightImageMonitorNode',
        namespace=TestRealsense2Node.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        parameters=[{
            'monitor_index': 1,
            'monitor_data_format': 'sensor_msgs/msg/Image',
        }],
        remappings=[('output', 'right/image_rect_raw_mono')]
    )

    composable_node_container = ComposableNodeContainer(
        name='container',
        namespace=TestRealsense2Node.generate_namespace(),
        package='rclcpp_components',
        executable='component_container_mt',
        prefix=container_prefix,
        sigterm_timeout=container_sigterm_timeout,
        composable_node_descriptions=[
            realsense_node,
            left_image_monitor_node,
            right_image_monitor_node,
        ],
        output='screen'
    )

    return [composable_node_container]

def generate_test_description():
    return TestRealsense2Node.generate_test_description_with_nsys(launch_setup)


class TestRealsense2Node(ROS2BenchmarkTest):
    """Live performance test for Realsense camera."""

    # Custom configurations
    config = ROS2BenchmarkConfig(
        benchmark_name='Realsense2 Camera Live Benchmark',
        benchmark_mode=BenchmarkMode.LIVE,
        benchmark_duration=5,
        test_iterations=5,
        collect_start_timestamps_from_monitors=True,
        custom_report_info={'data_resolution': IMAGE_RESOLUTION},
        monitor_info_list=[
            MonitorPerformanceCalculatorsInfo(
                'monitor_node0',
                [BasicPerformanceCalculator({
                    'report_prefix': 'Left Image',
                    'message_key_match': True
                })]),
            MonitorPerformanceCalculatorsInfo(
                'monitor_node1',
                [BasicPerformanceCalculator({
                    'report_prefix': 'Right Image',
                    'message_key_match': True
                })])
        ]
    )

    def test_benchmark(self):
        self.run_benchmark()
