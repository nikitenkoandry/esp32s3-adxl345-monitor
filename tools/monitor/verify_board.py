"""Capture the real ADXL345 UART stream and save a hardware verification report."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import serial

from pc_monitor.stream import CsvParser, CsvRecorder, Sample, parse_irq_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM16")
    parser.add_argument("--seconds", type=float, default=12)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--require-irq", action="store_true", help="Require growing INT1 counters and no acquisition faults")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "captures" / "adxl345_real")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    decoder, recorder = CsvParser(discard_first_line=True), CsvRecorder()
    connection = serial.Serial(port=None, baudrate=921600, timeout=0.05)
    connection.dtr = connection.rts = False
    connection.port = args.port
    count = invalid = first_count = 0
    first_at = last_at = None
    messages = []
    irq_reports = []
    minimum = [math.inf] * 3
    maximum = [-math.inf] * 3
    last_xyz = None
    try:
        connection.open()
        recorder.start(args.output.with_suffix(".csv"))
        if args.reset:
            connection.rts = True
            time.sleep(0.1)
            connection.rts = False
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            data = connection.read(max(1, min(connection.in_waiting, 65536)))
            if not data:
                continue
            values, comments, bad = decoder.feed(data)
            invalid += bad
            for comment in comments:
                if comment.startswith("# IRQ_STATS "):
                    irq = parse_irq_stats(comment)
                    if irq is not None and len(irq_reports) < 10000:
                        irq_reports.append(irq)
                    continue
                if comment not in messages and len(messages) < 30:
                    messages.append(comment)
            now = time.monotonic()
            if values:
                if first_at is None:
                    first_at, first_count = now, len(values)
                last_at = now
            samples = []
            pc_time = time.time()
            for xyz in values:
                samples.append(Sample(count, count / 800, pc_time, *xyz))
                count += 1
                last_xyz = xyz
                for i, value in enumerate(xyz):
                    minimum[i] = min(minimum[i], value)
                    maximum[i] = max(maximum[i], value)
            error = recorder.write(samples)
            if error:
                raise OSError(error)
    finally:
        connection.close()
        recorder.stop()

    rate = ((count - first_count) / (last_at - first_at)
            if first_at is not None and last_at > first_at else 0)
    report = {
        "port": args.port,
        "baud": 921600,
        "samples": count,
        "received_samples_per_second": round(rate, 2),
        "invalid_lines_including_reset_boot_text": invalid,
        "messages": messages,
        "last_xyz_g": last_xyz,
        "last_magnitude_g": round(math.sqrt(sum(v * v for v in last_xyz)), 4) if last_xyz else None,
        "min_xyz_g": minimum if count else None,
        "max_xyz_g": maximum if count else None,
        "csv": str(args.output.with_suffix(".csv")),
        "irq_reports": irq_reports,
    }
    irq_ok = False
    if len(irq_reports) >= 2:
        first, last = irq_reports[0], irq_reports[-1]
        edges = (last["irq_edges"] - first["irq_edges"]) & 0xFFFFFFFF
        elapsed = (last["last_irq_us"] - first["last_irq_us"]) & 0xFFFFFFFF
        irq_rate = edges * 1_000_000 / elapsed if elapsed else 0
        irq_ok = (edges >= 1000 and 700 <= irq_rate <= 900 and
                  all(r[k] == 0 for r in irq_reports for k in ("fifo_full", "queue_dropped", "timeouts", "spi_faults")) and
                  all(r["frames"] == r["queued"] + min(r["frames"], r["warmup"]) + r["queue_dropped"] for r in irq_reports) and
                  last["period_max_us"] < 10000)
        report["irq_summary"] = {"hardware_irq_rate_hz": round(irq_rate, 3),
                                 "hardware_mean_period_us": round(elapsed / edges, 3) if edges else None,
                                 "stability_checks_passed": irq_ok, "latest": last}
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    printable = {key: value for key, value in report.items() if key != "irq_reports"}
    printable["irq_report_count"] = len(irq_reports)
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0 if count >= 1000 and (irq_ok or not args.require_irq) else 1


if __name__ == "__main__":
    raise SystemExit(main())
