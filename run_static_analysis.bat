@echo off
setlocal
cd /d "%~dp0"

rem Match the isolated version check when loading project modules and children.
set "PYTHONHOME="
set "PYTHONPATH="

rem Prefer an explicit executable or the verified side-by-side runtime.
set "CHECK_PYTHON=%KADOCACIO_PYTHON%"
if not defined CHECK_PYTHON if exist "runtime\venv\Scripts\python.exe" set "CHECK_PYTHON=%CD%\runtime\venv\Scripts\python.exe"
if not defined CHECK_PYTHON set "CHECK_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%CHECK_PYTHON%" goto :setup_error

rem Read the version as data inside Python, never interpolate it into cmd.
"%CHECK_PYTHON%" -I -c "import sys, sysconfig; from pathlib import Path; expected = Path('.python-version').read_text(encoding='utf-8').strip(); raise SystemExit(0 if sys.version.split()[0] == expected and sys.prefix != sys.base_prefix and not sysconfig.get_config_var('Py_GIL_DISABLED') and getattr(sys, '_is_gil_enabled', lambda: False)() else 1)"
if not "%ERRORLEVEL%"=="0" goto :runtime_mismatch

rem Check the existing trust bundle without modifying dependencies.
"%CHECK_PYTHON%" -m scripts.tools.python_trust_check
if not "%ERRORLEVEL%"=="0" goto :setup_error

"%CHECK_PYTHON%" -m scripts.tools.static_analysis.run_all %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo Static analysis failed with exit code %EXIT_CODE%.
exit /b %EXIT_CODE%

:runtime_mismatch
echo The selected executable must be a venv with the required version and standard GIL.
echo Required Python version:
type .python-version
goto :setup_error

:setup_error
echo The required verified Python could not be used. See README.md for setup instructions.
echo Prepare runtime\venv or set KADOCACIO_PYTHON to the verified python.exe. Existing venvs are kept.
exit /b 1
