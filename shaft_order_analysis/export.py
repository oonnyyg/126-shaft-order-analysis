"""Export resampled CSV and JSON report."""

import csv
import json

from .core import AnalysisReport


def report_to_dict(report):
    config = report.config
    data = {
        "config": {
            "points_per_rev": config.points_per_rev,
            "orders": list(config.orders),
        },
        "revolution_count": len(report.revolutions),
        "empty_reason": report.empty_reason,
        "revolutions": [
            {
                "index": rev.index,
                "start_angle_rad": rev.start_angle,
                "end_angle_rad": rev.end_angle,
                "start_time_s": rev.start_time,
                "end_time_s": rev.end_time,
                "mean_speed_rps": rev.mean_speed_rps,
                "order_amplitudes": {
                    str(k): v for k, v in rev.order_amplitudes.items()
                },
            }
            for rev in report.revolutions
        ],
        "rms_by_order": {str(k): v for k, v in report.rms_by_order.items()},
        "synchronous_average_order_amplitudes": {
            str(k): v for k, v in report.synchronous_order_amplitudes.items()
        },
    }
    return data


def write_json_report(report, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report_to_dict(report), handle, indent=2)
        handle.write("\n")


def write_resampled_csv(report, path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["revolution", "sample_index", "angle_rad", "time_s", "vibration"]
        )
        for rev in report.revolutions:
            n = len(rev.samples)
            span = rev.end_angle - rev.start_angle
            for j, value in enumerate(rev.samples):
                angle = rev.start_angle + span * j / n
                t = rev.start_time + (rev.end_time - rev.start_time) * j / n
                writer.writerow([rev.index, j, angle, t, value])
