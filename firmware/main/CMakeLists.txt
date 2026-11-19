idf_component_register(
    SRCS "main.c" "adxl345.c" "acquisition.c" "monitor_protocol.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES esp_driver_spi esp_driver_gpio esp_driver_uart esp_timer esp_rom
)
