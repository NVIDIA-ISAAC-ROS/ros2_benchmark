# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2021-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
"""Nvidia SMI profiler class to measure CPU and GPU performance of benchmark tests."""

import numbers
import os
from pathlib import Path
import subprocess
from threading import Thread

import numpy as np
import psutil

from .profiler import Profiler
from .resource_metrics import ResourceMetrics

try:
    result = subprocess.run(
        ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
        capture_output=True, text=True, timeout=5)
    nvidia_smi_available = (result.returncode == 0)
except Exception:
    nvidia_smi_available = False

CPU_IDENTIFIER_STR = 'CPU: '
GPU_IDENTIFIER_STR = 'GPU: '


class NvidiaSmiProfiler(Profiler):
    """Profiler using nvidia-smi for GPU stats and psutil for CPU stats."""

    def __init__(self):
        """Construct NvidiaSmiProfiler."""
        super().__init__()
        if not nvidia_smi_available:
            self.get_logger().warning('nvidia-smi not available. GPU profiling disabled.')
        self.oc_event_count_at_start = None
        self.oc_event_count_for_run = None
        self.profiler_thread = None

    def _query_gpu_stats(self):
        """Query GPU utilization and memory from nvidia-smi."""
        if not nvidia_smi_available:
            return None, None
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None, None
            line = result.stdout.strip().split('\n')[0]
            parts = [p.strip() for p in line.split(',')]
            gpu_util = float(parts[0])
            mem_used = float(parts[1])
            mem_total = float(parts[2])
            mem_util = round(100 * mem_used / mem_total, 2)
            return gpu_util, mem_util
        except Exception:
            return None, None

    def start_profiling(self, interval: float = 1.0) -> Path:
        """
        Start profiling thread to keep track of performance metrics.

        Parameters
        ----------
        interval: float
            The interval between measurements, in seconds

        """
        super().start_profiling()
        self.oc_event_count_at_start = self._get_oc_event_count()

        def profiler_log_func():
            with open(self._log_file_path, 'w+') as logfile:
                while self._is_running:
                    cpu_line = f'{CPU_IDENTIFIER_STR}' \
                        f'{psutil.cpu_percent(interval=interval, percpu=True)}\n'
                    logfile.write(cpu_line)

                    if nvidia_smi_available:
                        gpu_util, mem_util = self._query_gpu_stats()
                        if gpu_util is not None:
                            gpu_line = f'{GPU_IDENTIFIER_STR}{gpu_util},{mem_util}\n'
                            logfile.write(gpu_line)

        self.profiler_thread = Thread(target=profiler_log_func)
        self.profiler_thread.start()
        return self._log_file_path

    def stop_profiling(self):
        """Stop profiling."""
        if self._is_running:
            super().stop_profiling()
            if self.profiler_thread is not None:
                self.profiler_thread.join()
        current_oc_count = self._get_oc_event_count()
        if current_oc_count is not None and self.oc_event_count_at_start is not None:
            self.oc_event_count_for_run = current_oc_count - self.oc_event_count_at_start

    @staticmethod
    def get_current_usage():
        """Return current resource usage."""
        profile_data = {}
        profile_data[ResourceMetrics.MEAN_OVERALL_CPU_UTILIZATION] = \
            np.mean(psutil.cpu_percent(interval=1.0, percpu=True))

        if nvidia_smi_available:
            profiler = NvidiaSmiProfiler()
            gpu_util, mem_util = profiler._query_gpu_stats()
            if gpu_util is not None:
                profile_data[ResourceMetrics.MEAN_DEVICE_UTILIZATION] = gpu_util
            if mem_util is not None:
                profile_data[ResourceMetrics.MEAN_DEVICE_MEMORY_UTILIZATION] = mem_util
        return profile_data

    def get_results(self, log_file_path=None) -> dict:
        """Return profiling results."""
        assert not self._is_running, 'Cannot collect results until profiler has been stopped!'

        log_file_path = self._log_file_path if log_file_path is None else log_file_path
        assert self._log_file_path is not None, 'No log file for reading profiling results.'

        profile_data = {}
        with open(log_file_path) as logfile:
            cpu_util_values = []
            gpu_util_values = []
            gpu_memory_values = []
            for line in logfile.readlines():
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

            if len(cpu_util_values) > 0:
                profile_data[ResourceMetrics.BASELINE_OVERALL_CPU_UTILIZATION] = \
                    cpu_util_values[0]
                profile_data[ResourceMetrics.MEAN_OVERALL_CPU_UTILIZATION] = \
                    np.mean(cpu_util_values)
                profile_data[ResourceMetrics.MAX_OVERALL_CPU_UTILIZATION] = \
                    np.max(cpu_util_values)
                profile_data[ResourceMetrics.MIN_OVERALL_CPU_UTILIZATION] = \
                    np.min(cpu_util_values)
                profile_data[ResourceMetrics.STDDEV_OVERALL_CPU_UTILIZATION] = \
                    np.std(cpu_util_values)

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

        if self.oc_event_count_for_run is not None:
            profile_data[ResourceMetrics.OC_EVENT_COUNT] = self.oc_event_count_for_run

        self._profile_data_list.append(profile_data)
        return profile_data

    def reset(self):
        """Reset the profiler state."""
        self._profile_data_list.clear()
        self.oc_event_count_at_start = None
        self.oc_event_count_for_run = None

    def conclude_results(self) -> dict:
        """Conclude final profiling outcome based on all previous results."""
        if len(self._profile_data_list) == 0:
            self.get_logger().warning('No prior profile data to conclude')
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
            ResourceMetrics.OC_EVENT_COUNT,
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
            if len(metric_value_list) > 2:
                metric_value_list.remove(max(metric_value_list))
                metric_value_list.remove(min(metric_value_list))
            if len(metric_value_list) == 0:
                continue

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

    def _get_oc_event_count(self):
        """
        Get current overcurrent event counter on supported systems.

        OC events result in severe CPU/GPU throttling, so they are an important metric to monitor
        during benchmarking. Returns None if not available (e.g., on x86 systems).
        """
        oc_event_file = None
        if os.path.exists('/sys/devices'):
            for root, dirs, files in os.walk('/sys/devices'):
                for file in files:
                    if file == 'oc3_event_cnt':
                        oc_event_file = os.path.join(root, file)
                        break
                if oc_event_file:
                    break

        oc_event_cnt = None
        if oc_event_file and os.path.exists(oc_event_file):
            with open(oc_event_file, 'r') as f:
                oc_event_cnt = int(f.read().strip())

        return oc_event_cnt
