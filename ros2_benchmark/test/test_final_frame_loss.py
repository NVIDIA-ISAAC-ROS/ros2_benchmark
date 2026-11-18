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
"""Reject invalid measured iterations before a successful summary can be exported."""

from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock

from ros2_benchmark import ros2_benchmark_test as benchmark_module
from ros2_benchmark.basic_performance_calculator import BasicPerformanceMetrics as Metrics
from ros2_benchmark.ros2_benchmark_config import BenchmarkMode


class TestFinalFrameLoss(unittest.TestCase):
    """Exercise the search predicate and the complete run-to-export control flow."""

    def metrics(self, sent=100, missed=0):
        return {Metrics.NUM_FRAMES_SENT: sent, Metrics.NUM_MISSED_FRAMES: missed,
                Metrics.MEAN_FRAME_RATE: 20, Metrics.MEAN_PLAYBACK_FRAME_RATE: 20}

    def controller(self, missed_counts, tolerance=0.05, fixed=False, prefix=''):
        calculator = Mock(config={'report_prefix': prefix})
        summary = self.metrics()
        calculator.conclude_performance.return_value = {prefix: summary} if prefix else summary
        config = SimpleNamespace(
            benchmark_name='Final loss validation', benchmark_mode=BenchmarkMode.LOOPING,
            enable_trial_buffer_preparation=False, collect_node_parameters=False,
            export_monitor_raw_data=False, publisher_lower_frequency=20 if fixed else 10,
            publisher_upper_frequency=20, benchmark_duration=5, test_iterations=5,
            pre_trial_run_wait_time_sec=0, post_trial_run_wait_time_sec=0,
            enable_resource_profiler=False, additional_fixed_publisher_rate_tests=[],
            linear_scan_acceptable_frame_loss_fraction=tolerance,
            monitor_info_list=[SimpleNamespace(calculators=[calculator])])
        observations = [self.metrics(missed=n) for n in missed_counts]
        if prefix:
            # The first JSON entry is deliberately not the configured primary monitor.
            observations = [{'auxiliary': self.metrics(), prefix: m} for m in observations]
        if fixed:
            observations.insert(0, {})  # Discarded fixed-rate trial run.
        controller = SimpleNamespace(
            config=config, get_logger=Mock(return_value=Mock()),
            pre_benchmark_hook=Mock(), prepare_buffer=Mock(),
            push_logger_name=Mock(), pop_logger_name=Mock(),
            determine_max_sustainable_framerate=Mock(return_value=20),
            benchmark_body=Mock(side_effect=observations), print_report=Mock(),
            reset_performance_calculators=Mock(), _resource_profiler=Mock(),
            assertTrue=self.assertTrue, construct_final_report=Mock(return_value=summary),
            export_report=Mock())
        cls = benchmark_module.ROS2BenchmarkTest
        for name in ('run_benchmark_looping_mode',
                     'get_performance_results_of_first_monitor_calculator'):
            setattr(controller, name, MethodType(getattr(cls, name), controller))
        self.calculator = calculator
        return controller

    def test_exact_fraction_and_configured_override(self):
        accepts = benchmark_module._frame_loss_is_acceptable
        for sent, missed, limit, expected in (
                (100, 5, 0.05, True), (100, 6, 0.05, False),
                (5, 1, 0.05, False), (72, 4, 0.05, False),
                (100, 0, 0, True), (100, 1, 0, False),
                (100, 8, 0.10, True), (100, 2, 0.01, False)):
            with self.subTest(sent=sent, missed=missed, limit=limit):
                self.assertEqual(accepts(self.metrics(sent, missed), limit), expected)

    def test_invalid_evidence_and_configuration_cannot_pass(self):
        accepts = benchmark_module._frame_loss_is_acceptable
        for sent, missed in ((0, 0), (100, -1), (100, 101), (None, 0), (100, None),
                             (float('nan'), 0), (100, float('inf')), ('100', 0)):
            with self.subTest(sent=sent, missed=missed):
                self.assertFalse(accepts(self.metrics(sent, missed), 0.05))
        for limit in (-0.01, 1.01, float('nan'), float('inf')):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    accepts(self.metrics(), limit)

    def test_bad_final_iteration_cannot_be_trimmed_or_exported(self):
        for bad_index in range(5):
            with self.subTest(bad_index=bad_index):
                counts = [0] * 5
                counts[bad_index] = 6
                controller = self.controller(counts)
                with self.assertRaisesRegex(AssertionError, f'iteration {bad_index+1}'):
                    benchmark_module.ROS2BenchmarkTest.run_benchmark(controller)
                self.calculator.conclude_performance.assert_not_called()
                controller.construct_final_report.assert_not_called()
                controller.export_report.assert_not_called()

    def test_configured_primary_monitor_is_checked(self):
        controller = self.controller([41] * 5, prefix='Depth')
        with self.assertRaisesRegex(AssertionError, 'missed=41, sent=100'):
            benchmark_module.ROS2BenchmarkTest.run_benchmark(controller)
        controller.export_report.assert_not_called()

    def test_valid_final_measurements_export_once(self):
        for limit, missed in ((0.05, 5), (0.10, 8), (0, 0)):
            with self.subTest(limit=limit):
                controller = self.controller([missed] * 5, tolerance=limit)
                benchmark_module.ROS2BenchmarkTest.run_benchmark(controller)
                self.assertEqual(controller.benchmark_body.call_count, 5)
                controller.export_report.assert_called_once()

    def test_explicit_fixed_rate_measurements_retain_loss_diagnostics(self):
        controller = self.controller([40] * 5, fixed=True)
        benchmark_module.ROS2BenchmarkTest.run_benchmark(controller)
        controller.determine_max_sustainable_framerate.assert_not_called()
        self.assertEqual(controller.benchmark_body.call_count, 6)
        controller.export_report.assert_called_once()


if __name__ == '__main__':
    unittest.main()
