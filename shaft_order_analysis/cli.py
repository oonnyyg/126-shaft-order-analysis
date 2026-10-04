"""Command-line entry point for shaft order analysis."""

import argparse
import sys

from .core import AnalysisConfig, DataError, analyze, load_angle_csv, load_vibration_csv
from .export import write_json_report, write_resampled_csv


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="shaft-order-analysis",
        description="Angular-domain order analysis for variable-speed shafts.",
    )
    parser.add_argument("--angle-csv", required=True,
                        help="CSV with time_s, cumulative_angle_rad")
    parser.add_argument("--vibration-csv", required=True,
                        help="CSV with time_s, vibration")
    parser.add_argument("--points-per-rev", type=int, default=64)
    parser.add_argument("--orders", default="1,2,3,4",
                        help="comma-separated positive integer orders")
    parser.add_argument("--resampled-csv", default="resampled.csv")
    parser.add_argument("--json-report", default="report.json")
    args = parser.parse_args(argv)

    try:
        orders = tuple(int(part) for part in args.orders.split(",") if part.strip())
        config = AnalysisConfig(points_per_rev=args.points_per_rev, orders=orders)
        angle_times, angles = load_angle_csv(args.angle_csv)
        vib_times, vib_values = load_vibration_csv(args.vibration_csv)
        report = analyze(angle_times, angles, vib_times, vib_values, config)
    except (DataError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    write_resampled_csv(report, args.resampled_csv)
    write_json_report(report, args.json_report)

    if report.empty_reason:
        print(f"No complete revolutions: {report.empty_reason}")
        return 0
    print(f"Analyzed {len(report.revolutions)} complete revolutions.")
    for rev in report.revolutions:
        amps = ", ".join(
            f"order {k}: {v:.6g}" for k, v in rev.order_amplitudes.items()
        )
        print(f"  rev {rev.index}: {rev.mean_speed_rps:.4f} rps | {amps}")
    print("RMS by order: " + ", ".join(
        f"{k}: {v:.6g}" for k, v in report.rms_by_order.items()))
    print(f"Wrote {args.resampled_csv} and {args.json_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
