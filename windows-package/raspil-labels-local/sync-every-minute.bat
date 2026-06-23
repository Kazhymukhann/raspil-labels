@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON=py -3"
%PYTHON% --version >nul 2>&1
if errorlevel 1 set "PYTHON=python"

echo Local label sync is running every 60 seconds.
echo Keep this window open.
echo Labels folder: labels inside the Cutting folder
echo.

:loop
echo ------------------------------------------------------------
echo %DATE% %TIME%
%PYTHON% sync_local.py
echo.
echo Waiting 60 seconds...
timeout /t 60 /nobreak >nul
goto loop
