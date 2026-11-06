@echo off
rem Called from the repository root inside the launcher's setlocal scope.
rem Match the isolated version check when loading project modules and children.
set "PYTHONHOME="
set "PYTHONPATH="

rem Prefer an explicit executable or the verified side-by-side runtime.
set "VERIFIED_PYTHON=%KADOCACIO_PYTHON%"
if not defined VERIFIED_PYTHON if exist "runtime\venv\Scripts\python.exe" set "VERIFIED_PYTHON=%CD%\runtime\venv\Scripts\python.exe"
if not defined VERIFIED_PYTHON set "VERIFIED_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%VERIFIED_PYTHON%" goto :setup_error

rem Read the version as data inside Python, never interpolate it into cmd.
"%VERIFIED_PYTHON%" -I -c "import sys, sysconfig; from pathlib import Path; expected = Path('.python-version').read_text(encoding='utf-8').strip(); raise SystemExit(0 if sys.version.split()[0] == expected and sys.prefix != sys.base_prefix and not sysconfig.get_config_var('Py_GIL_DISABLED') and getattr(sys, '_is_gil_enabled', lambda: False)() else 1)"
if not "%ERRORLEVEL%"=="0" goto :runtime_mismatch

rem Check the existing trust bundle without modifying dependencies.
"%VERIFIED_PYTHON%" -m scripts.tools.python_trust_check
if not "%ERRORLEVEL%"=="0" goto :setup_error

exit /b 0

:runtime_mismatch
echo The selected executable must be a venv with the required version and standard GIL.
echo Required Python version:
type .python-version

:setup_error
echo The required verified Python could not be used. See README.md for setup instructions.
exit /b 1
