@echo off
setlocal
set "SCRIPT_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_ROOT%update-all.ps1" %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
