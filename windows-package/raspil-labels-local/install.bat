@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=py -3"
%PYTHON% --version >nul 2>&1
if errorlevel 1 set "PYTHON=python"

echo Installing Python dependencies...
%PYTHON% -m pip install --upgrade pip
%PYTHON% -m pip install -r requirements.txt

echo.
echo Done. You can now run sync-once.bat or sync-every-minute.bat
pause
