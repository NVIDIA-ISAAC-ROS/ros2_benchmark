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
"""Test latency-seeded peak search without launching benchmark nodes."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from ros2_benchmark import ros2_benchmark_test as benchmark_module
from ros2_benchmark.basic_performance_calculator import BasicPerformanceCalculator
from ros2_benchmark.basic_performance_calculator import BasicPerformanceMetrics as Metrics


class TestPeakSearch(unittest.TestCase):
    """Require a measured linear-criteria pass for every returned search candidate."""

    def search(self, observe, step=5, linear_loss=0.05, duration=5):
        config = SimpleNamespace(
            publisher_lower_frequency=100, publisher_upper_frequency=120,
            pre_trial_run_wait_time_sec=0, post_trial_run_wait_time_sec=0,
            trial_run_duration_sec=0, latency_probe_iterations=0,
            benchmark_duration=duration, binary_search_duration_fraction=0.5,
            binary_search_terminal_interval_width=10,
            binary_search_acceptable_frame_rate_drop=10,
            binary_search_acceptable_frame_loss_fraction=0.05,
            linear_scan_duration_fraction=1, linear_scan_step_size=step,
            linear_scan_acceptable_frame_rate_drop=5,
            linear_scan_acceptable_frame_loss_fraction=linear_loss)
        controller = SimpleNamespace(
            config=config, push_logger_name=Mock(), pop_logger_name=Mock(),
            get_logger=Mock(return_value=Mock()), print_report=Mock(), fail=self.fail,
            get_performance_results_of_first_monitor_calculator=lambda result: result)
        self.probes = []

        def probe(count, rate):
            self.probes.append((count, rate))
            output, lost_fraction, publisher_met = observe(rate, len(self.probes))
            controller._playback_rate_met = publisher_met
            return {Metrics.MEAN_FRAME_RATE: output, Metrics.MEAN_PLAYBACK_FRAME_RATE: rate,
                    Metrics.NUM_FRAMES_SENT: count, Metrics.NUM_MISSED_FRAMES:
                    int(count * lost_fraction)}

        return benchmark_module.ROS2BenchmarkTest.determine_max_sustainable_framerate(
            controller, probe)

    def test_invalid_step_fails_before_publishing(self):
        for step in (0, -1, float('nan'), float('inf'), float('-inf')):
            with self.subTest(step=step):
                observe = Mock()
                with self.assertRaisesRegex(AssertionError, 'finite and greater than 0'):
                    self.search(observe, step=step)
                observe.assert_not_called()
                self.assertEqual(self.probes, [])

    def test_binary_seed_must_pass_each_linear_guard(self):
        for guard in ('rate', 'loss', 'publisher'):
            with self.subTest(guard=guard):
                def observe(rate, call):
                    if rate <= 105:
                        return rate, 0, True
                    if guard == 'rate':
                        return rate - 8, 0, True
                    if guard == 'loss':
                        return rate - 3, 0.03, True
                    return rate, 0, call <= 1

                self.assertEqual(self.search(observe, linear_loss=0.01), 105)
                # The binary probe is shorter than seed validation and backoff.
                self.assertEqual(self.probes, [(275, 110), (550, 110), (525, 105)])

    def test_valid_seed_retains_upward_search_and_last_passing_rate(self):
        for ceiling_passes in (False, True):
            with self.subTest(ceiling_passes=ceiling_passes):
                def observe(rate, _):
                    return (rate if rate < 120 or ceiling_passes else rate - 15), 0, True

                self.assertEqual(self.search(observe), 120 if ceiling_passes else 115)
                self.assertEqual([rate for _, rate in self.probes], [110, 110, 115, 120])

    def test_backoff_clamps_to_floor_and_fails_when_floor_fails(self):
        for floor_passes in (False, True):
            with self.subTest(floor_passes=floor_passes):
                def observe(rate, _):
                    return (rate if rate == 100 and floor_passes else rate - 8), 0, True

                if floor_passes:
                    self.assertEqual(self.search(observe, step=7), 100)
                else:
                    with self.assertRaisesRegex(AssertionError, 'minimum 100 Hz failed'):
                        self.search(observe, step=7)
                self.assertEqual([rate for _, rate in self.probes], [110, 110, 103, 100])

    def test_initial_unvalidated_floor_is_probed(self):
        def observe(rate, _):
            return (rate if rate == 100 else rate - 15), 0, True

        self.assertEqual(self.search(observe), 100)
        self.assertEqual([rate for _, rate in self.probes], [110, 100, 105])

    def test_binary_search_rejects_rounded_up_frame_loss(self):
        for missed, expected_seed in ((3, 110), (4, 100)):
            with self.subTest(missed=missed):
                def observe(rate, call):
                    if call == 1:  # The measured binary probe.
                        return rate, missed / 72, True
                    return (rate if rate <= 110 else rate - 15), 0, True

                self.assertEqual(self.search(observe, duration=144 / 110), 110)
                self.assertEqual(self.probes[0], (72, 110))
                # Four losses exceed 5%; this binary candidate must not seed linear search.
                self.assertEqual(self.probes[1][1], expected_seed)

    def test_linear_search_rejects_rounded_up_frame_loss(self):
        for missed, expected_rate in ((3, 110), (4, 105)):
            with self.subTest(missed=missed):
                def observe(rate, call):
                    if call > 1 and rate == 110:
                        return rate, missed / 72, True
                    return (rate if rate <= 110 else rate - 15), 0, True

                self.assertEqual(self.search(observe, duration=72 / 110), expected_rate)
                self.assertEqual(self.probes[1], (72, 110))


class TestBasicPerformanceCalculatorSingleMessage(unittest.TestCase):
    """Verify basic metrics for a single-message latency run."""

    def test_single_message_reports_end_to_end_latency(self):
        calculator = BasicPerformanceCalculator()
        calculator.set_logger(Mock())

        result = calculator.calculate_performance(
            {1: 1_000_000_000},
            {1: 1_025_000_000})

        self.assertEqual(result[Metrics.FIRST_SENT_RECEIVED_LATENCY], 25.0)
        self.assertEqual(result[Metrics.LAST_SENT_RECEIVED_LATENCY], 25.0)
        self.assertEqual(result[Metrics.NUM_FRAMES_SENT], 1)
        self.assertEqual(result[Metrics.NUM_MISSED_FRAMES], 0)
        self.assertNotIn(Metrics.MEAN_PLAYBACK_FRAME_RATE, result)


class TestLatencyProbeAlgorithm(unittest.TestCase):
    """Exercise optional latency seeding without launching ROS nodes."""

    def create_benchmark(
            self, trial_run_duration_sec=15.0, monitor_count=1,
            latency_probe_iterations=5,
            latency_probe_duration_sec=5.0):
        benchmark = object.__new__(benchmark_module.ROS2BenchmarkTest)
        monitor_info_list = []
        for monitor_index in range(monitor_count):
            report_prefix = f'Monitor {monitor_index}' if monitor_count > 1 else ''
            calculator = SimpleNamespace(config={'report_prefix': report_prefix})
            monitor_info_list.append(SimpleNamespace(
                service_name=f'monitor_node{monitor_index}',
                calculators=[calculator]))
        benchmark.config = SimpleNamespace(
            benchmark_duration=2.0,
            trial_run_duration_sec=trial_run_duration_sec,
            latency_probe_iterations=latency_probe_iterations,
            latency_probe_duration_sec=latency_probe_duration_sec,
            latency_probe_candidate_rate_factor=0.8,
            binary_search_duration_fraction=1.0,
            binary_search_terminal_interval_width=10.0,
            binary_search_acceptable_frame_loss_fraction=0.0,
            binary_search_acceptable_frame_rate_drop=0.0,
            linear_scan_acceptable_frame_loss_fraction=0.0,
            linear_scan_acceptable_frame_rate_drop=0.0,
            linear_scan_duration_fraction=1.0,
            linear_scan_step_size=5.0,
            monitor_info_list=monitor_info_list,
            post_trial_run_wait_time_sec=0.0,
            pre_trial_run_wait_time_sec=0.0,
            publisher_lower_frequency=10.0,
            publisher_upper_frequency=100.0,
        )
        benchmark._logger_name_stack = ['']
        benchmark.get_logger = Mock(return_value=Mock())
        benchmark.print_report = Mock()
        return benchmark

    def create_test_func(self, benchmark, latency_ms, sustainable_limit):
        calls = []
        if benchmark.config.latency_probe_iterations == 0:
            latency_samples = []
        elif isinstance(latency_ms, (list, tuple)):
            latency_samples = list(latency_ms)
        else:
            latency_samples = [
                latency_ms for _ in range(benchmark.config.latency_probe_iterations)]
        latency_sample_index = 0

        def test_func(
                message_count, target_freq, play_messages=True, calculate_performance=True):
            nonlocal latency_sample_index
            calls.append((
                message_count,
                target_freq,
                play_messages,
                calculate_performance))
            if not calculate_performance:
                return {}
            if latency_sample_index < len(latency_samples):
                benchmark._playback_rate_met = True
                sample_latency_ms = latency_samples[latency_sample_index]
                latency_sample_index += 1
                if sample_latency_ms is None:
                    raise benchmark_module.NoMonitorOutputError(
                        'No messages were observed from a monitor node')
                if not isinstance(sample_latency_ms, (list, tuple)):
                    sample_latency_ms = [
                        sample_latency_ms for _ in benchmark.config.monitor_info_list]
                if any(monitor_latency_ms is None for monitor_latency_ms in sample_latency_ms):
                    raise benchmark_module.NoMonitorOutputError(
                        'No messages were observed from a monitor node')
                latency_results = {}
                for monitor_info, monitor_latency_ms in zip(
                        benchmark.config.monitor_info_list, sample_latency_ms):
                    if isinstance(monitor_latency_ms, dict):
                        monitor_results = monitor_latency_ms
                    else:
                        monitor_results = {
                            Metrics.FIRST_SENT_RECEIVED_LATENCY: monitor_latency_ms,
                            Metrics.NUM_FRAMES_SENT: message_count,
                            Metrics.NUM_MISSED_FRAMES: 0,
                        }
                    report_prefix = monitor_info.calculators[0].config['report_prefix']
                    if report_prefix:
                        latency_results[report_prefix] = monitor_results
                    else:
                        latency_results.update(monitor_results)
                return latency_results

            sustainable = target_freq <= sustainable_limit
            benchmark._playback_rate_met = True
            monitor_results = {
                Metrics.MEAN_PLAYBACK_FRAME_RATE: target_freq,
                Metrics.MEAN_FRAME_RATE: target_freq if sustainable else 0.0,
                Metrics.NUM_FRAMES_SENT: message_count,
                Metrics.NUM_MISSED_FRAMES: 0 if sustainable else message_count,
            }
            report_prefix = (
                benchmark.config.monitor_info_list[0].calculators[0].config['report_prefix'])
            if report_prefix:
                return {report_prefix: monitor_results}
            return monitor_results

        return test_func, calls

    def assert_probe_frequencies(self, calls, expected):
        self.assertEqual(len(calls), len(expected))
        for (_, actual, _, _), expected_frequency in zip(calls, expected):
            self.assertAlmostEqual(actual, expected_frequency)

    def test_latency_seed_narrows_existing_search(self):
        benchmark = self.create_benchmark()
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=[15.0, 18.0, 20.0, 17.0, 16.0], sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 50.0)
        self.assert_probe_frequencies(calls, [10.0] * 6 + [40.0, 45.0, 50.0, 55.0])
        self.assertEqual(calls[0], (150, 10.0, True, False))
        self.assertTrue(all(call[0] == 50 for call in calls[1:6]))
        self.assertTrue(all(call[2] for call in calls[1:6]))

    def test_latency_probe_uses_duration_and_lower_bound_rate(self):
        benchmark = self.create_benchmark(
            latency_probe_iterations=1, latency_probe_duration_sec=0.25)
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=20.0, sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 50.0)
        self.assertEqual(calls[1], (3, 10.0, True, True))

    def test_latency_seed_uses_largest_latency_from_every_monitor(self):
        benchmark = self.create_benchmark(monitor_count=2)
        test_func, calls = self.create_test_func(
            benchmark,
            latency_ms=[
                [15.0, 16.0],
                [17.0, 18.0],
                [19.0, 25.0],
                [20.0, 21.0],
                [16.0, 17.0],
            ],
            sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 47.0)
        self.assert_probe_frequencies(
            calls, [10.0] * 6 + [32.0, 37.0, 42.0, 47.0, 52.0])

    def test_latency_seed_uses_largest_latency_with_fewer_than_five_samples(self):
        benchmark = self.create_benchmark(latency_probe_iterations=4)
        test_func, calls = self.create_test_func(
            benchmark,
            latency_ms=[15.0, 18.0, 20.0, 17.0],
            sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 50.0)
        self.assert_probe_frequencies(
            calls, [10.0] * 5 + [40.0, 45.0, 50.0, 55.0])

    def test_linear_scan_continues_above_inferred_upper_bound(self):
        benchmark = self.create_benchmark()
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=25.0, sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 47.0)
        self.assert_probe_frequencies(
            calls, [10.0] * 6 + [32.0, 37.0, 42.0, 47.0, 52.0])

    def test_linear_scan_backs_off_when_inferred_lower_bound_is_too_high(self):
        benchmark = self.create_benchmark()
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=12.5, sustainable_limit=60.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 59.0)
        self.assert_probe_frequencies(calls, [10.0] * 6 + [72.0, 64.0, 59.0])

    def test_missing_latency_falls_back_to_configured_window(self):
        benchmark = self.create_benchmark()
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=None, sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 49.375)
        self.assert_probe_frequencies(
            calls, [10.0] * 6 + [55.0, 32.5, 43.75, 49.375, 49.375, 54.375])

    def test_missing_monitor_output_discards_iteration(self):
        benchmark = self.create_benchmark(monitor_count=2)
        test_func, calls = self.create_test_func(
            benchmark,
            latency_ms=[
                [10.0, None],
                [20.0, 20.0],
                [15.0, 16.0],
                [17.0, 18.0],
                [19.0, 19.0],
            ],
            sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 50.0)
        self.assert_probe_frequencies(
            calls, [10.0] * 6 + [40.0, 45.0, 50.0, 55.0])

    def test_silent_iterations_are_discarded(self):
        benchmark = self.create_benchmark()
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=[None, 20.0, None, None, None], sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 50.0)
        self.assert_probe_frequencies(
            calls, [10.0] * 6 + [40.0, 45.0, 50.0, 55.0])

    def test_latency_seed_accepts_multiple_received_messages(self):
        benchmark = self.create_benchmark()
        latency_result = {
            Metrics.FIRST_SENT_RECEIVED_LATENCY: 20.0,
            Metrics.NUM_FRAMES_SENT: 3,
            Metrics.NUM_MISSED_FRAMES: 1,
        }
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=latency_result, sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 50.0)
        self.assert_probe_frequencies(
            calls, [10.0] * 6 + [40.0, 45.0, 50.0, 55.0])

    def test_candidate_above_ceiling_retains_configured_window(self):
        benchmark = self.create_benchmark()
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=5.0, sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 49.375)
        self.assert_probe_frequencies(
            calls, [10.0] * 6 + [55.0, 32.5, 43.75, 49.375, 49.375, 54.375])

    def test_negative_latency_probe_iterations_are_rejected(self):
        benchmark = self.create_benchmark(latency_probe_iterations=-1)
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=None, sustainable_limit=50.0)

        with self.assertRaisesRegex(
                ValueError, 'latency_probe_iterations must not be negative'):
            benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(calls, [])

    def test_zero_iterations_uses_trial_run_and_existing_search_sequence(self):
        benchmark = self.create_benchmark(latency_probe_iterations=0)
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=None, sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 49.375)
        self.assert_probe_frequencies(
            calls, [10.0, 55.0, 32.5, 43.75, 49.375, 49.375, 54.375])
        self.assertEqual(calls[0], (150, 10.0, True, False))
        self.assertTrue(all(calculate for _, _, _, calculate in calls[1:]))

    def test_zero_duration_skips_trial_run(self):
        benchmark = self.create_benchmark(
            latency_probe_iterations=0, trial_run_duration_sec=0.0)
        test_func, calls = self.create_test_func(
            benchmark, latency_ms=None, sustainable_limit=50.0)

        result = benchmark.determine_max_sustainable_framerate(test_func)

        self.assertEqual(result, 49.375)
        self.assert_probe_frequencies(
            calls, [55.0, 32.5, 43.75, 49.375, 49.375, 54.375])
        self.assertTrue(all(calculate for _, _, _, calculate in calls))


if __name__ == '__main__':
    unittest.main()
