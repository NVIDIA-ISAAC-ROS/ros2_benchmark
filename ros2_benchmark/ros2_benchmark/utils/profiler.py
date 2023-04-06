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

"""Profiler base class to measure the performance of benchmark tests."""

from abc import ABC, abstractmethod
from datetime import datetime
import os


class Profiler(ABC):
    """Profiler base class to measure the performance of benchmark tests."""

    DEFAILT_LOG_DIR = '/tmp'

    @abstractmethod
    def __init__(self):
        """Construct profiler."""
        self._is_running = False

        # Logfile path is generated once start_profiling() is called
        self._log_file_path = None

        self._profile_data_list = []

    @abstractmethod
    def start_profiling(self, log_dir=DEFAILT_LOG_DIR) -> None:
        """
        Run profiling program to keep track of performance metrics.

        Parameters
        ----------
        log_dir
            Path to write the logs to

        """
        assert not self._is_running, 'Profiler has already been started!'
        self._is_running = True

        # Create log file folders if they don't exist already
        os.makedirs(log_dir, exist_ok=True)

        self._log_file_path = os.path.join(
            log_dir,
            f'{type(self).__name__}_{datetime.timestamp(datetime.now())}.log')

        return self._log_file_path

    @abstractmethod
    def stop_profiling(self) -> None:
        """Stop profiling."""
        self._is_running = False

    @abstractmethod
    def get_results(self, log_file_path=None) -> dict:
        """Return profiling results."""
        return {}

    @abstractmethod
    def reset(self):
        """Reset the profiler state."""
        self._profile_data_list.clear()
        return

    @abstractmethod
    def conclude_results(self) -> dict:
        """Conclude final profiling outcome based on all previous results."""
        return {}
