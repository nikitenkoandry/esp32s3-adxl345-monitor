# ESP32-S3 firmware

This folder is a complete PlatformIO project. The Arduino sketch is
[`ADXL345_SPI_800Hz/ADXL345_SPI_800Hz.ino`](ADXL345_SPI_800Hz/ADXL345_SPI_800Hz.ino).
Its implementation and serial contract are the same as the tested source;
the project layout and helper scripts make setup portable.

## Build configuration

| Setting | Value |
| --- | --- |
| Target | ESP32-S3-DevKitC-1, 16 MB flash |
| Platform | Espressif32 6.12.0 |
| Framework | Arduino-ESP32 2.0.17 supplied by the pinned platform |
| Build/upload tool | PlatformIO Core 6.2.0 |
| Flash mode / partition scheme | DIO / default_16MB.csv |
| Upload speed | 460800 baud |
| Running serial stream | UART0 via USB-UART, 921600 baud |
| Native USB CDC on boot | Disabled in this configuration |

The PlatformIO board profile has other flash defaults; the supplied configuration
explicitly selects 16 MB. Adjust it to match your physical board before flashing.
No COM port is hard-coded in `platformio.ini`.

## Windows setup

From this folder:

```powershell
.\scripts\Install_Dependencies.cmd
.\scripts\Build_Firmware.cmd
.\scripts\Upload_Firmware.cmd COM16
```

The installer creates `firmware/.venv/` and installs the pinned PlatformIO Core.
Helpers use `firmware/.pio/core/` for downloaded platforms/toolchains unless
`PLATFORMIO_CORE_DIR` is already set. Build output is under
`firmware/.pio/build/esp32s3_adxl345/`. All these generated folders are ignored by
Git. The upload helper requires an explicit COM port and replaces the board's
firmware; it does not back up an unrelated application already on the board.

## PlatformIO CLI or VS Code

Open this folder with the PlatformIO VS Code extension, or use Python directly:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m platformio run -e esp32s3_adxl345
.\.venv\Scripts\python.exe -m platformio run -e esp32s3_adxl345 -t upload --upload-port COM16
```

CLI and VS Code can use their normal PlatformIO core/package cache. The Windows
helpers select a project-local cache for convenience. No machine-specific paths
or existing build directory are required by the project.

## Data path

```text
ADXL345 measurement -> sensor FIFO -> INT1 / GPIO4 rising edge
    -> ISR notification -> acquisition task -> RAM queue -> loop() -> UART -> PC
```

The sensor runs at nominal 800 Hz, normal power, full resolution, +/-16 g.
Four-wire SPI uses mode 3, MSB first, 2 MHz. FIFO stream mode with a watermark of
one sample is routed to active-high INT1. The ISR counts edges and records timing;
it does not read SPI or print Serial.

The acquisition task drains the FIFO using six-byte XYZ bursts with 5 µs between
reads. It discards the first 16 samples and then queues raw signed counts without
blocking. A 512-sample queue separates acquisition from UART output. Queue drops
are reported if the consumer cannot keep up. A notification wait beyond 100 ms
increments a timeout; there is no timer-based polling fallback.

At startup the sketch verifies DEVID=0xE5, configuration readback, and the INT1
connection. The wiring test temporarily uses DATA_READY and output polarity
inversion; steady acquisition uses WATERMARK. On the tested module, DATA_READY
with FIFO stayed high after its first edge, while WATERMARK=1 worked reliably.

## Output and diagnostics

The main loop converts counts to g using the nominal `1/256` scale and emits
three CSV numbers per line. It also emits a header and `#`-prefixed messages.
`# IRQ_STATS` reports cumulative acquisition counters roughly once per second;
`# WARNING` reports changes in selected fault counters.

See [the serial protocol](../docs/serial-protocol.md) for all field meanings.
The output has no per-sample hardware timestamp or sequence number. IRQ periods
and task wake latency are diagnostics, not end-to-end PC latency measurements.

Wiring is listed in the [repository README](../README.md). For sensor behavior,
see the [ADXL345 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ADXL345.pdf).
