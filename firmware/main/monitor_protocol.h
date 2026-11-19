/** @file monitor_protocol.h
 * @brief Pure C wire contract; does not depend on Arduino or ESP-IDF headers.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>

typedef struct {
    int16_t x, y, z;
} adxl_sample_t;

/** Cumulative uint32_t fields retain the existing PC monitor's field names. */
typedef struct {
    uint32_t irq_edges, last_irq_us, period_min_us, period_max_us;
    uint32_t frames, queued, fifo_full, queue_dropped, timeouts, max_fifo;
    uint32_t latency_max_us, spi_faults, empty_wakes;
} monitor_stats_t;

/** Return line length including LF, or -1 on formatting error/truncation.
 * Raw counts are converted with the same nominal 1/256 g scale as before.
 * Five decimal places describe output formatting, not calibrated accuracy.
 */
int monitor_format_sample(char *buffer, size_t capacity, const adxl_sample_t *sample);
int monitor_format_stats(char *buffer, size_t capacity, const monitor_stats_t *stats,
                         uint32_t uptime_ms, unsigned int int1);
int monitor_format_warning(char *buffer, size_t capacity, const monitor_stats_t *stats);
