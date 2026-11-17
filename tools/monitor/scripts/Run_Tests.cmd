@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
if /i not "%~1"=="/nopause" pause
exit /b 0
:failed
echo Tests failed. Run scripts\Install_Dependencies.cmd first and check the error above.
if /i not "%~1"=="/nopause" pause
exit /b 1
