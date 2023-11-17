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

import datetime
from enum import Enum
from functools import partial
import hashlib
import json
from math import ceil
import os
import platform
import sys
import time
from typing import Iterable
import unittest

import launch
from launch.actions import OpaqueFunction
import launch_testing.actions

import rclpy

from ros2_benchmark_interfaces.srv import GetTopicMessageTimestamps, PlayMessages
from ros2_benchmark_interfaces.srv import SetData, StartLoading, StopLoading
from ros2_benchmark_interfaces.srv import StartMonitoring, StartRecording

import rosbag2_py

from .basic_performance_calculator import BasicPerformanceMetrics
from .ros2_benchmark_config import BenchmarkMode
from .ros2_benchmark_config import ROS2BenchmarkConfig
from .utils.cpu_profiler import CPUProfiler
from .utils.nsys_utility import NsysUtility
from .utils.ros2_utility import ClientUtility


# The maximum allowed line width of a performance repeort displayed in the terminal
MAX_REPORT_OUTPUT_WIDTH = 90
idle_cpu_util = 0.0


class BenchmarkMetadata(Enum):
    """Benchmark metadata items to be included in a final report."""

    NAME = 'Test Name'
    TEST_DATETIME = 'Test Datetime'
    TEST_FILE_PATH = 'Test File Path'
    DEVICE_ARCH = 'Device Architecture'
    DEVICE_OS = 'Device OS'
    DEVICE_HOSTNAME = 'Device Hostname'
    BENCHMARK_MODE = 'Benchmark Mode'
    INPUT_DATA_PATH = 'Input Data Path'
    INPUT_DATA_HASH = 'Input Data Hash'
    INPUT_DATA_SIZE = 'Input Data Size (bytes)'
    INPUT_DATA_START_TIME = 'Input Data Start Time (s)'
    INPUT_DATA_END_TIME = 'Input Data End Time (s)'
    DATA_RESOLUTION = 'Data Resolution'
    IDLE_CPU_UTIL = 'Idle System CPU Util. (%)'
    PEAK_THROUGHPUT_PREDICTION = 'Peak Throughput Prediction (Hz)'
    CONFIG = 'Test Configurations'


class ROS2BenchmarkTest(unittest.TestCase):
    """The main ros2_benchmark framework test class."""

    # A config object that holds benchmark-relevant settings
    config = ROS2BenchmarkConfig()

    def __init__(self, *args, **kwargs):
        """Initialize ros2_benchmark."""
        # Calculated hash of the data to be loaded from a data loader node
        self._input_data_hash = ''

        # Size of the data (file)
        self._input_data_size_bytes = 0

        self._test_datetime = datetime.datetime.now(datetime.timezone.utc)

        # The absolute path of the top level launch script
        self._test_file_path = os.path.abspath(sys.argv[1])

        self._peak_throughput_prediction = 0.0
        self._logger_name_stack = ['']

        # Override default configs from env variablees
        self.override_config_from_env()

        self._cpu_profiler = CPUProfiler()
        self._cpu_profiler_log_file_path = ''

        super().__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls) -> None:
        """Set up before first test method."""
        # Initialize the ROS context for the test node
        rclpy.init()

    @classmethod
    def tearDownClass(cls) -> None:
        """Tear down after last test method."""
        # Shutdown the ROS context
        rclpy.shutdown()

    def setUp(self) -> None:
        """Set up before each test method."""
        # Create a ROS node for benchmark tests
        self.node = rclpy.create_node('Controller', namespace=self.generate_namespace())

    def tearDown(self) -> None:
        """Tear down after each test method."""
        self.node.destroy_node()

    @classmethod
    def generate_namespace(cls, *tokens: Iterable[str], absolute=True) -> str:
        """
        Generate a namespace with an optional list of tokens.

        This function is a utility for producing namespaced topic and service names in
        such a way that there are no collisions between 'dummy' nodes running for testing
        and 'normal' nodes running on the same machine.

        Parameters
        ----------
        tokens : Iterable[str]
            List of tokens to include in the namespace. Often used to generate
            separate namespaces for Isaac ROS and reference implementations.

        absolute: bool
            Whether or not to generate an absolute namespace, by default True.

        Returns
        -------
        str
            The generated namespace as a slash-delimited string

        """
        return ('/' if absolute else '') + '/'.join(
            filter(None, [cls.config.benchmark_namespace, *tokens]))

    @staticmethod
    def generate_test_description(
        nodes: Iterable[launch.Action], node_startup_delay: float = 5.0
    ) -> launch.LaunchDescription:
        """
        Generate a test launch description.

        The nodes included in this launch description will be launched as a test fixture
        immediately before the first test in the test class runs. Note that the graph is
        NOT shut down or re-launched between tests within the same class.

        Parameters
        ----------
        nodes : Iterable[launch.Action]
            List of Actions to launch before running the test.
        node_startup_delay : float, optional
            Seconds to delay by to account for node startup, by default 2.0

        Returns
        -------
        launch.LaunchDescription
            The LaunchDescription object to launch before running the test

        """
        # Wait until the system CPU usage become stable
        rclpy.logging.get_logger('r2b').info(
            'Waiting 10 seconds for measuring idle system CPU utilization...')
        time.sleep(10)
        global idle_cpu_util
        idle_cpu_util = CPUProfiler.get_current_cpu_usage()

        return launch.LaunchDescription(
            nodes + [
                # Start tests after a fixed delay for node startup
                launch.actions.TimerAction(
                    period=node_startup_delay, actions=[launch_testing.actions.ReadyToTest()])
            ]
        )

    @staticmethod
    def generate_test_description_with_nsys(
        launch_setup, node_startup_delay: float = 5.0
    ) -> launch.LaunchDescription:
        """Generate a test launch description with the nsys capability built in."""
        # Wait until the system CPU usage become stable
        rclpy.logging.get_logger('r2b').info(
            'Waiting 10 seconds for measuring idle system CPU utilization...')
        time.sleep(10)
        global idle_cpu_util
        idle_cpu_util = CPUProfiler.get_current_cpu_usage()

        launch_args = NsysUtility.generate_launch_args()
        bound_launch_setup = partial(
            NsysUtility.launch_setup_wrapper,
            launch_setup=launch_setup)
        nodes = launch_args + [OpaqueFunction(function=bound_launch_setup)]
        return launch.LaunchDescription(
            nodes + [
                # Start tests after a fixed delay for node startup
                launch.actions.TimerAction(
                    period=node_startup_delay,
                    actions=[launch_testing.actions.ReadyToTest()])
            ]
        )

    def get_logger(self, child_name=''):
        """Get logger with child layers."""
        if hasattr(self, 'node'):
            base_logger = self.node.get_logger()
        else:
            base_logger = rclpy.logging.get_logger('ROS2BenchmarkTest')

        if child_name:
            return base_logger.get_child(child_name)

        if len(self._logger_name_stack) == 0:
            return base_logger

        for logger_name in self._logger_name_stack:
            if logger_name:
                base_logger = base_logger.get_child(logger_name)

        return base_logger

    def push_logger_name(self, name):
        """Add a child layer to the logger."""
        self._logger_name_stack.append(name)

    def pop_logger_name(self):
        """Pop a child layer from the logger."""
        self._logger_name_stack.pop()

    def override_config_from_env(self):
        """Override config parameters with values from environment variables."""
        override_config_dict = {}
        for param_key in self.config.__dict__.keys():
            env_value = os.getenv(f'ROS2_BENCHMARK_OVERRIDE_{param_key.upper()}')
            if env_value is not None:
                override_config_dict[param_key] = env_value
                self.get_logger().info(
                    f'Updating a benchmark config from env: {param_key} = {env_value}')
        self.config.apply_to_attributes(override_config_dict)

    @classmethod
    def get_assets_root_path(cls):
        """Get assets path provided in configurations."""
        return cls.config.assets_root

    @classmethod
    def get_ros1_ws_path(cls):
        """Get ros1 workspace path provided in configurations."""
        return cls.config.ros1_ws

    def get_input_data_absolute_path(self):
        """Construct the absolute path of the input data file from configurations."""
        return os.path.join(self.config.assets_root, self.config.input_data_path)

    def print_report(self, report: dict, sub_heading: str = '') -> None:
        """Print the given report."""
        heading = self.config.benchmark_name

        # Temporarily remove configs from the report as we don't want it to be printed
        config_value = None
        if 'metadata' in report:
            config_value = report['metadata'].pop(BenchmarkMetadata.CONFIG, None)

        is_prev_dict = False
        table_blocks = []
        table_block_rows = []

        def construct_table_blocks_helper(prefix, data):
            nonlocal is_prev_dict
            nonlocal table_blocks
            nonlocal table_block_rows
            for key, value in data.items():
                key_str = str(key.value) if isinstance(key, Enum) else str(key)
                if isinstance(value, dict):
                    if not is_prev_dict and len(table_block_rows) > 0:
                        table_blocks.append(table_block_rows)
                        table_block_rows = []
                        is_prev_dict = True
                    construct_table_blocks_helper(f'{prefix}[{key_str}] ', value)
                    if not is_prev_dict:
                        table_blocks.append(table_block_rows)
                        table_block_rows = []
                        is_prev_dict = True
                elif isinstance(value, Enum):
                    table_block_rows.append(f'{prefix}{key_str} : {value.value}')
                    is_prev_dict = False
                elif isinstance(value, float):
                    table_block_rows.append(f'{prefix}{key_str} : {"{:.3f}".format(value)}')
                    is_prev_dict = False
                else:
                    table_block_rows.append(f'{prefix}{key_str} : {value}')
                    is_prev_dict = False

        construct_table_blocks_helper('', report)
        if len(table_block_rows) > 0:
            table_blocks.append(table_block_rows)
        max_row_width = max([len(row) for rows in table_blocks for row in rows] +
                            [len(heading), len(sub_heading)])
        max_row_width = min(max_row_width, MAX_REPORT_OUTPUT_WIDTH)

        def print_line_helper():
            self.get_logger().info('+-{}-+'.format('-'*max_row_width))

        def print_row_helper(row):
            self.get_logger().info('| {:<{width}} |'.format(row, width=max_row_width))

        def print_table_helper():
            print_line_helper()
            self.get_logger().info('| {:^{width}} |'.format(heading, width=max_row_width))
            if sub_heading:
                self.get_logger().info('| {:^{width}} |'.format(sub_heading, width=max_row_width))
            print_line_helper()
            for rows in table_blocks:
                for row in rows:
                    print_row_helper(row)
                print_line_helper()

        print_table_helper()

        if config_value is not None:
            report['metadata'][BenchmarkMetadata.CONFIG] = config_value

    def construct_final_report(self, report: dict) -> dict:
        """Construct and return the final report from the given report."""
        final_report = report

        if len(self.config.custom_report_info) > 0:
            final_report['custom'] = self.config.custom_report_info

        # Add benchmark metadata
        metadata = {}

        # Benchmark launch info
        metadata[BenchmarkMetadata.NAME] = self.config.benchmark_name
        metadata[BenchmarkMetadata.TEST_FILE_PATH] = self._test_file_path
        metadata[BenchmarkMetadata.TEST_DATETIME] = \
            self._test_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Systeme info
        uname = platform.uname()
        metadata[BenchmarkMetadata.DEVICE_HOSTNAME] = uname.node
        metadata[BenchmarkMetadata.DEVICE_ARCH] = uname.machine
        metadata[BenchmarkMetadata.DEVICE_OS] = \
            f'{uname.system} {uname.release} {uname.version}'
        metadata[BenchmarkMetadata.CONFIG] = self.config.to_yaml_str()
        metadata[BenchmarkMetadata.IDLE_CPU_UTIL] = idle_cpu_util

        # Benchmark data info
        metadata[BenchmarkMetadata.BENCHMARK_MODE] = self.config.benchmark_mode.value
        if self.config.benchmark_mode in [BenchmarkMode.LOOPING, BenchmarkMode.SWEEPING]:
            metadata[BenchmarkMetadata.PEAK_THROUGHPUT_PREDICTION] = \
                self._peak_throughput_prediction
        if self.config.input_data_path:
            metadata[BenchmarkMetadata.INPUT_DATA_PATH] = self.get_input_data_absolute_path()
            metadata[BenchmarkMetadata.INPUT_DATA_SIZE] = self._input_data_size_bytes
            metadata[BenchmarkMetadata.INPUT_DATA_HASH] = self._input_data_hash
        if self.config.input_data_start_time != -1:
            metadata[BenchmarkMetadata.INPUT_DATA_START_TIME] = \
                self.config.input_data_start_time
        if self.config.input_data_end_time != -1:
            metadata[BenchmarkMetadata.INPUT_DATA_END_TIME] = \
                self.config.input_data_end_time

        final_report['metadata'] = metadata

        return final_report

    def export_report(self, report: dict) -> None:
        """Export the given report to a JSON file."""

        def to_json_compatible_helper(data):
            data_out = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    data_out[str(key)] = to_json_compatible_helper(value)
                elif isinstance(value, Enum):
                    data_out[str(key)] = str(value)
                else:
                    try:
                        json.dumps(value)
                        data_out[str(key)] = value
                    except TypeError:
                        data_out[str(key)] = str(value)
            return data_out

        if self.config.log_file_name == '':
            timestr = self._test_datetime.strftime('%Y%m%d-%H%M%S')
            log_file_path = os.path.join(self.config.log_folder, f'r2b-log-{timestr}.json')
        else:
            log_file_path = os.path.join(self.config.log_folder, self.config.log_file_name)

        with open(log_file_path, 'a') as f:
            f.write(json.dumps(to_json_compatible_helper(report)))
        self.get_logger().info(f'Exported benchmark report to {log_file_path}')

    def create_service_client_blocking(self, service_type, service_name):
        """Create a service client and wait for it to be available."""
        namespaced_service_name = self.generate_namespace(service_name)
        service_client = ClientUtility.create_service_client_blocking(
            self.node, service_type, namespaced_service_name,
            self.config.setup_service_client_timeout_sec)
        if not service_client:
            self.fail(f'Failed to create a {service_name} service client')
        return service_client

    def get_service_response_from_future_blocking(
            self,
            future,
            check_success=False,
            timeout_sec=None):
        """Block and wait for a service future to return."""
        if timeout_sec is None:
            timeout_sec = self.config.default_service_future_timeout_sec
        future_result = ClientUtility.get_service_response_from_future_blocking(
            self.node, future, timeout_sec)
        if not future_result:
            self.fail('Failed to wait for a service future')
        if check_success and not future_result.success:
            self.fail('A service returned with an unsuccess response')
        return future_result

    def prepare_buffer(self):
        """Load data from a data loader node to a playback node."""
        self.push_logger_name('Loading')

        # Check the input data file
        input_data_path = self.get_input_data_absolute_path()
        try:
            rosbag_info = rosbag2_py.Info()
            rosbag_metadata = rosbag_info.read_metadata(input_data_path, 'sqlite3')
            rosbag_file_path = input_data_path
            if len(rosbag_metadata.files) > 0:
                rosbag_file_path = os.path.join(input_data_path, rosbag_metadata.files[0].path)
            elif len(rosbag_metadata.relative_file_paths) > 0:
                rosbag_file_path = os.path.join(
                    input_data_path, rosbag_metadata.relative_file_paths[0])
            self.get_logger().info('Checking input data file...')
            self.get_logger().info(f' - Rosbag path = {rosbag_file_path}')
            if rosbag_metadata.compression_mode:
                self.get_logger().info(
                    f' - Compression mode = {rosbag_metadata.compression_mode}')
            if rosbag_metadata.compression_format:
                self.get_logger().info(
                    f' - Compression format = {rosbag_metadata.compression_format}')
            self.get_logger().info('Computing input data file hash...')
            hash_md5 = hashlib.md5()
            self._input_data_size_bytes = 0
            with open(rosbag_file_path, 'rb') as input_data:
                while True:
                    next_chunk = input_data.read(4096)
                    self._input_data_size_bytes += len(next_chunk)
                    if next_chunk == b'':
                        break
                    hash_md5.update(next_chunk)
            self._input_data_hash = hash_md5.hexdigest()
            self.get_logger().info(f' - File hash = "{self._input_data_hash}"')
            self.get_logger().info(f' - File size (bytes) = {self._input_data_size_bytes}')
        except FileNotFoundError:
            self.fail(f'Could not open the input data file at "{input_data_path}"')

        # Create service clients
        set_data_client = self.create_service_client_blocking(
            SetData, 'set_data')
        start_loading_client = self.create_service_client_blocking(
            StartLoading, 'start_loading')
        stop_loading_client = self.create_service_client_blocking(
            StopLoading, 'stop_loading')
        start_recording_client = self.create_service_client_blocking(
            StartRecording, 'start_recording')

        # Set and initialize data
        self.get_logger().info('Requesting to initialize the data loader node')
        set_data_request = SetData.Request()
        set_data_request.data_path = input_data_path
        set_data_request.publish_tf_messages = self.config.publish_tf_messages_in_set_data
        set_data_request.publish_tf_static_messages = \
            self.config.publish_tf_static_messages_in_set_data
        set_data_future = set_data_client.call_async(set_data_request)
        self.get_service_response_from_future_blocking(
            set_data_future,
            check_success=True,
            timeout_sec=self.config.set_data_service_future_timeout_sec)

        # Start recording
        self.get_logger().info('Requesting to record messages.')
        start_recording_request = StartRecording.Request()
        start_recording_request.buffer_length = self.config.playback_message_buffer_size
        start_recording_request.timeout = self.config.start_recording_service_timeout_sec
        start_recording_request.record_data_timeline = self.config.record_data_timeline
        if self.config.benchmark_mode == BenchmarkMode.TIMELINE:
            self.get_logger().info('Requesting to get topic message timestamps.')
            start_recording_request.topic_message_timestamps = self.get_topic_message_timestamps()
        start_recording_future = start_recording_client.call_async(start_recording_request)

        # Load and play messages from the data loader node
        self.get_logger().info('Requesting to load messages.')
        start_loading_request = StartLoading.Request()
        start_loading_request.publish_in_real_time = self.config.load_data_in_real_time
        if self.config.input_data_start_time != -1:
            start_loading_request.start_time_offset_ns = \
                int(self.config.input_data_start_time * (10**9))
        if self.config.input_data_end_time != -1:
            start_loading_request.end_time_offset_ns = \
                int(self.config.input_data_end_time * (10**9))
        if self.config.benchmark_mode == BenchmarkMode.TIMELINE:
            start_loading_request.repeat_data = False
        else:
            start_loading_request.repeat_data = True
        start_loading_future = start_loading_client.call_async(
            start_loading_request)

        # Wait for the recording request to finish (or time out)
        self.get_logger().info('Waiting for the recording service to end.')
        start_recording_response = self.get_service_response_from_future_blocking(
            start_recording_future,
            timeout_sec=self.config.start_recording_service_future_timeout_sec)
        recorded_topic_message_counts = start_recording_response.recorded_topic_message_counts
        recorded_message_count = start_recording_response.recorded_message_count

        # Stop loading data
        self.get_logger().info('Requesting to stop loading data.')
        stop_loading_request = StopLoading.Request()
        stop_loading_future = stop_loading_client.call_async(stop_loading_request)
        self.get_service_response_from_future_blocking(stop_loading_future)

        # Wait for data loader service (start_loading) to end
        self.get_logger().info('Waiting for the start_loading serevice to end.')
        self.get_service_response_from_future_blocking(
            start_loading_future, check_success=True)

        self.assertTrue(recorded_message_count > 0, 'No message was recorded')

        if (not self.config.record_data_timeline):
            for topic_message_count in recorded_topic_message_counts:
                topic_name = topic_message_count.topic_name
                recorded_count = topic_message_count.message_count
                if self.config.benchmark_mode == BenchmarkMode.TIMELINE:
                    target_count = 0
                    for topic_message_timestamps in \
                            start_recording_request.topic_message_timestamps:
                        if topic_message_timestamps.topic_name == topic_name:
                            target_count = len(topic_message_timestamps.timestamps_ns)
                            break
                else:
                    target_count = self.config.playback_message_buffer_size
                self.assertTrue(
                    recorded_count >= target_count,
                    f'Not all messages were loaded ({topic_name}:{recorded_count}/{target_count})')

        self.get_logger().info(
            f'All {recorded_message_count} messages were sucessfully recorded')

        self.pop_logger_name()

    def get_topic_message_timestamps(self):
        """Get topic message timestamps from the service get_topic_message_timestamps."""
        get_topic_message_timestamps_client = self.create_service_client_blocking(
            GetTopicMessageTimestamps, 'get_topic_message_timestamps')
        get_topic_message_timestamps_request = GetTopicMessageTimestamps.Request()
        if self.config.input_data_start_time != -1:
            get_topic_message_timestamps_request.start_time_offset_ns = \
                int(self.config.input_data_start_time * (10**9))
        if self.config.input_data_end_time != -1:
            get_topic_message_timestamps_request.end_time_offset_ns = \
                int(self.config.input_data_end_time * (10**9))
        get_topic_message_timestamps_future = get_topic_message_timestamps_client.call_async(
            get_topic_message_timestamps_request)
        get_topic_message_timestamps_response = self.get_service_response_from_future_blocking(
            get_topic_message_timestamps_future, check_success=True)
        return get_topic_message_timestamps_response.topic_message_timestamps

    def benchmark_body(self,
                       playback_message_count=0,
                       target_freq=0,
                       play_messages=True) -> dict:
        """
        Run benchmark test.

        Parameters
        ----------
        playback_message_count :
            The number of messages to be tested
        target_freq :
            Target test publisher rate
        play_messages :
            Enable publishing benchmark messages from a playback node

        Returns
        -------
        dict
            Performance results

        """
        # Create play_messages service
        if play_messages:
            play_messages_client = self.create_service_client_blocking(
                PlayMessages, 'play_messages')

        # Create and send monitor service requests
        monitor_service_client_map = {}
        monitor_service_future_map = {}
        for monitor_info in self.config.monitor_info_list:
            # Create a monitor service client
            start_monitoring_client = self.create_service_client_blocking(
                StartMonitoring, monitor_info.service_name)
            if start_monitoring_client is None:
                return

            # Start monitoring messages
            self.get_logger().info(
                f'Requesting to monitor end messages from service "{monitor_info.service_name}".')
            start_monitoring_request = StartMonitoring.Request()
            if not play_messages:
                start_monitoring_request.timeout = int(self.config.benchmark_duration)
                start_monitoring_request.message_count = 0
            else:
                start_monitoring_request.timeout = self.config.start_monitoring_service_timeout_sec
                start_monitoring_request.message_count = playback_message_count
            start_monitoring_request.revise_timestamps_as_message_ids = \
                self.config.revise_timestamps_as_message_ids
            start_monitoring_request.record_start_timestamps = \
                self.config.collect_start_timestamps_from_monitors
            start_monitoring_future = start_monitoring_client.call_async(
                start_monitoring_request)

            monitor_service_client_map[monitor_info.service_name] = start_monitoring_client
            monitor_service_future_map[monitor_info.service_name] = start_monitoring_future

        # Start CPU profiler
        if self.config.enable_cpu_profiler:
            self._cpu_profiler.stop_profiling()
            self._cpu_profiler.start_profiling(self.config.cpu_profiling_interval_sec)
            self.get_logger().info('CPU profiling stared.')

        playback_start_timestamps = {}
        if play_messages:
            # Start playing messages
            self.get_logger().info(
                f'Requesting to play messages in playback_mode = {self.config.benchmark_mode}.')
            play_messages_request = PlayMessages.Request()
            play_messages_request.playback_mode = self.config.benchmark_mode.value
            play_messages_request.target_publisher_rate = target_freq
            play_messages_request.message_count = playback_message_count
            play_messages_request.enforce_publisher_rate = self.config.enforce_publisher_rate
            play_messages_request.revise_timestamps_as_message_ids = \
                self.config.revise_timestamps_as_message_ids
            play_messages_future = play_messages_client.call_async(play_messages_request)

            # Watch playback node timeout
            self.get_logger().info('Waiting for the playback service to finish.')
            play_messages_response = self.get_service_response_from_future_blocking(
                play_messages_future,
                check_success=True,
                timeout_sec=self.config.play_messages_service_future_timeout_sec)

            for i in range(len(play_messages_response.timestamps.keys)):
                key = play_messages_response.timestamps.keys[i]
                start_timestamp = play_messages_response.timestamps.timestamps_ns[i]
                playback_start_timestamps[key] = start_timestamp
        else:
            self.get_logger().info(
                f'Running live benchmarking for {self.config.benchmark_duration} seconds...')
            time.sleep(int(self.config.benchmark_duration))

        # Get end timestamps from all monitors
        monitor_start_timestamps_map = {}
        monitor_end_timestamps_map = {}
        for monitor_info in self.config.monitor_info_list:
            self.get_logger().info(
                f'Waiting for the monitor service "{monitor_info.service_name}" to finish.')
            monitor_response = self.get_service_response_from_future_blocking(
                monitor_service_future_map[monitor_info.service_name])
            start_timestamps_from_monitor = {}
            end_timestamps = {}
            for i in range(len(monitor_response.end_timestamps.keys)):
                key = monitor_response.end_timestamps.keys[i]
                end_timestamp = monitor_response.end_timestamps.timestamps_ns[i]
                end_timestamps[key] = end_timestamp
                if self.config.collect_start_timestamps_from_monitors:
                    start_timestamp = monitor_response.start_timestamps.timestamps_ns[i]
                    start_timestamps_from_monitor[key] = start_timestamp
            if self.config.collect_start_timestamps_from_monitors:
                monitor_start_timestamps_map[monitor_info.service_name] = \
                    start_timestamps_from_monitor
            else:
                monitor_start_timestamps_map[monitor_info.service_name] = \
                    playback_start_timestamps
            monitor_end_timestamps_map[monitor_info.service_name] = end_timestamps

        # Stop CPU profiler
        if self.config.enable_cpu_profiler:
            self._cpu_profiler.stop_profiling()
            self.get_logger().info('CPU profiling stopped.')

        # Calculate performance results
        performance_results = {}
        for monitor_info in self.config.monitor_info_list:
            start_timestamps = monitor_start_timestamps_map[monitor_info.service_name]
            end_timestamps = monitor_end_timestamps_map[monitor_info.service_name]
            if len(end_timestamps) == 0:
                error_message = 'No messages were observed from the monitor node ' + \
                    monitor_info.service_name
                self.get_logger().error(error_message)
                raise RuntimeError(error_message)
            for calculator in monitor_info.calculators:
                performance_results.update(
                    calculator.calculate_performance(start_timestamps, end_timestamps))

        # Add CPU profiler results
        if self.config.enable_cpu_profiler:
            performance_results.update(self._cpu_profiler.get_results())

        return performance_results

    def determine_max_sustainable_framerate(self, test_func) -> float:
        """
        Find the maximum sustainable test pulbisher framerate by using autotuner.

        Parameters
        ----------
        test_func
            The benchmark function to be tested

        Returns
        -------
        float
            The maximum sustainable test pulbisher framerate

        """
        self.push_logger_name('Probing')

        # Phase 1: Binary Search to identify interval

        current_upper_freq = self.config.publisher_upper_frequency
        current_lower_freq = self.config.publisher_lower_frequency

        # Run a trial run to warm up the graph
        try:
            probe_freq = (current_upper_freq + current_lower_freq) / 2
            message_count = ceil(
                self.config.benchmark_duration *
                self.config.binary_search_duration_fraction *
                probe_freq)
            self.get_logger().info(f'Starting the trial probe at {probe_freq} Hz')
            probe_perf_results = test_func(message_count, probe_freq)
            self.print_report(
                probe_perf_results,
                sub_heading=f'Trial Probe {probe_freq}Hz')
        except Exception:
            self.get_logger().info(
                f'Ignoring an exception occured in the trial probe at {probe_freq} Hz')
        finally:
            self.get_logger().info(
                f'Finished the first trial probe at {probe_freq} Hz')

        # Continue binary search until the search window is small enough to justify a linear scan
        while (
            abs(current_upper_freq - current_lower_freq) >
            self.config.binary_search_terminal_interval_width
        ):
            probe_freq = (current_upper_freq + current_lower_freq) / 2
            self.get_logger().info(
                f'Binary Search: Probing for max sustainable frequency at {probe_freq} Hz')

            # Perform mini-benchmark at this probe frequency
            message_count = ceil(
                self.config.benchmark_duration *
                self.config.binary_search_duration_fraction *
                probe_freq)
            probe_perf_results = test_func(message_count, probe_freq)
            self.print_report(
                probe_perf_results,
                sub_heading=f'Throughput Search Probe {probe_freq}Hz')

            # Check if this probe frequency was sustainable
            first_monitor_perf = self.get_performance_results_of_first_monitor_calculator(
                probe_perf_results)
            if (first_monitor_perf[BasicPerformanceMetrics.MEAN_FRAME_RATE] >=
                first_monitor_perf[BasicPerformanceMetrics.MEAN_PLAYBACK_FRAME_RATE] -
                self.config.binary_search_acceptable_frame_rate_drop
                ) and (
                    first_monitor_perf[BasicPerformanceMetrics.NUM_MISSED_FRAMES] <=
                    ceil(first_monitor_perf[BasicPerformanceMetrics.NUM_FRAMES_SENT] *
                         self.config.binary_search_acceptable_frame_loss_fraction)
            ):
                current_lower_freq = probe_freq
            else:
                current_upper_freq = probe_freq

        target_freq = current_lower_freq

        # Phase 2: Linear scan through interval from low to high

        # Increase probe frequency, until failures occur or ceiling is reached
        while True:
            probe_freq = target_freq + self.config.linear_scan_step_size
            if probe_freq > self.config.publisher_upper_frequency:
                break

            self.get_logger().info(
                f'Linear Scan: Probing for max sustainable frequency at {probe_freq} Hz')

            # Perform mini-benchmark at this probe frequency
            message_count = ceil(
                self.config.benchmark_duration *
                self.config.linear_scan_duration_fraction *
                probe_freq)
            probe_perf_results = test_func(message_count, probe_freq)
            self.print_report(
                probe_perf_results,
                sub_heading=f'Throughput Search Probe {probe_freq}Hz')

            # Check if this probe frequency was sustainable
            first_monitor_perf = self.get_performance_results_of_first_monitor_calculator(
                probe_perf_results)
            if (first_monitor_perf[BasicPerformanceMetrics.MEAN_FRAME_RATE] >=
                first_monitor_perf[BasicPerformanceMetrics.MEAN_PLAYBACK_FRAME_RATE] -
                self.config.linear_scan_acceptable_frame_rate_drop
                ) and (
                first_monitor_perf[BasicPerformanceMetrics.NUM_MISSED_FRAMES] <=
                ceil(first_monitor_perf[BasicPerformanceMetrics.NUM_FRAMES_SENT] *
                     self.config.linear_scan_acceptable_frame_loss_fraction)
            ):
                target_freq = probe_freq
            else:
                # The new probe frequency is too high, so terminate the linear scan
                break

        self.get_logger().info(
            f'Final predicted max sustainable frequency was {target_freq}Hz')

        # Check if target frequency is at either lower or higher bound of range
        BOUNDARY_LIMIT_EPSILON = 5  # (Hz)
        if target_freq >= self.config.publisher_upper_frequency - BOUNDARY_LIMIT_EPSILON:
            self.get_logger().warn(
                f'Final playback framerate {target_freq} Hz is close to or above max framerate '
                f'{self.config.publisher_upper_frequency} Hz used in search window. ')
            self.get_logger().warn(
                'Consider increasing this maximum!')
        elif target_freq <= self.config.publisher_lower_frequency + BOUNDARY_LIMIT_EPSILON:
            self.get_logger().warn(
                f'Final playback framerate {target_freq} Hz is close to or below min framerate '
                f'{self.config.publisher_lower_frequency} Hz used in search window. ')
            self.get_logger().warn(
                'Consider decreasing this minimum!')

        self.pop_logger_name()
        return target_freq

    def pre_benchmark_hook(self):
        """Override for benchamrk setup."""
        pass

    def post_benchmark_hook(self):
        """Override for benchmark cleanup."""
        pass

    def run_benchmark(self):
        """
        Run benchmarking.

        Entry method for running benchmark method self.benchmark_body() under various
        benchmark modes.
        """
        self.get_logger().info(f'Starting {self.config.benchmark_name} Benchmark')

        self.get_logger().info('Executing pre-benchmark setup')
        self.pre_benchmark_hook()

        self.get_logger().info(f'Running benchmark: mode={self.config.benchmark_mode}')
        perf_results = {}
        if self.config.benchmark_mode == BenchmarkMode.LIVE:
            perf_results = self.run_benchmark_live_mode()
        else:
            # Prepare playback buffers
            if self.config.enable_trial_buffer_preparation:
                self.push_logger_name('Trial')
                self.get_logger().info('Starting trial message buffering')
                self.prepare_buffer()
                self.pop_logger_name()
            self.get_logger().info('Buffering test messages')
            self.prepare_buffer()
            self.get_logger().info('Finished buffering test messages')

            if self.config.benchmark_mode == BenchmarkMode.TIMELINE:
                perf_results = self.run_benchmark_timeline_playback_mode()
            elif (self.config.benchmark_mode == BenchmarkMode.LOOPING) or \
                 (self.config.benchmark_mode == BenchmarkMode.SWEEPING):
                perf_results = self.run_benchmark_looping_mode()

        final_report = self.construct_final_report(perf_results)
        self.print_report(final_report, sub_heading='Final Report')
        self.export_report(final_report)

    def run_benchmark_live_mode(self) -> dict:
        """
        Run benchmarking in live mode.

        This benchmark mode measures performance of a graph under test contains
        data sources.
        """
        self.push_logger_name('Live')

        # Run trial round
        self.push_logger_name('Trial')
        try:
            performance_results = self.benchmark_body(play_messages=False)
            self.print_report(performance_results, sub_heading='Trial')
        except Exception:
            self.get_logger().info('Ignoring an exception occured in the trial run')
        self.pop_logger_name()

        # Run benchmark iterations
        self.reset_performance_calculators()
        self._cpu_profiler.reset()
        for i in range(self.config.test_iterations):
            self.get_logger().info(f'Starting Iteration {i+1}')
            performance_results = self.benchmark_body(play_messages=False)
            self.print_report(performance_results, sub_heading=f'#{i+1}')

        # Conclude performance measurements from the iteratoins
        final_perf_results = {}
        for monitor_info in self.config.monitor_info_list:
            for calculator in monitor_info.calculators:
                final_perf_results.update(calculator.conclude_performance())
        # Conclude CPU profiler data
        if self.config.enable_cpu_profiler:
            final_perf_results.update(self._cpu_profiler.conclude_results())

        self.pop_logger_name()
        return final_perf_results

    def run_benchmark_timeline_playback_mode(self) -> dict:
        """
        Run benchmarking in timeline mode.

        This benchmark mode plays benchmark messages based on a recorded timeline.
        """
        self.push_logger_name('Timeline')
        playback_message_count = \
            int(self.config.benchmark_duration * self.config.publisher_upper_frequency)
        perf_results = self.benchmark_body(
            playback_message_count,
            self.config.publisher_upper_frequency)
        self.pop_logger_name()
        return perf_results

    def run_benchmark_looping_mode(self) -> dict:
        """
        Run benchmarking.

        This benchmark method aims to test the maximum output framerate for the
        benchmark method self.benchmark_body().
        """
        self.push_logger_name('Looping')

        # Run Autotuner
        self.get_logger().info('Running autotuner')
        target_freq = self.determine_max_sustainable_framerate(self.benchmark_body)
        self._peak_throughput_prediction = target_freq
        self.get_logger().info(
            'Finished autotuning. '
            f'Running full-scale benchmark for predicted peak frame rate: {target_freq}')

        playback_message_count = int(self.config.benchmark_duration * target_freq)

        # Run benchmark iterations
        self.reset_performance_calculators()
        self._cpu_profiler.reset()
        for i in range(self.config.test_iterations):
            self.get_logger().info(f'Starting Iteration {i+1}')
            performance_results = self.benchmark_body(
                playback_message_count,
                target_freq)
            self.print_report(performance_results, sub_heading=f'{target_freq}Hz #{i+1}')

        # Conclude performance measurements from the iteratoins
        final_perf_results = {}
        for monitor_info in self.config.monitor_info_list:
            for calculator in monitor_info.calculators:
                final_perf_results.update(calculator.conclude_performance())
        # Conclude CPU profiler data
        if self.config.enable_cpu_profiler:
            final_perf_results.update(self._cpu_profiler.conclude_results())

        # Run additional fixed rate test
        self.push_logger_name('FixedRate')
        additional_test_fixed_publisher_rates = \
            set(self.config.additional_fixed_publisher_rate_tests)
        self.get_logger().info(
            'Starting fixed publisher rate tests for: '
            f'{additional_test_fixed_publisher_rates}')
        for target_freq in additional_test_fixed_publisher_rates:
            first_monitor_perf = self.get_performance_results_of_first_monitor_calculator(
                final_perf_results)
            mean_pub_fps = first_monitor_perf[BasicPerformanceMetrics.MEAN_PLAYBACK_FRAME_RATE]
            if mean_pub_fps*1.05 < target_freq:
                self.get_logger().info(
                    f'Skipped testing the fixed publisher rate for {target_freq}fps '
                    'as it is higher than the previously measured max sustainable '
                    f'rate: {mean_pub_fps}')
                continue
            self.get_logger().info(
                f'Testing fixed publisher rate at {target_freq}fps')
            playback_message_count = int(self.config.benchmark_duration * target_freq)
            performance_results = self.benchmark_body(
                playback_message_count,
                target_freq)
            self.print_report(performance_results, sub_heading=f'Fixed {target_freq} FPS')

            # Add the test result to the output metrics
            final_perf_results[f'{target_freq}fps'] = performance_results

        self.pop_logger_name()
        return final_perf_results

    def get_performance_results_of_first_monitor_calculator(self, performance_results):
        """Get dict that contains the first calculator's performance results."""
        calculator = self.config.monitor_info_list[0].calculators[0]
        if 'report_prefix' in calculator.config and calculator.config['report_prefix']:
            return performance_results[calculator.config['report_prefix']]
        return performance_results

    def reset_performance_calculators(self):
        """Reset the states of all performance calculators associated with all monitors."""
        for monitor_info in self.config.monitor_info_list:
            for calculator in monitor_info.calculators:
                calculator.reset()
