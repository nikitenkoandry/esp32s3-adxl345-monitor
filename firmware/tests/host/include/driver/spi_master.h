/* Only declarations used by the actual adxl345.c driver under test. */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#define SPI2_HOST 2
#define SPI_DMA_DISABLED 0
#define SPI_TRANS_USE_RXDATA 1U
#define SPI_TRANS_USE_TXDATA 2U
typedef void *spi_device_handle_t;
typedef struct {
    int mosi_io_num, miso_io_num, sclk_io_num, quadwp_io_num, quadhd_io_num;
    int data4_io_num, data5_io_num, data6_io_num, data7_io_num, max_transfer_sz;
} spi_bus_config_t;
typedef struct {
    unsigned command_bits, mode;
    int clock_speed_hz, spics_io_num, queue_size;
} spi_device_interface_config_t;
typedef struct {
    uint32_t flags;
    uint16_t cmd;
    size_t length;
    uint8_t tx_data[4], rx_data[4];
    void *rx_buffer;
} spi_transaction_t;
esp_err_t spi_bus_initialize(int host, const spi_bus_config_t *bus, int dma);
esp_err_t spi_bus_add_device(int host, const spi_device_interface_config_t *config,
                             spi_device_handle_t *device);
esp_err_t spi_bus_remove_device(spi_device_handle_t device);
esp_err_t spi_bus_free(int host);
esp_err_t spi_device_polling_transmit(spi_device_handle_t device, spi_transaction_t *t);
