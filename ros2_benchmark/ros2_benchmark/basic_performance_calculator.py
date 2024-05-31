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

from enum import Enum
import numbers

import numpy
import rclpy


class BasicPerformanceMetrics(Enum):
    """Basic performance metrics."""

    RECEIVED_DURATION = 'Delta between First & Last Received Frames (ms)'
    MEAN_PLAYBACK_FRAME_RATE = 'Mean Playback Frame Rate (fps)'
    MEAN_FRAME_RATE = 'Mean Frame Rate (fps)'
    NUM_MISSED_FRAMES = '# of Missed Frames'
    NUM_FRAMES_SENT = '# of Frames Sent'
    FIRST_SENT_RECEIVED_LATENCY = 'First Sent to First Received Latency (ms)'
    LAST_SENT_RECEIVED_LATENCY = 'Last Sent to Last Received Latency (ms)'
    FIRST_INPUT_LATENCY = 'First Frame End-to-end Latency (ms)'
    LAST_INPUT_LATENCY = 'Last Frame End-to-end Latency (ms)'
    MAX_LATENCY = 'Max. End-to-End Latency (ms)'
    MIN_LATENCY = 'Min. End-to-End Latency (ms)'
    MEAN_LATENCY = 'Mean End-to-End Latency (ms)'
    MAX_JITTER = 'Max. Frame-to-Frame Jitter (ms)'
    MIN_JITTER = 'Min. Frame-to-Frame Jitter (ms)'
    MEAN_JITTER = 'Mean Frame-to-Frame Jitter (ms)'
    STD_DEV_JITTER = 'Frame-to-Frame Jitter Std. Deviation (ms)'


class BasicPerformanceCalculator():
    """Calculator that computes performance with basic metrics."""

    def __init__(self, config: dict = {}) -> None:
        """Initialize the calculator."""
        self.config = config
        self._report_prefix = config.get('report_prefix', '')
        self._message_key_match = config.get('message_key_match', False)
        self._logger = None
        self._perf_data_list = []

    def set_logger(self, logger):
        """Set logger that enables to print log messages."""
        self._logger = logger

    def get_logger(self):
        """Get logger for printing log messages."""
        if self._logger is not None:
            return self._logger
        return rclpy.logging.get_logger(self.__class__.__name__)

    def get_info(self):
        """Return a dict containing information for loading this calculator class."""
        info = {}
        info['module_name'] = self.__class__.__module__
        info['class_name'] = self.__class__.__name__
        info['config'] = self.config
        return info

    def reset(self):
        """Reset the calculator state."""
        self._perf_data_list.clear()

    def calculate_performance(self,
                              start_timestamps_ns: dict,
                              end_timestamps_ns: dict) -> dict:
        """Calculate performance based on message start and end timestamps."""
        perf_data = {}

        # BasicPerformanceMetrics.RECEIVED_DURATION
        last_end_timestamp_ms = list(end_timestamps_ns.values())[-1] / 10**6
        first_end_timestamp_ms = list(end_timestamps_ns.values())[0] / 10**6
        received_duration_ms = last_end_timestamp_ms - first_end_timestamp_ms
        perf_data[BasicPerformanceMetrics.RECEIVED_DURATION] = received_duration_ms

        # BasicPerformanceMetrics.MEAN_PLAYBACK_FRAME_RATE
        if (len(start_timestamps_ns) > 1):
            last_sent_time_ms = list(start_timestamps_ns.values())[-1] / 10**6
            first_sent_time_ms = list(start_timestamps_ns.values())[0] / 10**6
            sent_duration_ms = last_sent_time_ms - first_sent_time_ms
            perf_data[BasicPerformanceMetrics.MEAN_PLAYBACK_FRAME_RATE] = len(
                start_timestamps_ns) / (sent_duration_ms / 1000.0)

            perf_data[BasicPerformanceMetrics.FIRST_SENT_RECEIVED_LATENCY] = \
                first_end_timestamp_ms - first_sent_time_ms
            perf_data[BasicPerformanceMetrics.LAST_SENT_RECEIVED_LATENCY] = \
                last_end_timestamp_ms - last_sent_time_ms

            perf_data[BasicPerformanceMetrics.NUM_MISSED_FRAMES] = \
                len(start_timestamps_ns) - len(end_timestamps_ns)
            perf_data[BasicPerformanceMetrics.NUM_FRAMES_SENT] = len(start_timestamps_ns)

        # BasicPerformanceMetrics.MEAN_FRAME_RATE
        if received_duration_ms > 0:
            perf_data[BasicPerformanceMetrics.MEAN_FRAME_RATE] = len(
                end_timestamps_ns) / (received_duration_ms / 1000.0)
        else:
            self.get_logger().warning(
                'Could not compute MEAN_FRAME_RATE due to an invalid value of'
                f'RECEIVED_DURATION = {received_duration_ms}')
            self.get_logger().warning(
                'This could be caused by insufficient timestamps received: '
                f'#start_timestamps={len(start_timestamps_ns)} '
                f'#end_timestamps = {len(end_timestamps_ns)}')

        if self._message_key_match:
            # Calculate latency between sent and received messages
            end_to_end_latencies_ms = []
            for message_key, start_timestamp_ns in start_timestamps_ns.items():
                if message_key in end_timestamps_ns:
                    end_to_end_latencies_ms.append(
                        (end_timestamps_ns[message_key] - start_timestamp_ns) / 10**6)

            if len(end_to_end_latencies_ms) > 0:
                perf_data[BasicPerformanceMetrics.FIRST_INPUT_LATENCY] = \
                    end_to_end_latencies_ms[0]
                perf_data[BasicPerformanceMetrics.LAST_INPUT_LATENCY] = \
                    end_to_end_latencies_ms[-1]
                perf_data[BasicPerformanceMetrics.MAX_LATENCY] = \
                    max(end_to_end_latencies_ms)
                perf_data[BasicPerformanceMetrics.MIN_LATENCY] = \
                    min(end_to_end_latencies_ms)
                perf_data[BasicPerformanceMetrics.MEAN_LATENCY] = \
                    sum(end_to_end_latencies_ms) / len(end_to_end_latencies_ms)
            else:
                self.get_logger().warning('No end-to-end latency data available.')

        # Calculate frame-to-frame jitter if at least 3 valid end timestamps are received
        if len(end_timestamps_ns) > 2:
            np_end_timestamps_ms = (numpy.array(list(end_timestamps_ns.values())))/(10**6)
            jitters = numpy.abs(numpy.diff(numpy.diff(np_end_timestamps_ms)))
            perf_data[BasicPerformanceMetrics.MAX_JITTER] = float(numpy.max(jitters))
            perf_data[BasicPerformanceMetrics.MIN_JITTER] = float(numpy.min(jitters))
            perf_data[BasicPerformanceMetrics.MEAN_JITTER] = float(numpy.mean(jitters))
            perf_data[BasicPerformanceMetrics.STD_DEV_JITTER] = float(numpy.std(
                jitters))
        else:
            self.get_logger().warning(
                'Received insufficient end timestamps for calculating frame-to-frame jitters.'
                f'3 were needed but only {len(end_timestamps_ns)} timestamp(s) were received.')

        # Store the current perf results to be concluded later
        self._perf_data_list.append(perf_data)

        if self._report_prefix != '':
            return {self._report_prefix: perf_data}
        return perf_data

    def conclude_performance(self) -> dict:
        """Calculate final statistical performance outcome based on all results."""
        if len(self._perf_data_list) == 0:
            self.get_logger().warn('No prior performance measurements to conclude')
            return {}

        MEAN_METRICS = [
            BasicPerformanceMetrics.NUM_FRAMES_SENT,
            BasicPerformanceMetrics.FIRST_INPUT_LATENCY,
            BasicPerformanceMetrics.LAST_INPUT_LATENCY,
            BasicPerformanceMetrics.FIRST_SENT_RECEIVED_LATENCY,
            BasicPerformanceMetrics.LAST_SENT_RECEIVED_LATENCY,
            BasicPerformanceMetrics.MEAN_LATENCY,
            BasicPerformanceMetrics.NUM_MISSED_FRAMES,
            BasicPerformanceMetrics.RECEIVED_DURATION,
            BasicPerformanceMetrics.MEAN_FRAME_RATE,
            BasicPerformanceMetrics.STD_DEV_JITTER,
            BasicPerformanceMetrics.MEAN_PLAYBACK_FRAME_RATE,
        ]
        MAX_METRICS = [
            BasicPerformanceMetrics.MAX_LATENCY,
            BasicPerformanceMetrics.MAX_JITTER,
            BasicPerformanceMetrics.MEAN_JITTER,
        ]
        MIN_METRICS = [
            BasicPerformanceMetrics.MIN_LATENCY,
            BasicPerformanceMetrics.MIN_JITTER,
        ]

        final_perf_data = {}
        for metric in BasicPerformanceMetrics:
            metric_value_list = [perf_data.get(metric, None) for perf_data in self._perf_data_list]
            if not all(isinstance(value, numbers.Number) for value in metric_value_list):
                continue

            # Remove the best and the worst before concluding the metric
            metric_value_list.remove(max(metric_value_list))
            metric_value_list.remove(min(metric_value_list))

            if metric in MEAN_METRICS:
                final_perf_data[metric] = sum(metric_value_list)/len(metric_value_list)
            elif metric in MAX_METRICS:
                final_perf_data[metric] = max(metric_value_list)
            elif metric in MIN_METRICS:
                final_perf_data[metric] = min(metric_value_list)
            else:
                final_perf_data[metric] = 'INVALID VALUES: NO CONCLUDED METHOD ASSIGNED'

        self.reset()
        if self._report_prefix != '':
            return {self._report_prefix: final_perf_data}
        return final_perf_data
