@echo off
setlocal
cd /d "%~dp0.."
if "%~1"=="" (
    echo Usage: scripts\Upload_Firmware.cmd COM16
    echo Upload replaces the selected board's firmware. Close other serial programs first.
    exit /b 1
)
call "scripts\IDF_Environment.cmd"
if errorlevel 1 goto failed
python "%IDF_PATH%\tools\idf.py" -DIDF_TARGET=esp32s3 -p "%~1" -b 460800 flash
if errorlevel 1 goto failed
echo Upload finished on %~1. Open the PC monitor at 921600 baud.
if /i not "%~2"=="/nopause" pause
exit /b 0
:failed
echo Upload failed. Check the ESP-IDF environment, selected port, and error above.
if /i not "%~2"=="/nopause" pause
exit /b 1
