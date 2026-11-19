/** Host checks execute the production C driver and wire formatter against a
 * modeled register bus. This is not a hardware/interrupt timing measurement.
 */
#include "adxl345.h"
#include "board_config.h"
#include "driver/spi_master.h"
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

static uint8_t registers[64], xyz_bytes[6];
static bool fail_transfer, fail_add, corrupt_readback, awaiting_fifo_delay;
static unsigned free_calls, burst_reads, delayed_us;

esp_err_t spi_bus_initialize(int host, const spi_bus_config_t *bus, int dma)
{
    assert(host == SPI2_HOST && dma == SPI_DMA_DISABLED);
    assert(bus->sclk_io_num == 12 && bus->mosi_io_num == 11 && bus->miso_io_num == 13);
    assert(bus->quadwp_io_num == -1 && bus->quadhd_io_num == -1);
    assert(bus->data4_io_num == -1 && bus->data7_io_num == -1);
    assert(bus->max_transfer_sz == 6);
    return ESP_OK;
}

esp_err_t spi_bus_add_device(int host, const spi_device_interface_config_t *config,
                             spi_device_handle_t *device)
{
    assert(host == SPI2_HOST && config->command_bits == 8);
    assert(config->mode == 3 && config->clock_speed_hz == 2000000);
    assert(config->spics_io_num == 10 && config->queue_size == 1);
    if (fail_add) return ESP_FAIL;
    *device = (void *)registers;
    return ESP_OK;
}

esp_err_t spi_bus_remove_device(spi_device_handle_t device)
{
    assert(device == (void *)registers);
    return ESP_OK;
}

esp_err_t spi_bus_free(int host)
{
    assert(host == SPI2_HOST);
    ++free_calls;
    return ESP_OK;
}

esp_err_t spi_device_polling_transmit(spi_device_handle_t device, spi_transaction_t *t)
{
    assert(device == (void *)registers);
    assert(!awaiting_fifo_delay); // No status/next-sample read before the delay.
    if (fail_transfer) return ESP_FAIL;
    const uint8_t address = t->cmd & 0x3f;
    if (t->cmd & 0x80) {
        if (t->cmd & 0x40) {
            assert(t->cmd == 0xf2 && t->length == 48 && t->rx_buffer != NULL);
            memcpy(t->rx_buffer, xyz_bytes, sizeof(xyz_bytes));
            ++burst_reads;
            awaiting_fifo_delay = true;
        } else {
            assert(t->length == 8 && t->flags == SPI_TRANS_USE_RXDATA);
            t->rx_data[0] = registers[address];
            if (corrupt_readback && address == ADXL_REG_BW_RATE) t->rx_data[0] ^= 1;
        }
    } else {
        assert(t->length == 8 && t->flags == SPI_TRANS_USE_TXDATA);
        registers[address] = t->tx_data[0];
    }
    return ESP_OK;
}

void esp_rom_delay_us(uint32_t delay)
{
    assert(delay == 5);
    delayed_us += delay;
    awaiting_fifo_delay = false;
}

int main(void)
{
    uint8_t value = 0;
    adxl_sample_t sample = {123, 456, 789};
    assert(adxl345_read_register(0, &value) == ESP_ERR_INVALID_STATE);
    fail_add = true;
    assert(adxl345_init() == ESP_FAIL && free_calls == 1);
    fail_add = false;
    assert(adxl345_init() == ESP_OK);
    assert(adxl345_init() == ESP_ERR_INVALID_STATE);
    assert(adxl345_read_register(0, NULL) == ESP_ERR_INVALID_ARG);
    assert(adxl345_read_sample(NULL) == ESP_ERR_INVALID_ARG);
    assert(adxl345_configure() == ESP_ERR_INVALID_RESPONSE); // Wrong device ID.
    registers[0] = 0xe5;
    assert(adxl345_configure() == ESP_OK);
    assert(registers[ADXL_REG_BW_RATE] == 0x0d);
    assert(registers[ADXL_REG_DATA_FORMAT] == 0x0b);
    assert(registers[ADXL_REG_FIFO_CTL] == 0x81);
    assert(registers[ADXL_REG_POWER_CTL] == 0 && registers[ADXL_REG_INT_ENABLE] == 0);
    assert(registers[ADXL_REG_INT_MAP] == 0);
    assert(registers[ADXL_REG_OFSX] == 0 && registers[ADXL_REG_OFSY] == 0 && registers[ADXL_REG_OFSZ] == 0);
    corrupt_readback = true;
    assert(adxl345_configure() == ESP_ERR_INVALID_RESPONSE);
    corrupt_readback = false;
    fail_transfer = true;
    assert(adxl345_read_register(0, &value) == ESP_FAIL);
    assert(adxl345_write_register(0, 0) == ESP_FAIL);
    assert(adxl345_configure() == ESP_FAIL);
    assert(adxl345_read_sample(&sample) == ESP_FAIL);
    assert(sample.x == 123 && sample.y == 456 && sample.z == 789);
    fail_transfer = false;
    const uint8_t signed_values[] = {0x00, 0x80, 0xff, 0x7f, 0xff, 0xff};
    memcpy(xyz_bytes, signed_values, sizeof(xyz_bytes));
    assert(adxl345_read_sample(&sample) == ESP_OK);
    assert(sample.x == -32768 && sample.y == 32767 && sample.z == -1);
    assert(burst_reads == 1 && delayed_us == 10);
    assert(adxl345_read_register(ADXL_REG_FIFO_STATUS, &value) == ESP_OK);
    assert(adxl345_clear_fifo() == ESP_OK && registers[ADXL_REG_FIFO_CTL] == 0x81);
    assert(burst_reads == 2 && delayed_us == 15);
    assert(adxl345_deinit() == ESP_OK && free_calls == 2);

    // stdout is an actual wire fixture consumed by the unmodified PC parser.
    char line[MONITOR_LINE_CAPACITY];
    puts("# ADXL345: ESP-IDF C host protocol test");
    puts("X_g,Y_g,Z_g");
    sample = (adxl_sample_t){-1, 2, 256};
    assert(monitor_format_sample(line, sizeof(line), &sample) > 0);
    assert(strcmp(line, "-0.00391,0.00781,1.00000\n") == 0);
    fputs(line, stdout);
    sample = (adxl_sample_t){-4096, 4095, 0};
    assert(monitor_format_sample(line, sizeof(line), &sample) > 0);
    fputs(line, stdout);
    assert(monitor_format_sample(line, 4, &sample) == -1);
    monitor_stats_t stats = {.irq_edges = 1000, .last_irq_us = 1250000,
        .frames = 1000, .queued = 984, .period_min_us = 1250, .period_max_us = 1251,
        .max_fifo = 1, .latency_max_us = 20};
    assert(monitor_format_stats(line, sizeof(line), &stats, 2500, 0) > 0);
    fputs(line, stdout);
    const monitor_stats_t maximum = {
        .irq_edges = UINT32_MAX, .last_irq_us = UINT32_MAX, .frames = UINT32_MAX,
        .queued = UINT32_MAX, .period_min_us = UINT32_MAX - 1, .period_max_us = UINT32_MAX,
        .fifo_full = UINT32_MAX, .queue_dropped = UINT32_MAX, .timeouts = UINT32_MAX,
        .max_fifo = UINT32_MAX, .latency_max_us = UINT32_MAX, .spi_faults = UINT32_MAX,
        .empty_wakes = UINT32_MAX};
    assert(monitor_format_stats(line, sizeof(line), &maximum, UINT32_MAX, 1) > 0);
    fputs(line, stdout);
    assert(monitor_format_stats(line, 16, &stats, 0, 0) == -1);
    assert(monitor_format_warning(line, sizeof(line), &maximum) > 0);
    assert(strncmp(line, "# WARNING: ", 11) == 0);
    stats.period_min_us = UINT32_MAX;
    assert(monitor_format_stats(line, sizeof(line), &stats, 0, 0) > 0);
    assert(strstr(line, "period_min_us=0 ") != NULL);
    fputs("C driver/protocol checks passed\n", stderr);
    return 0;
}
