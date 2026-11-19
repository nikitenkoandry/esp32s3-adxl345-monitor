# ESP32-S3 firmware — native ESP-IDF C

This is a native **ESP-IDF 6.0.2** project. Application sources are C files in
`main/`; Arduino, the Arduino component, C++ sketches, and PlatformIO are not
required. The previous Arduino implementation remains available in Git history.

## Hardware and defaults

| Setting | Value |
| --- | --- |
| Target | ESP32-S3-DevKitC-1, 16 MB flash, no PSRAM requirement |
| SPI host / mode / clock | SPI2 / mode 3 / 2 MHz, MSB first |
| Pins | SCLK 12, MOSI 11, MISO 13, CS 10, INT1 4 |
| Sensor | ADXL345, full resolution, +/-16 g, nominal 800 Hz ODR |
| Interrupt | Active-high FIFO Watermark=1 on INT1 -> GPIO4 |
| Buffering | Sensor stream FIFO and a 512-sample RAM queue |
| UART | UART0, TX GPIO43 / RX GPIO44, 921600 baud, 8N1 |
| Upload speed | 460800 baud |
| Flash / CPU / tick rate | DIO 80 MHz, 16 MB / 240 MHz / FreeRTOS 1000 Hz |

Use 3.3 V power/logic and a common ground. Use the board's **USB-UART connector**;
this project does not implement native USB CDC or USB Serial/JTAG streaming.
The full wiring table is in the [repository README](../README.md).

`partitions.csv` retains the previous 16 MB offsets, including app0 at 0x10000.
This does not implement OTA; use the generated ESP-IDF flash arguments for a
complete upload. Check physical flash size before changing to another board.
`sdkconfig.defaults` is versioned; generated `sdkconfig` and `build/` are ignored.

## Install ESP-IDF

Use Espressif's [ESP-IDF setup guide](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32s3/get-started/index.html)
and install ESP-IDF **6.0.2** with ESP32-S3 tools. Open its activated terminal.
Alternatively set `IDF_PATH` to your complete SDK checkout; the Windows helpers
call its `export.bat` to activate its tools and Python environment. No absolute
SDK path is stored in the project.

From this folder in an activated PowerShell/ESP-IDF terminal:

```powershell
.\scripts\Install_Dependencies.cmd
.\scripts\Build_Firmware.cmd
# Only when you intend to replace the selected board's firmware:
.\scripts\Upload_Firmware.cmd COM16
```

`Install_Dependencies.cmd` validates an installed SDK; it does not install
PlatformIO or create an Arduino environment. Replace COM16 with your board's
port and close other serial programs before upload. Helpers accept `/nopause`
for automation (after the COM port for upload).

Native CLI from this folder, after SDK activation:

```text
idf.py -DIDF_TARGET=esp32s3 build
idf.py -DIDF_TARGET=esp32s3 -p COM16 -b 460800 flash
```

On macOS/Linux use ESP-IDF's `export.sh` and the same CLI with the appropriate
serial device. The component build uses ESP-IDF's minimal-build mode. Expected
outputs are `build/adxl345_monitor.bin`, its ELF/map, bootloader, partition table,
and `build/flasher_args.json`. A build alone does not modify any hardware.

## Source map

| File | Responsibility |
| --- | --- |
| `main/main.c` | app_main, UART setup, INT1 line test, single output writer |
| `main/adxl345.c` | Native SPI register/burst driver, configuration/readback |
| `main/acquisition.c` | GPIO ISR, FreeRTOS acquisition task, counters, FIFO drain |
| `main/monitor_protocol.c` | Pure C formatting of compatible CSV and diagnostics |
| `main/board_config.h` | Wiring, baud, clock, queue, and settling constants |
| `main/monitor_protocol.h` | Raw XYZ and diagnostic structures, wire formatter API |

## Runtime behavior

```text
ADXL345 measurement -> FIFO -> INT1 / GPIO4 rising edge
  -> ISR/task notification on core 1 -> acquisition task on core 1
  -> nonblocking RAM queue -> app_main UART writer -> existing PC monitor
```

The GPIO ISR is allocated by the acquisition task on core 1, so the ISR and its
recipient share a core. The ISR only records timing/counts and notifies the task. It never calls SPI,
UART, or a blocking function. Notifications may coalesce, so the task reads actual
FIFO occupancy and drains all entries. A sample is one six-byte burst with
hardware-controlled CS and a 5 us post-read delay.

The native SPI API `spi_device_polling_transmit()` waits for one bus transaction;
this is **not timer polling for new sensor measurements**. All runtime reads
remain triggered by INT1. A missing notification increments a timeout after
100 ms without an automatic polling fallback.

The first 16 samples are counted and discarded. Later samples use nonblocking
queue insertion; a full queue increments `queue_dropped`. At startup the driver
checks DEVID=0xE5 and configuration readback. The INT1 wiring test temporarily
uses DATA_READY and polarity inversion, then restores standby and normal
polarity. Normal acquisition enables only WATERMARK, as on the tested module.

On selected GPIO initialization or runtime SPI/status faults the task disables/removes the GPIO handler,
stops measurement, publishes `spi_faults`, then deletes itself. This prevents an
ISR from notifying a deleted task or invalid samples from being emitted. Reset
is required to restart acquisition after such a failure. The output task remains
available for aggregate diagnostic reporting.

## Compatibility with the existing PC monitor

The same `X_g,Y_g,Z_g` header and three-number XYZ rows are emitted at 921600 baud.
Conversion is still raw count / 256 with five decimal places. The same 16
`# IRQ_STATS` fields and `# WARNING` prefix are retained. Startup retains the
`# ADXL345:` prefix so the receiver can recognize a restart. **No PC application
source changes are needed.** See [the serial protocol](../docs/serial-protocol.md).

UART0 has one application writer with a TX ring buffer. Application/bootloader
logs and console output are disabled in defaults to keep normal runtime CSV
clean. ROM messages during reset may still use the ROM boot baud rate, as before.

800 Hz is nominal; aggregate IRQ timings are not hardware timestamps for each
XYZ line. Gravity remains included. This firmware does not estimate yaw, angles,
or a stable position trajectory. The PC model's previous limitations apply.

## Tests without a board

After installing the monitor's pySerial dependency, run from the repository root
with that Python environment and a host GCC/Clang compiler on PATH (or set `CC`):

```powershell
.\tools\monitor\.venv\Scripts\python.exe firmware\tests\host\run_tests.py
.\tools\monitor\scripts\Run_Tests.cmd
```

The C tests execute the production SPI driver, acquisition task, ISR, and wire
formatter against modeled SDK/SPI/FreeRTOS APIs. They check register setup,
readback and transfer failures, signed decoding, FIFO delay, warmup, coalesced
reads, nonblocking backpressure, timeout behavior without polling, timestamp
wrap, invalid FIFO counts, and cleanup before task deletion. Actual formatted
bytes are then passed in seven-byte chunks through the existing PC receiver.

Host tests do not prove electrical wiring, real IRQ latency, actual ODR, or
physical board behavior. On 19 November 2026 the native firmware was flashed and
checked on COM16: a 120-second capture received 94,256 samples with zero reported
acquisition faults or malformed lines. Live plots and the 3D model were also
observed in the unchanged PC monitor. Native and historical Arduino results are
listed separately in [validation notes](../docs/validation.md).

Driver references: [ESP-IDF SPI master](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32s3/api-reference/peripherals/spi_master.html),
[GPIO](https://docs.espressif.com/projects/esp-idf/en/v6.0.2/esp32s3/api-reference/peripherals/gpio.html),
[ADXL345 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ADXL345.pdf).
