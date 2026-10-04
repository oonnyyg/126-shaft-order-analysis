"""导出重采样 CSV 与 JSON 报告。"""

from __future__ import annotations

import csv
import json

from .core import TWO_PI, AnalysisResult


def write_resampled_csv(result: AnalysisResult, path: str) -> None:
    """每行一个重采样点：转序号、累计转角、时间、振动值。"""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["revolution", "angle_rad", "time_s", "vibration"])
        n = result.config.samples_per_rev
        for rev in result.revolutions:
            duration = rev.time_end - rev.time_start
            for i in range(n):
                angle = rev.angle_start + i * TWO_PI / n
                time = rev.time_start + duration * i / n
                writer.writerow(
                    [rev.index, f"{angle:.12g}", f"{time:.12g}", f"{rev.samples[i]:.12g}"]
                )


def write_report_json(result: AnalysisResult, path: str) -> None:
    """JSON 报告：逐转幅度、RMS 汇总、同步平均阶次。"""
    report = {
        "config": {
            "samples_per_rev": result.config.samples_per_rev,
            "orders": list(result.config.orders),
        },
        "empty_reason": result.empty_reason,
        "revolutions": [
            {
                "index": rev.index,
                "angle_start": rev.angle_start,
                "time_start": rev.time_start,
                "time_end": rev.time_end,
                "mean_rpm": rev.mean_rpm,
                "amplitudes": {str(k): v for k, v in rev.amplitudes.items()},
            }
            for rev in result.revolutions
        ],
        "rms_amplitudes": {str(k): v for k, v in result.rms_amplitudes.items()},
        "synchronous_average": {
            "waveform": list(result.sync_average),
            "amplitudes": {str(k): v for k, v in result.sync_amplitudes.items()},
        },
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
