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

from enum import Enum
import importlib
import os
import sys

import yaml

from .basic_performance_calculator import BasicPerformanceCalculator
from .utils.image_utility import Resolution

BUILTIN_ros2_benchmark_CONFIG_FILE = os.path.join(
    os.path.dirname(__file__),
    'default_ros2_benchmark_config.yaml')


class MonitorPerformanceCalculatorsInfo:
    def __init__(self,
                 service_name='start_monitoring0',
                 calculators=[BasicPerformanceCalculator()]) -> None:
        """Initialize a monitor's performance calculators info."""
        self.service_name = service_name
        self.calculators = calculators

    def get_info(self):
        """Return a dict containing information for setting this monitor info object."""
        info = {}
        info['service_name'] = self.service_name
        info['calculators'] = []
        for calculator in self.calculators:
            info['calculators'].append(calculator.get_info())
        return info


class BenchmarkMode(Enum):
    """
    Benchmark modes supported in the framework.

    The enum values must match what is defined in ros2_benchmark_interfaces::srv::PlayMessage
    """

    TIMELINE = 0
    LOOPING = 1
    SWEEPING = 2
    LIVE = 3


class ROS2BenchmarkConfig():
    """A class that holds configurations for ros2_benchmark."""

    __builtin_config_file_path = BUILTIN_ros2_benchmark_CONFIG_FILE

    # It is only necessary to add a parameter to this map if we want
    # to enable overriding such a parameter from an env variable and
    # its type is not string (as env only supports string values).
    __config_type_map = {
        'revise_timestamps_as_message_ids': bool,
        'collect_start_timestamps_from_monitors': bool,
        'enable_cpu_profiler': bool,
        'publish_tf_messages_in_set_data': bool,
        'publish_tf_static_messages_in_set_data': bool,
        'load_data_in_real_time': bool,
        'record_data_timeline': bool,
        'enable_trial_buffer_preparation': bool,
        'cpu_profiling_interval_sec': float,
        'benchmark_duration': float,
        'setup_service_client_timeout_sec': float,
        'start_recording_service_timeout_sec': int,
        'start_monitoring_service_timeout_sec': int,
        'default_service_future_timeout_sec': float,
        'set_data_service_future_timeout_sec': float,
        'start_recording_service_future_timeout_sec': float,
        'play_messages_service_future_timeout_sec': float,
        'test_iterations': int,
        'playback_message_buffer_size': int,
        'publisher_upper_frequency': float,
        'publisher_lower_frequency': float,
        'enforce_publisher_rate': bool,
        'binary_search_terminal_interval_width': float,
        'binary_search_duration_fraction': float,
        'binary_search_acceptable_frame_loss_fraction': float,
        'binary_search_acceptable_frame_rate_drop': float,
        'linear_scan_step_size': float,
        'linear_scan_duration_fraction': float,
        'linear_scan_acceptable_frame_loss_fraction': float,
        'linear_scan_acceptable_frame_rate_drop': float,
        'input_data_start_time': float,
        'input_data_end_time': float
    }

    def __init__(self, config_file_path: str = '', *args, **kw):
        """Initialize default and given configs and apply to attribtues."""
        self.apply_to_attributes(dict(*args, **kw))

        if config_file_path != '':
            try:
                self.apply_to_attributes(
                    load_config_file(config_file_path)['ros2_benchmark_config'],
                    override=False)
            except (FileNotFoundError, yaml.YAMLError, TypeError) as error:
                print('Failed to load a custom benchmark config file.')
                raise error
        try:
            self.apply_to_attributes(
                load_config_file(self.__builtin_config_file_path)['ros2_benchmark_config'],
                override=False)
        except (FileNotFoundError, yaml.YAMLError, TypeError) as error:
            print('Failed to load a default benchmark config file.')
            raise error

    def apply_to_attributes(self, config_dict, override=True):
        """Apply the given configuration key-value pairs to instance attributes."""
        for key, value in config_dict.items():
            if override is False and hasattr(self, key):
                continue
            if key == 'benchmark_mode' and isinstance(value, str):
                if value not in BenchmarkMode.__members__:
                    raise TypeError(f'Unknown benchmark mode: "{value}"')
                setattr(self, key, BenchmarkMode.__members__[value])
            elif key == 'monitor_info_list':
                monitor_info_list = []
                for monitor_info in value:
                    if isinstance(monitor_info, MonitorPerformanceCalculatorsInfo):
                        monitor_info_list.append(monitor_info)
                        continue
                    calculator_list = []
                    for calculator in monitor_info['calculators']:
                        calculator_module = importlib.import_module(calculator['module_name'])
                        calculator_class = getattr(calculator_module, calculator['class_name'])
                        calculator_config = calculator['config'] if 'config' in calculator else {}
                        calculator_list.append(calculator_class(calculator_config))
                    monitor_info_list.append(
                        MonitorPerformanceCalculatorsInfo(
                            monitor_info['service_name'],
                            calculator_list))
                setattr(self, key, monitor_info_list)
            else:
                if key in self.__config_type_map:
                    value_type = self.__config_type_map[key]
                    if value_type is bool and isinstance(value, str):
                        if value.lower() in ['false', '0']:
                            value = False
                        else:
                            value = True
                    setattr(self, key, self.__config_type_map[key](value))
                else:
                    setattr(self, key, value)

    def to_yaml_str(self):
        """Export all configurations as a YAML string."""
        yaml.add_representer(Resolution, Resolution.yaml_representer)

        config_dict = {}
        for key, value in self.__dict__.items():
            if key == 'benchmark_mode':
                config_dict[key] = str(value)
            elif key == 'monitor_info_list':
                monitor_info_list_export = []
                for monitor_info in value:
                    monitor_info_list_export.append(monitor_info.get_info())
                config_dict[key] = monitor_info_list_export
            else:
                config_dict[key] = value
        return yaml.dump({'ros2_benchmark_config': config_dict}, allow_unicode=True)


def load_config_file(config_file_path: str):
    """Load a benchmark configuration file and return its dict object."""
    try:
        with open(config_file_path) as config_file:
            return yaml.safe_load(config_file.read())
    except FileNotFoundError as error:
        print('Could not find benchmark config file at '
              f'"{config_file_path}".', sys.stderr)
        raise error
    except yaml.YAMLError as error:
        print('Invalid benchmark configs detected in '
              f'"{config_file_path}".', sys.stderr)
        raise error
