/**
 * @file ADXL345_SPI_800Hz.ino
 * @brief Interrupt-driven, three-axis acceleration streaming for ESP32-S3.
 *
 * HARDWARE CONNECTIONS
 * --------------------
 * Target: ESP32-S3-DevKitC-1 with an ADXL345 module, Arduino-ESP32 framework.
 * Use 3.3 V power and logic, a common ground, and a USB data cable.
 *
 *   ADXL345 signal          ESP32-S3 connection
 *   --------------------   ----------------------
 *   VCC                    3V3
 *   GND                    GND
 *   SCLK                   GPIO12
 *   SDA / SDI / MOSI       GPIO11
 *   SDO / MISO             GPIO13
 *   CS                     GPIO10
 *   INT1                   GPIO4  (required)
 *
 * MEASUREMENT CONFIGURATION
 * -------------------------
 * - Four-wire SPI, mode 3, MSB first, 2 MHz bus clock.
 * - Full-resolution, right-justified XYZ data; range: +/-16 g.
 * - Normal-power mode with a nominal output data rate (ODR) of 800 Hz.
 * - Stream FIFO, watermark threshold of one complete XYZ sample.
 * - Active-high watermark interrupt routed to INT1, detected on GPIO4.
 *
 * DATA FLOW
 * ---------
 *   ADXL345 measurement -> FIFO -> INT1 rising edge -> onDataReady() ISR
 *     -> task notification -> acquisitionTask() -> 512-sample RAM queue
 *     -> loop() -> UART / USB-UART -> PC acceleration monitor.
 *
 * The sensor controls sample timing. ESP32 does not poll it on a periodic
 * sampling timer. The ISR only records timing/counters and wakes a task;
 * SPI transactions and serial printing never run inside the ISR.
 * acquisitionTask() drains every available FIFO entry before waiting again.
 * Multiple notifications can coalesce, so FIFO occupancy, rather than the
 * notification count, determines how many XYZ samples must be read.
 *
 * STARTUP AND FAULT HANDLING
 * -------------------------
 * setup() checks device ID 0xE5, writes and reads back the configuration,
 * then verifies that GPIO4 follows the sensor's interrupt output polarity.
 * DATA_READY is enabled only for this wiring test. Normal acquisition uses
 * the FIFO WATERMARK interrupt, even though the ISR retains its historical
 * name onDataReady(). The first 16 acquired samples are discarded for settling.
 *
 * A missing interrupt produces a timeout after a 100 ms notification wait;
 * there is no automatic fallback to timer polling. Queue insertion is
 * nonblocking: a slow UART consumer cannot stall the acquisition task.
 * Suspected FIFO overrun, queue drops, timeouts, and basic SPI/status faults
 * are exposed through diagnostics rather than silently hidden.
 *
 * SERIAL OUTPUT CONTRACT
 * ----------------------
 * UART baud rate: 921600. The supplied PlatformIO configuration uses UART0
 * through the board's USB-UART adapter (USB CDC On Boot is disabled).
 *
 *   X_g,Y_g,Z_g                         Startup column header
 *   -0.00391,0.00781,1.00000            Example measurement, in g
 *   # IRQ_STATS uptime_ms=... ...       Periodic diagnostic comment
 *   # WARNING: ...                     Acquisition warning
 *
 * Each measurement is one line containing three signed decimal values.
 * The nominal conversion is raw_count / 256; five printed decimal places
 * are formatting, not a claim of sensor accuracy. Lines beginning with '#'
 * contain messages, not acceleration samples. Diagnostics are emitted about
 * once per second by loop(), independently of the acquisition task.
 *
 * TIMING AND INTERPRETATION
 * -------------------------
 * 800 Hz is a nominal sensor setting, not a guaranteed exact 1250 us period.
 * Actual ODR depends on the sensor; USB/UART delivery can arrive in batches.
 * IRQ timing measures interrupt service events. If FIFO accumulates data,
 * one edge can lead to multiple sample reads. XYZ lines carry no individual
 * sample number or acquisition timestamp; IRQ_STATS is aggregate telemetry.
 * Unsigned 32-bit microsecond timestamps wrap about every 71.6 minutes.
 * Differences use unsigned subtraction to handle a single wrap correctly.
 *
 * Acceleration includes gravity. Offset registers are set to zero; this is
 * not a calibration procedure. Gravity-based roll/pitch can be estimated on
 * the PC during rest or gentle motion. This sketch does not estimate angles,
 * remove gravity, measure yaw, or reconstruct a stable XYZ position path.
 *
 * Reference: ADXL345 datasheet, Interrupts / FIFO / Register Map sections:
 * https://www.analog.com/media/en/technical-documentation/data-sheets/ADXL345.pdf
 */

#include <Arduino.h>
#include <SPI.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

// ---------------------------------------------------------------------------
// Hardware pins, transport settings, and sensor register configuration.
// ---------------------------------------------------------------------------
constexpr int PIN_SCLK = 12;
constexpr int PIN_MOSI = 11;
constexpr int PIN_MISO = 13;
constexpr int PIN_CS   = 10;
constexpr int PIN_INT1 = 4;

constexpr uint32_t SERIAL_BAUD = 921600;
constexpr uint32_t SPI_HZ = 2000000;
constexpr float G_PER_LSB = 1.0f / 256.0f; // Nominal scale; calibration may be needed.
constexpr size_t QUEUE_SAMPLES = 512;     // About 0.64 s at 800 Hz.

constexpr uint8_t REG_DEVID       = 0x00;
constexpr uint8_t REG_OFSX        = 0x1E;
constexpr uint8_t REG_OFSY        = 0x1F;
constexpr uint8_t REG_OFSZ        = 0x20;
constexpr uint8_t REG_BW_RATE     = 0x2C;
constexpr uint8_t REG_POWER_CTL   = 0x2D;
constexpr uint8_t REG_INT_ENABLE  = 0x2E;
constexpr uint8_t REG_INT_MAP     = 0x2F;
constexpr uint8_t REG_INT_SOURCE  = 0x30;
constexpr uint8_t REG_DATA_FORMAT = 0x31;
constexpr uint8_t REG_DATAX0      = 0x32;
constexpr uint8_t REG_FIFO_CTL    = 0x38;
constexpr uint8_t REG_FIFO_STATUS = 0x39;

// FULL_RES=1, right justified, 4-wire SPI, range +/-16 g.
// Range bits: 0x08 -> +/-2 g; 0x09 -> +/-4 g; 0x0A -> +/-8 g.
constexpr uint8_t DATA_FORMAT = 0x0B;
constexpr uint8_t RATE_800_HZ = 0x0D;     // LOW_POWER=0, ODR=800 Hz.
constexpr uint8_t FIFO_STREAM = 0x81;     // Stream mode; watermark at one complete sample.
constexpr uint8_t IRQ_WATERMARK = 0x02;
constexpr uint8_t IRQ_DATA_READY = 0x80; // Used only for the startup INT1 wiring test.
constexpr uint32_t WARMUP_SAMPLES = 16;

/** @brief One raw, signed XYZ sample; conversion to g occurs only in loop(). */
struct Sample {
  int16_t x;
  int16_t y;
  int16_t z;
};

QueueHandle_t sampleQueue = nullptr;
TaskHandle_t acquisitionTaskHandle = nullptr;
SPISettings adxlSPI(SPI_HZ, MSBFIRST, SPI_MODE3);
portMUX_TYPE statsMux = portMUX_INITIALIZER_UNLOCKED;

/**
 * @brief Shared acquisition telemetry, protected by statsMux.
 *
 * Counters are cumulative and unsigned 32-bit; they eventually wrap.
 * A FIFO-full event reports an observed condition, not an exact lost-sample
 * count. spiFaults detects selected readback/status problems, not every
 * possible SPI bit error. Snapshot values describe the latest published batch.
 */
struct Diagnostics {
  uint32_t irqEdges = 0;              // Rising GPIO4 edges since ISR attachment.
  uint32_t lastIrqUs = 0;             // Most recent ISR timestamp, low 32 bits.
  uint32_t periodMinUs = UINT32_MAX;   // Shortest IRQ interval; reset after warmup.
  uint32_t periodMaxUs = 0;           // Longest IRQ interval; reset after warmup.
  uint32_t frames = 0;                // FIFO samples read, including warmup.
  uint32_t queued = 0;                // Samples successfully offered to UART queue.
  uint32_t fifoFullEvents = 0;        // Observations of full FIFO / overrun flag.
  uint32_t queueDropped = 0;          // Samples rejected because the RAM queue was full.
  uint32_t timeouts = 0;              // Notification waits that expired after 100 ms.
  uint32_t maxFifo = 0;               // Largest FIFO occupancy observed, in samples.
  uint32_t latencyMaxUs = 0;          // Max age of latest IRQ when its task services it.
  uint32_t spiFaults = 0;             // Selected config readback / FIFO-status faults.
  uint32_t emptyWakes = 0;            // Notifications serviced with no FIFO sample.
};

Diagnostics diagnostics;

/**
 * @brief Handle a rising INT1 edge with minimal work in interrupt context.
 *
 * Updates edge timing under the ISR-safe lock, then uses a FreeRTOS task
 * notification to wake acquisitionTask(). Requests an immediate context
 * switch when appropriate. The task handle is assigned before attaching
 * this ISR. No SPI, serial output, queue sample copying, or blocking calls.
 * @note The enabled runtime source is WATERMARK, not DATA_READY.
 */
void IRAM_ATTR onDataReady() {
  const uint32_t nowUs = static_cast<uint32_t>(esp_timer_get_time());
  portENTER_CRITICAL_ISR(&statsMux);
  if (diagnostics.irqEdges != 0) {
    const uint32_t period = nowUs - diagnostics.lastIrqUs; // Wrap-safe for uint32_t.
    if (period < diagnostics.periodMinUs) diagnostics.periodMinUs = period;
    if (period > diagnostics.periodMaxUs) diagnostics.periodMaxUs = period;
  }
  diagnostics.lastIrqUs = nowUs;
  ++diagnostics.irqEdges;
  portEXIT_CRITICAL_ISR(&statsMux);
  BaseType_t higherPriorityTaskWoken = pdFALSE;
  vTaskNotifyGiveFromISR(acquisitionTaskHandle, &higherPriorityTaskWoken);
  if (higherPriorityTaskWoken) portYIELD_FROM_ISR();
}

/**
 * @brief Copy shared telemetry under a short critical section.
 * @return A coherent copy of the currently published Diagnostics fields.
 * Serial formatting is done after releasing the lock so printing cannot
 * keep the ISR waiting. Acquisition counters are published after each drain.
 */
Diagnostics snapshotDiagnostics() {
  portENTER_CRITICAL(&statsMux);
  const Diagnostics result = diagnostics;
  portEXIT_CRITICAL(&statsMux);
  return result;
}

/**
 * @brief Write one ADXL345 register using a dedicated CS transaction.
 * @param reg Register address; only the low six address bits are transmitted.
 * @param value Complete eight-bit register value, not a masked bit update.
 * Called during setup or by the acquisition task; not safe for concurrent
 * callers sharing this SPI peripheral without additional serialization.
 */
void writeRegister(uint8_t reg, uint8_t value) {
  SPI.beginTransaction(adxlSPI);
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(reg & 0x3F);
  SPI.transfer(value);
  digitalWrite(PIN_CS, HIGH);
  SPI.endTransaction();
}

/**
 * @brief Read one register with the SPI read bit set and a dummy data byte.
 * @param reg Register address, before adding SPI command bits.
 * @return The received byte. This transfer has no independent CRC/error flag;
 * callers validate known configuration values or plausible status ranges.
 */
uint8_t readRegister(uint8_t reg) {
  SPI.beginTransaction(adxlSPI);
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(0x80 | (reg & 0x3F)); // Bit 7: read.
  uint8_t value = SPI.transfer(0x00);
  digitalWrite(PIN_CS, HIGH);
  SPI.endTransaction();
  return value;
}

/**
 * @brief Pop one complete XYZ sample with a six-byte burst starting at DATAX0.
 * @param[out] x Raw signed X count (little-endian register pair).
 * @param[out] y Raw signed Y count (little-endian register pair).
 * @param[out] z Raw signed Z count (little-endian register pair).
 *
 * CS stays low for the whole XYZ read. The 5 us delay after CS rises allows
 * FIFO data to advance before another data/FIFO_STATUS access at 2 MHz SPI.
 * During acquisition, call only for entries reported by FIFO_STATUS; an empty
 * FIFO must not be treated as a fresh sample. The one startup discard is
 * performed separately while clearing the old sensor state.
 */
void readAxes(int16_t &x, int16_t &y, int16_t &z) {
  uint8_t data[6];
  SPI.beginTransaction(adxlSPI);
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(0xC0 | REG_DATAX0); // Read + multiple bytes, starting at DATAX0.
  for (size_t i = 0; i < sizeof(data); ++i) {
    data[i] = SPI.transfer(0x00);
  }
  digitalWrite(PIN_CS, HIGH);
  SPI.endTransaction();

  // Required FIFO-pop interval before the next data/FIFO_STATUS read.
  delayMicroseconds(5);

  x = static_cast<int16_t>(uint16_t(data[0]) | (uint16_t(data[1]) << 8));
  y = static_cast<int16_t>(uint16_t(data[2]) | (uint16_t(data[3]) << 8));
  z = static_cast<int16_t>(uint16_t(data[4]) | (uint16_t(data[5]) << 8));
}

/**
 * @brief Print a fatal setup error and stop startup in a yielding wait loop.
 * @param message Human-readable serial message, normally prefixed with '#'.
 * Does not fabricate measurements or automatically retry a failed setup.
 */
void stopWithError(const char *message) {
  Serial.println(message);
  while (true) {
    delay(1000);
  }
}

/**
 * @brief Own SPI access after setup and move interrupt-ready samples into RAM.
 *
 * Startup clears the FIFO/old source state, attaches the ISR, enables the
 * watermark output, and starts measurement. The task then blocks on an IRQ
 * notification. After waking it reads FIFO occupancy and drains all entries,
 * checking again until empty so the next sample can raise a new edge.
 *
 * The first WARMUP_SAMPLES frames are counted but not queued. Later frames
 * use xQueueSend(..., 0): a full queue increases queueDropped rather than
 * blocking sensor service. Local counters are published under statsMux after
 * each drain. No UART printing is performed here.
 *
 * A 100 ms notification timeout is diagnostic only: the task continues waiting
 * for interrupts and does not read SPI as a timer-based fallback. A failed
 * interrupt-configuration readback increments spiFaults and deletes this task.
 * @note Created on core 1 with priority 4 and a 4096-byte task stack.
 */
void acquisitionTask(void *) {
  // Only this task accesses SPI after setup(). Serial runs in loop().
  acquisitionTaskHandle = xTaskGetCurrentTaskHandle();
  writeRegister(REG_FIFO_CTL, 0x00);
  int16_t discardX, discardY, discardZ;
  readAxes(discardX, discardY, discardZ);
  (void)readRegister(REG_INT_SOURCE);
  writeRegister(REG_FIFO_CTL, FIFO_STREAM);
  writeRegister(REG_INT_MAP, 0x00); // Watermark -> INT1, active high.
  attachInterrupt(digitalPinToInterrupt(PIN_INT1), onDataReady, RISING);
  writeRegister(REG_INT_ENABLE, IRQ_WATERMARK);
  writeRegister(REG_POWER_CTL, 0x08);
  if (readRegister(REG_INT_ENABLE) != IRQ_WATERMARK || readRegister(REG_INT_MAP) != 0x00) {
    portENTER_CRITICAL(&statsMux);
    ++diagnostics.spiFaults;
    portEXIT_CRITICAL(&statsMux);
    vTaskDelete(nullptr);
  }

  uint32_t frames = 0, queued = 0, fifoFullEvents = 0, queueDropped = 0;
  uint32_t maxFifo = 0, spiFaults = 0, emptyWakes = 0;

  while (true) {
    // A missing INT1 wire is reported; there is deliberately no polling fallback.
    if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100)) == 0) {
      portENTER_CRITICAL(&statsMux);
      ++diagnostics.timeouts;
      portEXIT_CRITICAL(&statsMux);
      continue;
    }
    portENTER_CRITICAL(&statsMux);
    const uint32_t latency = static_cast<uint32_t>(esp_timer_get_time()) - diagnostics.lastIrqUs;
    if (latency > diagnostics.latencyMaxUs) diagnostics.latencyMaxUs = latency;
    portEXIT_CRITICAL(&statsMux);

    bool gotData = false;
    // Watermark stays asserted while FIFO contains at least one sample. Drain it
    // completely so the next sample can generate a new rising edge.
    while (true) {
      const uint8_t source = readRegister(REG_INT_SOURCE);
      const uint8_t count = readRegister(REG_FIFO_STATUS) & 0x3F;
      if (count > 32) { // Invalid SPI/FIFO status: do not manufacture XYZ samples.
        ++spiFaults;
        break;
      }
      if ((source & 0x01) || count >= 32) ++fifoFullEvents;
      if (count > maxFifo) maxFifo = count;
      if (count == 0) {
        if (!gotData) ++emptyWakes;
        break;
      }
      gotData = true;
      for (uint8_t i = 0; i < count; ++i) {
        Sample sample{};
        readAxes(sample.x, sample.y, sample.z); // One six-byte burst, then 5 us FIFO-pop delay.
        ++frames;
        if (frames == WARMUP_SAMPLES) {
          // Period extrema describe steady acquisition, excluding sensor startup.
          portENTER_CRITICAL(&statsMux);
          diagnostics.periodMinUs = UINT32_MAX;
          diagnostics.periodMaxUs = 0;
          portEXIT_CRITICAL(&statsMux);
        }
        if (frames <= WARMUP_SAMPLES) continue;
        if (xQueueSend(sampleQueue, &sample, 0) == pdTRUE) ++queued;
        else ++queueDropped; // A stalled USB consumer must not block acquisition.
      }
    }
    portENTER_CRITICAL(&statsMux);
    diagnostics.frames = frames;
    diagnostics.queued = queued;
    diagnostics.fifoFullEvents = fifoFullEvents;
    diagnostics.queueDropped = queueDropped;
    diagnostics.maxFifo = maxFifo;
    diagnostics.spiFaults = spiFaults;
    diagnostics.emptyWakes = emptyWakes;
    portEXIT_CRITICAL(&statsMux);
  }
}

/**
 * @brief Initialize transport, validate the sensor and INT1 wire, then start acquisition.
 *
 * Sequence:
 * 1. Start Serial and configure CS, SPI, and GPIO4 as an input with pulldown.
 * 2. Require DEVID=0xE5; configure offsets, resolution/range, rate, and FIFO
 *    in standby, then verify key registers by reading them back.
 * 3. Run the INT1 line test: disabled output LOW -> DATA_READY HIGH ->
 *    inverted output LOW. GPIO4 is never driven as an output by ESP32.
 * 4. Restore normal polarity/standby, clear FIFO, allocate the sample queue,
 *    print the stream header, and create the acquisition task.
 *
 * Failed checks stop startup with a serial explanation. The wiring test
 * temporarily uses DATA_READY; steady-state sampling uses WATERMARK=1.
 */
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1500); // Allow the terminal to connect; do not wait indefinitely for USB.

  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_INT1, INPUT_PULLDOWN);
  SPI.begin(PIN_SCLK, PIN_MISO, PIN_MOSI, PIN_CS);
  delay(10);

  uint8_t id = readRegister(REG_DEVID);
  if (id != 0xE5) {
    Serial.printf("# Unexpected DEVID: 0x%02X; expected 0xE5\n", id);
    stopWithError("# Check 3V3, GND, CS, SCLK, MOSI and MISO.");
  }

  writeRegister(REG_POWER_CTL, 0x00); // Standby while configuring.
  writeRegister(REG_INT_ENABLE, 0x00);
  writeRegister(REG_INT_MAP, 0x00);
  writeRegister(REG_FIFO_CTL, 0x00);
  writeRegister(REG_OFSX, 0x00);
  writeRegister(REG_OFSY, 0x00);
  writeRegister(REG_OFSZ, 0x00);
  writeRegister(REG_DATA_FORMAT, DATA_FORMAT);
  writeRegister(REG_BW_RATE, RATE_800_HZ);
  writeRegister(REG_FIFO_CTL, FIFO_STREAM);

  if (readRegister(REG_DATA_FORMAT) != DATA_FORMAT ||
      readRegister(REG_BW_RATE) != RATE_800_HZ ||
      readRegister(REG_FIFO_CTL) != FIFO_STREAM ||
      readRegister(REG_POWER_CTL) != 0x00) {
    stopWithError("# ADXL345 configuration readback failed.");
  }

  // Verify that GPIO4 really follows the sensor's INT1 output before acquisition.
  // GPIO4 always remains an input. INT_INVERT controls the sensor output polarity.
  writeRegister(REG_POWER_CTL, 0x08);
  delay(15);
  const int inactive = digitalRead(PIN_INT1);
  const uint8_t testSource = readRegister(REG_INT_SOURCE);
  writeRegister(REG_INT_ENABLE, IRQ_DATA_READY);
  delayMicroseconds(50);
  const int active = digitalRead(PIN_INT1);
  writeRegister(REG_DATA_FORMAT, DATA_FORMAT | 0x20);
  delayMicroseconds(50);
  const int inverted = digitalRead(PIN_INT1);
  writeRegister(REG_INT_ENABLE, 0x00);
  writeRegister(REG_DATA_FORMAT, DATA_FORMAT);
  writeRegister(REG_POWER_CTL, 0x00);
  writeRegister(REG_FIFO_CTL, 0x00);
  writeRegister(REG_FIFO_CTL, FIFO_STREAM);
  Serial.printf("# IRQ_LINE_TEST inactive=%d active=%d inverted=%d source=0x%02X\n",
                inactive, active, inverted, testSource);
  if (inactive != LOW || active != HIGH || inverted != LOW || !(testSource & IRQ_DATA_READY)) {
    stopWithError("# INT1 wiring test failed: check ADXL345 INT1 -> ESP32-S3 GPIO4.");
  }

  sampleQueue = xQueueCreate(QUEUE_SAMPLES, sizeof(Sample));
  if (sampleQueue == nullptr) {
    stopWithError("# Not enough RAM for sample queue.");
  }

  Serial.println("# ADXL345: SPI mode 3, 2 MHz, 800 Hz, full resolution, +/-16 g; FIFO watermark=1 INT1 -> GPIO4");
  Serial.println("X_g,Y_g,Z_g");
  if (xTaskCreatePinnedToCore(acquisitionTask, "adxl345", 4096, nullptr, 4, nullptr, 1) != pdPASS) {
    stopWithError("# Could not create acquisition task.");
  }
}

/**
 * @brief Send queued XYZ measurements and periodic health information to the PC.
 *
 * Waits up to 20 ms for one queued sample, converts raw counts to g, and
 * prints exactly three comma-separated values. This wait is a queue-consumer
 * timeout, not the sensor's sample schedule. loop() never reads sensor SPI.
 *
 * About once per second, copies Diagnostics and emits '# IRQ_STATS'. A change
 * in FIFO-full, dropped, timeout, or SPI-fault counters also emits '# WARNING'.
 * UART/USB backpressure can slow this consumer; acquisition stays independent
 * until the finite RAM queue fills, at which point drops are counted.
 *
 * Diagnostic field meanings:
 * - uptime_ms / last_irq_us: ESP32 uptime clocks, with uint32_t wraparound.
 * - irq_edges / frames / queued / warmup: IRQs, reads, queued samples, discard count.
 * - fifo_full / queue_dropped / timeouts / spi_faults: fault observations/counters.
 * - max_fifo: maximum observed FIFO sample count, not the current fill level.
 * - period_min_us / period_max_us: IRQ intervals after the warmup extrema reset.
 * - latency_max_us: latest-IRQ age at the task service point, not complete SPI
 *   transaction latency or end-to-end delivery time to the PC.
 * - empty_wakes: serviced notifications with no available sample.
 * - int1: instantaneous GPIO4 level when this line is printed.
 */
void loop() {
  static uint32_t lastDiagnosticsMs = 0;
  static uint32_t reportedFifoFull = 0, reportedQueueDropped = 0;
  static uint32_t reportedTimeouts = 0, reportedSpiFaults = 0;
  Sample sample{};

  if (xQueueReceive(sampleQueue, &sample, pdMS_TO_TICKS(20)) == pdTRUE) {
    Serial.printf("%.5f,%.5f,%.5f\n", sample.x * G_PER_LSB, sample.y * G_PER_LSB, sample.z * G_PER_LSB);
  }

  if (millis() - lastDiagnosticsMs < 1000) return;
  lastDiagnosticsMs = millis();
  const Diagnostics s = snapshotDiagnostics();
  if (s.fifoFullEvents != reportedFifoFull || s.queueDropped != reportedQueueDropped ||
      s.timeouts != reportedTimeouts || s.spiFaults != reportedSpiFaults) {
    Serial.printf("# WARNING: FIFO full events=%lu; queue dropped=%lu; irq_timeouts=%lu; spi_faults=%lu; check INT1 -> GPIO4\n",
                  (unsigned long)s.fifoFullEvents, (unsigned long)s.queueDropped,
                  (unsigned long)s.timeouts, (unsigned long)s.spiFaults);
    reportedFifoFull = s.fifoFullEvents;
    reportedQueueDropped = s.queueDropped;
    reportedTimeouts = s.timeouts;
    reportedSpiFaults = s.spiFaults;
  }
  Serial.printf("# IRQ_STATS uptime_ms=%lu irq_edges=%lu last_irq_us=%lu frames=%lu queued=%lu warmup=%lu fifo_full=%lu queue_dropped=%lu timeouts=%lu max_fifo=%lu period_min_us=%lu period_max_us=%lu latency_max_us=%lu spi_faults=%lu empty_wakes=%lu int1=%d\n",
                (unsigned long)lastDiagnosticsMs, (unsigned long)s.irqEdges, (unsigned long)s.lastIrqUs, (unsigned long)s.frames,
                (unsigned long)s.queued, (unsigned long)WARMUP_SAMPLES, (unsigned long)s.fifoFullEvents,
                (unsigned long)s.queueDropped, (unsigned long)s.timeouts, (unsigned long)s.maxFifo,
                (unsigned long)(s.periodMinUs == UINT32_MAX ? 0 : s.periodMinUs),
                (unsigned long)s.periodMaxUs, (unsigned long)s.latencyMaxUs,
                (unsigned long)s.spiFaults, (unsigned long)s.emptyWakes, digitalRead(PIN_INT1));
}
