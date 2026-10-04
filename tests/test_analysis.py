"""阶次分析测试：变转速、异构时间网格、直流偏置、空结果。"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shaft_order_analysis import AnalysisConfig, analyze
from shaft_order_analysis.cli import main as cli_main
from shaft_order_analysis.core import (
    DataValidationError,
    load_angle_csv,
    load_vibration_csv,
)

TWO_PI = 2.0 * math.pi


def make_angle_record(revs, points_per_rev, ramp=0.0):
    """变转速角度记录：omega(t) = 1 + ramp*t，返回 (times, angles)。"""
    n = revs * points_per_rev + 1
    if ramp:
        t_end = (-1.0 + math.sqrt(1.0 + 2.0 * ramp * revs * TWO_PI)) / ramp
    else:
        t_end = revs * TWO_PI
    times = [t_end * i / (n - 1) for i in range(n)]
    angles = [t + 0.5 * ramp * t * t for t in times]
    return times, angles


def make_vibration_record(angle_of, times, offset=0.0, amp1=0.0, amp2=0.0):
    """振动 = offset + amp1*cos(theta) + amp2*cos(2*theta)。"""
    values = [
        offset + amp1 * math.cos(angle_of(t)) + amp2 * math.cos(2.0 * angle_of(t))
        for t in times
    ]
    return list(times), values


class TestVariableSpeed(unittest.TestCase):
    def test_linear_chirp_recovers_orders(self):
        ramp = 0.3
        angle_times, angles = make_angle_record(revs=8, points_per_rev=50, ramp=ramp)
        # 振动用另一套更密且错开的时间网格。
        vib_times = [angle_times[-1] * (i + 0.37) / 1601 for i in range(1601)]
        _, vib_values = make_vibration_record(
            lambda t: t + 0.5 * ramp * t * t, vib_times, amp1=1.5, amp2=0.5
        )
        config = AnalysisConfig(samples_per_rev=64, orders=(1, 2, 3))
        result = analyze(angle_times, angles, vib_times, vib_values, config)
        self.assertIsNone(result.empty_reason)
        self.assertGreaterEqual(len(result.revolutions), 6)
        for rev in result.revolutions:
            self.assertAlmostEqual(rev.amplitudes[1], 1.5, places=2)
            self.assertAlmostEqual(rev.amplitudes[2], 0.5, places=2)
            self.assertAlmostEqual(rev.amplitudes[3], 0.0, places=2)
        self.assertAlmostEqual(result.rms_amplitudes[1], 1.5, places=2)
        self.assertAlmostEqual(result.sync_amplitudes[1], 1.5, places=2)
        rpms = [rev.mean_rpm for rev in result.revolutions]
        self.assertGreater(max(rpms) - min(rpms), 0.5)


class TestDCOffset(unittest.TestCase):
    def test_dc_offset_removed(self):
        angle_times, angles = make_angle_record(revs=5, points_per_rev=40)
        vib_times = [angle_times[-1] * i / 300 for i in range(301)]
        _, vib_values = make_vibration_record(lambda t: t, vib_times, offset=7.25, amp1=2.0)
        config = AnalysisConfig(samples_per_rev=32, orders=(1, 2))
        result = analyze(angle_times, angles, vib_times, vib_values, config)
        for rev in result.revolutions:
            self.assertAlmostEqual(rev.amplitudes[1], 2.0, places=2)
            self.assertAlmostEqual(rev.amplitudes[2], 0.0, places=2)
        # 同步平均波形已去均值（直流被移除）。
        n = len(result.sync_average)
        self.assertAlmostEqual(sum(result.sync_average) / n, 0.0, places=2)


class TestEmptyAndValidation(unittest.TestCase):
    def test_no_full_revolution(self):
        config = AnalysisConfig(samples_per_rev=8, orders=(1,))
        result = analyze([0.0, 1.0, 2.0], [0.0, 2.0, 4.0], [0.0, 1.0, 2.0], [0.0, 1.0, 0.0], config)
        self.assertEqual(result.empty_reason, "共同覆盖范围内不足一个完整转")
        self.assertEqual(result.revolutions, ())

    def test_no_overlap(self):
        config = AnalysisConfig(samples_per_rev=8, orders=(1,))
        result = analyze([0.0, 1.0], [0.0, 7.0], [5.0, 6.0], [0.0, 1.0], config)
        self.assertEqual(result.empty_reason, "两份记录的时间范围没有重叠")

    def test_partial_revolutions_discarded(self):
        config = AnalysisConfig(samples_per_rev=8, orders=(1,))
        result = analyze(
            [0.0, 10.0], [0.5 * TWO_PI, 3.5 * TWO_PI], [0.0, 10.0], [0.0, 0.0], config
        )
        self.assertEqual(len(result.revolutions), 2)
        self.assertAlmostEqual(result.revolutions[0].angle_start, TWO_PI)

    def test_validation_rejects_bad_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.csv")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("time,angle\n0.0,0.0\n0.5,0.5\n0.5,1.0\n")
            with self.assertRaises(DataValidationError):
                load_angle_csv(bad)
            nan_file = os.path.join(tmp, "nan.csv")
            with open(nan_file, "w", encoding="utf-8") as fh:
                fh.write("time,vibration\n0.0,1.0\n1.0,nan\n")
            with self.assertRaises(DataValidationError):
                load_vibration_csv(nan_file)

    def test_order_must_be_below_nyquist(self):
        with self.assertRaises(DataValidationError):
            AnalysisConfig(samples_per_rev=8, orders=(4,))
        with self.assertRaises(DataValidationError):
            AnalysisConfig(samples_per_rev=7, orders=(1,))


class TestCli(unittest.TestCase):
    def test_cli_end_to_end(self):
        angle_times, angles = make_angle_record(revs=4, points_per_rev=40, ramp=0.2)
        vib_times = [angle_times[-1] * i / 250 for i in range(251)]
        _, vib_values = make_vibration_record(
            lambda t: t + 0.1 * t * t, vib_times, offset=1.0, amp1=1.0
        )
        with tempfile.TemporaryDirectory() as tmp:
            angle_csv = os.path.join(tmp, "angle.csv")
            vib_csv = os.path.join(tmp, "vib.csv")
            resampled = os.path.join(tmp, "resampled.csv")
            report = os.path.join(tmp, "report.json")
            with open(angle_csv, "w", encoding="utf-8") as fh:
                fh.write("time,angle\n")
                for t, a in zip(angle_times, angles):
                    fh.write(f"{t},{a}\n")
            with open(vib_csv, "w", encoding="utf-8") as fh:
                fh.write("time,vibration\n")
                for t, v in zip(vib_times, vib_values):
                    fh.write(f"{t},{v}\n")
            rc = cli_main([
                "--angle-csv", angle_csv,
                "--vibration-csv", vib_csv,
                "--samples-per-rev", "32",
                "--orders", "1,2",
                "--resampled-out", resampled,
                "--report-out", report,
            ])
            self.assertEqual(rc, 0)
            import json
            with open(report, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertIsNone(data["empty_reason"])
            self.assertAlmostEqual(data["rms_amplitudes"]["1"], 1.0, places=2)
            with open(resampled, encoding="utf-8") as fh:
                lines = fh.read().strip().splitlines()
            self.assertEqual(len(lines), 1 + 32 * len(data["revolutions"]))


if __name__ == "__main__":
    unittest.main()
