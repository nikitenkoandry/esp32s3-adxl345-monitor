# Validation and reproducible checks

## Repository layout verification — 17 November 2026

After separating the firmware and desktop tool into this repository:

- Both dependency installers succeeded in newly created local Python environments.
- The firmware build helper produced the ESP32-S3 image successfully, reusing
  an existing cache of the pinned Espressif platform/toolchain.
- All 24 monitor tests passed from the new monitor folder.
- The Windows EXE build helper produced the standalone monitor successfully.
- The firmware sketch, monitor application modules, and tests were copied
  byte-for-byte from the previously verified sources.
- Generated outputs, local environments, and captures were confirmed ignored by Git.

No board was flashed and no new physical measurement was performed as part of
the repository relocation. The upload helper was checked to reject a missing
COM-port argument before attempting an upload.

## Historical hardware result

The firmware logic and desktop monitor were tested on a physical ESP32-S3 board
with 16 MB flash and an ADXL345 on **16 November 2026**. The board used USB-UART
COM16 and the wiring in the repository README.

| Measurement | Observed result |
| --- | --- |
| Capture duration | 60 seconds |
| Valid XYZ samples received | 47,141 |
| PC reception rate | 785.69 samples/s |
| Hardware INT1 edge rate | 785.664 Hz |
| Observed IRQ period extrema | 1268–1277 µs |
| Maximum reported task service latency | 22 µs |
| Maximum observed FIFO occupancy | 1 sample |
| FIFO full events / RAM queue drops | 0 / 0 |
| IRQ timeouts / SPI-status faults | 0 / 0 |
| Malformed stream lines | 0 |

On the same recording, 47,141 model states had a maximum adjacent pose change
of approximately 0.0145°. Gravity direction remained consistent with the model
orientation matrix. This was a continuity check on recorded data, not a controlled
physical rotation accuracy test. Live graphs, the 3D model, tab switching, and
growing INT1 counters were also checked in the Windows EXE.

These are historical observations for one sensor/board, not guarantees for every
module. Nominal 800 Hz differs from the observed unit's actual rate. Task latency
is aggregate firmware telemetry rather than complete sensor-to-PC latency.

The original private captures, board flash backups, and machine-specific logs are
not part of this repository. The source relocation does not itself constitute a
new hardware or flash verification.

## Automated source checks

From `tools/monitor/` after dependency installation:

```powershell
.\scripts\Run_Tests.cmd
# Equivalent command:
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The 24 tests cover fragmented/corrupt serial input, warnings/restarts, CSV
preservation during UI queue overflow, simulated disconnection, demo generation,
peak-preserving graph downsampling, known tilt poses, angle wrap, full-turn
continuity, filter recovery after rejected acceleration, free fall, and IRQ
diagnostic parsing.

Build the firmware from `firmware/` with `scripts/Build_Firmware.cmd`. A successful
build verifies the source and build configuration; it does not prove physical
wiring, sensor performance, or a flashed board's behavior.

## Repeat the real-board test

First flash the intended board, then disconnect all GUI/serial applications from
its port. From `tools/monitor/`:

```powershell
.\.venv\Scripts\python.exe verify_board.py --port COM16 --seconds 60 --require-irq
```

Replace COM16 as appropriate. Output goes to the ignored `captures/` folder.
`--reset` is optional and intentionally toggles RTS to restart ESP32; it is not
required by default. Existing cumulative faults can cause the strict IRQ check
to fail even if the original condition has recovered; use a deliberate clean
startup when comparing fault-free runs.

The utility checks receipt of sufficient XYZ samples, increasing IRQ counters,
a broadly plausible rate, selected zero-fault counters, accounting consistency,
and IRQ-period bounds. It is a practical regression check, not an exhaustive
proof of zero line loss, calibration accuracy, or full motion tracking.
