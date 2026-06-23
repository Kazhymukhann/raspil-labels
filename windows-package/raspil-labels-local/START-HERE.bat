@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Raspil labels - auto sync

echo.
echo ================================================
echo  Raspil labels
echo ================================================
echo.

call :find_python
if not defined PYTHON (
    echo Python was not found. Trying to install Python 3.12 with winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo.
        echo winget was not found. Trying direct download from python.org...
        call :download_python
    ) else (
        winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    )
    call :find_python
)

if not defined PYTHON (
    echo.
    echo Python is still not available. Close this window and run START-HERE.bat again.
    pause
    exit /b 1
)

echo Python: %PYTHON%
echo.
echo Installing/updating Python packages...
%PYTHON% -m ensurepip --upgrade >nul 2>&1
%PYTHON% -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto :pip_error
%PYTHON% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :pip_error

echo.
echo Ready. The program will watch XML changes and update labels automatically.
echo.
echo Put XML files into the Cutting folder inside this package.
echo.
echo Labels will be generated in the labels folder inside that Cutting folder.
echo.
echo Keep this window open on the machine computer.
echo To stop syncing, close this window.
echo.

%PYTHON% sync_local.py --watch
pause

:pip_error
echo.
echo Python package installation failed.
echo Check the internet connection and run START-HERE.bat again.
pause
exit /b 1

:find_python
set "PYTHON="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
    exit /b 0
)
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python"
    exit /b 0
)
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYTHON="%LocalAppData%\Programs\Python\Python312\python.exe""
    exit /b 0
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set "PYTHON="%ProgramFiles%\Python312\python.exe""
    exit /b 0
)
exit /b 0

:download_python
set "PYTHON_INSTALLER=%TEMP%\python-3.12.10-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
echo Downloading Python installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"
if errorlevel 1 goto :download_failed
echo Installing Python for this Windows user...
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
if errorlevel 1 goto :download_failed
exit /b 0

:download_failed
echo.
echo Automatic Python download/install failed.
echo The Python download page will open now.
echo Click "Download Windows installer (64-bit)", install Python,
echo enable "Add python.exe to PATH", then run START-HERE.bat again.
start https://www.python.org/downloads/windows/
pause
exit /b 1
