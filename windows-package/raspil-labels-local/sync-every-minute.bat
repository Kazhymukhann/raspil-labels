@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=py -3"
%PYTHON% --version >nul 2>&1
if errorlevel 1 set "PYTHON=python"

echo Local label sync watch mode is running.
echo Keep this window open.
echo Labels folder: labels inside the Cutting folder
echo.

%PYTHON% sync_local.py --watch
pause
