@echo off
setlocal

REM Attempt to activate a Conda environment if available
if exist "%~dp0..\..\conda.env" (
    call "%~dp0..\..\conda.env" || echo Warning: could not activate conda environment.
) else if exist "%~dp0..\..\venv\Scripts\activate.bat" (
    call "%~dp0..\..\venv\Scripts\activate.bat"
)

python -m pip install -r "%~dp0..\..\requirements.txt" >nul 2>&1
if errorlevel 1 (
    echo Failed to install dependencies. See README for setup instructions.
    pause
    exit /b 1
)

python "%~dp0..\..\app.py"
if errorlevel 1 (
    echo Launch failed. Please review the console output and README.md troubleshooting section.
    pause
    exit /b 1
)

pause
