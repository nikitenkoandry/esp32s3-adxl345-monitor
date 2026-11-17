@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name ADXL345_Monitor --distpath dist --workpath build\pyinstaller --specpath build ADXL345_Monitor.pyw
if errorlevel 1 goto failed
echo Ready: dist\ADXL345_Monitor.exe
if /i not "%~1"=="/nopause" pause
exit /b 0
:failed
echo Build failed. Run scripts\Install_Dependencies.cmd first and check the error above.
if /i not "%~1"=="/nopause" pause
exit /b 1
