#pragma once
#include "FreeRTOS.h"
typedef void *TaskHandle_t;
typedef void (*TaskFunction_t)(void *);
TaskHandle_t xTaskGetCurrentTaskHandle(void);
void vTaskNotifyGiveFromISR(TaskHandle_t task, BaseType_t *woken);
uint32_t ulTaskNotifyTake(BaseType_t clear, TickType_t wait);
void vTaskDelete(TaskHandle_t task);
BaseType_t xTaskCreatePinnedToCore(TaskFunction_t function, const char *name,
    uint32_t stack, void *argument, UBaseType_t priority, TaskHandle_t *handle, int core);
