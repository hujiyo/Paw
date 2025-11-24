@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PAW_DIR=%SCRIPT_DIR%.."
set "VENV_DIR=%PAW_DIR%\paw_env"

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Error: Virtual environment not found
    pause
    exit /b 1
)

if not exist "%PAW_DIR%\paw.py" (
    echo Error: paw.py not found
    pause
    exit /b 1
)

cd /d "%PAW_DIR%"
call "%VENV_DIR%\Scripts\activate.bat"
python paw.py %*

endlocal
