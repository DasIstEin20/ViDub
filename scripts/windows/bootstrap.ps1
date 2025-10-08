<#
    ViDubb WSL2 bootstrap script for Windows 11 (PowerShell 7.5+).
    Run from an elevated PowerShell terminal at the root of the repository.
#>

[CmdletBinding()]
param(
    [switch]$SkipWslInstall,
    [switch]$CpuOnly
)

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run bootstrap.ps1 from an elevated PowerShell session."
}

if ($PSVersionTable.PSVersion -lt [Version]"7.5") {
    throw "PowerShell 7.5 or later is required. Current version: $($PSVersionTable.PSVersion)"
}

Write-Host "[1/6] Checking NVIDIA driver and CUDA runtime on Windows..." -ForegroundColor Cyan
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $nvidia = nvidia-smi.exe --query-gpu=name,driver_version --format=csv,noheader 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Detected GPU: $nvidia" -ForegroundColor Green
    } else {
        Write-Warning "nvidia-smi returned a non-zero exit code. Ensure the latest Game Ready or Studio driver is installed."
    }
} else {
    Write-Warning "nvidia-smi is not available. Install the latest NVIDIA RTX driver with CUDA 12.x support."
}

Write-Host "[2/6] Enabling required Windows features for WSL2 (VirtualMachinePlatform, Microsoft-Windows-Subsystem-Linux)..." -ForegroundColor Cyan
$features = @(
    'VirtualMachinePlatform',
    'Microsoft-Windows-Subsystem-Linux'
)
foreach ($feature in $features) {
    & dism.exe /online /enable-feature /featurename:$feature /all /norestart | Out-Null
}

if (-not $SkipWslInstall) {
    Write-Host "[3/6] Installing or updating WSL with Ubuntu 24.04 as the default distribution..." -ForegroundColor Cyan
    & wsl.exe --update | Out-Null
    & wsl.exe --install -d Ubuntu-24.04 | Out-Null
    & wsl.exe --set-default Ubuntu-24.04 | Out-Null
    & wsl.exe --set-default-version 2 | Out-Null
} else {
    Write-Host "Skipping WSL installation per user request." -ForegroundColor Yellow
}

Write-Host "[4/6] Ensuring the NVIDIA CUDA bridge for WSL2 is active..." -ForegroundColor Cyan
& wsl.exe --status

$repoWindowsPath = (Resolve-Path -LiteralPath '.').Path
$repoWslPath = (& wsl.exe wslpath -a -u "$repoWindowsPath").Trim()

Write-Host "[5/6] Updating Ubuntu packages and installing system dependencies inside WSL (this may prompt for your Ubuntu password)..." -ForegroundColor Cyan
$aptCommands = @'
set -e
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip python3-dev build-essential ffmpeg git libsndfile1
'@
$aptArgs = @('-d','Ubuntu-24.04','--','bash','-lc',$aptCommands)
& wsl.exe @aptArgs

Write-Host "[6/6] Creating the Python virtual environment and installing ViDubb dependencies..." -ForegroundColor Cyan
$installCommands = @'
set -e
cd "${REPO_PATH}"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install --upgrade -r requirements.txt
if [ "${CpuOnly}" = "True" ]; then
    pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
    pip install --upgrade tensorflow
else
    pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu122
    pip install --upgrade "tensorflow[and-cuda]"
fi
pip install --upgrade openai-whisper
python <<'PY'
import sys
import torch
import tensorflow as tf
print('Python version:', sys.version)
print('Torch version:', torch.__version__)
print('Torch CUDA available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('Torch GPU:', torch.cuda.get_device_name(0))
print('TensorFlow version:', tf.__version__)
print('TensorFlow GPUs:', [gpu.name for gpu in tf.config.list_physical_devices('GPU')])
PY
'@
$cpuValue = $CpuOnly.IsPresent.ToString()
$installArgs = @('-d','Ubuntu-24.04','--env',"CpuOnly=$cpuValue",'--env',"REPO_PATH=$repoWslPath",'--','bash','-lc',$installCommands)
& wsl.exe @installArgs

Write-Host "Bootstrap complete! Activate the environment from WSL with: source .venv/bin/activate" -ForegroundColor Green
