@echo off
cd /d "%~dp0"
set KADOKA_STRESS_MATCHES=90
set KADOKA_STRESS_SPEED=1
set KADOKA_STRESS_SECONDS=30
.venv\Scripts\python.exe -m scripts.tools.league_stress_test
pause
