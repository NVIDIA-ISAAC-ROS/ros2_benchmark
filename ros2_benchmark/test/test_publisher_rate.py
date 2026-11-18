# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
"""Check publisher-rate evidence and its controller behavior without launching nodes."""

import math
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from ros2_benchmark import ros2_benchmark_test as benchmark_module
from ros2_benchmark.ros2_benchmark_config import BenchmarkMode
from ros2_benchmark.ros2_benchmark_test import _achieved_publisher_rate
from ros2_benchmark.ros2_benchmark_test import _publisher_rate_is_sufficient


class TestPublisherRate(unittest.TestCase):
    """Distinguish average offered rate from deadline jitter and sample-count bias."""

    def test_uniform_jittered_and_unordered_samples(self):
        cases = [
            ([10, 11, 12, 13], [0, 1000000, 2000000, 3000000]),
            ([10, 11, 12, 13], [0, 2100000, 2200000, 3000000]),
            ([12, 10, 11], [2000000, 0, 1000000]),
        ]
        for keys, timestamps in cases:
            with self.subTest(keys=keys, timestamps=timestamps):
                self.assertEqual(_achieved_publisher_rate(keys, timestamps), 1000.0)

    def test_low_rate_count_bias_cannot_accept_underdriven_probe(self):
        rate = _achieved_publisher_rate(range(5), [0, 10**9, 2*10**9, 3*10**9, 4*10**9])
        self.assertEqual(rate, 1.0)
        self.assertTrue(_publisher_rate_is_sufficient(rate, 1.0, 0.01))
        self.assertFalse(_publisher_rate_is_sufficient(rate, 1.25, 0.01))
        self.assertFalse(_publisher_rate_is_sufficient(400, 2000, 0.01))

    def test_invalid_or_insufficient_timestamp_evidence_fails_closed(self):
        cases = [([], []), ([0], [0]), ([0, 1], [0]), ([0, 0], [0, 1]),
                 ([0, 1], [1, 1]), ([0, 1, 2], [0, 2, 1]),
                 ([2, 0, 1], [1, 0, 2]), ([0, 1], [0, math.nan])]
        for keys, timestamps in cases:
            with self.subTest(keys=keys, timestamps=timestamps):
                rate = _achieved_publisher_rate(keys, timestamps)
                self.assertIsNone(rate)
                self.assertFalse(_publisher_rate_is_sufficient(rate, 1000, 0.01))

    def test_tolerance_boundaries_and_invalid_configuration(self):
        achieved_rate = _achieved_publisher_rate(
            [0, 1, 2, 3], [0, 2100000, 2200000, 3000000])
        self.assertTrue(_publisher_rate_is_sufficient(achieved_rate, 1000, 0.01))

        for rate, tolerance, expected in [(990, 0.01, True), (989.999, 0.01, False),
                                          (1000, 0, True), (999.999, 0, False)]:
            with self.subTest(rate=rate, tolerance=tolerance):
                self.assertEqual(_publisher_rate_is_sufficient(rate, 1000, tolerance), expected)
        for tolerance in (-0.01, 1, math.nan, math.inf):
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                _publisher_rate_is_sufficient(1000, 1000, tolerance)
        for target in (0, -1, math.nan, math.inf):
            with self.subTest(target=target):
                self.assertFalse(_publisher_rate_is_sufficient(1000, target, 0.01))

    @staticmethod
    def make_controller(mode, timestamps, deadline_rate_met=False):
        response = SimpleNamespace(
            publisher_rate_met=deadline_rate_met,
            timestamps=SimpleNamespace(keys=list(range(len(timestamps))),
                                       timestamps_ns=timestamps))
        client = MagicMock()
        controller = SimpleNamespace(
            config=SimpleNamespace(
                benchmark_mode=mode, monitor_info_list=[], enable_resource_profiler=False,
                enforce_publisher_rate=False, revise_timestamps_as_message_ids=False,
                play_messages_service_future_timeout_sec=1, publisher_rate_tolerance_fraction=0.01,
                pre_stop_monitoring_wait_time_sec=0, export_monitor_raw_data=False,
                benchmark_duration=0),
            create_service_client_blocking=MagicMock(return_value=client),
            get_service_response_from_future_blocking=MagicMock(return_value=response),
            get_logger=MagicMock(return_value=MagicMock()))
        return controller, client

    def test_controller_uses_average_despite_missed_deadline(self):
        cases = [([0, 2100000, 2200000, 3000000], True),
                 ([0, 2500000, 5000000, 7500000], False)]
        for timestamps, expected in cases:
            with self.subTest(timestamps=timestamps):
                controller, _ = self.make_controller(BenchmarkMode.LOOPING, timestamps)
                result = benchmark_module.ROS2BenchmarkTest.benchmark_body(controller, 4, 1000)
                self.assertEqual(result, {})
                self.assertEqual(controller._playback_rate_met, expected)

    def test_single_frame_fixed_rate_timeline_and_live_do_not_abort(self):
        for mode, play, expected in [(BenchmarkMode.LOOPING, True, False),
                                     (BenchmarkMode.TIMELINE, True, True),
                                     (BenchmarkMode.LIVE, False, True)]:
            with self.subTest(mode=mode):
                controller, client = self.make_controller(mode, [0])
                controller.config.enforce_publisher_rate = True
                result = benchmark_module.ROS2BenchmarkTest.benchmark_body(
                    controller, 1, 1, play_messages=play)
                self.assertEqual(result, {})
                self.assertEqual(controller._playback_rate_met, expected)
                if play:
                    self.assertTrue(client.call_async.call_args.args[0].enforce_publisher_rate)


if __name__ == '__main__':
    unittest.main()
