param(
    [string]$LockOut = "requirements-lock-win-py310.txt",
    [switch]$PreferExistingTorch
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Write-Host "[ViDub] Repository root: $repoRoot"
Set-Location $repoRoot

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    throw "Python executable not found. Install Python 3.10 (x64) and ensure python.exe is on PATH."
}

$pyVersion = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
$pyParts = $pyVersion.Split('.')
if ([int]$pyParts[0] -lt 3 -or ([int]$pyParts[0] -eq 3 -and [int]$pyParts[1] -lt 10)) {
    throw "Python 3.10 or newer is required. Detected version $pyVersion."
}
Write-Host "[ViDub] Using python.exe ($pyVersion) at $($pythonCmd.Path)"

$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[ViDub] Creating virtual environment in $venvDir"
    & python -m venv $venvDir
}

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment creation failed."
}

$pickScript = Join-Path $repoRoot "scripts\win\pick_env_matrix.py"
if (-not (Test-Path $pickScript)) {
    throw "Matrix solver not found at $pickScript"
}

$lockFullPath = Join-Path $repoRoot $LockOut
$pickArgs = @($pickScript, "--lock-out", $lockFullPath)
if ($PreferExistingTorch) {
    $pickArgs += "--prefer-existing-torch"
}

Write-Host "[ViDub] Resolving dependency matrix..."
& $venvPython @pickArgs
if ($LASTEXITCODE -ne 0) {
    throw "Dependency matrix resolution failed."
}

if (-not (Test-Path $lockFullPath)) {
    throw "Lock file was not created at $lockFullPath"
}
Write-Host "[ViDub] Lock file ready: $lockFullPath"

Write-Host "[ViDub] Upgrading pip"
& $venvPython -m pip install --upgrade pip

Write-Host "[ViDub] Installing locked requirements"
& $venvPython -m pip install -r $lockFullPath

$summaryScript = @'
import shutil
import torch
import numpy
import numba
import tensorflow as tf

print(f"Torch: {torch.__version__}")
print(f"Torch CUDA build: {getattr(torch.version, 'cuda', 'n/a')}")
print(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
print(f"TensorFlow: {tf.__version__}")
print(f"NumPy: {numpy.__version__}")
print(f"Numba: {numba.__version__}")
print(f"FFmpeg on PATH: {bool(shutil.which('ffmpeg'))}")
'@

Write-Host "[ViDub] Environment summary"
$summaryOutput = & $venvPython -c $summaryScript
$summaryOutput -split "`n" | ForEach-Object { Write-Host "  $_" }

Write-Host "[ViDub] Bootstrap complete. Activate the environment with:`n  .venv\Scripts\activate"
