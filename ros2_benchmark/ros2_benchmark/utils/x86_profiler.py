# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2021-2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
"""CPU profiler class to measure performance of benchmark tests."""

import numbers
from pathlib import Path
from threading import Thread

import numpy as np
import psutil

from .profiler import Profiler
from .resource_metrics import ResourceMetrics

try:
    import gpustat
    gpustat_imported = True
except Exception:
    gpustat_imported = False

CPU_IDENTIFIER_STR = 'CPU: '
GPU_IDENTIFIER_STR = 'GPU: '


class X86Profiler(Profiler):
    """x86 profiler class to measure x86 performance of benchmark tests."""

    def __init__(self):
        """Construct x86 profiler."""
        super().__init__()
        if not gpustat_imported:
            self.get_logger().warn('Failed to import gpustat. Disabled GPU profiling.')

    def start_profiling(self, interval: float = 1.0) -> Path:
        """
        Start x86 profiling thread to keep track of performance metrics.

        Parameters
        ----------
        interval: float
            The interval between measurements, in seconds

        """
        super().start_profiling()

        # While the is_running flag is true, log CPU/GPU usage
        def profiler_log_func():
            with open(self._log_file_path, 'w+') as logfile:
                while self._is_running:
                    # Measure CPU stats
                    cpu_line = f'{CPU_IDENTIFIER_STR}' \
                        f'{psutil.cpu_percent(interval=interval, percpu=True)}\n'
                    logfile.write(cpu_line)

                    if gpustat_imported:
                        # Measure GPU stats
                        gpu_query = gpustat.new_query().gpus[0]
                        gpu_util = gpu_query.utilization
                        gpu_memory_util = round(
                            100 * gpu_query.memory_used / gpu_query.memory_total, 2)
                        gpu_line = f'{GPU_IDENTIFIER_STR}{gpu_util},{gpu_memory_util}\n'
                        logfile.write(gpu_line)

        self.profiler_thread = Thread(target=profiler_log_func)
        self.profiler_thread.start()

        return self._log_file_path

    def stop_profiling(self):
        """Stop profiling."""
        if self._is_running:
            super().stop_profiling()
            # Wait for thread to stop
            self.profiler_thread.join()

    @staticmethod
    def get_current_usage():
        """Return current x86 usage."""
        profile_data = {}
        profile_data[ResourceMetrics.MEAN_OVERALL_CPU_UTILIZATION] = \
            np.mean(psutil.cpu_percent(interval=1.0, percpu=True))
        if gpustat_imported:
            gpu_query = gpustat.new_query().gpus[0]
            profile_data[ResourceMetrics.MEAN_DEVICE_UTILIZATION] = \
                gpu_query.utilization
            profile_data[ResourceMetrics.MEAN_DEVICE_MEMORY_UTILIZATION] = \
                round(100 * gpu_query.memory_used / gpu_query.memory_total, 2)
        return profile_data

    def get_results(self, log_file_path=None) -> dict:
        """Return x86 profiling results."""
        assert not self._is_running, 'Cannot collect results until profiler has been stopped!'

        log_file_path = self._log_file_path if log_file_path is None else log_file_path
        assert self._log_file_path is not None, 'No log file for reading CPU  profiling results.'

        profile_data = {}
        with open(log_file_path) as logfile:
            cpu_util_values = []
            gpu_util_values = []
            gpu_memory_values = []
            for line in logfile.readlines():
                # Remove brackets from line before splitting entries by comma

                if line[:len(CPU_IDENTIFIER_STR)] == CPU_IDENTIFIER_STR:
                    line = line[len(CPU_IDENTIFIER_STR):]
                    cpu_util_values.append(np.mean([float(v) for v in line[1:-2].split(',')]))

                if line[:len(GPU_IDENTIFIER_STR)] == GPU_IDENTIFIER_STR:
                    line = line[len(GPU_IDENTIFIER_STR):]
                    gpu_value_list = line.replace('\n', '').split(',')
                    gpu_util_values.append(float(gpu_value_list[0]))
                    gpu_memory_values.append(float(gpu_value_list[1]))

            cpu_util_values = np.array(cpu_util_values)
            gpu_util_values = np.array(gpu_util_values)
            gpu_memory_values = np.array(gpu_memory_values)

            profile_data[ResourceMetrics.BASELINE_OVERALL_CPU_UTILIZATION] = cpu_util_values[0]
            profile_data[ResourceMetrics.MEAN_OVERALL_CPU_UTILIZATION] = np.mean(cpu_util_values)
            profile_data[ResourceMetrics.MAX_OVERALL_CPU_UTILIZATION] = np.max(cpu_util_values)
            profile_data[ResourceMetrics.MIN_OVERALL_CPU_UTILIZATION] = np.min(cpu_util_values)
            profile_data[ResourceMetrics.STDDEV_OVERALL_CPU_UTILIZATION] = np.std(cpu_util_values)

            if len(gpu_util_values) > 0:
                profile_data[ResourceMetrics.BASELINE_DEVICE_UTILIZATION] = gpu_util_values[0]
                profile_data[ResourceMetrics.MEAN_DEVICE_UTILIZATION] = np.mean(gpu_util_values)
                profile_data[ResourceMetrics.STDDEV_DEVICE_UTILIZATION] = np.std(gpu_util_values)
                profile_data[ResourceMetrics.MAX_DEVICE_UTILIZATION] = max(gpu_util_values)
                profile_data[ResourceMetrics.MIN_DEVICE_UTILIZATION] = min(gpu_util_values)

            if len(gpu_memory_values) > 0:
                profile_data[ResourceMetrics.BASELINE_DEVICE_MEMORY_UTILIZATION] = \
                    gpu_memory_values[0]
                profile_data[ResourceMetrics.MEAN_DEVICE_MEMORY_UTILIZATION] = np.mean(
                    gpu_memory_values)
                profile_data[ResourceMetrics.STDDEV_DEVICE_MEMORY_UTILIZATION] = np.std(
                    gpu_memory_values)
                profile_data[ResourceMetrics.MAX_DEVICE_MEMORY_UTILIZATION] = \
                    max(gpu_memory_values)
                profile_data[ResourceMetrics.MIN_DEVICE_MEMORY_UTILIZATION] = \
                    min(gpu_memory_values)

        self._profile_data_list.append(profile_data)

        return profile_data

    def reset(self):
        """Reset the profiler state."""
        self._profile_data_list.clear()
        return

    def conclude_results(self) -> dict:
        """Conclude final profiling outcome based on all previous results."""
        if len(self._profile_data_list) == 0:
            self.get_logger().warn('No prior profile data to conclude')
            return {}

        MEAN_METRICS = [
            ResourceMetrics.BASELINE_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.BASELINE_DEVICE_UTILIZATION,
            ResourceMetrics.BASELINE_DEVICE_MEMORY_UTILIZATION,
            ResourceMetrics.MEAN_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.MEAN_DEVICE_UTILIZATION,
            ResourceMetrics.MEAN_DEVICE_MEMORY_UTILIZATION,
            ResourceMetrics.STDDEV_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.STDDEV_DEVICE_UTILIZATION,
            ResourceMetrics.STDDEV_DEVICE_MEMORY_UTILIZATION,
        ]
        MAX_METRICS = [
            ResourceMetrics.MAX_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.MAX_DEVICE_UTILIZATION,
            ResourceMetrics.MAX_DEVICE_MEMORY_UTILIZATION,
        ]
        MIN_METRICS = [
            ResourceMetrics.MIN_OVERALL_CPU_UTILIZATION,
            ResourceMetrics.MIN_DEVICE_UTILIZATION,
            ResourceMetrics.MIN_DEVICE_MEMORY_UTILIZATION,
        ]

        final_profile_data = {}
        for metric in ResourceMetrics:
            metric_value_list = [
                profile_data.get(metric, None) for profile_data in self._profile_data_list
            ]
            if not all(isinstance(value, numbers.Number) for value in metric_value_list):
                continue

            # Remove the best and the worst before concluding the metric
            metric_value_list.remove(max(metric_value_list))
            metric_value_list.remove(min(metric_value_list))

            if metric in MEAN_METRICS:
                final_profile_data[metric] = sum(metric_value_list) / len(metric_value_list)
            elif metric in MAX_METRICS:
                final_profile_data[metric] = max(metric_value_list)
            elif metric in MIN_METRICS:
                final_profile_data[metric] = min(metric_value_list)
            else:
                final_profile_data[metric] = 'INVALID VALUES: NO CONCLUDED METHOD ASSIGNED'

        self.reset()
        return final_profile_data
