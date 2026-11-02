@echo off
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
runtime\python.exe -B run.py start %*
if errorlevel 1 pause
