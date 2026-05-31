@echo off
setlocal
set "NAPCAT_ROOT=D:\project\qqbot\tools\napcat\onekey\NapCat.44498.Shell"
set "SCRIPT_ROOT=D:\project\qqbot\scripts"

if not exist "%NAPCAT_ROOT%\NapCatWinBootMain.exe" (
    echo NapCat package not found: %NAPCAT_ROOT%
    exit /b 1
)

wt.exe -d "%NAPCAT_ROOT%" powershell.exe -NoExit -ExecutionPolicy Bypass -File "%SCRIPT_ROOT%\start_napcat_onekey.ps1"
