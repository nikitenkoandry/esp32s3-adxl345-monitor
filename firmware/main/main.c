/** @file main.c
 * @brief ESP-IDF C entry point: validate wiring, start acquisition, stream CSV.
 *
 * UART0 TX=43/RX=44 uses the existing USB-UART bridge at 921600 baud, 8N1.
 * app_main is the sole application UART writer. The sensor task and ISR never
 * print. ESP-IDF console/application/bootloader logs are disabled in defaults
 * so normal runtime lines remain compatible with the existing PC monitor.
 * ROM output during reset can still occur at its own boot baud rate.
 */
#include "acquisition.h"
#include "adxl345.h"
#include "board_config.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include <stdio.h>
#include <string.h>

static void send_line(const char *line)
{
    const size_t length = strlen(line);
    if (uart_write_bytes(UART_NUM_0, line, length) != (int)length) {
        // A broken transport cannot reliably report its own failure.
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static void fatal_setup(const char *reason, esp_err_t error)
{
    char line[256];
    snprintf(line, sizeof(line), "# ERROR: %s (%s)\n", reason, esp_err_to_name(error));
    send_line(line);
    for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
}

static esp_err_t initialize_uart(void)
{
    const uart_config_t config = {
        .baud_rate = MONITOR_BAUD, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
    esp_err_t err = uart_param_config(UART_NUM_0, &config);
    if (err != ESP_OK) return err;
    err = uart_set_pin(UART_NUM_0, MONITOR_UART_TX, MONITOR_UART_RX,
                       UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) return err;
    // ESP-IDF requires an RX ring larger than its hardware FIFO even though
    // this application accepts no commands. TX backpressure only blocks app_main.
    return uart_driver_install(UART_NUM_0, 1024, 8192, 0, NULL, 0);
}

/** Toggle the sensor output, never GPIO4 itself, to verify INT1 connectivity.
 * Preserve the prior LOW -> HIGH -> inverted LOW wiring test. DATA_READY is
 * temporary here; only WATERMARK is enabled after acquisition starts.
 */
static esp_err_t verify_int1(void)
{
    esp_err_t err = adxl345_write_register(ADXL_REG_POWER_CTL, 0x08);
    if (err != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(15));
    const int inactive = gpio_get_level(ADXL_PIN_INT1);
    uint8_t source;
    err = adxl345_read_register(ADXL_REG_INT_SOURCE, &source);
    if (err != ESP_OK) goto cleanup;
    err = adxl345_write_register(ADXL_REG_INT_ENABLE, ADXL_IRQ_DATA_READY);
    if (err != ESP_OK) goto cleanup;
    esp_rom_delay_us(50);
    const int active = gpio_get_level(ADXL_PIN_INT1);
    err = adxl345_write_register(ADXL_REG_DATA_FORMAT, ADXL_DATA_FORMAT | 0x20);
    if (err != ESP_OK) goto cleanup;
    esp_rom_delay_us(50);
    const int inverted = gpio_get_level(ADXL_PIN_INT1);
    char line[128];
    snprintf(line, sizeof(line), "# IRQ_LINE_TEST inactive=%d active=%d inverted=%d source=0x%02X\n",
             inactive, active, inverted, source);
    send_line(line);
    if (inactive != 0 || active != 1 || inverted != 0 || !(source & ADXL_IRQ_DATA_READY)) {
        err = ESP_ERR_INVALID_RESPONSE;
    }
cleanup:
    // Attempt every restore even when a previous transfer failed.
    {
        const uint8_t restore[][2] = {
            {ADXL_REG_INT_ENABLE, 0}, {ADXL_REG_DATA_FORMAT, ADXL_DATA_FORMAT},
            {ADXL_REG_POWER_CTL, 0}, {ADXL_REG_FIFO_CTL, 0},
            {ADXL_REG_FIFO_CTL, ADXL_FIFO_STREAM},
        };
        for (size_t i = 0; i < sizeof(restore) / sizeof(restore[0]); ++i) {
            const esp_err_t restored = adxl345_write_register(restore[i][0], restore[i][1]);
            if (err == ESP_OK) err = restored;
        }
    }
    return err;
}

void app_main(void)
{
    if (initialize_uart() != ESP_OK) return; // No usable transport to report over.
    vTaskDelay(pdMS_TO_TICKS(1500));
    const gpio_config_t interrupt_pin = {
        .pin_bit_mask = 1ULL << ADXL_PIN_INT1, .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE, .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&interrupt_pin);
    if (err != ESP_OK) fatal_setup("Could not configure INT1 input", err);
    err = adxl345_init();
    if (err != ESP_OK) fatal_setup("Could not initialize SPI", err);
    err = adxl345_configure();
    if (err != ESP_OK) fatal_setup("ADXL345 DEVID/configuration check failed; check SPI/power", err);
    err = verify_int1();
    if (err != ESP_OK) fatal_setup("INT1 wiring test failed: check ADXL345 INT1 -> ESP32-S3 GPIO4", err);

    QueueHandle_t queue = xQueueCreate(SAMPLE_QUEUE_LENGTH, sizeof(adxl_sample_t));
    if (queue == NULL) fatal_setup("Not enough RAM for sample queue", ESP_ERR_NO_MEM);
    send_line("# ADXL345: SPI mode 3, 2 MHz, 800 Hz, full resolution, +/-16 g; FIFO watermark=1 INT1 -> GPIO4; ESP-IDF C\n");
    send_line("X_g,Y_g,Z_g\n");
    err = acquisition_start(queue);
    if (err != ESP_OK) fatal_setup("Could not start acquisition task/ISR", err);

    uint32_t last_report_ms = 0;
    monitor_stats_t reported = {0};
    char line[MONITOR_LINE_CAPACITY];
    for (;;) {
        adxl_sample_t sample;
        if (xQueueReceive(queue, &sample, pdMS_TO_TICKS(20)) == pdTRUE) {
            if (monitor_format_sample(line, sizeof(line), &sample) < 0) {
                fatal_setup("Sample formatting failed", ESP_ERR_INVALID_SIZE);
            }
            send_line(line);
        }
        const uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
        if (now_ms - last_report_ms < 1000) continue;
        last_report_ms = now_ms;
        const monitor_stats_t stats = acquisition_snapshot();
        if (stats.fifo_full != reported.fifo_full || stats.queue_dropped != reported.queue_dropped ||
            stats.timeouts != reported.timeouts || stats.spi_faults != reported.spi_faults) {
            if (monitor_format_warning(line, sizeof(line), &stats) < 0) {
                fatal_setup("Warning formatting failed", ESP_ERR_INVALID_SIZE);
            }
            send_line(line);
            reported = stats;
        }
        if (monitor_format_stats(line, sizeof(line), &stats, now_ms,
                                 gpio_get_level(ADXL_PIN_INT1)) < 0) {
            fatal_setup("Diagnostics formatting failed", ESP_ERR_INVALID_SIZE);
        }
        send_line(line);
    }
}
