@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: start_task.bat ISSUE_NUMBER
  exit /b 2
)
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" -m scripts.tools.context_pack %~1
