"""Core angular-domain order analysis (standard library only)."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field

TWO_PI = 2.0 * math.pi


class DataError(ValueError):
    """Raised when input records fail validation."""


def _load_two_column_csv(path, first_name, second_name):
    times = []
    values = []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if rows and rows[0][0].strip().lower() in ("time", "t", "time_s"):
        rows = rows[1:]
    for lineno, row in enumerate(rows, start=1):
        if len(row) < 2:
            raise DataError(f"{path}: row {lineno} needs two columns")
        try:
            t = float(row[0])
            v = float(row[1])
        except ValueError as exc:
            raise DataError(f"{path}: row {lineno} is not numeric") from exc
        if not (math.isfinite(t) and math.isfinite(v)):
            raise DataError(f"{path}: row {lineno} has non-finite data")
        times.append(t)
        values.append(v)
    if len(times) < 2:
        raise DataError(f"{path}: need at least two samples")
    _require_strictly_increasing(times, path, "time")
    return times, values


def _require_strictly_increasing(values, path, name):
    for i in range(1, len(values)):
        if not values[i] > values[i - 1]:
            raise DataError(f"{path}: {name} must be strictly increasing")


def load_angle_csv(path):
    """Load (time_s, cumulative_angle_rad); both strictly increasing."""
    times, angles = _load_two_column_csv(path, "angle", "angle")
    _require_strictly_increasing(angles, path, "cumulative angle")
    return times, angles


def load_vibration_csv(path):
    """Load (time_s, vibration); time strictly increasing."""
    times, values = _load_two_column_csv(path, "vibration", "vibration")
    return times, values


def _interp(xs, ys, x):
    """Linear interpolation; xs strictly increasing, x within [xs[0], xs[-1]]."""
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    frac = (x - xs[lo]) / span
    return ys[lo] + frac * (ys[hi] - ys[lo])


def _dft_magnitudes(samples, orders):
    """Peak amplitudes 2*|X_k|/N for the requested orders."""
    n = len(samples)
    mean = sum(samples) / n
    centered = [s - mean for s in samples]
    result = {}
    for order in orders:
        re = 0.0
        im = 0.0
        for j, value in enumerate(centered):
            phase = -TWO_PI * order * j / n
            re += value * math.cos(phase)
            im += value * math.sin(phase)
        result[order] = 2.0 * math.hypot(re, im) / n
    return result


@dataclass(frozen=True)
class AnalysisConfig:
    points_per_rev: int = 64
    orders: tuple = (1, 2, 3, 4)

    def __post_init__(self):
        if (
            not isinstance(self.points_per_rev, int)
            or self.points_per_rev <= 0
            or self.points_per_rev % 2 != 0
        ):
            raise DataError("points_per_rev must be a positive even integer")
        for order in self.orders:
            if not isinstance(order, int) or order < 1:
                raise DataError("orders must be positive integers")
            if order >= self.points_per_rev / 2:
                raise DataError(
                    f"order {order} must be < points_per_rev/2 "
                    f"({self.points_per_rev / 2})"
                )


@dataclass
class RevolutionResult:
    index: int
    start_angle: float
    end_angle: float
    start_time: float
    end_time: float
    mean_speed_rps: float
    samples: list
    order_amplitudes: dict


@dataclass
class AnalysisReport:
    config: AnalysisConfig
    revolutions: list = field(default_factory=list)
    rms_by_order: dict = field(default_factory=dict)
    synchronous_average: list = field(default_factory=list)
    synchronous_order_amplitudes: dict = field(default_factory=dict)
    empty_reason: str = ""


def analyze(angle_times, angles, vib_times, vib_values, config=None):
    """Run the full order analysis over jointly covered complete revolutions."""
    config = config or AnalysisConfig()
    report = AnalysisReport(config=config)

    t_start = max(angle_times[0], vib_times[0])
    t_end = min(angle_times[-1], vib_times[-1])
    if t_end <= t_start:
        report.empty_reason = "no overlapping time range between the two records"
        return report

    a_start = _interp(angle_times, angles, t_start)
    a_end = _interp(angle_times, angles, t_end)
    first_rev = math.ceil(a_start / TWO_PI)
    last_rev = math.floor(a_end / TWO_PI)
    if last_rev < first_rev:
        report.empty_reason = (
            "no complete revolution within the overlapping time range"
        )
        return report

    n = config.points_per_rev
    for rev in range(first_rev, last_rev):
        angle_lo = rev * TWO_PI
        angle_hi = (rev + 1) * TWO_PI
        t_lo = _interp(angles, angle_times, angle_lo)
        t_hi = _interp(angles, angle_times, angle_hi)
        samples = []
        for j in range(n):
            angle_j = angle_lo + (angle_hi - angle_lo) * j / n
            t_j = _interp(angles, angle_times, angle_j)
            samples.append(_interp(vib_times, vib_values, t_j))
        report.revolutions.append(
            RevolutionResult(
                index=rev,
                start_angle=angle_lo,
                end_angle=angle_hi,
                start_time=t_lo,
                end_time=t_hi,
                mean_speed_rps=1.0 / (t_hi - t_lo),
                samples=samples,
                order_amplitudes=_dft_magnitudes(samples, config.orders),
            )
        )

    m = len(report.revolutions)
    if m == 0:
        report.empty_reason = (
            "no complete revolution within the overlapping time range"
        )
        return report
    for order in config.orders:
        squares = [rev.order_amplitudes[order] ** 2 for rev in report.revolutions]
        report.rms_by_order[order] = math.sqrt(sum(squares) / len(squares))

    report.synchronous_average = [
        sum(rev.samples[j] for rev in report.revolutions) / m for j in range(n)
    ]
    report.synchronous_order_amplitudes = _dft_magnitudes(
        report.synchronous_average, config.orders
    )
    return report
