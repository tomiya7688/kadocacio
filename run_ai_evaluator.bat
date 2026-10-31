@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"

rem Match the isolated version check when loading project modules and children.
set "PYTHONHOME="
set "PYTHONPATH="

rem Prefer an explicit executable or the verified side-by-side runtime.
set "EVAL_PYTHON=%KADOCACIO_PYTHON%"
if not defined EVAL_PYTHON if exist "runtime\venv\Scripts\python.exe" set "EVAL_PYTHON=%CD%\runtime\venv\Scripts\python.exe"
if not defined EVAL_PYTHON set "EVAL_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%EVAL_PYTHON%" goto :setup_error

rem Read the version as data inside Python, never interpolate it into cmd.
"%EVAL_PYTHON%" -I -c "import sys, sysconfig; from pathlib import Path; expected = Path('.python-version').read_text(encoding='utf-8').strip(); raise SystemExit(0 if sys.version.split()[0] == expected and sys.prefix != sys.base_prefix and not sysconfig.get_config_var('Py_GIL_DISABLED') and getattr(sys, '_is_gil_enabled', lambda: False)() else 1)"
if not "%ERRORLEVEL%"=="0" goto :runtime_mismatch

rem Check the existing trust bundle without modifying dependencies.
"%EVAL_PYTHON%" -m scripts.tools.python_trust_check
if not "%ERRORLEVEL%"=="0" goto :setup_error

"%EVAL_PYTHON%" -m scripts.tools.ai_evaluator %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo AI evaluation failed with exit code %EXIT_CODE%.
goto :finish

:runtime_mismatch
echo The selected executable must be a venv with the required version and standard GIL.
echo Required Python version:
type .python-version
goto :setup_error

:setup_error
echo The required verified Python could not be used. See README.md for setup instructions.
echo Prepare runtime\venv or set KADOCACIO_PYTHON to the verified python.exe. Existing venvs are kept.
set "EXIT_CODE=1"

:finish
rem Keep the evaluation status across an optional interactive pause.
if not defined CI if not "%KADOKA_NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
