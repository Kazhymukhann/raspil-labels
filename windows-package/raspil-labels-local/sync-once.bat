@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=py -3"
%PYTHON% --version >nul 2>&1
if errorlevel 1 set "PYTHON=python"

echo Running one local sync...
%PYTHON% sync_local.py

echo.
echo Done. Labels are in:
echo %CD%\Cutting для ФРЦ\labels
pause
