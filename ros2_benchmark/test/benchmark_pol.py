# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
End-to-end benchmark test using pol.bag.

Tests the full benchmark framework with a minimal passthrough graph.
Also useful for measuring the benchmark framework's top speed without any load.

Required:
- Datasets:
    - test/pol.bag (included in repo)
"""

import os

from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

from ros2_benchmark import BenchmarkMode, ROS2BenchmarkConfig, ROS2BenchmarkTest

DIR_PATH = os.path.dirname(os.path.realpath(__file__))
ROSBAG_PATH = os.path.join(DIR_PATH, 'pol.bag')


def launch_setup(container_prefix, container_sigterm_timeout):
    """Generate launch description for benchmark test."""
    data_loader_node = ComposableNode(
        name='DataLoaderNode',
        namespace=TestBenchmarkPol.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::DataLoaderNode',
        remappings=[
            ('image', 'data_loader/image'),
            ('camera_info', 'data_loader/camera_info')
        ]
    )

    playback_node = ComposableNode(
        name='PlaybackNode',
        namespace=TestBenchmarkPol.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::PlaybackNode',
        parameters=[{
            'data_formats': [
                'sensor_msgs/msg/Image',
                'sensor_msgs/msg/CameraInfo'
            ],
        }],
        remappings=[
            ('buffer/input0', 'data_loader/image'),
            ('input0', 'image'),
            ('buffer/input1', 'data_loader/camera_info'),
            ('input1', 'camera_info')
        ]
    )

    monitor_node = ComposableNode(
        name='MonitorNode',
        namespace=TestBenchmarkPol.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        parameters=[{
            'monitor_data_format': 'sensor_msgs/msg/Image',
        }],
        remappings=[
            ('output', 'image')
        ]
    )

    composable_node_container = ComposableNodeContainer(
        name='container',
        namespace=TestBenchmarkPol.generate_namespace(),
        package='rclcpp_components',
        executable='component_container_mt',
        prefix=container_prefix,
        sigterm_timeout=container_sigterm_timeout,
        composable_node_descriptions=[
            data_loader_node,
            playback_node,
            monitor_node,
        ],
        output='screen'
    )

    return [composable_node_container]


def generate_test_description():
    return TestBenchmarkPol.generate_test_description_with_nsys(launch_setup)


class TestBenchmarkPol(ROS2BenchmarkTest):
    """End-to-end benchmark test using pol.bag."""

    config = ROS2BenchmarkConfig(
        benchmark_name='POL End-to-End Benchmark Test',
        input_data_path=ROSBAG_PATH,
        benchmark_mode=BenchmarkMode.TIMELINE,
        benchmark_duration=2.0,
        test_iterations=1,
        publisher_upper_frequency=100.0,
        publisher_lower_frequency=10.0,
        playback_message_buffer_size=100,
    )

    def test_benchmark(self):
        self.run_benchmark()
