@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1

rem Validate the runtime before launching the tool.
call scripts\tools\verify_python.bat
if not "%ERRORLEVEL%"=="0" exit /b 1

rem Keep the established load-test settings scoped to this launch.
set "KADOKA_STRESS_MATCHES=90"
set "KADOKA_STRESS_SPEED=1"
set "KADOKA_STRESS_SECONDS=30"
"%VERIFIED_PYTHON%" -m scripts.tools.league_stress_test

:finished
rem Preserve the tool exit status across an optional interactive pause.
set "TOOL_EXIT_CODE=%ERRORLEVEL%"
if not defined CI if not "%KADOKA_NO_PAUSE%"=="1" pause
exit /b %TOOL_EXIT_CODE%
