@echo off
setlocal
set "SCRIPT_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_ROOT%start-all.ps1" %*
exit /b %ERRORLEVEL%
