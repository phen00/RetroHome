@echo off
rem Builds the Windows release: dist\RetroHome\RetroHome.exe plus a .zip (and a .rar if WinRAR is installed).
rem Double-click this file. Needs Python 3.11-3.13 from python.org (3.12 recommended) and an internet connection.
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PY="
for %%v in (3.12 3.13 3.11) do (
    if not defined PY (
        py -%%v -c "import sys" >nul 2>nul && set "PY=py -%%v"
    )
)
if not defined PY (
    python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/ and run this again.
    goto :fail
)
echo Using: %PY%
%PY% -c "import sys; v=sys.version_info; print('Python', sys.version.split()[0]); sys.exit(0 if (3,9)<=v[:2]<=(3,13) else 1)"
if errorlevel 1 (
    echo.
    echo WARNING: this Python is very new or very old. If the build fails, install Python 3.12 from python.org
    echo          ^(you can keep your current one^) and run this again - it is picked automatically.
    echo.
)

if exist .build-venv rmdir /s /q .build-venv
%PY% -m venv .build-venv || goto :fail
set "VPY=.build-venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip || goto :fail
"%VPY%" -m pip install --only-binary :all: -r packaging\requirements-build.txt || goto :fail
"%VPY%" -m pip install --only-binary :all: py7zr >nul 2>nul

for /f "delims=" %%v in ('call "%VPY%" -c "import retrohome; print(retrohome.__version__)"') do set "VERSION=%%v"
echo Building RetroHome %VERSION% ...

"%VPY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller packaging\RetroHome.spec || goto :fail
copy /y README.md dist\RetroHome\README.md >nul
copy /y CHANGELOG.md dist\RetroHome\CHANGELOG.md >nul

set "NAME=RetroHome-%VERSION%-Windows-x64"
if exist "dist\%NAME%.zip" del "dist\%NAME%.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\RetroHome' -DestinationPath 'dist\%NAME%.zip' -Force" || goto :fail

set "RAR="
if exist "%ProgramFiles%\WinRAR\Rar.exe" set "RAR=%ProgramFiles%\WinRAR\Rar.exe"
if exist "%ProgramFiles(x86)%\WinRAR\Rar.exe" set "RAR=%ProgramFiles(x86)%\WinRAR\Rar.exe"
if defined RAR (
    if exist "dist\%NAME%.rar" del "dist\%NAME%.rar"
    pushd dist
    "%RAR%" a -r -m5 -idq "%NAME%.rar" RetroHome
    popd
)

echo.
echo ============================================================
echo  Done!  dist\RetroHome\RetroHome.exe
echo         dist\%NAME%.zip
if defined RAR echo         dist\%NAME%.rar
if not defined RAR echo  (install WinRAR to also get a .rar - the .zip works everywhere)
echo ============================================================
if not defined CI pause
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
if not defined CI pause
exit /b 1
