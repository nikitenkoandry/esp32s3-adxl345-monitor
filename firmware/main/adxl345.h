/** @file adxl345.h
 * @brief ADXL345 four-wire SPI driver using the native ESP-IDF SPI master API.
 * Setup owns the device initially; only the acquisition task uses it afterwards.
 * Callers must not access the device concurrently.
 */
#pragma once
#include <stdint.h>
#include "esp_err.h"
#include "monitor_protocol.h"

enum {
    ADXL_REG_DEVID = 0x00,
    ADXL_REG_OFSX = 0x1e, ADXL_REG_OFSY = 0x1f, ADXL_REG_OFSZ = 0x20,
    ADXL_REG_BW_RATE = 0x2c, ADXL_REG_POWER_CTL = 0x2d,
    ADXL_REG_INT_ENABLE = 0x2e, ADXL_REG_INT_MAP = 0x2f,
    ADXL_REG_INT_SOURCE = 0x30, ADXL_REG_DATA_FORMAT = 0x31,
    ADXL_REG_DATAX0 = 0x32, ADXL_REG_FIFO_CTL = 0x38,
    ADXL_REG_FIFO_STATUS = 0x39,
    ADXL_DATA_FORMAT = 0x0b, ADXL_RATE_800_HZ = 0x0d,
    ADXL_FIFO_STREAM = 0x81, ADXL_IRQ_WATERMARK = 0x02,
    ADXL_IRQ_DATA_READY = 0x80,
};

esp_err_t adxl345_init(void);
esp_err_t adxl345_deinit(void);
esp_err_t adxl345_read_register(uint8_t address, uint8_t *value);
esp_err_t adxl345_write_register(uint8_t address, uint8_t value);
/** Check DEVID, configure in standby, and read back key configuration fields. */
esp_err_t adxl345_configure(void);
/** Read six little-endian bytes in one CS transaction; wait >=5 us afterwards. */
esp_err_t adxl345_read_sample(adxl_sample_t *sample);
/** Discard stale data and restore stream mode while measurement is stopped. */
esp_err_t adxl345_clear_fifo(void);
