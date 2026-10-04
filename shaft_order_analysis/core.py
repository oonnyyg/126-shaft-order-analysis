"""核心算法：数据校验、整转划分、角域重采样与阶次计算。"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field

TWO_PI = 2.0 * math.pi


class DataValidationError(ValueError):
    """输入数据不满足要求时抛出。"""


@dataclass(frozen=True)
class AnalysisConfig:
    """分析配置。

    samples_per_rev: 每转等角度采样点数，必须为正偶数。
    orders: 需要计算的阶次（正整数，且严格小于采样点数的一半）。
    """

    samples_per_rev: int = 64
    orders: tuple[int, ...] = (1, 2, 3)

    def __post_init__(self) -> None:
        if self.samples_per_rev <= 0 or self.samples_per_rev % 2 != 0:
            raise DataValidationError("samples_per_rev 必须为正偶数")
        half = self.samples_per_rev // 2
        for order in self.orders:
            if not isinstance(order, int) or order <= 0:
                raise DataValidationError("阶次必须为正整数")
            if order >= half:
                raise DataValidationError(
                    f"阶次 {order} 必须严格小于半采样点数 {half}"
                )


def _read_xy_csv(path: str, x_name: str, y_name: str) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or x_name not in reader.fieldnames or y_name not in reader.fieldnames:
            raise DataValidationError(
                f"{path}: 需要列 {x_name!r} 与 {y_name!r}，实际列 {reader.fieldnames}"
            )
        for row in reader:
            try:
                x = float(row[x_name])
                y = float(row[y_name])
            except (TypeError, ValueError) as exc:
                raise DataValidationError(f"{path}: 无法解析数值行 {row}") from exc
            if not (math.isfinite(x) and math.isfinite(y)):
                raise DataValidationError(f"{path}: 存在非有限数值 {row}")
            xs.append(x)
            ys.append(y)
    if len(xs) < 2:
        raise DataValidationError(f"{path}: 至少需要两行数据")
    return xs, ys


def _require_strictly_increasing(values: list[float], label: str, path: str) -> None:
    for prev, cur in zip(values, values[1:]):
        if not cur > prev:
            raise DataValidationError(f"{path}: {label} 必须严格递增（{prev} -> {cur}）")


def load_angle_csv(path: str) -> tuple[list[float], list[float]]:
    """读取时间-累计转角 CSV（列 time, angle），角度不折回。"""
    times, angles = _read_xy_csv(path, "time", "angle")
    _require_strictly_increasing(times, "时间", path)
    _require_strictly_increasing(angles, "累计转角", path)
    return times, angles


def load_vibration_csv(path: str) -> tuple[list[float], list[float]]:
    """读取时间-振动 CSV（列 time, vibration）。"""
    times, values = _read_xy_csv(path, "time", "vibration")
    _require_strictly_increasing(times, "时间", path)
    return times, values


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    """线性插值，要求 xs 严格递增且 xs[0] <= x <= xs[-1]。"""
    lo, hi = 0, len(xs) - 1
    if x <= xs[lo]:
        return ys[lo]
    if x >= xs[hi]:
        return ys[hi]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    frac = (x - xs[lo]) / span
    return ys[lo] + frac * (ys[hi] - ys[lo])


@dataclass(frozen=True)
class RevolutionSegment:
    """一整转的采样结果。"""

    index: int  # 第几转（从 0 计）
    angle_start: float  # 该转起始累计角度（2π 的整数倍）
    time_start: float  # 起始角度对应的插值时间
    time_end: float  # 结束角度对应的插值时间
    samples: tuple[float, ...]  # 等角度重采样振动值（含起点不含终点）

    @property
    def mean_rpm(self) -> float:
        return 60.0 / (self.time_end - self.time_start)


def segment_revolutions(
    angle_times: list[float],
    angles: list[float],
    vib_times: list[float],
    vib_values: list[float],
    samples_per_rev: int,
) -> tuple[list[RevolutionSegment], str | None]:
    """按累计角度 2π 整数倍划分完整转，并做等角度重采样。

    只保留两份记录时间范围共同覆盖的完整转；首尾不足一转的部分舍弃。
    返回 (分段列表, 空结果原因)。无完整转时原因非 None。
    """
    t_lo = max(angle_times[0], vib_times[0])
    t_hi = min(angle_times[-1], vib_times[-1])
    if not t_hi > t_lo:
        return [], "两份记录的时间范围没有重叠"

    # 共同时间范围对应的累计角度范围。
    a_lo = _interp(angle_times, angles, t_lo)
    a_hi = _interp(angle_times, angles, t_hi)
    first_rev = math.ceil(a_lo / TWO_PI)
    last_rev = math.floor(a_hi / TWO_PI)  # 该整数倍为最后一转的终点
    if last_rev - first_rev < 1:
        return [], "共同覆盖范围内不足一个完整转"

    segments: list[RevolutionSegment] = []
    for k in range(first_rev, last_rev):
        a_start = k * TWO_PI
        a_end = (k + 1) * TWO_PI
        t_start = _interp(angles, angle_times, a_start)  # 转角反求时间
        t_end = _interp(angles, angle_times, a_end)
        sample_angles = [
            a_start + i * TWO_PI / samples_per_rev for i in range(samples_per_rev)
        ]
        sample_times = [_interp(angles, angle_times, a) for a in sample_angles]
        samples = tuple(_interp(vib_times, vib_values, t) for t in sample_times)
        segments.append(
            RevolutionSegment(
                index=k - first_rev,
                angle_start=a_start,
                time_start=t_start,
                time_end=t_end,
                samples=samples,
            )
        )
    return segments, None


def order_amplitudes(samples: tuple[float, ...], orders: tuple[int, ...]) -> dict[int, float]:
    """去均值后用 DFT 计算各阶次峰值幅度：2*|X_k|/N。"""
    n = len(samples)
    mean = sum(samples) / n
    centered = [s - mean for s in samples]
    result: dict[int, float] = {}
    for order in orders:
        re = 0.0
        im = 0.0
        for i, value in enumerate(centered):
            phase = -TWO_PI * order * i / n
            re += value * math.cos(phase)
            im += value * math.sin(phase)
        result[order] = 2.0 * math.hypot(re, im) / n
    return result


@dataclass(frozen=True)
class RevolutionResult:
    """单转分析结果。"""

    index: int
    angle_start: float
    time_start: float
    time_end: float
    mean_rpm: float
    amplitudes: dict[int, float]
    samples: tuple[float, ...] = ()


@dataclass(frozen=True)
class AnalysisResult:
    """整体分析结果。"""

    config: AnalysisConfig
    revolutions: tuple[RevolutionResult, ...]
    rms_amplitudes: dict[int, float]  # 各阶次跨转幅度均方根
    sync_average: tuple[float, ...]  # 跨转同步平均波形（已去均值）
    sync_amplitudes: dict[int, float]  # 同步平均波形的阶次幅度
    empty_reason: str | None = None


def analyze(
    angle_times: list[float],
    angles: list[float],
    vib_times: list[float],
    vib_values: list[float],
    config: AnalysisConfig,
) -> AnalysisResult:
    """完整分析流程。"""
    segments, reason = segment_revolutions(
        angle_times, angles, vib_times, vib_values, config.samples_per_rev
    )
    if reason is not None:
        return AnalysisResult(
            config=config,
            revolutions=(),
            rms_amplitudes={o: 0.0 for o in config.orders},
            sync_average=(),
            sync_amplitudes={o: 0.0 for o in config.orders},
            empty_reason=reason,
        )

    revolutions: list[RevolutionResult] = []
    for seg in segments:
        revolutions.append(
            RevolutionResult(
                index=seg.index,
                angle_start=seg.angle_start,
                time_start=seg.time_start,
                time_end=seg.time_end,
                mean_rpm=seg.mean_rpm,
                amplitudes=order_amplitudes(seg.samples, config.orders),
                samples=seg.samples,
            )
        )

    rms: dict[int, float] = {}
    for order in config.orders:
        squares = sum(rev.amplitudes[order] ** 2 for rev in revolutions)
        rms[order] = math.sqrt(squares / len(revolutions))

    n = config.samples_per_rev
    sync = [sum(seg.samples[i] for seg in segments) / len(segments) for i in range(n)]
    sync_amps = order_amplitudes(tuple(sync), config.orders)
    sync_mean = sum(sync) / n
    sync = [s - sync_mean for s in sync]

    return AnalysisResult(
        config=config,
        revolutions=tuple(revolutions),
        rms_amplitudes=rms,
        sync_average=tuple(sync),
        sync_amplitudes=sync_amps,
    )
