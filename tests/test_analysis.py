import math
import unittest

from shaft_order_analysis.core import (
    AnalysisConfig,
    DataError,
    analyze,
)

TWO_PI = 2.0 * math.pi


def make_constant_speed(speed_rps, duration, dt, amp=1.0, order=2, offset=0.0):
    """Angle/vibration records at constant speed on the same time grid."""
    n = int(duration / dt) + 1
    times = [i * dt for i in range(n)]
    angles = [TWO_PI * speed_rps * t for t in times]
    vib = [offset + amp * math.cos(order * a) for a in angles]
    return times, angles, times, vib


class ConstantSpeedTests(unittest.TestCase):
    def test_recovers_order_amplitude(self):
        t, a, tv, v = make_constant_speed(2.0, 5.0, 0.001, amp=1.5, order=3)
        report = analyze(t, a, tv, v, AnalysisConfig(points_per_rev=64, orders=(1, 2, 3)))
        self.assertEqual(len(report.revolutions), 10)
        for rev in report.revolutions:
            self.assertAlmostEqual(rev.order_amplitudes[3], 1.5, places=3)
            self.assertAlmostEqual(rev.order_amplitudes[1], 0.0, places=3)
            self.assertAlmostEqual(rev.mean_speed_rps, 2.0, places=6)

    def test_dc_offset_removed(self):
        t, a, tv, v = make_constant_speed(1.0, 4.0, 0.002, amp=0.8, order=2, offset=5.0)
        report = analyze(t, a, tv, v, AnalysisConfig(points_per_rev=32, orders=(1, 2)))
        for rev in report.revolutions:
            self.assertAlmostEqual(rev.order_amplitudes[2], 0.8, places=3)
            self.assertAlmostEqual(rev.order_amplitudes[1], 0.0, places=3)

    def test_partial_revolutions_dropped(self):
        # 3.5 revolutions -> only 3 complete revolutions analyzed.
        t, a, tv, v = make_constant_speed(1.0, 3.5, 0.005)
        report = analyze(t, a, tv, v, AnalysisConfig(points_per_rev=16, orders=(1,)))
        self.assertEqual(len(report.revolutions), 3)
        self.assertEqual(report.revolutions[0].start_angle, 0.0)
        self.assertAlmostEqual(report.revolutions[-1].end_angle, 3 * TWO_PI)


class VariableSpeedTests(unittest.TestCase):
    def test_speed_change(self):
        # Speed ramps from 1 to 3 rps; vibration locked to 2nd order.
        n = 4001
        duration = 4.0
        times = [duration * i / (n - 1) for i in range(n)]
        # angle(t) = 2*pi*(t + 0.5*t^2) -> speed 1..3 rps
        angles = [TWO_PI * (t + 0.5 * t * t) for t in times]
        vib = [0.7 * math.cos(2 * ang) for ang in angles]
        report = analyze(times, angles, times, vib,
                         AnalysisConfig(points_per_rev=64, orders=(1, 2, 4)))
        self.assertEqual(len(report.revolutions), 12)
        for rev in report.revolutions:
            self.assertAlmostEqual(rev.order_amplitudes[2], 0.7, places=3)
            self.assertAlmostEqual(rev.order_amplitudes[1], 0.0, places=3)
        speeds = [rev.mean_speed_rps for rev in report.revolutions]
        self.assertTrue(all(b > s for s, b in zip(speeds, speeds[1:])))

    def test_different_time_grids(self):
        # Angle and vibration sampled on different, non-aligned grids.
        n_a = 501
        n_v = 737
        duration = 3.0
        at = [duration * i / (n_a - 1) for i in range(n_a)]
        angles = [TWO_PI * 1.5 * t for t in at]
        vt = [duration * i / (n_v - 1) for i in range(n_v)]
        vib = [1.2 * math.cos(3 * TWO_PI * 1.5 * t) for t in vt]
        report = analyze(at, angles, vt, vib,
                         AnalysisConfig(points_per_rev=32, orders=(3,)))
        self.assertEqual(len(report.revolutions), 4)
        for rev in report.revolutions:
            self.assertAlmostEqual(rev.order_amplitudes[3], 1.2, places=2)


class EmptyAndValidationTests(unittest.TestCase):
    def test_no_complete_revolution(self):
        t, a, tv, v = make_constant_speed(1.0, 0.5, 0.005)
        report = analyze(t, a, tv, v, AnalysisConfig(points_per_rev=16, orders=(1,)))
        self.assertEqual(report.revolutions, [])
        self.assertIn("no complete revolution", report.empty_reason)

    def test_no_time_overlap(self):
        t, a, tv, v = make_constant_speed(1.0, 3.0, 0.01)
        tv2 = [x + 100.0 for x in tv]
        report = analyze(t, a, tv2, v, AnalysisConfig(points_per_rev=16, orders=(1,)))
        self.assertEqual(report.revolutions, [])
        self.assertIn("no overlapping time range", report.empty_reason)

    def test_order_must_be_below_nyquist(self):
        with self.assertRaises(DataError):
            AnalysisConfig(points_per_rev=8, orders=(4,))

    def test_points_per_rev_must_be_positive_even(self):
        with self.assertRaises(DataError):
            AnalysisConfig(points_per_rev=7, orders=(1,))


class SynchronousAverageTests(unittest.TestCase):
    def test_synchronous_average_not_mean_of_amplitudes(self):
        # Phase flips between revolutions: per-rev amplitudes stay high,
        # synchronous average cancels out.
        n = 2001
        duration = 4.0
        times = [duration * i / (n - 1) for i in range(n)]
        angles = [TWO_PI * t for t in times]

        def vib_at(angle):
            rev = int(angle / TWO_PI)
            sign = 1.0 if rev % 2 == 0 else -1.0
            return sign * math.cos(angle)

        vib = [vib_at(ang) for ang in angles]
        report = analyze(times, angles, times, vib,
                         AnalysisConfig(points_per_rev=32, orders=(1,)))
        self.assertEqual(len(report.revolutions), 4)
        for rev in report.revolutions:
            self.assertAlmostEqual(rev.order_amplitudes[1], 1.0, places=4)
        self.assertAlmostEqual(report.rms_by_order[1], 1.0, places=4)
        self.assertAlmostEqual(report.synchronous_order_amplitudes[1], 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
