@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install.ps1 %*
if errorlevel 1 echo No se ha completado la instalacion. Revisa el mensaje anterior.
pause
