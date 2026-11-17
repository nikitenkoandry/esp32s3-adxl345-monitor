import csv
import math
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pc_monitor.stream import (
    CsvParser, CsvRecorder, DemoWorker, Mailbox, Receiver, SAMPLE_RATE, Sample,
    SerialWorker, peak_indices,
)


class ParserTests(unittest.TestCase):
    def test_every_possible_chunk_boundary(self):
        data = b"# ADXL345: test\r\nX_g,Y_g,Z_g\n-0.00391,0,1.00000\r\n0.25,-0.5,15.99609\n"
        for split in range(len(data) + 1):
            parser = CsvParser()
            a, m1, bad1 = parser.feed(data[:split])
            b, m2, bad2 = parser.feed(data[split:])
            self.assertEqual(a + b, [(-0.00391, 0, 1), (0.25, -0.5, 15.99609)])
            self.assertEqual(m1 + m2, ["# ADXL345: test"])
            self.assertEqual(bad1 + bad2, 0)

    def test_garbage_nonfinite_and_impossible_values(self):
        parser = CsvParser()
        values, _, invalid = parser.feed(
            b"nan,0,1\ninf,0,1\n1e308,0,1\n33,0,1\nboot message\n1,2\n\xff\n0,0,1\n")
        self.assertEqual(values, [(0, 0, 1)])
        self.assertEqual(invalid, 7)

    def test_discard_partial_first_line_and_oversized_line(self):
        parser = CsvParser(discard_first_line=True)
        self.assertEqual(parser.feed(b"391,0,1")[0], [])
        self.assertEqual(parser.feed(b"\n0,0,1\n")[0], [(0, 0, 1)])
        self.assertEqual(parser.feed(b"x" * 100000)[2], 1)
        self.assertLessEqual(len(parser.pending), 512)
        values, _, invalid = parser.feed(b"bad remainder\n1,2,3\n")
        self.assertEqual(values, [(1, 2, 3)])
        self.assertEqual(invalid, 0)


class PipelineTests(unittest.TestCase):
    def test_recording_keeps_all_samples_when_display_overflows(self):
        box, recorder = Mailbox(capacity=2), CsvRecorder()
        receiver = Receiver(box, recorder)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "signal.csv"
            recorder.start(path)
            receiver.accept(b"0,0,1\n" * 800)
            recorder.stop()
            with path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 800)
            self.assertEqual(float(rows[-1]["t_est_s"]), 799 / 800)
            self.assertEqual(rows[-1]["z_g"], "1.00000")
        samples, _, stats = box.take()
        self.assertEqual([s.index for s in samples], [798, 799])
        self.assertEqual(stats.received, 800)
        self.assertEqual(stats.display_dropped, 798)

    def test_warning_and_reboot_mark_discontinuities(self):
        box = Mailbox()
        receiver = Receiver(box, CsvRecorder())
        receiver.accept(b"0,0,1\n")
        receiver.accept(b"# WARNING: FIFO full events=1; queue dropped=0\n0,0,1\n")
        receiver.accept(b"# ADXL345: restarted\n0,0,1\n")
        samples, events, stats = box.take()
        self.assertEqual([s.gap_before for s in samples], [False, True, True])
        self.assertEqual(stats.device_warnings, 2)
        self.assertTrue(any("restarted" in e.text for e in events))

    def test_serial_disconnect_closes_port_and_keeps_last_complete_sample(self):
        class FakeSerial:
            def __init__(self, **kwargs):
                self.chunks = [b"partial\nX_g,Y_g,Z_g\n", b"0.5,-0.25,1.0\n0."]
                self.closed = False
                self.dtr = self.rts = True
                self.port = None

            def open(self):
                self.assert_lines = not self.dtr and not self.rts

            @property
            def in_waiting(self):
                return len(self.chunks[0]) if self.chunks else 1

            def read(self, _):
                if not self.chunks:
                    raise OSError("USB unplugged")
                return self.chunks.pop(0)

            def close(self):
                self.closed = True

        connection = FakeSerial()
        box = Mailbox()
        with patch("serial.Serial", return_value=connection):
            worker = SerialWorker("COM123", 921600, box, CsvRecorder())
            worker.start()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(connection.closed)
        self.assertTrue(connection.assert_lines)
        samples, events, stats = box.take()
        self.assertEqual([(s.x, s.y, s.z) for s in samples], [(0.5, -0.25, 1.0)])
        self.assertEqual(stats.invalid, 0)
        self.assertTrue(any(e.level == "error" and "USB unplugged" in e.text for e in events))
        self.assertEqual(events[-1].level, "disconnected")

    def test_demo_runs_at_nominal_rate_and_stops(self):
        box = Mailbox()
        worker = DemoWorker(box, CsvRecorder())
        start = time.monotonic()
        worker.start()
        time.sleep(0.3)
        worker.stop_event.set()
        worker.join(timeout=1)
        elapsed = time.monotonic() - start
        samples, _, stats = box.take()
        self.assertFalse(worker.is_alive())
        self.assertGreater(stats.received, 100)
        self.assertLess(abs(stats.received - elapsed * SAMPLE_RATE), 100)
        self.assertAlmostEqual(samples[-1].t, samples[-1].index / SAMPLE_RATE)
        self.assertTrue(all(math.isfinite(s.x) for s in samples))


class PlotTests(unittest.TestCase):
    def test_peak_reduction_preserves_single_sample_impulses_and_order(self):
        data = [0.0] * 48000
        data[1001], data[1002], data[47998] = 15.0, -15.0, 10.0
        indices = peak_indices(data, 900)
        self.assertEqual(indices, sorted(set(indices)))
        self.assertEqual((indices[0], indices[-1]), (0, 47999))
        self.assertTrue({1001, 1002, 47998}.issubset(indices))
        self.assertLess(len(indices), 1810)


if __name__ == "__main__":
    unittest.main()
