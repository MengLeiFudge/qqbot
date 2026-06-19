@echo off
setlocal
set "SCRIPT_ROOT=%~dp0"
for %%I in ("%SCRIPT_ROOT%..") do set "WORKSPACE_ROOT=%%~fI"
set "RUNTIME_SCRIPT=%WORKSPACE_ROOT%\tools\runtime-scripts\update-all.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUNTIME_SCRIPT%" %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
