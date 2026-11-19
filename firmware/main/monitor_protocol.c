/** @file monitor_protocol.c
 * @brief Format the existing XYZ/comment protocol for the unmodified PC tool.
 * One producer owns the output transport; no ESP-IDF log prefixes or ANSI colors
 * are inserted into these lines. All status lines begin with '#'.
 */
#include "monitor_protocol.h"
#include "board_config.h"
#include <inttypes.h>
#include <stdio.h>

static int checked_length(int result, size_t capacity)
{
    return result < 0 || (size_t)result >= capacity ? -1 : result;
}

int monitor_format_sample(char *buffer, size_t capacity, const adxl_sample_t *sample)
{
    return checked_length(snprintf(buffer, capacity, "%.5f,%.5f,%.5f\n",
        sample->x / 256.0, sample->y / 256.0, sample->z / 256.0), capacity);
}

int monitor_format_stats(char *buffer, size_t capacity, const monitor_stats_t *s,
                         uint32_t uptime_ms, unsigned int int1)
{
    return checked_length(snprintf(buffer, capacity,
        "# IRQ_STATS uptime_ms=%" PRIu32 " irq_edges=%" PRIu32
        " last_irq_us=%" PRIu32 " frames=%" PRIu32 " queued=%" PRIu32
        " warmup=%u fifo_full=%" PRIu32 " queue_dropped=%" PRIu32
        " timeouts=%" PRIu32 " max_fifo=%" PRIu32 " period_min_us=%" PRIu32
        " period_max_us=%" PRIu32 " latency_max_us=%" PRIu32
        " spi_faults=%" PRIu32 " empty_wakes=%" PRIu32 " int1=%u\n",
        uptime_ms, s->irq_edges, s->last_irq_us, s->frames, s->queued,
        (unsigned int)WARMUP_SAMPLES, s->fifo_full, s->queue_dropped,
        s->timeouts, s->max_fifo,
        s->period_min_us == UINT32_MAX ? 0 : s->period_min_us,
        s->period_max_us, s->latency_max_us, s->spi_faults, s->empty_wakes,
        int1 ? 1U : 0U), capacity);
}

int monitor_format_warning(char *buffer, size_t capacity, const monitor_stats_t *s)
{
    return checked_length(snprintf(buffer, capacity,
        "# WARNING: FIFO full events=%" PRIu32 "; queue dropped=%" PRIu32
        "; irq_timeouts=%" PRIu32 "; spi_faults=%" PRIu32 "; check INT1 -> GPIO4\n",
        s->fifo_full, s->queue_dropped, s->timeouts, s->spi_faults), capacity);
}
