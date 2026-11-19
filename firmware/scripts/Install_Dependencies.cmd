@echo off
setlocal
cd /d "%~dp0.."
call "scripts\IDF_Environment.cmd"
if errorlevel 1 goto failed
python "%IDF_PATH%\tools\idf.py" --version
if errorlevel 1 goto failed
echo ESP-IDF tools are ready. Run scripts\Build_Firmware.cmd.
if /i not "%~1"=="/nopause" pause
exit /b 0
:failed
echo Install ESP-IDF using Espressif's installer, activate it, and check the error above.
if /i not "%~1"=="/nopause" pause
exit /b 1
