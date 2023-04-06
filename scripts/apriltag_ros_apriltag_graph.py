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
Performance test for apriltag_ros graph.

The graph consists of the following:
- Preprocessors:
    1. PrepResizeNode: resizes images to HD
- Graph under Test:
    1. RectifyNode: rectifies images
    2. AprilTagNode: detects Apriltags

Required:
- Packages:
    - apriltag_ros
- Datasets:
    - assets/datasets/r2b_dataset/r2b_storage
"""

from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

from ros2_benchmark import ImageResolution
from ros2_benchmark import ROS2BenchmarkConfig, ROS2BenchmarkTest

IMAGE_RESOLUTION = ImageResolution.HD
ROSBAG_PATH = 'datasets/r2b_dataset/r2b_storage'

def launch_setup(container_prefix, container_sigterm_timeout):
    """Generate launch description for benchmarking apriltag_ros graph."""

    # Detector parameters to detect all 36h11 tags
    cfg_36h11 = {
        'image_transport': 'raw',
        'family': '36h11',
        'size': 0.162
    }

    rectify_node = ComposableNode(
        name='RectifyNode',
        namespace=TestAprilTagGraph.generate_namespace(),
        package='image_proc',
        plugin='image_proc::RectifyNode'
    )

    apriltag_node = ComposableNode(
        name='AprilTagNode',
        namespace=TestAprilTagGraph.generate_namespace(),
        package='apriltag_ros',
        plugin='AprilTagNode',
        parameters=[cfg_36h11],
        remappings=[
            ('detections', 'apriltag_detections')
        ]
    )

    data_loader_node = ComposableNode(
        name='DataLoaderNode',
        namespace=TestAprilTagGraph.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::DataLoaderNode',
        remappings=[('hawk_0_left_rgb_image', 'data_loader/image'),
                    ('hawk_0_left_rgb_camera_info', 'data_loader/camera_info')]
    )

    prep_resize_node = ComposableNode(
        name='PrepResizeNode',
        namespace=TestAprilTagGraph.generate_namespace(),
        package='image_proc',
        plugin='image_proc::ResizeNode',
        parameters=[{
            'width': IMAGE_RESOLUTION['width'],
            'height': IMAGE_RESOLUTION['height'],
            'use_scale': False,
        }],
        remappings=[
            ('image/image_raw', 'data_loader/image'),
            ('image/camera_info', 'data_loader/camera_info'),
            ('resize/image_raw', 'buffer/image'),
            ('resize/camera_info', 'buffer/camera_info'),
        ]
    )

    playback_node = ComposableNode(
        name='PlaybackNode',
        namespace=TestAprilTagGraph.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::PlaybackNode',
        parameters=[{
            'data_formats': [
                'sensor_msgs/msg/Image',
                'sensor_msgs/msg/CameraInfo'],
        }],
        remappings=[('buffer/input0', 'buffer/image'),
                    ('input0', 'image'),
                    ('buffer/input1', 'buffer/camera_info'),
                    ('input1', 'camera_info')],
    )

    monitor_node = ComposableNode(
        name='MonitorNode',
        namespace=TestAprilTagGraph.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        parameters=[{
            'monitor_data_format': 'apriltag_msgs/msg/AprilTagDetectionArray',
        }],
        remappings=[
            ('output', 'apriltag_detections')],
    )

    composable_node_container = ComposableNodeContainer(
        name='container',
        namespace=TestAprilTagGraph.generate_namespace(),
        package='rclcpp_components',
        executable='component_container_mt',
        prefix=container_prefix,
        sigterm_timeout=container_sigterm_timeout,
        composable_node_descriptions=[
            data_loader_node,
            prep_resize_node,
            playback_node,
            monitor_node,
            rectify_node,
            apriltag_node
        ],
        output='screen'
    )

    return [composable_node_container]

def generate_test_description():
    return TestAprilTagGraph.generate_test_description_with_nsys(launch_setup)

class TestAprilTagGraph(ROS2BenchmarkTest):
    """Performance test for AprilTag graph."""

    # Custom configurations
    config = ROS2BenchmarkConfig(
        benchmark_name='apriltag_ros AprilTag Graph Benchmark',
        input_data_path=ROSBAG_PATH,
        # The slice of the rosbag to use
        input_data_start_time=3.0,
        input_data_end_time=3.5,
        # Upper and lower bounds of peak throughput search window
        publisher_upper_frequency=600.0,
        publisher_lower_frequency=10.0,
        # The number of frames to be buffered
        playback_message_buffer_size=10,
        custom_report_info={'data_resolution': IMAGE_RESOLUTION}
    )

    def test_benchmark(self):
        self.run_benchmark()
