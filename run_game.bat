@echo off
cd /d "%~dp0"
set "PYTHON_CMD=py"
where py >nul 2>nul
if errorlevel 1 set "PYTHON_CMD=python"

if not exist ".venv\Scripts\python.exe" (
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :setup_error
)

.venv\Scripts\python.exe -c "import pygame" >nul 2>nul
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :setup_error
)

.venv\Scripts\python.exe main.py
if errorlevel 1 goto :runtime_error
exit /b 0

:runtime_error
echo.
echo The game stopped because an error occurred. Please copy the traceback shown above.
pause
exit /b 1

:setup_error
echo.
echo Python or the required packages could not be prepared. Check Python 3 and your internet connection.
pause
exit /b 1
