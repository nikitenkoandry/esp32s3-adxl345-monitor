@echo off
rem Called from another helper under its setlocal environment.
if not defined IDF_PATH (
    echo ESP-IDF is not activated. Open an ESP-IDF terminal or set IDF_PATH to its installation folder.
    echo This project is tested with ESP-IDF 6.0.2. Arduino and PlatformIO are not required.
    exit /b 1
)
if not exist "%IDF_PATH%\export.bat" (
    echo Cannot find export.bat under IDF_PATH. Select a complete ESP-IDF installation.
    exit /b 1
)
call "%IDF_PATH%\export.bat"
exit /b %errorlevel%
