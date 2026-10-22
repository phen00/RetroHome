@echo off
rem RetroHome launcher for Windows. First run installs pygame-ce into a local .venv folder.
setlocal
set DIR=%~dp0
set VENV=%DIR%.venv

if not exist "%VENV%\Scripts\pythonw.exe" (
    echo Setting up RetroHome ^(first run^)...
    where py >nul 2>nul && (py -3 -m venv "%VENV%") || (python -m venv "%VENV%")
    if errorlevel 1 (
        echo.
        echo Python 3 is required. Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^) and run this again.
        pause
        exit /b 1
    )
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r "%DIR%requirements.txt"
)

start "" "%VENV%\Scripts\pythonw.exe" "%DIR%run.py" %*
