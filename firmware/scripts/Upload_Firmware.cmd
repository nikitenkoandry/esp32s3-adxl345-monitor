@echo off
setlocal
cd /d "%~dp0.."
if "%~1"=="" (
    echo Usage: scripts\Upload_Firmware.cmd COM16
    echo Choose the port of the board you intend to flash. Upload replaces its firmware.
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" goto failed
if not defined PLATFORMIO_CORE_DIR set "PLATFORMIO_CORE_DIR=%CD%\.pio\core"
".venv\Scripts\python.exe" -m platformio run -e esp32s3_adxl345 -t upload --upload-port "%~1"
if errorlevel 1 goto failed
echo Upload finished on %~1. Open the monitor at 921600 baud.
if /i not "%~2"=="/nopause" pause
exit /b 0
:failed
echo Upload failed. Close serial monitors, check the port, and review the error above.
if /i not "%~2"=="/nopause" pause
exit /b 1
