@echo off
setlocal
cd /d "%~dp0"

rem Prefer an explicit executable or the verified side-by-side runtime.
set "GAME_PYTHON=%KADOCACIO_PYTHON%"
if not defined GAME_PYTHON if exist "runtime\venv\Scripts\python.exe" set "GAME_PYTHON=%CD%\runtime\venv\Scripts\python.exe"
if not defined GAME_PYTHON set "GAME_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%GAME_PYTHON%" goto :setup_error

rem Read the version as data inside Python, never interpolate it into cmd.
"%GAME_PYTHON%" -I -c "import sys, sysconfig; from pathlib import Path; expected = Path('.python-version').read_text(encoding='utf-8').strip(); raise SystemExit(0 if sys.version.split()[0] == expected and sys.prefix != sys.base_prefix and not sysconfig.get_config_var('Py_GIL_DISABLED') and getattr(sys, '_is_gil_enabled', lambda: False)() else 1)"
if not "%ERRORLEVEL%"=="0" goto :runtime_mismatch

rem Keep native exit checks outside parenthesized blocks, including negative codes.
"%GAME_PYTHON%" -m scripts.tools.python_trust_check >nul 2>nul
if "%ERRORLEVEL%"=="0" goto :check_pygame
"%GAME_PYTHON%" -m pip --isolated --disable-pip-version-check --cache-dir "runtime\pip-cache" install --upgrade --no-deps --require-hashes -r requirements-bootstrap.txt
if not "%ERRORLEVEL%"=="0" goto :setup_error
"%GAME_PYTHON%" -m scripts.tools.python_trust_check
if not "%ERRORLEVEL%"=="0" goto :setup_error

:check_pygame
"%GAME_PYTHON%" -c "import pygame" >nul 2>nul
if "%ERRORLEVEL%"=="0" goto :run_game
"%GAME_PYTHON%" -m pip --isolated --cache-dir "runtime\pip-cache" install -r requirements.txt
if not "%ERRORLEVEL%"=="0" goto :setup_error

:run_game
"%GAME_PYTHON%" main.py %*
if not "%ERRORLEVEL%"=="0" goto :runtime_error
exit /b 0

:runtime_error
echo.
echo The game stopped because an error occurred. Please copy the traceback shown above.
if not defined CI pause
exit /b 1

:runtime_mismatch
echo The selected executable must be a venv with the required version and standard GIL.
echo Required Python version:
type .python-version
"%GAME_PYTHON%" -I -c "import sys; print('Selected Python version:', sys.version.split()[0])"
goto :setup_error

:setup_error
echo.
echo The required verified Python could not be used. See README.md for setup instructions.
echo Prepare runtime\venv or set KADOCACIO_PYTHON to the verified python.exe. Existing venvs are kept.
if not defined CI pause
exit /b 1
