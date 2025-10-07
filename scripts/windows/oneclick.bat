@echo off
setlocal

powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" %*
if errorlevel 1 (
    echo [ViDub] Bootstrap failed.
    exit /b 1
)

if exist "%~dp0..\..\.venv\Scripts\python.exe" (
    "%~dp0..\..\.venv\Scripts\python.exe" app.py
) else (
    python app.py
)
