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

"""Metrics for resource profiling."""

from enum import Enum


class ResourceMetrics(Enum):
    """Metrics for resource profiling."""

    RESOURCE_PROFILING_SAMPLING_RATE = 'Device Profile Sampling Rate (Hz)'
    # CPU utilization
    BASELINE_OVERALL_CPU_UTILIZATION = 'Baseline Overall CPU Utilization (%)'
    MAX_OVERALL_CPU_UTILIZATION = 'Max. Overall CPU Utilization (%)'
    MIN_OVERALL_CPU_UTILIZATION = 'Min. Overall CPU Utilization (%)'
    MEAN_OVERALL_CPU_UTILIZATION = 'Mean Overall CPU Utilization (%)'
    STDDEV_OVERALL_CPU_UTILIZATION = 'Std Dev Overall CPU Utilization (%)'
    # Host memory utilization
    BASELINE_HOST_MEMORY_UTILIZATION = 'Baseline Host Memory Utilization (%)'
    MAX_HOST_MEMORY_UTILIZATION = 'Max. Host Memory Utilization (%)'
    MIN_HOST_MEMORY_UTILIZATION = 'Min. Host Memory Utilization (%)'
    MEAN_HOST_MEMORY_UTILIZATION = 'Mean Host Memory Utilization (%)'
    STDDEV_HOST_MEMORY_UTILIZATION = 'SD. Host Memory Utilization (%)'
    # Device utilization
    BASELINE_DEVICE_UTILIZATION = 'Baseline Device Utilization (%)'
    MAX_DEVICE_UTILIZATION = 'Max. Device Utilization (%)'
    MIN_DEVICE_UTILIZATION = 'Min. Device Utilization (%)'
    MEAN_DEVICE_UTILIZATION = 'Mean Device Utilization (%)'
    STDDEV_DEVICE_UTILIZATION = 'SD. Device Utilization (%)'
    # Device memory utilization
    BASELINE_DEVICE_MEMORY_UTILIZATION = 'Baseline Device Memory Utilization (%)'
    MAX_DEVICE_MEMORY_UTILIZATION = 'Max. Device Memory Utilization (%)'
    MIN_DEVICE_MEMORY_UTILIZATION = 'Min. Device Memory Utilization (%)'
    MEAN_DEVICE_MEMORY_UTILIZATION = 'Mean Device Memory Utilization (%)'
    STDDEV_DEVICE_MEMORY_UTILIZATION = 'SD. Device Memory Utilization (%)'
    # Encoder utilization
    BASELINE_ENCODER_UTILIZATION = 'Baseline Encoder Utilization (%)'
    MAX_ENCODER_UTILIZATION = 'Max. Encoder Utilization (%)'
    MIN_ENCODER_UTILIZATION = 'Min. Encoder Utilization (%)'
    MEAN_ENCODER_UTILIZATION = 'Mean Encoder Utilization (%)'
    STDDEV_ENCODER_UTILIZATION = 'SD. Encoder Utilization (%)'
    # Decoder utilization
    BASELINE_DECODER_UTILIZATION = 'Baseline Decoder Utilization (%)'
    MAX_DECODER_UTILIZATION = 'Max. Decoder Utilization (%)'
    MIN_DECODER_UTILIZATION = 'Min. Decoder Utilization (%)'
    MEAN_DECODER_UTILIZATION = 'Mean Decoder Utilization (%)'
    STDDEV_DECODER_UTILIZATION = 'SD. Decoder Utilization (%)'
    # OC event count
    OC_EVENT_COUNT = 'Overcurrent Event Count'
