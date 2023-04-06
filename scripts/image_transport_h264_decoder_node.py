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
Performance test for image_transport H264 decoder node.

The graph consists of the following:
- Preprocessors:
    1. PrepResizeNode: resizes images to full HD
    2. PrepRepublishEncoderNode: encodes images to h264
- Graph under Test:
    1. RepublishDecoderNode: decodes compressed images

Required:
- Packages:
    - ros2_h264_encoder
    - h264_msgs
    - h264_image_transport
- Datasets:
    - assets/datasets/r2b_dataset/r2b_mezzanine
"""

from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode

from ros2_benchmark import ImageResolution
from ros2_benchmark import ROS2BenchmarkConfig, ROS2BenchmarkTest

IMAGE_RESOLUTION = ImageResolution.FULL_HD
ROSBAG_PATH = 'datasets/r2b_dataset/r2b_mezzanine'

def launch_setup(container_prefix, container_sigterm_timeout):
    """Generate launch description for benchmarking image_transport decoder node."""

    republish_node = Node(
        name='RepublishDecoderNode',
        namespace=TestH264DecoderNode.generate_namespace(),
        package='image_transport',
        executable='republish',
        arguments=['h264',  'raw', '--ros-args', '--log-level', 'error'],
        remappings=[
            ('in/h264', 'compressed_image'),
            ('out', 'image_uncompressed'),
        ],
    )

    data_loader_node = ComposableNode(
        name='DataLoaderNode',
        namespace=TestH264DecoderNode.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::DataLoaderNode',
        remappings=[('hawk_0_left_rgb_image', 'data_loader/left_image'),
                    ('hawk_0_left_rgb_camera_info', 'data_loader/left_camera_info')]
    )

    prep_resize_node = ComposableNode(
        name='PrepResizeNode',
        namespace=TestH264DecoderNode.generate_namespace(),
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
            ('resize/image_raw', 'resized/image_raw'),
            ('resize/camera_info', 'resized/camera_info'),
        ]
    )

    prep_encoder_node = Node(
        name='PrepRepublishEncoderNode',
        namespace=TestH264DecoderNode.generate_namespace(),
        package='image_transport',
        executable='republish',
        arguments=['raw', 'h264'],
        remappings=[
            ('in', 'resized/image_raw'),
            ('out/h264', 'image_h264'),
        ],
    )

    playback_node = ComposableNode(
        name='PlaybackNode',
        namespace=TestH264DecoderNode.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::PlaybackNode',
        parameters=[{
            'data_formats': [
                'h264_msgs/msg/Packet'],
        }],
        remappings=[('buffer/input0', 'image_h264'),
                    ('input0', 'compressed_image')],
    )

    monitor_node = ComposableNode(
        name='MonitorNode',
        namespace=TestH264DecoderNode.generate_namespace(),
        package='ros2_benchmark',
        plugin='ros2_benchmark::MonitorNode',
        parameters=[{
            'monitor_data_format': 'sensor_msgs/msg/Image',
        }],
        remappings=[
            ('output', 'image_uncompressed')],
    )

    composable_node_container = ComposableNodeContainer(
        name='container',
        namespace=TestH264DecoderNode.generate_namespace(),
        package='rclcpp_components',
        executable='component_container_mt',
        prefix=container_prefix,
        sigterm_timeout=container_sigterm_timeout,
        composable_node_descriptions=[
            data_loader_node,
            prep_resize_node,
            playback_node,
            monitor_node
        ],
        output='screen'
    )

    return [prep_encoder_node, republish_node, composable_node_container]

def generate_test_description():
    return TestH264DecoderNode.generate_test_description_with_nsys(launch_setup)


class TestH264DecoderNode(ROS2BenchmarkTest):
    """Performance test for image_transport H264 decoder node."""

    # Custom configurations
    config = ROS2BenchmarkConfig(
        benchmark_name='image_transport H264 Decoder Node Benchmark',
        input_data_path=ROSBAG_PATH,
        # Upper and lower bounds of peak throughput search window
        publisher_upper_frequency=200.0,
        publisher_lower_frequency=10.0,
        # The number of frames to be buffered
        playback_message_buffer_size=1
    )

    def test_benchmark(self):
        self.run_benchmark()
