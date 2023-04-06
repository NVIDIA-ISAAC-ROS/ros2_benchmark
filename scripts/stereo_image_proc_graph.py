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
"""
Performance test for stereo_image_proc point cloud graph.

The graph consists of the following:
- Preprocessors:
    1. PrepLeftResizeNode, PrepRightResizeNode: resizes images to quarter HD
- Graph under Test:
    1. DisparityNode: creates disparity images from stereo pair
    2. PointCloudNode: converts disparity to pointcloud

Required:
- Packages:
    - stereo_image_proc
- Datasets:
    - assets/datasets/r2b_dataset/r2b_hideaway
"""

import os

from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

from ros2_benchmark import ImageResolution
from ros2_benchmark import ROS2BenchmarkConfig, ROS2BenchmarkTest

IMAGE_RESOLUTION = ImageResolution.QUARTER_HD
ROSBAG_PATH = 'datasets/r2b_dataset/r2b_hideaway'

def launch_setup(container_prefix, container_sigterm_timeout):
    """Generate launch description for benchmarking stereo_image_proc point cloud graph."""

    env = os.environ.copy()
    env['OSPL_VERBOSITY'] = '8'  # 8 = OS_NONE
    # bare minimum formatting for console output matching
    env['RCUTILS_CONSOLE_OUTPUT_FORMAT'] = '{message}'

    disparity_node = ComposableNode(
        name='DisparityNode',
        namespace=TestStereoGraph.generate_namespace(),
        package='stereo_image_proc',
        plugin='stereo_image_proc::DisparityNode',
        parameters=[{
                'queue_size': 500,
                'approx': False,
                'use_system_default_qos': False
        }],
        remappings=[
            ('/left/camera_info', '/left/camera_info'),
            ('/right/camera_info', '/right/camera_info'),
            ('/left/image_rect', '/left/image_rect'),
            ('/right/image_rect', '/right/image_rect')],
    )

    pointcloud_node = ComposableNode(
        name='PointCloudNode',
        namespace=TestStereoGraph.generate_namespace(),
        package='stereo_image_proc',
        plugin='stereo_image_proc::PointCloudNode',
        parameters=[{
                'approximate_sync': False,
                'avoid_point_cloud_padding': False,
                'use_color': False,
                'use_system_default_qos': False,
        }],
        remappings=[
            ('/left/camera_info', '/left/camera_info'),
            ('/right/camera_info', '/right/camera_info'),
            ('/left/image_rect', '/left/image_rect'),
            ('/right/image_rect', '/right/image_rect'),
            ('left/image_rect_color', 'left/image_rect')],
    )

    data_loader_node = ComposableNode(
        name='DataLoaderNode',
        namespace=TestStereoGraph.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::DataLoaderNode',
        remappings=[('hawk_0_left_rgb_image', 'data_loader/left_image'),
                    ('hawk_0_left_rgb_camera_info', 'data_loader/left_camera_info'),
                    ('hawk_0_right_rgb_image', 'data_loader/right_image'),
                    ('hawk_0_right_rgb_camera_info', 'data_loader/right_camera_info')]
    )

    prep_left_resize_node = ComposableNode(
        name='PrepLeftResizeNode',
        namespace=TestStereoGraph.generate_namespace(),
        package='image_proc',
        plugin='image_proc::ResizeNode',
        parameters=[{
            'width': IMAGE_RESOLUTION['width'],
            'height': IMAGE_RESOLUTION['height'],
            'use_scale': False,
        }],
        remappings=[
            ('image/image_raw', 'data_loader/left_image'),
            ('image/camera_info', 'data_loader/left_camera_info'),
            ('resize/image_raw', 'buffer/left/image_resized'),
            ('resize/camera_info', 'buffer/left/camera_info_resized'),
        ]
    )

    prep_right_resize_node = ComposableNode(
        name='PrepRightResizeNode',
        namespace=TestStereoGraph.generate_namespace(),
        package='image_proc',
        plugin='image_proc::ResizeNode',
        parameters=[{
            'width': IMAGE_RESOLUTION['width'],
            'height': IMAGE_RESOLUTION['height'],
            'use_scale': False,
        }],
        remappings=[
            ('image/image_raw', 'data_loader/right_image'),
            ('image/camera_info', 'data_loader/right_camera_info'),
            ('resize/image_raw', 'buffer/right/image_resized'),
            ('resize/camera_info', 'buffer/right/camera_info_resized'),
        ]
    )

    playback_node = ComposableNode(
        name='PlaybackNode',
        namespace=TestStereoGraph.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::PlaybackNode',
        parameters=[{
            'data_formats': [
                'sensor_msgs/msg/Image',
                'sensor_msgs/msg/CameraInfo',
                'sensor_msgs/msg/Image',
                'sensor_msgs/msg/CameraInfo'],
        }],
        remappings=[('buffer/input0', 'buffer/left/image_resized'),
                    ('input0', 'left/image_rect'),
                    ('buffer/input1', 'buffer/left/camera_info_resized'),
                    ('input1', 'left/camera_info'),
                    ('buffer/input2', 'buffer/right/image_resized'),
                    ('input2', 'right/image_rect'),
                    ('buffer/input3', 'buffer/right/camera_info_resized'),
                    ('input3', 'right/camera_info')],
    )

    monitor_node = ComposableNode(
        name='MonitorNode',
        namespace=TestStereoGraph.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        parameters=[{
            'monitor_data_format': 'sensor_msgs/msg/PointCloud2',
        }],
        remappings=[
            ('output', 'points2')],
    )

    composable_node_container = ComposableNodeContainer(
        name='container',
        namespace=TestStereoGraph.generate_namespace(),
        package='rclcpp_components',
        executable='component_container_mt',
        prefix=container_prefix,
        sigterm_timeout=container_sigterm_timeout,
        composable_node_descriptions=[
            data_loader_node,
            prep_left_resize_node,
            prep_right_resize_node,
            playback_node,
            monitor_node,
            disparity_node,
            pointcloud_node
        ],
        output='screen'
    )

    return [composable_node_container]

def generate_test_description():
    return TestStereoGraph.generate_test_description_with_nsys(launch_setup)


class TestStereoGraph(ROS2BenchmarkTest):
    """Performance test for stereo image pointcloud graph."""

    # Custom configurations
    config = ROS2BenchmarkConfig(
        benchmark_name='Stereo Image Pointcloud Graph Benchmark',
        input_data_path=ROSBAG_PATH,
        # Upper and lower bounds of peak throughput search window
        publisher_upper_frequency=100.0,
        publisher_lower_frequency=10.0,
        # The number of frames to be buffered
        playback_message_buffer_size=100,
        custom_report_info={'data_resolution': IMAGE_RESOLUTION}
    )

    def test_benchmark(self):
        self.run_benchmark()
