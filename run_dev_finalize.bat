@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1

rem Validate the runtime before launching the tool.
call scripts\tools\verify_python.bat
if not "%ERRORLEVEL%"=="0" exit /b 1

"%VERIFIED_PYTHON%" -m scripts.tools.git_workflow %*
exit /b %ERRORLEVEL%
