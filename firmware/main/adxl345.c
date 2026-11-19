/** @file adxl345.c
 * @brief Native SPI2 register/burst transfers, with hardware-controlled CS.
 * SPI 'polling transmit' waits for a single bus transaction to finish; it does
 * not poll the sensor for new measurements. INT1 schedules all runtime reads.
 * Six-byte bursts and the post-read delay follow the ADXL345 FIFO requirements.
 */
#include "adxl345.h"
#include "board_config.h"
#include "driver/spi_master.h"
#include "esp_rom_sys.h"

static spi_device_handle_t device;

esp_err_t adxl345_init(void)
{
    if (device != NULL) return ESP_ERR_INVALID_STATE;
    const spi_bus_config_t bus = {
        .mosi_io_num = ADXL_PIN_MOSI, .miso_io_num = ADXL_PIN_MISO,
        .sclk_io_num = ADXL_PIN_SCLK, .quadwp_io_num = -1, .quadhd_io_num = -1,
        .data4_io_num = -1, .data5_io_num = -1,
        .data6_io_num = -1, .data7_io_num = -1,
        .max_transfer_sz = 6,
    };
    esp_err_t err = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED);
    if (err != ESP_OK) return err;
    const spi_device_interface_config_t config = {
        .command_bits = 8, .mode = 3, .clock_speed_hz = ADXL_SPI_HZ,
        .spics_io_num = ADXL_PIN_CS, .queue_size = 1,
    };
    err = spi_bus_add_device(SPI2_HOST, &config, &device);
    if (err != ESP_OK) {
        (void)spi_bus_free(SPI2_HOST);
        device = NULL;
    }
    return err;
}

esp_err_t adxl345_deinit(void)
{
    if (device == NULL) return ESP_ERR_INVALID_STATE;
    esp_err_t err = spi_bus_remove_device(device);
    if (err != ESP_OK) return err;
    device = NULL;
    return spi_bus_free(SPI2_HOST);
}

esp_err_t adxl345_write_register(uint8_t address, uint8_t value)
{
    if (device == NULL) return ESP_ERR_INVALID_STATE;
    spi_transaction_t transaction = {
        .cmd = address & 0x3f, .length = 8,
        .flags = SPI_TRANS_USE_TXDATA, .tx_data = {value},
    };
    return spi_device_polling_transmit(device, &transaction);
}

esp_err_t adxl345_read_register(uint8_t address, uint8_t *value)
{
    if (value == NULL) return ESP_ERR_INVALID_ARG;
    if (device == NULL) return ESP_ERR_INVALID_STATE;
    spi_transaction_t transaction = {
        .cmd = 0x80 | (address & 0x3f), .length = 8,
        .flags = SPI_TRANS_USE_RXDATA,
    };
    const esp_err_t err = spi_device_polling_transmit(device, &transaction);
    if (err == ESP_OK) *value = transaction.rx_data[0];
    return err;
}

esp_err_t adxl345_read_sample(adxl_sample_t *sample)
{
    if (sample == NULL) return ESP_ERR_INVALID_ARG;
    if (device == NULL) return ESP_ERR_INVALID_STATE;
    uint8_t bytes[6] = {0};
    spi_transaction_t transaction = {
        .cmd = 0xc0 | ADXL_REG_DATAX0, .length = 48, .rx_buffer = bytes,
    };
    const esp_err_t err = spi_device_polling_transmit(device, &transaction);
    esp_rom_delay_us(FIFO_POP_DELAY_US);
    if (err != ESP_OK) return err;
    sample->x = (int16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8));
    sample->y = (int16_t)((uint16_t)bytes[2] | ((uint16_t)bytes[3] << 8));
    sample->z = (int16_t)((uint16_t)bytes[4] | ((uint16_t)bytes[5] << 8));
    return ESP_OK;
}

esp_err_t adxl345_configure(void)
{
    uint8_t value;
    esp_err_t err = adxl345_read_register(ADXL_REG_DEVID, &value);
    if (err != ESP_OK) return err;
    if (value != 0xe5) return ESP_ERR_INVALID_RESPONSE;
    const uint8_t settings[][2] = {
        {ADXL_REG_POWER_CTL, 0}, {ADXL_REG_INT_ENABLE, 0},
        {ADXL_REG_INT_MAP, 0}, {ADXL_REG_FIFO_CTL, 0},
        {ADXL_REG_OFSX, 0}, {ADXL_REG_OFSY, 0}, {ADXL_REG_OFSZ, 0},
        {ADXL_REG_DATA_FORMAT, ADXL_DATA_FORMAT},
        {ADXL_REG_BW_RATE, ADXL_RATE_800_HZ},
        {ADXL_REG_FIFO_CTL, ADXL_FIFO_STREAM},
    };
    for (size_t i = 0; i < sizeof(settings) / sizeof(settings[0]); ++i) {
        err = adxl345_write_register(settings[i][0], settings[i][1]);
        if (err != ESP_OK) return err;
    }
    const uint8_t checks[][2] = {
        {ADXL_REG_DATA_FORMAT, ADXL_DATA_FORMAT},
        {ADXL_REG_BW_RATE, ADXL_RATE_800_HZ},
        {ADXL_REG_FIFO_CTL, ADXL_FIFO_STREAM}, {ADXL_REG_POWER_CTL, 0},
    };
    for (size_t i = 0; i < sizeof(checks) / sizeof(checks[0]); ++i) {
        err = adxl345_read_register(checks[i][0], &value);
        if (err != ESP_OK) return err;
        if (value != checks[i][1]) return ESP_ERR_INVALID_RESPONSE;
    }
    return ESP_OK;
}

esp_err_t adxl345_clear_fifo(void)
{
    esp_err_t err = adxl345_write_register(ADXL_REG_FIFO_CTL, 0);
    if (err != ESP_OK) return err;
    adxl_sample_t discard;
    err = adxl345_read_sample(&discard);
    if (err != ESP_OK) return err;
    uint8_t source;
    err = adxl345_read_register(ADXL_REG_INT_SOURCE, &source);
    if (err != ESP_OK) return err;
    return adxl345_write_register(ADXL_REG_FIFO_CTL, ADXL_FIFO_STREAM);
}
