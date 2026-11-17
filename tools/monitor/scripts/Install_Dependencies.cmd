@echo off
setlocal
cd /d "%~dp0.."
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto failed
python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import tkinter, serial; print('Tkinter and pySerial are available.')"
if errorlevel 1 goto failed
echo Ready. Run scripts\Start_Monitor.cmd or scripts\Start_3D_Demo.cmd.
if /i not "%~1"=="/nopause" pause
exit /b 0
:failed
echo Setup failed. Python 3.10+ with Tkinter and internet access are required.
if /i not "%~1"=="/nopause" pause
exit /b 1
