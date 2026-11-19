/** @file acquisition.c
 * @brief A GPIO ISR wakes a dedicated FreeRTOS task; it never reads SPI/UART.
 *
 * The sensor determines the nominal 800 Hz sample timing. Notifications may
 * coalesce, so each wake drains FIFO according to occupancy, not edge count.
 * Missing INT1 interrupts produce 100 ms timeouts with no polling fallback.
 * Nonblocking queue insertion preserves acquisition service under UART stalls.
 */
#include "acquisition.h"
#include "adxl345.h"
#include "board_config.h"
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_intr_alloc.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include <stdbool.h>
#include <stdint.h>

static QueueHandle_t samples;
static TaskHandle_t acquisition_task_handle;
static portMUX_TYPE stats_lock = portMUX_INITIALIZER_UNLOCKED;
static monitor_stats_t statistics = {.period_min_us = UINT32_MAX};

static void IRAM_ATTR on_int1(void *argument)
{
    (void)argument;
    const uint32_t now = (uint32_t)esp_timer_get_time();
    portENTER_CRITICAL_ISR(&stats_lock);
    if (statistics.irq_edges != 0) {
        const uint32_t period = now - statistics.last_irq_us;
        if (period < statistics.period_min_us) statistics.period_min_us = period;
        if (period > statistics.period_max_us) statistics.period_max_us = period;
    }
    statistics.last_irq_us = now;
    ++statistics.irq_edges;
    portEXIT_CRITICAL_ISR(&stats_lock);
    BaseType_t task_woken = pdFALSE;
    vTaskNotifyGiveFromISR(acquisition_task_handle, &task_woken);
    if (task_woken) portYIELD_FROM_ISR();
}

monitor_stats_t acquisition_snapshot(void)
{
    portENTER_CRITICAL(&stats_lock);
    const monitor_stats_t result = statistics;
    portEXIT_CRITICAL(&stats_lock);
    return result;
}

/** Publish only task-owned fields so ISR timestamps/counts are not overwritten. */
static void publish_counters(const monitor_stats_t *totals)
{
    portENTER_CRITICAL(&stats_lock);
    statistics.frames = totals->frames;
    statistics.queued = totals->queued;
    statistics.fifo_full = totals->fifo_full;
    statistics.queue_dropped = totals->queue_dropped;
    statistics.max_fifo = totals->max_fifo;
    statistics.spi_faults = totals->spi_faults;
    statistics.empty_wakes = totals->empty_wakes;
    portEXIT_CRITICAL(&stats_lock);
}

/** Stop the GPIO source before deleting its notification recipient.
 * A bus/status failure requires a reset and is exposed as spi_faults. Do not
 * keep producing plausible XYZ values from failed transactions.
 */
static void stop_acquisition(monitor_stats_t *totals)
{
    (void)gpio_intr_disable(ADXL_PIN_INT1);
    (void)gpio_isr_handler_remove(ADXL_PIN_INT1);
    (void)adxl345_write_register(ADXL_REG_INT_ENABLE, 0);
    (void)adxl345_write_register(ADXL_REG_POWER_CTL, 0);
    ++totals->spi_faults;
    publish_counters(totals);
    vTaskDelete(NULL);
}

static void acquisition_task(void *argument)
{
    (void)argument;
    monitor_stats_t totals = {0};
    acquisition_task_handle = xTaskGetCurrentTaskHandle();
    uint8_t enabled, mapped;
    // Allocate the GPIO interrupt on the same core as its recipient task.
    // ISR completion and task deletion are then serialized on core 1.
    if (gpio_install_isr_service(ESP_INTR_FLAG_IRAM) != ESP_OK ||
        adxl345_clear_fifo() != ESP_OK ||
        adxl345_write_register(ADXL_REG_INT_MAP, 0) != ESP_OK ||
        gpio_set_intr_type(ADXL_PIN_INT1, GPIO_INTR_POSEDGE) != ESP_OK ||
        gpio_isr_handler_add(ADXL_PIN_INT1, on_int1, NULL) != ESP_OK ||
        adxl345_write_register(ADXL_REG_INT_ENABLE, ADXL_IRQ_WATERMARK) != ESP_OK ||
        adxl345_write_register(ADXL_REG_POWER_CTL, 0x08) != ESP_OK ||
        adxl345_read_register(ADXL_REG_INT_ENABLE, &enabled) != ESP_OK ||
        adxl345_read_register(ADXL_REG_INT_MAP, &mapped) != ESP_OK ||
        enabled != ADXL_IRQ_WATERMARK || mapped != 0) {
        stop_acquisition(&totals);
        return;
    }

    for (;;) {
        if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(IRQ_WAIT_MS)) == 0) {
            portENTER_CRITICAL(&stats_lock);
            ++statistics.timeouts;
            portEXIT_CRITICAL(&stats_lock);
            continue; // No timed SPI reads and no manufactured samples.
        }
        portENTER_CRITICAL(&stats_lock);
        const uint32_t latency = (uint32_t)esp_timer_get_time() - statistics.last_irq_us;
        if (latency > statistics.latency_max_us) statistics.latency_max_us = latency;
        portEXIT_CRITICAL(&stats_lock);

        bool got_data = false;
        for (;;) {
            uint8_t source, count;
            if (adxl345_read_register(ADXL_REG_INT_SOURCE, &source) != ESP_OK ||
                adxl345_read_register(ADXL_REG_FIFO_STATUS, &count) != ESP_OK) {
                stop_acquisition(&totals);
                return;
            }
            count &= 0x3f;
            if (count > 32) {
                stop_acquisition(&totals);
                return;
            }
            if ((source & 1) || count >= 32) ++totals.fifo_full;
            if (count > totals.max_fifo) totals.max_fifo = count;
            if (count == 0) {
                if (!got_data) ++totals.empty_wakes;
                break;
            }
            got_data = true;
            for (uint8_t i = 0; i < count; ++i) {
                adxl_sample_t sample;
                if (adxl345_read_sample(&sample) != ESP_OK) {
                    stop_acquisition(&totals);
                    return;
                }
                ++totals.frames;
                if (totals.frames == WARMUP_SAMPLES) {
                    portENTER_CRITICAL(&stats_lock);
                    statistics.period_min_us = UINT32_MAX;
                    statistics.period_max_us = 0;
                    portEXIT_CRITICAL(&stats_lock);
                }
                if (totals.frames <= WARMUP_SAMPLES) continue;
                if (xQueueSend(samples, &sample, 0) == pdTRUE) ++totals.queued;
                else ++totals.queue_dropped;
            }
        }
        publish_counters(&totals);
    }
}

esp_err_t acquisition_start(QueueHandle_t queue)
{
    if (queue == NULL) return ESP_ERR_INVALID_ARG;
    if (acquisition_task_handle != NULL) return ESP_ERR_INVALID_STATE;
    samples = queue;
    // Handle is set inside the task before attaching the interrupt source.
    if (xTaskCreatePinnedToCore(acquisition_task, "adxl345", 4096, NULL, 4,
                              &acquisition_task_handle, 1) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}
