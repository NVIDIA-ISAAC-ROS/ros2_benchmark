# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check that a quiet ROS executor cannot prevent the service deadline check."""

import os
import subprocess
import sys
import textwrap
import unittest


class TestServiceDeadline(unittest.TestCase):
    """Exercise the real executor in a process that can be killed on regression."""

    def test_pending_future_times_out_without_callbacks(self):
        script = textwrap.dedent("""
            import time
            import rclpy
            from rclpy.task import Future
            from ros2_benchmark.utils.ros2_utility import ClientUtility

            rclpy.init()
            node = rclpy.create_node('service_deadline_test', enable_rosout=False)
            try:
                for _ in range(5):
                    rclpy.spin_once(node, timeout_sec=0)
                future = Future()
                start = time.monotonic()
                result = ClientUtility.get_service_response_from_future_blocking(
                    node, future, 0.15)
                elapsed = time.monotonic() - start
                assert result is None, result
                assert 0.10 <= elapsed < 1.0, elapsed
                assert not future.done(), 'Timeout must not cancel server work'
            finally:
                node.destroy_node()
                rclpy.shutdown()
        """)
        result = subprocess.run(
            [sys.executable, '-c', script],
            env={**os.environ, 'PYTHONPATH': os.pathsep.join(sys.path),
                 'ROS_AUTOMATIC_DISCOVERY_RANGE': 'LOCALHOST'},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
