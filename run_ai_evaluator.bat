@echo off
chcp 65001 > nul
cd /d "%~dp0"
set "PYTHON_CMD=py"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
%PYTHON_CMD% -m scripts.tools.ai_evaluator %*
if errorlevel 1 (
  echo.
  echo AI評価を実行できませんでした。
)
pause
