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
from inspect import signature
import platform

from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration


class NsysUtility():
    """Utilities for enabling Nsight System profiling."""

    @staticmethod
    def generate_launch_args():
        """
        Generate launch args for nsight systme profiling.

        Usage Example: launch_test <path to your script>
                       enable_nsys:=<true, false>
                       nsys_profile_name:=<your profile output name>
                       nsys_profile_flags:=<your profiling flags>
        """
        return [
            DeclareLaunchArgument('enable_nsys', default_value='false',
                                  description='Enable nsys profiling'),
            DeclareLaunchArgument('nsys_profile_name', default_value='',
                                  description='Label to append for nsys profile output'),
            DeclareLaunchArgument('nsys_profile_flags', default_value='--trace=osrt,nvtx,cuda',
                                  description='Flags for nsys profile')
        ]

    @staticmethod
    def generate_nsys_prefix(context):
        """Generate prefi for nsight systme profiling."""
        enable_nsys = IfCondition(LaunchConfiguration(
            'enable_nsys')).evaluate(context)
        nsys_profile_name = LaunchConfiguration(
            'nsys_profile_name').perform(context)
        nsys_profile_flags = LaunchConfiguration(
            'nsys_profile_flags').perform(context)

        container_prefix = ''
        if enable_nsys:
            if(not nsys_profile_name):
                current_time = datetime.datetime.now(datetime.timezone.utc).\
                               strftime('%Y-%m-%dT%H:%M:%SZ')
                nsys_profile_name = f'profile_{platform.machine()}_{current_time}'
            container_prefix = f'nsys profile {nsys_profile_flags} -o {nsys_profile_name}'
        return (enable_nsys, container_prefix)

    @staticmethod
    def launch_setup_wrapper(context, launch_setup):
        """Invoke the launch_setup method with nsys parameters for ComposableNodeContainer."""
        enable_nsys, container_prefix = NsysUtility.generate_nsys_prefix(context)
        launch_setup_parameters = signature(launch_setup).parameters
        if (not all(param in launch_setup_parameters for param in
                    ['container_prefix', 'container_sigterm_timeout'])):
            if enable_nsys:
                raise RuntimeError(
                    'Incorrect launch_setup signature. '
                    'When Nsys is enbaled, the signature must be: '
                    'def launch_setup(container_prefix, container_sigterm_timeout)')
            else:
                return launch_setup()
        container_sigterm_timeout = '1000' if enable_nsys else '5'
        return launch_setup(
            container_prefix=container_prefix,
            container_sigterm_timeout=container_sigterm_timeout)
