@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Keep this wrapper ASCII-only so cmd.exe can parse it before code-page setup.
rem Python itself runs in UTF-8 and writes Japanese output after code page 65001 is active.
%SystemRoot%\System32\chcp.com 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "SDL_VIDEODRIVER=dummy"
set "SDL_AUDIODRIVER=dummy"
set "KADOKA_DISABLE_GPU=1"

if exist ".venv\Scripts\python.exe" goto use_venv
set "KADOKA_PYTHON=py"
set "KADOKA_PYTHON_PREFIX=-3"
goto run_evaluator

:use_venv
set "KADOKA_PYTHON=.venv\Scripts\python.exe"
set "KADOKA_PYTHON_PREFIX="

:run_evaluator
if "%~1"=="" goto run_default
"%KADOKA_PYTHON%" %KADOKA_PYTHON_PREFIX% -m scripts.tools.developer_league_evaluator %*
goto finished

:run_default
"%KADOKA_PYTHON%" %KADOKA_PYTHON_PREFIX% -m scripts.tools.developer_league_evaluator --hours 8 --seasons 0 --leagues all --quality PRECISE --processes auto

:finished
set "KADOKA_EXIT_CODE=%ERRORLEVEL%"
if not "%KADOKA_NO_PAUSE%"=="1" pause
exit /b %KADOKA_EXIT_CODE%
