"""Serial acquisition and recording, independent of the graphical interface."""

from __future__ import annotations

import csv
import math
import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SAMPLE_RATE = 800.0
BAUD_RATE = 921600
MAX_LINE_BYTES = 512


@dataclass(frozen=True, slots=True)
class Sample:
    index: int
    t: float
    pc_time: float
    x: float
    y: float
    z: float
    gap_before: bool = False


@dataclass(frozen=True, slots=True)
class Event:
    level: str
    text: str


@dataclass(frozen=True, slots=True)
class Stats:
    received: int
    invalid: int
    device_warnings: int
    display_dropped: int
    last_rx: float
    irq: dict[str, int] | None = None


def parse_irq_stats(line: str) -> dict[str, int] | None:
    if not line.startswith("# IRQ_STATS "):
        return None
    try:
        pairs = [word.split("=", 1) for word in line[len("# IRQ_STATS "):].split()]
        if any(len(pair) != 2 or not pair[1].isascii() or not pair[1].isdigit() for pair in pairs):
            return None
        result = {key: int(value) for key, value in pairs}
        required = {"uptime_ms", "irq_edges", "last_irq_us", "frames", "queued", "warmup",
                    "fifo_full", "queue_dropped", "timeouts", "max_fifo", "period_min_us",
                    "period_max_us", "latency_max_us", "spi_faults", "empty_wakes", "int1"}
        if (not required <= result.keys() or len(result) != len(pairs) or
                result["int1"] not in (0, 1) or any(value > 0xFFFFFFFF for value in result.values())):
            return None
        return result
    except (ValueError, OverflowError):
        return None


class CsvParser:
    """Handle fragmented lines, boot messages and malformed input with bounded RAM."""

    def __init__(self, discard_first_line: bool = False):
        self.pending = bytearray()
        self.discarding = discard_first_line

    def feed(self, data: bytes) -> tuple[list[tuple[float, float, float]], list[str], int]:
        samples, messages = [], []
        invalid = 0
        parts = data.split(b"\n")
        for i, part in enumerate(parts):
            complete = i < len(parts) - 1
            if self.discarding:
                if complete:
                    self.discarding = False
                continue
            if len(self.pending) + len(part) > MAX_LINE_BYTES:
                self.pending.clear()
                self.discarding = not complete
                invalid += 1
                continue
            self.pending.extend(part)
            if not complete:
                continue
            raw = bytes(self.pending).strip()
            self.pending.clear()
            if not raw:
                continue
            try:
                line = raw.decode("ascii")
                if line.startswith("#"):
                    messages.append(line)
                    continue
                if line.lower().replace(" ", "") == "x_g,y_g,z_g":
                    continue
                fields = line.split(",")
                if len(fields) != 3:
                    raise ValueError("expected three axes")
                values = tuple(float(field) for field in fields)
                if not all(math.isfinite(v) and abs(v) <= 32 for v in values):
                    raise ValueError("invalid acceleration for a +/-16 g sensor")
                samples.append(values)
            except (UnicodeDecodeError, ValueError, OverflowError):
                invalid += 1
        return samples, messages, invalid


class Mailbox:
    """A bounded, thread-safe handoff; acquisition never waits for the GUI."""

    def __init__(self, capacity: int = 16000):
        self.lock = threading.Lock()
        self.capacity = capacity
        self.reset()

    def reset(self):
        with self.lock:
            self.samples: deque[Sample] = deque(maxlen=self.capacity)
            self.events: deque[Event] = deque(maxlen=100)
            self.received = self.invalid = self.device_warnings = self.display_dropped = 0
            self.last_rx = 0.0
            self.irq = None

    def update_irq(self, stats: dict[str, int]):
        with self.lock:
            self.irq = stats.copy()

    def publish(self, samples: list[Sample], invalid: int = 0):
        with self.lock:
            self.invalid += invalid
            if samples:
                self.received += len(samples)
                self.last_rx = time.monotonic()
                self.display_dropped += max(0, len(self.samples) + len(samples) - self.capacity)
                self.samples.extend(samples)

    def event(self, level: str, text: str):
        with self.lock:
            self.events.append(Event(level, text))
            if level == "device_warning":
                self.device_warnings += 1

    def take(self) -> tuple[list[Sample], list[Event], Stats]:
        with self.lock:
            samples, events = list(self.samples), list(self.events)
            self.samples.clear()
            self.events.clear()
            stats = Stats(self.received, self.invalid, self.device_warnings,
                          self.display_dropped, self.last_rx, self.irq.copy() if self.irq is not None else None)
        return samples, events, stats


class CsvRecorder:
    """Record every parsed sample in the reader thread, before display downsampling."""

    def __init__(self):
        self.lock = threading.Lock()
        self.file = None
        self.writer = None
        self.path: Path | None = None
        self.rows = 0
        self.last_flush = 0.0

    @property
    def active(self) -> bool:
        with self.lock:
            return self.file is not None

    def start(self, path: str | Path):
        with self.lock:
            if self.file is not None:
                raise RuntimeError("Recording is already active")
            file = open(path, "w", newline="", encoding="utf-8")
            try:
                writer = csv.writer(file)
                writer.writerow(["sample", "t_est_s", "pc_rx_time_utc", "x_g", "y_g", "z_g", "gap_before"])
                file.flush()
            except Exception:
                file.close()
                raise
            self.file, self.writer, self.path = file, writer, Path(path)
            self.rows, self.last_flush = 0, time.monotonic()

    def write(self, samples: list[Sample]) -> str | None:
        with self.lock:
            if self.file is None:
                return None
            try:
                self.writer.writerows(
                    (s.index, f"{s.t:.6f}",
                     datetime.fromtimestamp(s.pc_time, timezone.utc).isoformat(timespec="milliseconds"),
                     f"{s.x:.5f}", f"{s.y:.5f}", f"{s.z:.5f}", int(s.gap_before))
                    for s in samples
                )
                self.rows += len(samples)
                if time.monotonic() - self.last_flush >= 1:
                    self.file.flush()
                    self.last_flush = time.monotonic()
            except (OSError, ValueError) as exc:
                try:
                    self.file.close()
                except OSError:
                    pass
                self.file = self.writer = None
                return str(exc)
        return None

    def stop(self):
        with self.lock:
            file, self.file, self.writer = self.file, None, None
            if file is not None:
                file.close()


class Receiver:
    def __init__(self, mailbox: Mailbox, recorder: CsvRecorder, *, discard_first_line=False):
        self.mailbox, self.recorder = mailbox, recorder
        self.parser = CsvParser(discard_first_line)
        self.index = 0
        self.gap_pending = False

    def accept(self, data: bytes):
        values, messages, invalid = self.parser.feed(data)
        for message in messages:
            if message.startswith("# IRQ_STATS "):
                irq = parse_irq_stats(message)
                if irq is not None:
                    self.mailbox.update_irq(irq)
                else:
                    self.mailbox.event("info", "Invalid INT1 diagnostic line.")
                continue
            reboot = message.startswith("# ADXL345:") and self.index > 0
            warning = "WARNING" in message.upper() or reboot
            self.mailbox.event("device_warning" if warning else "info", message)
            if reboot:
                self.mailbox.event("info", "ESP32 restarted; the exact gap duration is unknown.")
            self.gap_pending |= warning
        self.gap_pending |= invalid > 0
        now = time.time()
        samples = []
        for x, y, z in values:
            samples.append(Sample(self.index, self.index / SAMPLE_RATE, now, x, y, z, self.gap_pending))
            self.gap_pending = False
            self.index += 1
        error = self.recorder.write(samples)
        if error:
            self.mailbox.event("error", f"CSV recording stopped: {error}")
        self.mailbox.publish(samples, invalid)


class SerialWorker(threading.Thread):
    def __init__(self, port: str, baud: int, mailbox: Mailbox, recorder: CsvRecorder):
        super().__init__(name="ADXL345-serial", daemon=True)
        self.port, self.baud = port, baud
        self.mailbox, self.recorder = mailbox, recorder
        self.stop_event = threading.Event()

    def run(self):
        connection = None
        try:
            import serial
            # Set these before opening to avoid intentionally toggling the ESP32 reset lines.
            # Some USB drivers can nevertheless pulse DTR/RTS on open.
            connection = serial.Serial(port=None, baudrate=self.baud, timeout=0.05)
            connection.dtr = False
            connection.rts = False
            connection.port = self.port
            connection.open()
            receiver = Receiver(self.mailbox, self.recorder, discard_first_line=True)
            self.mailbox.event("connected", f"Connected: {self.port}, {self.baud} baud.")
            while not self.stop_event.is_set():
                data = connection.read(max(1, min(connection.in_waiting, 65536)))
                if data:
                    receiver.accept(data)
        except Exception as exc:
            if not self.stop_event.is_set():
                self.mailbox.event("error", f"USB/COM error ({self.port}): {exc}")
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            self.mailbox.event("disconnected", "Reception stopped.")


class DemoWorker(threading.Thread):
    """Generate the same CSV stream as the firmware, at nominally 800 samples/s."""

    def __init__(self, mailbox: Mailbox, recorder: CsvRecorder):
        super().__init__(name="ADXL345-demo", daemon=True)
        self.mailbox, self.recorder = mailbox, recorder
        self.stop_event = threading.Event()

    def run(self):
        receiver = Receiver(self.mailbox, self.recorder)
        rng = random.Random(345)
        start = time.monotonic()
        index = 0
        self.mailbox.event("connected", "Demo: gentle X/Y tilts, 800 samples/s.")
        from pc_monitor.orientation import gravity_for_tilt
        try:
            while not self.stop_event.wait(0.01):
                target = int((time.monotonic() - start) * SAMPLE_RATE)
                target = min(target, index + 1600)
                lines = []
                for i in range(index, target):
                    t = i / SAMPLE_RATE
                    roll = math.radians(40) * math.sin(2 * math.pi * 0.10 * t)
                    pitch = math.radians(30) * math.sin(2 * math.pi * 0.065 * t + 0.5)
                    x, y, z = (v + rng.uniform(-0.002, 0.002)
                               for v in gravity_for_tilt(roll, pitch))
                    lines.append(f"{x:.5f},{y:.5f},{z:.5f}\n")
                if lines:
                    receiver.accept("".join(lines).encode("ascii"))
                index = target
        finally:
            self.mailbox.event("disconnected", "Demo stopped.")


def available_ports() -> list[tuple[str, str]]:
    from serial.tools import list_ports
    return [(p.device, p.description) for p in sorted(list_ports.comports())]


def peak_indices(values: list[float], max_buckets: int) -> list[int]:
    """Keep local minima AND maxima in their original order, preserving narrow spikes."""
    if len(values) <= max_buckets * 2:
        return list(range(len(values)))
    step = math.ceil(len(values) / max_buckets)
    indices = [0]
    for begin in range(0, len(values), step):
        end = min(begin + step, len(values))
        low = high = begin
        for i in range(begin + 1, end):
            if values[i] < values[low]:
                low = i
            if values[i] > values[high]:
                high = i
        indices.extend(sorted({low, high}))
    indices.append(len(values) - 1)
    return sorted(set(indices))
