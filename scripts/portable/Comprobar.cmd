@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
runtime\python.exe -B verify.py --full --libraries
pause
