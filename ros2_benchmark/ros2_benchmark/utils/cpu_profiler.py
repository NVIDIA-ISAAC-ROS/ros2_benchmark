# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2021-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from enum import Enum
import numbers
from pathlib import Path
from threading import Thread

import numpy as np
import psutil

from .profiler import Profiler


class CPUProfilingMetrics(Enum):
    """Metrics for CPU profiling."""

    MAX_CPU_UTIL = 'Max. CPU Util. (%)'
    MIN_CPU_UTIL = 'Min. CPU Util. (%)'
    MEAN_CPU_UTIL = 'Mean CPU Util. (%)'
    STD_DEV_CPU_UTIL = 'Std. Deviation CPU Util. (%)'
    BASELINE_CPU_UTIL = 'Baseline CPU Util. (%)'


class CPUProfiler(Profiler):
    """CPU profiler class to measure CPU performance of benchmark tests."""

    def __init__(self):
        """Construct CPU profiler."""
        super().__init__()

    def start_profiling(self, interval: float = 1.0) -> Path:
        """
        Start CPU profiling thread to keep track of performance metrics.

        Parameters
        ----------
        interval: float
            The interval between measurements, in seconds

        """
        super().start_profiling()

        # While the is_running flag is true, log CPU usage
        def psutil_log():
            with open(self._log_file_path, 'w+') as logfile:
                while self._is_running:
                    logfile.write(
                        f'{psutil.cpu_percent(interval=interval, percpu=True)}\n')

        self.psutil_thread = Thread(target=psutil_log)
        self.psutil_thread.start()

        return self._log_file_path

    def stop_profiling(self):
        """Stop profiling."""
        if self._is_running:
            super().stop_profiling()
            # Wait for thread to stop
            self.psutil_thread.join()

    @staticmethod
    def get_current_cpu_usage():
        """Return current CPU usage."""
        return np.mean(psutil.cpu_percent(interval=1.0, percpu=True))

    def get_results(self, log_file_path=None) -> dict:
        """Return CPU profiling results."""
        assert not self._is_running, 'Cannot collect results until profiler has been stopped!'

        log_file_path = self._log_file_path if log_file_path is None else log_file_path
        assert self._log_file_path is not None, 'No log file for reading CPU  profiling results.'

        profile_data = {}
        with open(log_file_path) as logfile:
            cpu_values = []
            for line in logfile.readlines():
                # Remove brackets from line before splitting entries by comma
                cpu_values.append(np.mean([float(v)
                                  for v in line[1:-2].split(',')]))

            cpu_values = np.array(cpu_values)
            profile_data[CPUProfilingMetrics.MAX_CPU_UTIL] = np.max(cpu_values)
            profile_data[CPUProfilingMetrics.MIN_CPU_UTIL] = np.min(cpu_values)
            profile_data[CPUProfilingMetrics.MEAN_CPU_UTIL] = np.mean(cpu_values)
            profile_data[CPUProfilingMetrics.STD_DEV_CPU_UTIL] = np.std(cpu_values)
            profile_data[CPUProfilingMetrics.BASELINE_CPU_UTIL] = cpu_values[0]

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
            CPUProfilingMetrics.MEAN_CPU_UTIL,
            CPUProfilingMetrics.STD_DEV_CPU_UTIL,
            CPUProfilingMetrics.BASELINE_CPU_UTIL
        ]
        MAX_METRICS = [
            CPUProfilingMetrics.MAX_CPU_UTIL
        ]
        MIN_METRICS = [
            CPUProfilingMetrics.MIN_CPU_UTIL
        ]

        final_profile_data = {}
        for metric in CPUProfilingMetrics:
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
