@echo off
setlocal
cd /d "%~dp0"

python -m scripts.tools.static_analysis.run_all %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Static analysis failed with exit code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
