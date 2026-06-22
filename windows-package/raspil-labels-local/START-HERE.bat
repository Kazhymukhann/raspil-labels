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
    echo Python не найден. Пробую установить Python 3.12 через winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo.
        echo На этом Windows нет winget, поэтому автоматическая установка Python невозможна.
        echo Открой страницу https://www.python.org/downloads/windows/
        echo Установи Python 3.10+ и включи галочку "Add python.exe to PATH".
        echo Потом снова открой этот файл START-HERE.bat.
        start https://www.python.org/downloads/windows/
        pause
        exit /b 1
    )
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    call :find_python
)

if not defined PYTHON (
    echo.
    echo Python всё ещё не найден. Закрой это окно и открой START-HERE.bat ещё раз.
    pause
    exit /b 1
)

echo Python: %PYTHON%
echo.
echo Устанавливаю/обновляю библиотеки...
%PYTHON% -m ensurepip --upgrade >nul 2>&1
%PYTHON% -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto :pip_error
%PYTHON% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :pip_error

if not exist "Cutting для ФРЦ" mkdir "Cutting для ФРЦ"

echo.
echo Готово. Теперь программа будет обновлять labels каждую минуту.
echo.
echo XML класть сюда:
echo %CD%\Cutting для ФРЦ
echo.
echo Готовые бирки будут здесь:
echo %CD%\Cutting для ФРЦ\labels
echo.
echo Окно можно держать открытым на компьютере станка.
echo Чтобы остановить - закрыть окно.
echo.

:loop
echo ------------------------------------------------------------
echo %DATE% %TIME%
%PYTHON% sync_local.py
echo.
echo Жду 60 секунд...
timeout /t 60 /nobreak >nul
goto loop

:pip_error
echo.
echo Не получилось установить библиотеки.
echo Проверь интернет и попробуй открыть START-HERE.bat ещё раз.
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
