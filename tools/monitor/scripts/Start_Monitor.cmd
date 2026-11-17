@echo off
setlocal
cd /d "%~dp0.."
if exist "dist\ADXL345_Monitor.exe" (
    start "" "%CD%\dist\ADXL345_Monitor.exe" %*
    exit /b 0
)
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run scripts\Install_Dependencies.cmd first.
    pause
    exit /b 1
)
start "" "%CD%\.venv\Scripts\pythonw.exe" "%CD%\ADXL345_Monitor.pyw" %*
