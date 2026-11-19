/** Execute the production acquisition task with scripted IRQ/FIFO/queue events.
 * Each scenario is a separate process with fresh firmware static state.
 * Simulated scheduling validates logic, not electrical signals or real latency.
 */
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include "acquisition.h"
#include "adxl345.h"
#include "board_config.h"
#include "driver/gpio.h"
#include "esp_intr_alloc.h"
#include "freertos/task.h"

static jmp_buf finished;
static TaskFunction_t task_function;
static gpio_isr_t irq_handler;
static uint8_t registers[64];
static uint64_t clock_us = UINT32_MAX - 255ULL;
static unsigned int wait_calls, register_reads, reads_before_wait, queue_calls;
static unsigned int fifo_count, irq_notifications;
static int irq_disabled, service_removed, service_installs;
static int outcome;
static const char *scenario;

esp_err_t adxl345_clear_fifo(void) { return ESP_OK; }
esp_err_t adxl345_write_register(uint8_t address, uint8_t value)
{
    registers[address] = value;
    return ESP_OK;
}
esp_err_t adxl345_read_register(uint8_t address, uint8_t *value)
{
    ++register_reads;
    if (wait_calls && !strcmp(scenario, "bus-failure") && address == ADXL_REG_INT_SOURCE) return ESP_FAIL;
    if (address == ADXL_REG_FIFO_STATUS) *value = (uint8_t)fifo_count;
    else if (address == ADXL_REG_INT_SOURCE) *value = fifo_count >= 32 ? 1 : 0;
    else *value = registers[address];
    return ESP_OK;
}
esp_err_t adxl345_read_sample(adxl_sample_t *sample)
{
    assert(fifo_count > 0);
    if (!strcmp(scenario, "burst-failure")) return ESP_FAIL;
    *sample = (adxl_sample_t){1, 2, 256};
    --fifo_count;
    return ESP_OK;
}
esp_err_t gpio_set_intr_type(int pin, int type)
{
    assert(pin == 4 && type == GPIO_INTR_POSEDGE);
    return ESP_OK;
}
esp_err_t gpio_isr_handler_add(int pin, gpio_isr_t handler, void *argument)
{
    assert(pin == 4 && argument == NULL);
    irq_handler = handler;
    return ESP_OK;
}
esp_err_t gpio_intr_disable(int pin)
{
    assert(pin == 4);
    irq_disabled = 1;
    return ESP_OK;
}
esp_err_t gpio_isr_handler_remove(int pin)
{
    assert(pin == 4 && irq_disabled);
    irq_handler = NULL;
    return ESP_OK;
}
esp_err_t gpio_install_isr_service(int flags)
{
    assert(flags == ESP_INTR_FLAG_IRAM);
    ++service_installs;
    if (!strcmp(scenario, "service-failure")) return ESP_FAIL;
    return ESP_OK;
}
void gpio_uninstall_isr_service(void) { service_removed = 1; }
int64_t esp_timer_get_time(void) { return (int64_t)clock_us; }
TaskHandle_t xTaskGetCurrentTaskHandle(void) { return (void *)1; }
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t function, const char *name,
    uint32_t stack, void *argument, UBaseType_t priority, TaskHandle_t *handle, int core)
{
    assert(!strcmp(name, "adxl345") && stack == 4096 && priority == 4 && core == 1);
    assert(argument == NULL);
    if (!strcmp(scenario, "task-failure")) return pdFALSE;
    *handle = (void *)1;
    task_function = function;
    return pdPASS;
}
void vTaskNotifyGiveFromISR(TaskHandle_t task, BaseType_t *woken)
{
    assert(task == (void *)1 && !irq_disabled);
    ++irq_notifications;
    *woken = pdTRUE;
}
void vTaskDelete(TaskHandle_t task)
{
    assert(task == NULL && irq_disabled && irq_handler == NULL);
    assert(registers[ADXL_REG_INT_ENABLE] == 0 && registers[ADXL_REG_POWER_CTL] == 0);
    outcome = 2;
    longjmp(finished, 1);
}
BaseType_t xQueueSend(QueueHandle_t queue, const void *item, TickType_t wait)
{
    assert(queue == (void *)2 && wait == 0); // Backpressure cannot block acquisition.
    const adxl_sample_t *sample = item;
    assert(sample->z == 256);
    ++queue_calls;
    return queue_calls == 1 ? pdTRUE : pdFALSE;
}
uint32_t ulTaskNotifyTake(BaseType_t clear, TickType_t wait)
{
    assert(clear == pdTRUE && wait == 100);
    ++wait_calls;
    if (!strcmp(scenario, "normal") && wait_calls == 1) {
        reads_before_wait = register_reads;
        return 0;
    }
    if (!strcmp(scenario, "normal")) {
        if (wait_calls == 2) {
            assert(register_reads == reads_before_wait); // Timeout caused no SPI fallback.
            fifo_count = 18;
        } else if (wait_calls == 3) fifo_count = 32;
        else if (wait_calls == 4) fifo_count = 0;
        else {
            outcome = 1;
            longjmp(finished, 1);
        }
    } else {
        assert(wait_calls == 1);
        fifo_count = !strcmp(scenario, "invalid-fifo") ? 33 : 2;
    }
    assert(irq_handler != NULL);
    if (irq_notifications) clock_us += 1280;
    irq_handler(NULL);
    clock_us += 20;
    return 1;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    scenario = argv[1];
    assert(acquisition_start(NULL) == ESP_ERR_INVALID_ARG);
    if (!strcmp(scenario, "task-failure")) {
        assert(acquisition_start((void *)2) == ESP_ERR_NO_MEM);
        assert(!service_removed && service_installs == 0);
    } else {
        assert(acquisition_start((void *)2) == ESP_OK);
        if (setjmp(finished) == 0) task_function(NULL);
        const monitor_stats_t stats = acquisition_snapshot();
        if (!strcmp(scenario, "normal")) {
            assert(outcome == 1 && !irq_disabled);
            assert(stats.frames == 50 && stats.queued == 1 && stats.queue_dropped == 33);
            assert(stats.frames == stats.queued + WARMUP_SAMPLES + stats.queue_dropped);
            assert(stats.timeouts == 1 && stats.fifo_full == 1 && stats.max_fifo == 32);
            assert(stats.empty_wakes == 1 && stats.spi_faults == 0 && stats.irq_edges == 3);
            assert(stats.period_min_us == 1300 && stats.period_max_us == 1300);
            assert(stats.latency_max_us == 20);
        } else {
            assert(outcome == 2 && irq_disabled && stats.spi_faults == 1);
            assert(stats.frames == 0 && stats.queued == 0 && queue_calls == 0);
        }
        assert(service_installs == 1);
    }
    printf("C acquisition scenario passed: %s\n", scenario);
    return 0;
}
