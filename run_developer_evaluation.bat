@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1

rem Validate the runtime before launching the tool.
call scripts\tools\verify_python.bat
if not "%ERRORLEVEL%"=="0" exit /b 1

rem Keep this wrapper ASCII-only so cmd.exe can parse it before code-page setup.
rem Python itself runs in UTF-8 and writes Japanese output after code page 65001 is active.
%SystemRoot%\System32\chcp.com 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "SDL_VIDEODRIVER=dummy"
set "SDL_AUDIODRIVER=dummy"
set "KADOKA_DISABLE_GPU=1"

rem An explicit argument list replaces the default unattended run.
if "%~1"=="" goto :run_default
"%VERIFIED_PYTHON%" -m scripts.tools.developer_league_evaluator %*
goto :finished

:run_default
"%VERIFIED_PYTHON%" -m scripts.tools.developer_league_evaluator --hours 8 --seasons 0 --leagues all --quality PRECISE --processes auto

:finished
rem Preserve the tool exit status across an optional interactive pause.
set "TOOL_EXIT_CODE=%ERRORLEVEL%"
if not defined CI if not "%KADOKA_NO_PAUSE%"=="1" pause
exit /b %TOOL_EXIT_CODE%
