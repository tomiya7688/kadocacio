@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Development Python is missing: .venv\Scripts\python.exe
  exit /b 2
)
".venv\Scripts\python.exe" -m scripts.tools.godot_runner %*
exit /b %errorlevel%
