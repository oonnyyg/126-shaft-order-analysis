"""命令行入口。"""

from __future__ import annotations

import argparse
import sys

from .core import (
    AnalysisConfig,
    DataValidationError,
    analyze,
    load_angle_csv,
    load_vibration_csv,
)
from .export import write_report_json, write_resampled_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shaft-order-analysis",
        description="变转速振动信号的角域阶次分析（仅标准库）",
    )
    parser.add_argument("--angle-csv", required=True, help="时间-累计转角 CSV（列 time,angle）")
    parser.add_argument("--vibration-csv", required=True, help="时间-振动 CSV（列 time,vibration）")
    parser.add_argument("--samples-per-rev", type=int, default=64, help="每转采样点数（正偶数）")
    parser.add_argument("--orders", default="1,2,3", help="逗号分隔的阶次列表，如 1,2,3")
    parser.add_argument("--resampled-out", default="resampled.csv", help="重采样 CSV 输出路径")
    parser.add_argument("--report-out", default="report.json", help="JSON 报告输出路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        orders = tuple(int(part) for part in args.orders.split(",") if part.strip())
        if not orders:
            raise DataValidationError("--orders 至少需要一个阶次")
        config = AnalysisConfig(samples_per_rev=args.samples_per_rev, orders=orders)
        angle_times, angles = load_angle_csv(args.angle_csv)
        vib_times, vib_values = load_vibration_csv(args.vibration_csv)
    except (DataValidationError, OSError, ValueError) as exc:
        print(f"输入错误: {exc}", file=sys.stderr)
        return 2

    result = analyze(angle_times, angles, vib_times, vib_values, config)
    write_resampled_csv(result, args.resampled_out)
    write_report_json(result, args.report_out)

    if result.empty_reason is not None:
        print(f"无完整转可分析：{result.empty_reason}")
        return 0

    print(f"共 {len(result.revolutions)} 个完整转")
    for rev in result.revolutions:
        amps = "  ".join(f"order{o}={rev.amplitudes[o]:.4f}" for o in config.orders)
        print(f"rev {rev.index:3d}  rpm={rev.mean_rpm:9.2f}  {amps}")
    print("RMS: " + ", ".join(f"order{o}={result.rms_amplitudes[o]:.4f}" for o in config.orders))
    print("同步平均: " + ", ".join(f"order{o}={result.sync_amplitudes[o]:.4f}" for o in config.orders))
    print(f"已写出 {args.resampled_out} 与 {args.report_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
