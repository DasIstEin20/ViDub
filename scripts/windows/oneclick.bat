@echo off
REM Simple wrapper to launch the PowerShell bootstrapper with execution policy bypassed.
setlocal
set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%bootstrap.ps1

if not exist "%PS_SCRIPT%" (
    echo [ViDubb] bootstrap.ps1 not found. Please check your checkout.
    exit /b 1
)

REM Elevate to PowerShell 7 if available, otherwise fall back to default pwsh.
for %%P in (pwsh.exe powershell.exe) do (
    where %%P >nul 2>nul
    if not errorlevel 1 (
        set PWSH=%%P
        goto :found
    )
)
echo [ViDubb] PowerShell 7.5+ is required. Install from https://aka.ms/powershell.
exit /b 1

:found
%PWSH% -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
endlocal
