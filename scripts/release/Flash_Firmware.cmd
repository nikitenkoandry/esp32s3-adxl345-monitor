@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" goto usage
if /i "%~1"=="--check" goto check

rem Validate the COM name and image hashes before installing dependencies.
python flash_firmware.py "%~1" --check
if errorlevel 1 goto failed
if not exist ".flash-venv\Scripts\python.exe" (
    python -m venv .flash-venv
    if errorlevel 1 goto failed
)
".flash-venv\Scripts\python.exe" -c "import esptool; raise SystemExit(esptool.__version__ != '5.3.1')" >nul 2>&1
if errorlevel 1 (
    ".flash-venv\Scripts\python.exe" -m pip install -r requirements-flash.txt
    if errorlevel 1 goto failed
)
".flash-venv\Scripts\python.exe" flash_firmware.py "%~1"
if errorlevel 1 goto failed
exit /b 0

:check
python flash_firmware.py --check
exit /b %errorlevel%

:usage
echo Usage: Flash_Firmware.cmd COM16
echo Check images without accessing hardware: Flash_Firmware.cmd --check
echo Replace COM16 with your actual USB-UART port. Close the monitor first.
exit /b 2

:failed
echo Firmware upload did not complete. See the error above.
echo Python 3.10+ with pip/venv is required; first-time setup needs internet access.
exit /b 1
