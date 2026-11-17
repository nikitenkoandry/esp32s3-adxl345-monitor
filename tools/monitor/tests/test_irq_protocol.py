import unittest

from pc_monitor.stream import CsvParser, CsvRecorder, Mailbox, Receiver, parse_irq_stats


def stats_line(**overrides):
    values = dict(uptime_ms=5000, irq_edges=2750, last_irq_us=4999321,
                  frames=2750, queued=2734, warmup=16, fifo_full=0,
                  queue_dropped=0, timeouts=0, max_fifo=1,
                  period_min_us=1250, period_max_us=1290, latency_max_us=30,
                  spi_faults=0, empty_wakes=0, int1=0)
    values.update(overrides)
    return "# IRQ_STATS " + " ".join(f"{key}={value}" for key, value in values.items())


class IrqProtocolTests(unittest.TestCase):
    def test_counters_and_hardware_time_are_parsed(self):
        irq = parse_irq_stats(stats_line())
        self.assertEqual(irq["irq_edges"], 2750)
        self.assertEqual(irq["last_irq_us"], 4999321)
        self.assertEqual(irq["frames"], irq["queued"] + irq["warmup"])

    def test_rejects_truncated_negative_duplicate_and_overflow_fields(self):
        self.assertIsNone(parse_irq_stats("# IRQ_STATS irq_edges=5"))
        self.assertIsNone(parse_irq_stats(stats_line(timeouts=-1)))
        self.assertIsNone(parse_irq_stats(stats_line() + " irq_edges=3"))
        self.assertIsNone(parse_irq_stats(stats_line(irq_edges=2**32)))
        self.assertIsNone(parse_irq_stats(stats_line(int1=2)))

    def test_diagnostics_do_not_create_acceleration_samples_or_gaps(self):
        box = Mailbox()
        receiver = Receiver(box, CsvRecorder())
        packet = ("0,0,1\n" + stats_line() + "\n0.1,0.2,0.9\n").encode("ascii")
        # A split inside a diagnostics field must be harmless.
        receiver.accept(packet[:71])
        receiver.accept(packet[71:])
        samples, events, stats = box.take()
        self.assertEqual(len(samples), 2)
        self.assertFalse(any(s.gap_before for s in samples))
        self.assertEqual(events, [])
        self.assertEqual(stats.invalid, 0)
        self.assertEqual(stats.device_warnings, 0)
        self.assertEqual(stats.irq["irq_edges"], 2750)
        box.reset()
        self.assertIsNone(box.take()[2].irq)

    def test_full_uint32_counters_fit_the_line_framer(self):
        values = parse_irq_stats(stats_line())
        values = {key: 0xFFFFFFFF for key in values}
        values["int1"] = 1
        line = stats_line(**values)
        self.assertLess(len(line), 512)
        samples, messages, invalid = CsvParser().feed((line + "\n").encode("ascii"))
        self.assertEqual(samples, [])
        self.assertEqual(invalid, 0)
        self.assertIsNotNone(parse_irq_stats(messages[0]))


if __name__ == "__main__":
    unittest.main()
