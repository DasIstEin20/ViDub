# ViDubb – 2025 GPU-ready Installation Guide

This guide replaces legacy setup instructions with a single, foolproof workflow for Windows 11 + WSL2 (Ubuntu 24.04) users running NVIDIA RTX GPUs (e.g., RTX 3080) and developers on native Linux. The steps below deliver a CUDA 12-ready environment with TensorFlow, PyTorch, Whisper, and all ViDubb dependencies configured in under 10 minutes.

---

## 📦 What you get
- ✅ Automatic WSL2 + CUDA bridge configuration for RTX GPUs
- ✅ Hardened PowerShell bootstrapper that creates `.venv`, installs dependencies, and validates GPU access
- ✅ Native Linux manual workflow with matching package versions
- ✅ Built-in CPU-only fallback and troubleshooting aids

> **Tip:** Every command block includes inline comments so you know exactly what each step is doing.

---

## 1️⃣ Prerequisites

| Platform | Requirement |
|----------|-------------|
| Windows host | Windows 11 23H2+, PowerShell 7.5+, latest NVIDIA RTX driver with CUDA 12.x support |
| GPU | NVIDIA RTX 20xx/30xx/40xx (tested with RTX 3080) |
| WSL | WSL2 with Ubuntu 24.04 LTS |
| Python | 3.10+ inside WSL (Ubuntu 24.04 ships 3.12 by default, which is compatible) |
| Storage | ≥ 15 GB free (CUDA wheels + models) |

**Before you start**
1. Install [PowerShell 7.5+](https://learn.microsoft.com/powershell/scripting/install/installing-powershell) and launch it as **Administrator**.
2. Update your NVIDIA driver from [GeForce](https://www.nvidia.com/en-us/geforce/drivers/) or [Quadro](https://www.nvidia.com/Download/index.aspx) to ensure CUDA 12.x compatibility.
3. Optional but recommended: reboot after driver updates.

---

## 2️⃣ Setup & Dependencies (Windows or WSL)

Clone the repository to a short Windows path (so it mirrors cleanly into WSL) and switch into it:

```powershell
# PowerShell (Windows) – clone the project next to your home directory
cd ~  # Navigate to your Windows home folder
git clone https://github.com/medahmedkrichen/ViDubb.git
cd ViDubb
```

The remaining steps assume you are inside the repository root.

---

## 3️⃣ WSL2 GPU Bridge Setup

Use PowerShell to verify that WSL2 can see your RTX GPU and that CUDA forwarding is active:

```powershell
# 1. Confirm WSL2 is installed and running version 2
wsl --status

# 2. List installed distributions (Ubuntu-24.04 should be present)
wsl --list --verbose

# 3. Check GPU access from within WSL (prompts for Ubuntu password)
wsl -d Ubuntu-24.04 -- nvidia-smi  # Shows RTX GPU if CUDA bridge is healthy
```

If any command fails:
- Run `wsl --install -d Ubuntu-24.04` and reboot.
- Update the WSL kernel with `wsl --update` and reboot.
- Ensure the NVIDIA driver version is ≥ 545 with CUDA 12 support.

---

## 4️⃣ One-Click Installation (Windows)

Use the provided scripts to handle everything—from enabling Windows features to validating GPU access. Both scripts live in `scripts/windows/`.

### `scripts/windows/oneclick.bat`
- Double-click from File Explorer **or** run from PowerShell.
- Detects PowerShell 7+, bypasses execution policy, and launches the bootstrapper.

### `scripts/windows/bootstrap.ps1`
A fully-commented PowerShell 7 script that:
1. Verifies administrative privileges, PowerShell version, and NVIDIA GPU availability.
2. Enables the **VirtualMachinePlatform** and **WSL** Windows features.
3. Installs/updates WSL with Ubuntu 24.04 and forces version 2.
4. Runs `wsl --status` to confirm the CUDA bridge.
5. Installs Ubuntu packages (`python3-venv`, `ffmpeg`, `libsndfile1`, etc.).
6. Creates `.venv`, upgrades `pip`, installs ViDubb + Whisper dependencies, and pulls GPU-accelerated Torch/TensorFlow wheels.
7. Prints a short Python report confirming that both Torch and TensorFlow detect your GPU.

Run it as Administrator from the repo root:

```powershell
# PowerShell 7.5+ (elevated)
.
\scripts\windows\oneclick.bat              # Launches the bootstrapper via PowerShell
# Optional flags:
#   scripts\windows\bootstrap.ps1 -SkipWslInstall   # Skip WSL install if already configured
#   scripts\windows\bootstrap.ps1 -CpuOnly          # Force CPU wheels when no RTX GPU is available
```

When the script finishes you can open Ubuntu (WSL) and activate the environment:

```bash
# Inside Ubuntu 24.04 (WSL2)
cd /mnt/c/Users/<your-user>/ViDubb
source .venv/bin/activate
python -m pip list | head -n 10  # Quick sanity check
```

---

## 5️⃣ Manual Installation (Linux)

Use these steps if you are on native Ubuntu 24.04, Debian derivatives, or prefer to manage the environment manually inside WSL.

```bash
# 1. Update packages and install system dependencies
sudo apt update && sudo apt install -y \  # Refresh package index and install build tools
    python3 python3-venv python3-pip python3-dev \  # Python runtime + headers
    build-essential ffmpeg git libsndfile1          # Media + compilation support

# 2. Clone the repository if you have not already
git clone https://github.com/medahmedkrichen/ViDubb.git
cd ViDubb

# 3. Create an isolated Python environment
python3 -m venv .venv                              # Create .venv in project root
source .venv/bin/activate                          # Activate the environment

# 4. Upgrade pip tooling and install dependencies
python -m pip install --upgrade pip setuptools wheel
pip install --upgrade -r requirements.txt          # Core libraries shipped with ViDubb

# 5a. GPU wheels (default)
pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu122
pip install --upgrade "tensorflow[and-cuda]"       # Installs TensorFlow with CUDA 12.x support

# 5b. CPU fallback (if no NVIDIA GPU is available)
# pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
# pip install --upgrade tensorflow

# 6. Install Whisper for transcription
pip install --upgrade openai-whisper

# 7. Validate the stack
python - <<'PY'
import torch, tensorflow as tf
print("Torch CUDA available:", torch.cuda.is_available())
print("Torch device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")
print("TensorFlow GPUs:", [gpu.name for gpu in tf.config.list_physical_devices('GPU')])
PY
```

---

## 6️⃣ 🔥 Quick Test Run

With the virtual environment activated (`source .venv/bin/activate`), run a short inference pass on a sample video:

```bash
# Copy a test clip into the project (replace with your own .mp4 if desired)
cp videos/sample_input.mp4 /tmp/sample.mp4  # Example only; adjust path as needed

# Launch a minimal transcription + dubbing test (GPU accelerated if available)
python inference.py \                         # Main ViDubb entry point
    --input_video /tmp/sample.mp4 \          # Test video path
    --target_language en \                   # Translate/clone to English
    --voice_clone true \                     # Enable voice cloning
    --whisper_model medium.en                # Medium Whisper model for balance
```

A successful run prints diarization progress, Whisper transcription, and saves output to `results/`.

---

## 7️⃣ Troubleshooting & FAQ

### GPU not detected inside WSL
- Re-run `wsl --update` and reboot Windows.
- Install the latest NVIDIA driver and confirm `nvidia-smi` works on Windows **and** inside WSL.
- Inside WSL, ensure `/usr/lib/wsl/lib/libcuda.so` exists. If not, update WSL again.

### Slow installs or pip timeouts
- Mirror the PyTorch/TensorFlow downloads via `pip install --timeout 600 ...`.
- Set `PIP_EXTRA_INDEX_URL` if you use an internal mirror.

### Switching to CPU-only mode later
- Re-run `scripts/windows/bootstrap.ps1 -CpuOnly` (Windows) or reinstall the CPU wheels manually (Linux snippet above).
- Remove GPU-specific packages with `pip uninstall tensorflow[and-cuda]` and reinstall plain `tensorflow`.

### `.venv` activation problems in WSL
- Ensure the repo lives under `/mnt/c/...` with standard Windows permissions.
- Run `chmod +x scripts/windows/*.ps1` inside WSL if you cloned from Linux and execution bits are missing.

### Bridge connectivity issues between Windows and WSL
- Disable third-party VPNs/firewalls temporarily; they can block Hyper-V networking.
- Run `wsl --shutdown` then relaunch Ubuntu to refresh the interop channel.

---

You are now ready to explore ViDubb with a modern, GPU-accelerated toolchain. Happy dubbing! 🎬
