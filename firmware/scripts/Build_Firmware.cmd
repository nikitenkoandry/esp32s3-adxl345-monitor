@echo off
setlocal
cd /d "%~dp0.."
call "scripts\IDF_Environment.cmd"
if errorlevel 1 goto failed
python "%IDF_PATH%\tools\idf.py" -DIDF_TARGET=esp32s3 build
if errorlevel 1 goto failed
echo Ready: build\adxl345_monitor.bin
if /i not "%~1"=="/nopause" pause
exit /b 0
:failed
echo Build failed. Activate ESP-IDF 6.0.2 and check the error above.
if /i not "%~1"=="/nopause" pause
exit /b 1
