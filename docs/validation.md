# Validation and reproducible checks

## Native ESP-IDF C port — 19 November 2026

The current firmware application was rewritten in C and built with the installed
ESP-IDF **6.0.2** SDK for ESP32-S3. Application compilation uses four C translation
units; the build has no Arduino component. The full 16 MB partition layout and
generated bootloader/partition/application flash arguments were produced.

Checks completed for the C port:

- Production SPI driver tested with a modeled register bus: pins/mode/clock/CS,
  configuration, wrong DEVID, corrupt readback, transfer failure, signed XYZ
  decoding, six-byte bursts, and post-read delay.
- Production acquisition task/ISR tested in six separate scenarios: normal
  IRQ/FIFO operation with warmup, notification coalescing, timestamp wrap,
  backpressure and an empty wake; invalid FIFO count; register transfer failure;
  burst transfer failure; task allocation failure; and GPIO ISR allocation failure.
- Actual C-generated XYZ and maximum-width IRQ_STATS lines passed through the
  unchanged PC receiver in seven-byte fragments, with zero malformed rows or
  unexpected gap markers in the healthy fixture.
- All **24 existing monitor tests passed**. No Python monitor application change
  was needed.
- Windows helpers were migrated from PlatformIO to native ESP-IDF. Upload still
  requires an explicit serial port.

These build and simulated host checks preceded the hardware run documented
below. Historical Arduino measurements are kept in a separate section and must
not be attributed to the C port.

## ESP-IDF hardware verification — 19 November 2026

The native C firmware was flashed to the physical ESP32-S3 on COM16 with all four
write checksums verified: bootloader, partition table, initial OTA data, and app.
The first 1 MiB of the previous flash was saved in two independent reads with
matching SHA-256 hashes. This backup covers every sector written by this upload;
it is not a full 16 MiB flash dump. Backups and captures remain private, ignored
build artifacts.

A reset/startup probe identified the `ESP-IDF C` startup tag and working INT1.
The following steady-state capture ran for 120 seconds without resetting:

| Measurement | ESP-IDF result |
| --- | --- |
| Valid XYZ samples | 94,256 |
| PC reception rate | 785.46 samples/s |
| INT1 edge rate | 785.439 Hz |
| IRQ period extrema | 1270–1276 us |
| Maximum reported task service latency | 15 us |
| Maximum observed FIFO occupancy | 1 sample |
| FIFO full / queue drops / timeouts / SPI faults | 0 / 0 / 0 / 0 |
| Malformed lines / warning messages | 0 / 0 |

All 94,256 samples also passed through the unchanged monitor tilt estimator,
with zero gap markers. The captured signal included changing gravity directions
and some dynamic acceleration: 92,440 states were classified gravity-like and
1,816 dynamic. The largest model change over 16 samples (20 ms nominal) was
3.709 degrees, with no artificial 180-degree step in this capture. This is a
numerical continuity check, not measured GUI frame timing or calibrated physical
angle accuracy. Reported latency describes task service, not PC delivery time.

The unchanged Windows EXE connected at 921600 baud and displayed real XYZ graphs
and the 3D model. Growing sample/INT1 counts and zero bad lines, warnings, UI drops,
FIFO full events, firmware drops, and timeouts were observed on both pages.
On the final GUI connection, 203,349 samples and a cumulative INT1 count of
822,948 were visible with all listed fault counters still zero. The 3D tab
remained live; physical angle accuracy was not calibrated. The verification tool
saved the primary capture used for numerical analysis.

Local reports are `firmware/build/hardware_check/esp_idf_flash_manifest.json`,
`esp_idf_stability_120s.json`, `esp_idf_stability_120s_model.json`, and
`esp_idf_gui_verified.json`. These
machine-specific reports and raw captures are excluded from the source repository.
The observations apply to this board and test interval, not every ADXL345 module.

## Historical repository layout verification — 17 November 2026

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

The **historical Arduino firmware** and desktop monitor were tested on a physical ESP32-S3 board
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

Build the native C firmware from an activated ESP-IDF 6.0.2 environment in
`firmware/` with `scripts/Build_Firmware.cmd`. A successful
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
