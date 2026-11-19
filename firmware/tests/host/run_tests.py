"""Compile production C with a modeled SPI bus; validate its bytes in the PC parser.

Requires a host C compiler: GCC/Clang, or CC pointing to a compatible executable.
Outputs are kept in ignored firmware/build/host. No board access is performed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys

firmware = Path(__file__).resolve().parents[2]
host = Path(__file__).resolve().parent
output = firmware / "build" / "host"
output.mkdir(parents=True, exist_ok=True)
compiler = os.environ.get("CC") or shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Install a host GCC/Clang C compiler or set CC.")
executable = output / ("test_driver_protocol.exe" if os.name == "nt" else "test_driver_protocol")
subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wpedantic",
                "-I", str(host / "include"), "-I", str(firmware / "main"),
                str(firmware / "main" / "adxl345.c"),
                str(firmware / "main" / "monitor_protocol.c"),
                str(host / "test_driver_protocol.c"), "-o", str(executable)], check=True)
wire = subprocess.run([str(executable)], stdout=subprocess.PIPE, check=True).stdout
acquisition_exe = output / ("test_acquisition.exe" if os.name == "nt" else "test_acquisition")
subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wpedantic",
                "-I", str(host / "include"), "-I", str(firmware / "main"),
                str(firmware / "main" / "acquisition.c"),
                str(host / "test_acquisition.c"), "-o", str(acquisition_exe)], check=True)
for scenario in ("normal", "invalid-fifo", "bus-failure", "burst-failure", "task-failure", "service-failure"):
    subprocess.run([str(acquisition_exe), scenario], check=True)
sys.path.insert(0, str(firmware.parent / "tools" / "monitor"))
from pc_monitor.stream import CsvRecorder, Mailbox, Receiver, parse_irq_stats

box = Mailbox()
receiver = Receiver(box, CsvRecorder())
for offset in range(0, len(wire), 7):
    receiver.accept(wire[offset:offset + 7])
samples, events, stats = box.take()
assert len(samples) == 2
assert (samples[0].x, samples[0].y, samples[0].z) == (-0.00391, 0.00781, 1.0)
assert (samples[1].x, samples[1].y, samples[1].z) == (-16.0, 15.99609, 0.0)
assert not any(s.gap_before for s in samples)
assert stats.invalid == 0 and stats.device_warnings == 0
assert stats.irq["irq_edges"] == 0xffffffff and stats.irq["int1"] == 1
assert stats.irq["warmup"] == 16
for line in wire.decode("ascii").splitlines():
    if line.startswith("# IRQ_STATS "):
        assert len(line) < 512 and parse_irq_stats(line) is not None
print("C SPI/formatting checks and fragmented PC protocol interoperability passed.")
