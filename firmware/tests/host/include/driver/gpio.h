#pragma once
#include "esp_err.h"
#define GPIO_INTR_POSEDGE 1
typedef void (*gpio_isr_t)(void *);
esp_err_t gpio_set_intr_type(int pin, int type);
esp_err_t gpio_isr_handler_add(int pin, gpio_isr_t handler, void *argument);
esp_err_t gpio_intr_disable(int pin);
esp_err_t gpio_isr_handler_remove(int pin);
esp_err_t gpio_install_isr_service(int flags);
void gpio_uninstall_isr_service(void);
