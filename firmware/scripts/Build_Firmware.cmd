@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" goto failed
if not defined PLATFORMIO_CORE_DIR set "PLATFORMIO_CORE_DIR=%CD%\.pio\core"
".venv\Scripts\python.exe" -m platformio run -e esp32s3_adxl345
if errorlevel 1 goto failed
echo Ready: .pio\build\esp32s3_adxl345\firmware.bin
if /i not "%~1"=="/nopause" pause
exit /b 0
:failed
echo Build failed. Run scripts\Install_Dependencies.cmd first and check the error above.
if /i not "%~1"=="/nopause" pause
exit /b 1
