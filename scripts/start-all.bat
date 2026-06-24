@echo off
setlocal
set "SCRIPT_ROOT=%~dp0"
for %%I in ("%SCRIPT_ROOT%..") do set "WORKSPACE_ROOT=%%~fI"
set "RUNTIME_SCRIPT=%WORKSPACE_ROOT%\tools\runtime-scripts\start-all.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RUNTIME_SCRIPT%" -Target astrbot -SkipInstall -AstrBotProfile both -FeatureMode full %*
set "START_ALL_EXIT_CODE=%ERRORLEVEL%"
if not "%START_ALL_EXIT_CODE%"=="0" (
    echo Press any key to close this window . . .
    pause >nul
)
exit /b %START_ALL_EXIT_CODE%
