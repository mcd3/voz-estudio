@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
runtime\python.exe -B run.py stop
pause
