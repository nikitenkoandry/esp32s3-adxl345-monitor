# Serial protocol

This document describes the current firmware contract, not a proposed extension.
The running UART0 stream uses **921600 baud, 8 data bits, no parity, 1 stop bit**.
The supplied target routes it through the board's USB-UART adapter. Lines end in
LF; receivers may strip CR/LF and must tolerate fragmented USB reads.

## Measurement lines

```text
X_g,Y_g,Z_g
-0.00391,0.00781,1.00000
```

The first line is a startup header. Every following measurement has exactly three
comma-separated decimal values: X, Y, Z acceleration in g. The conversion uses
the nominal `raw_count / 256` scale. Five decimal places are output formatting,
not a claim of measurement accuracy. Acceleration includes gravity; offsets are
initialized to zero rather than calibrated.

No per-sample sequence number, hardware timestamp, checksum, gyro data, or angles
are included. USB batch timing cannot be treated as sensor acquisition timing.

## Messages and diagnostics

Lines beginning with `#` are messages and must not be parsed as XYZ samples.

- `# ADXL345: ...` identifies startup and the running configuration.
- `# IRQ_LINE_TEST ...` reports the temporary INT1 wiring/polarity check.
- `# WARNING: ...` reports changes in selected acquisition fault counters.
- `# IRQ_STATS ...` provides whitespace-separated `name=value` fields about once
  per second. Healthy diagnostic lines do not introduce gaps in the monitor.

| IRQ_STATS field | Meaning |
| --- | --- |
| `uptime_ms` | ESP32 millisecond uptime when the report is emitted |
| `irq_edges` | Rising GPIO4 edges since ISR attachment |
| `last_irq_us` | Low 32 bits of the latest ISR microsecond timestamp |
| `frames` | Total XYZ FIFO samples read, including warmup |
| `queued` | Samples successfully inserted into the UART consumer's RAM queue |
| `warmup` | Startup discard count, currently 16 |
| `fifo_full` | Observations of FIFO full / overrun conditions |
| `queue_dropped` | Samples rejected because the RAM queue was full |
| `timeouts` | Acquisition notification waits exceeding 100 ms |
| `max_fifo` | Maximum observed FIFO occupancy, in complete XYZ samples |
| `period_min_us` | Shortest IRQ interval after the warmup extrema reset |
| `period_max_us` | Longest IRQ interval after the warmup extrema reset |
| `latency_max_us` | Maximum age of the latest IRQ at the task service point |
| `spi_faults` | Selected configuration readback / FIFO-status faults |
| `empty_wakes` | Notifications serviced with no FIFO sample available |
| `int1` | GPIO4 level when this report is printed, 0 or 1 |

Counters and times are unsigned 32-bit values and eventually wrap. Microsecond
timestamps wrap about every 71.6 minutes; interval calculations use unsigned
subtraction. FIFO-full observations are not an exact count of lost samples, and
SPI fault checks do not detect every possible corrupt transfer. Task latency is
not the complete SPI transaction time or PC end-to-end latency.

Watermark remains asserted while FIFO contains at least one sample. If processing
is delayed, one edge/notification can lead to several sample reads; ISR counts and
sample counts need not match one-to-one. Telemetry combines ISR fields with the
most recently published acquisition batch. Counts can predate a PC connection.

## Monitor recording format

The monitor writes a separate analysis-friendly CSV format:

```text
sample,t_est_s,pc_rx_time_utc,x_g,y_g,z_g,gap_before
0,0.000000,2026-11-16T12:00:00.000+00:00,-0.00391,0.00781,1.00000,0
```

`sample` counts valid lines on the PC since connection. `t_est_s` is that count
divided by nominal 800 Hz; a recording started later can begin at a nonzero index.
`pc_rx_time_utc` is the PC batch processing time. `gap_before=1` indicates a known
or suspected discontinuity; its exact sensor-time duration is unavailable.
Display units and tilt smoothing do not alter the raw g values in this file.
