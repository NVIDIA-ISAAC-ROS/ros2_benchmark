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

"""Tegrastats profiler class to measure CPU and GPU performance of benchmark tests."""

import numbers
from pathlib import Path
import re
import shutil
import subprocess
import time

import numpy as np

from .profiler import Profiler
from .resource_metrics import ResourceMetrics


class TegrastatsProfiler(Profiler):
    """Tegrastats profiler class to measure CPU and GPU performance of benchmark tests."""

    def __init__(self, tegrastats_path='tegrastats'):
        """Construct CPU profiler."""
        super().__init__()
        self.tegrastats_path = tegrastats_path
        if shutil.which(self.tegrastats_path) is None:
            raise FileNotFoundError(f'{self.tegrastats_path} not found in $PATH')
        self._tegrastats_process = None
        self._tegrastats_output_lines = []

    def start_profiling(self, interval: float = 1.0) -> Path:
        """
        Start tegrastats profiling to keep track of performance metrics.

        Parameters
        ----------
        interval: float
            The interval between measurements, in seconds

        """
        super().start_profiling()
        self._tegrastats_process = subprocess.Popen(
            [self.tegrastats_path, '--interval', str(int(interval*1000))],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return self._log_file_path

    def stop_profiling(self):
        """Stop profiling."""
        super().stop_profiling()
        if self._tegrastats_process is not None:
            self._tegrastats_process.terminate()
            output, _ = self._tegrastats_process.communicate()
            output = output.decode('utf-8')
            self._tegrastats_output_lines = output.splitlines()
            self._tegrastats_process = None

    @staticmethod
    def get_current_usage():
        """Return current tegrastats usage."""
        tegrastats_profiler = TegrastatsProfiler()
        tegrastats_profiler.start_profiling(interval=0.1)
        time.sleep(2)
        tegrastats_profiler.stop_profiling()
        return tegrastats_profiler.get_results()

    def get_results(self, log_file_path=None) -> dict:
        """Return tegrastats profiling results."""
        assert not self._is_running, 'Cannot collect results until profiler has been stopped!'

        if log_file_path is not None:
            self.get_logger().warn(f'Ignored provided log_file_path={log_file_path} as '
                                   'TegrastatsProfiler does not use it.')

        profile_data = {}
        gpu_values = []
        cpu_values = []
        for line in self._tegrastats_output_lines:
            fields = line.split()
            gpu_str = fields[fields.index('GR3D_FREQ')+1]
            cpu_str = fields[fields.index('CPU')+1][1:-1]
            gpu_values.append(float(gpu_str.split('%')[0]))
            cpu_array = re.split('%@[0-9]+[,]?', cpu_str)
            cpu_array = [float(value) for value in cpu_array[:-1]]
            cpu_values.append(np.mean(cpu_array))

        profile_data[ResourceMetrics.BASELINE_DEVICE_UTILIZATION] = gpu_values[0]
        profile_data[ResourceMetrics.MEAN_DEVICE_UTILIZATION] = np.mean(gpu_values)
        profile_data[ResourceMetrics.STDDEV_DEVICE_UTILIZATION] = np.std(gpu_values)
        profile_data[ResourceMetrics.MAX_DEVICE_UTILIZATION] = max(gpu_values)
        profile_data[ResourceMetrics.MIN_DEVICE_UTILIZATION] = min(gpu_values)

        profile_data[ResourceMetrics.BASELINE_OVERALL_CPU_UTILIZATION] = cpu_values[0]
        profile_data[ResourceMetrics.MEAN_OVERALL_CPU_UTILIZATION] = np.mean(cpu_values)
        profile_data[ResourceMetrics.STDDEV_OVERALL_CPU_UTILIZATION] = np.std(cpu_values)
        profile_data[ResourceMetrics.MAX_OVERALL_CPU_UTILIZATION] = max(cpu_values)
        profile_data[ResourceMetrics.MIN_OVERALL_CPU_UTILIZATION] = min(cpu_values)

        self._profile_data_list.append(profile_data)
        return profile_data

    def reset(self):
        """Reset the profiler state."""
        self.stop_profiling()
        self._profile_data_list.clear()
        return

    def conclude_results(self) -> dict:
        """Conclude final profiling outcome based on all previous results."""
        if len(self._profile_data_list) == 0:
            self.get_logger().warn('No prior profile data to conclude')
            return {}

        MEAN_METRICS = [
            # baseline
            ResourceMetrics.BASELINE_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.BASELINE_DEVICE_UTILIZATION,
            ResourceMetrics.BASELINE_HOST_MEMORY_UTILIZATION,
            ResourceMetrics.BASELINE_DEVICE_MEMORY_UTILIZATION,
            ResourceMetrics.BASELINE_ENCODER_UTILIZATION,
            ResourceMetrics.BASELINE_DECODER_UTILIZATION,
            # mean
            ResourceMetrics.MEAN_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.MEAN_DEVICE_UTILIZATION,
            ResourceMetrics.MEAN_HOST_MEMORY_UTILIZATION,
            ResourceMetrics.MEAN_DEVICE_MEMORY_UTILIZATION,
            ResourceMetrics.MEAN_ENCODER_UTILIZATION,
            ResourceMetrics.MEAN_DECODER_UTILIZATION,
            # std
            ResourceMetrics.STDDEV_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.STDDEV_DEVICE_UTILIZATION,
            ResourceMetrics.STDDEV_HOST_MEMORY_UTILIZATION,
            ResourceMetrics.STDDEV_DEVICE_MEMORY_UTILIZATION,
            ResourceMetrics.STDDEV_ENCODER_UTILIZATION,
            ResourceMetrics.STDDEV_DECODER_UTILIZATION,
        ]
        MAX_METRICS = [
            ResourceMetrics.MAX_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.MAX_DEVICE_UTILIZATION,
            ResourceMetrics.MAX_HOST_MEMORY_UTILIZATION,
            ResourceMetrics.MAX_DEVICE_MEMORY_UTILIZATION,
            ResourceMetrics.MAX_ENCODER_UTILIZATION,
            ResourceMetrics.MAX_DECODER_UTILIZATION,
        ]
        MIN_METRICS = [
            ResourceMetrics.MIN_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.MIN_DEVICE_UTILIZATION,
            ResourceMetrics.MIN_HOST_MEMORY_UTILIZATION,
            ResourceMetrics.MIN_DEVICE_MEMORY_UTILIZATION,
            ResourceMetrics.MIN_ENCODER_UTILIZATION,
            ResourceMetrics.MIN_DECODER_UTILIZATION,
        ]

        final_profile_data = {}
        for metric in ResourceMetrics:
            metric_value_list = [profile_data.get(metric, None) for
                                 profile_data in self._profile_data_list]
            if not all(isinstance(value, numbers.Number) for value in metric_value_list):
                continue

            # Remove the best and the worst before concluding the metric
            metric_value_list.remove(max(metric_value_list))
            metric_value_list.remove(min(metric_value_list))

            if metric in MEAN_METRICS:
                final_profile_data[metric] = sum(metric_value_list)/len(metric_value_list)
            elif metric in MAX_METRICS:
                final_profile_data[metric] = max(metric_value_list)
            elif metric in MIN_METRICS:
                final_profile_data[metric] = min(metric_value_list)
            else:
                final_profile_data[metric] = 'INVALID VALUES: NO CONCLUDED METHOD ASSIGNED'

        self.reset()
        return final_profile_data
