/** @file board_config.h
 * @brief Fixed wiring and acquisition settings, shared with the host C tests.
 * Use 3.3 V logic and a common ground. UART0 connects to the USB-UART bridge;
 * native USB CDC is not used. A 16 MB ESP32-S3 flash layout is configured.
 */
#pragma once

#define ADXL_PIN_SCLK       12
#define ADXL_PIN_MOSI       11
#define ADXL_PIN_MISO       13
#define ADXL_PIN_CS         10
#define ADXL_PIN_INT1        4
#define MONITOR_UART_TX     43
#define MONITOR_UART_RX     44
#define ADXL_SPI_HZ    2000000
#define MONITOR_BAUD    921600
#define SAMPLE_QUEUE_LENGTH 512
#define WARMUP_SAMPLES       16
#define IRQ_WAIT_MS         100
#define FIFO_POP_DELAY_US     5
#define MONITOR_LINE_CAPACITY 512
