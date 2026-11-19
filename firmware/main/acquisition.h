/** @file acquisition.h
 * @brief INT1-triggered FIFO acquisition; queue consumption is independent.
 */
#pragma once
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "monitor_protocol.h"

/** Start the ISR/task after configuration and the wiring test, in standby. */
esp_err_t acquisition_start(QueueHandle_t queue);
/** Copy shared fields under the same critical-section lock used by the ISR. */
monitor_stats_t acquisition_snapshot(void);
