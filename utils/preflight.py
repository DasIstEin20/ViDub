"""Pre-flight checks for the ViDub one-click experience."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv


@dataclass
class CheckResult:
    name: str
    status: str  # "ok", "warning", "error"
    message: str


def _run_command_available(command: str) -> bool:
    return shutil.which(command) is not None


def check_ffmpeg() -> CheckResult:
    if _run_command_available("ffmpeg"):
        return CheckResult("FFmpeg", "ok", "FFmpeg executable found in PATH.")
    return CheckResult(
        "FFmpeg",
        "error",
        "FFmpeg is not installed or not visible in PATH. Install it and ensure the ffmpeg command works.",
    )


def check_ffprobe() -> CheckResult:
    if _run_command_available("ffprobe"):
        return CheckResult("FFprobe", "ok", "FFprobe executable found in PATH.")
    return CheckResult(
        "FFprobe",
        "warning",
        "FFprobe is missing. Embedded subtitle detection will be disabled.",
    )


def check_torch_cuda() -> CheckResult:
    try:
        import torch

        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            return CheckResult("CUDA", "ok", f"CUDA available ({device_count} device(s)).")
        return CheckResult("CUDA", "warning", "PyTorch is installed but CUDA devices were not detected.")
    except Exception as exc:  # pylint: disable=broad-except
        return CheckResult("PyTorch", "error", f"PyTorch not available: {exc}")


def check_required_models() -> List[CheckResult]:
    checks: List[CheckResult] = []
    wav2lip_path = Path("Wav2Lip/checkpoints/wav2lip_gan.pth")
    if wav2lip_path.exists():
        checks.append(CheckResult("Wav2Lip", "ok", "Wav2Lip checkpoint detected."))
    else:
        checks.append(
            CheckResult(
                "Wav2Lip",
                "warning",
                "Wav2Lip checkpoint not found. Download checkpoints/wav2lip_gan.pth into the Wav2Lip folder.",
            )
        )

    face_detector = Path("Wav2Lip/face_detection/detection/s3fd.pth")
    if face_detector.exists():
        checks.append(CheckResult("Face detector", "ok", "S3FD face detector weights present."))
    else:
        checks.append(
            CheckResult(
                "Face detector",
                "warning",
                "S3FD face detector weights not found. Run tools/download_models.py or follow README instructions.",
            )
        )
    return checks


def check_env_tokens() -> CheckResult:
    load_dotenv()
    required_tokens = ["GROQ_API_KEY", "HUGGINGFACEHUB_API_TOKEN"]
    missing = [name for name in required_tokens if not os.getenv(name)]
    if missing:
        return CheckResult(
            "API tokens",
            "warning",
            f"Missing tokens in .env: {', '.join(missing)}. Some features (translation, diarization) may fail.",
        )
    return CheckResult("API tokens", "ok", "Required API tokens available in environment or .env file.")


def run_preflight_checks() -> List[CheckResult]:
    """Run all pre-flight checks and return their results."""

    results: List[CheckResult] = [check_ffmpeg(), check_ffprobe(), check_torch_cuda(), check_env_tokens()]
    results.extend(check_required_models())
    return results


def format_preflight_report(results: Iterable[CheckResult]) -> str:
    lines: List[str] = []
    status_emoji = {"ok": "✅", "warning": "⚠️", "error": "❌"}
    for res in results:
        emoji = status_emoji.get(res.status, "•")
        lines.append(f"{emoji} {res.name}: {res.message}")
    return "\n".join(lines)
