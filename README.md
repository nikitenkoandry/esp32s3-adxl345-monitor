# ESP32-S3 ADXL345 Monitor

Interrupt-driven ADXL345 firmware and an English desktop acceleration monitor.
Read XYZ over SPI, stream measurements through USB-UART, view live plots and a
gravity-based 3D tilt model, and record raw acceleration to CSV.

The repository contains source code, documentation, and setup/build scripts.
Firmware images, Windows executables, Python environments, toolchains, and
measurement files are generated locally and excluded from Git.

## Project layout

```text
firmware/                  ESP32-S3 PlatformIO project
  ADXL345_SPI_800Hz/        Documented Arduino sketch
  scripts/                 Windows setup, build, and upload helpers
tools/monitor/             Standalone Python/Tk desktop tool
  pc_monitor/              Interface, serial receiver, and tilt visualization
  scripts/                 Windows setup, launch, test, and EXE build helpers
  tests/                   Parser, recording, tilt, and diagnostics tests
  verify_board.py          Optional real-board stream verification
docs/                      Serial protocol and historical validation notes
```

## Hardware

The supplied firmware configuration targets **ESP32-S3-DevKitC-1 with 16 MB flash**.
PSRAM is not required. Check the flash configuration before using another board.
Use an ADXL345 module with **3.3 V power and logic**, a shared ground, and a USB
data cable connected to the board's USB-UART port.

| ADXL345 | ESP32-S3 |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SCLK | GPIO12 |
| SDA / SDI / MOSI | GPIO11 |
| SDO / MISO | GPIO13 |
| CS | GPIO10 |
| INT1 | GPIO4 |

**INT1 is required.** The firmware uses a one-sample FIFO watermark interrupt;
there is no polling fallback if the interrupt wire is missing.

## Quick start on Windows

Install **Python 3.10+ with Tkinter** and make the `python` command available.
The usual Python for Windows installer includes Tkinter. Setup scripts create
separate local environments for the firmware tools and desktop monitor.

### 1. Build and flash the ESP32-S3

Run these commands from the repository root in PowerShell:

```powershell
.\firmware\scripts\Install_Dependencies.cmd
.\firmware\scripts\Build_Firmware.cmd
.\firmware\scripts\Upload_Firmware.cmd COM16
```

Replace `COM16` with your board's port. Uploading replaces its installed firmware.
Close Arduino Serial Monitor and the desktop monitor before uploading. The first
build downloads the pinned Espressif platform and toolchain and needs internet
access. You can also open `firmware/` directly in VS Code with PlatformIO.

### 2. Start the desktop monitor

```powershell
.\tools\monitor\scripts\Install_Dependencies.cmd
.\tools\monitor\scripts\Start_Monitor.cmd
```

Choose your COM port, select **921600 baud**, and click **Connect**. Open
**XYZ Graphs** for acceleration or **3D Orientation** for the tilt demonstration.
The COM port must be free of other serial applications.

### 3. Try it without hardware

```powershell
.\tools\monitor\scripts\Start_3D_Demo.cmd
```

**DEMO** clearly identifies synthetic data. Firmware setup is unnecessary for
this mode; only the monitor environment is required.

## What is included

| Component | Behavior |
| --- | --- |
| SPI acquisition | Mode 3, 2 MHz, full resolution, +/-16 g, nominal 800 Hz ODR |
| Interrupt handling | INT1 wakes a FreeRTOS task; SPI and Serial stay outside the ISR |
| Buffering | Sensor stream FIFO plus a nonblocking 512-sample RAM queue |
| XYZ plots | Live values, 2–60 s history, g or m/s², independent scaling, graph pause |
| 3D tilt | Roll/pitch, reference pose, smoothing, independent model pause, quality hints |
| Recording | Raw acceleration in g, CSV sample counters, PC times, and gap markers |
| Diagnostics | INT1 edges, FIFO full events, firmware queue drops, and timeouts |

Graph/model pauses and tab switching do not stop reception or active recording.

## Timing and measurement scope

**800 Hz is the nominal setting**, not a promise of an exact measured rate. The
previously tested sensor produced about 785.7 samples/s. Graph time is estimated
from received sample count / 800; XYZ lines have no individual hardware timestamp.

Acceleration includes gravity. The model estimates two gravity-based tilt angles
when stationary or moving gently. It does not determine heading/yaw, a stable XYZ
travel path, or full six-degree-of-freedom motion. Strong linear acceleration can
distort the estimate. See the detailed monitor guide for interpretation.

## Tests and optional Windows EXE

```powershell
.\tools\monitor\scripts\Run_Tests.cmd
.\tools\monitor\scripts\Build_EXE.cmd
```

The EXE is generated at `tools/monitor/dist/ADXL345_Monitor.exe`; it needs no
Python installation on the destination PC. It is not committed to this source
repository. The launch scripts prefer a locally built EXE when present.

For automation, setup/build/test scripts accept `/nopause` as their first
argument; the upload script accepts it after the COM port.

## Documentation

- [Firmware setup and architecture](firmware/README.md)
- [Monitor controls, recording, and troubleshooting](tools/monitor/README.md)
- [Serial protocol and diagnostic fields](docs/serial-protocol.md)
- [Historical hardware verification and reproducible checks](docs/validation.md)

The sketch itself includes English descriptions of every function, the wiring,
data flow, configuration, and timing limitations.
