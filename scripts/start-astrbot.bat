@echo off
setlocal
set "SCRIPT_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_ROOT%start-all.ps1" -Target astrbot -SkipInstall -AstrBotProfile both -FeatureMode full %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
