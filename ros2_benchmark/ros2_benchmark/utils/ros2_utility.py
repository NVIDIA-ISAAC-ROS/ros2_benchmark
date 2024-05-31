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

import time

import rclpy


class ClientUtility:
    """A class for hosting utility methods for ROS 2 serevice clients."""

    @staticmethod
    def create_service_client_blocking(node, service_type, service_name, timeout_sec):
        """Create a service client and wait for it to be available."""
        service_client = node.create_client(service_type, service_name)
        start_time = time.time()
        while not service_client.wait_for_service(timeout_sec=1):
            node.get_logger().info(
                f'{service_name} service is not available yet, waiting...')
            if (time.time() - start_time) > timeout_sec:
                node.get_logger().info(
                    f'Creating {service_name} service client timed out')
                return None
        return service_client

    @staticmethod
    def get_service_response_from_future_blocking(node, future, timeout_sec):
        """Block and wait for a service future to return."""
        start_time = time.time()
        while not future.done():
            rclpy.spin_once(node)
            if (time.time() - start_time) > timeout_sec:
                node.get_logger().info(
                    f'Waiting for a service future timed out ({timeout_sec}s)')
                return None
        return future.result()
