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


def _parse_major_minor(version_string: str) -> tuple[int, int]:
    parts: List[int] = []
    for piece in version_string.split('.'):
        digits = ''.join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
        if len(parts) == 2:
            break
    while len(parts) < 2:
        parts.append(0)
    return parts[0], parts[1]


def check_ffmpeg() -> CheckResult:
    if _run_command_available("ffmpeg"):
        return CheckResult("FFmpeg", "ok", "FFmpeg executable found in PATH.")
    return CheckResult(
        "FFmpeg",
        "warning",
        "FFmpeg is not installed or not visible in PATH. Install it to enable full audio/video processing.",
    )


def check_ffprobe() -> CheckResult:
    if _run_command_available("ffprobe"):
        return CheckResult("FFprobe", "ok", "FFprobe executable found in PATH.")
    return CheckResult(
        "FFprobe",
        "warning",
        "FFprobe is missing. Embedded subtitle detection will be disabled.",
    )


def check_torch_environment() -> List[CheckResult]:
    results: List[CheckResult] = []
    try:
        import torch  # type: ignore
    except Exception as exc:  # pylint: disable=broad-except
        return [CheckResult("PyTorch", "error", f"Failed to import PyTorch: {exc}")]

    cuda_build = getattr(getattr(torch, "version", None), "cuda", "n/a")
    results.append(CheckResult("PyTorch", "ok", f"torch {torch.__version__} (CUDA build: {cuda_build})"))

    try:
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            results.append(CheckResult("CUDA availability", "ok", f"torch.cuda.is_available() -> True ({device_count} device(s))"))
        else:
            results.append(
                CheckResult(
                    "CUDA availability",
                    "warning",
                    "torch.cuda.is_available() -> False. The app will run on CPU unless a GPU is accessible.",
                )
            )
    except Exception as exc:  # pylint: disable=broad-except
        results.append(CheckResult("CUDA availability", "warning", f"Could not query CUDA devices: {exc}"))
    return results


def check_tensorflow_environment() -> List[CheckResult]:
    try:
        import tensorflow as tf  # type: ignore
    except Exception as exc:  # pylint: disable=broad-except
        return [CheckResult("TensorFlow", "error", f"Failed to import TensorFlow: {exc}")]
    return [CheckResult("TensorFlow", "ok", f"tensorflow {tf.__version__}")]


def check_numpy_numba() -> List[CheckResult]:
    results: List[CheckResult] = []
    try:
        import numpy as np  # type: ignore
    except Exception as exc:  # pylint: disable=broad-except
        return [CheckResult("NumPy", "error", f"Failed to import NumPy: {exc}")]

    results.append(CheckResult("NumPy", "ok", f"numpy {np.__version__}"))

    try:
        import numba  # type: ignore
    except Exception as exc:  # pylint: disable=broad-except
        results.append(CheckResult("Numba", "error", f"Failed to import Numba: {exc}"))
        return results

    results.append(CheckResult("Numba", "ok", f"numba {numba.__version__}"))

    major, minor = _parse_major_minor(np.__version__)
    if (major, minor) >= (2, 0) and numba.__version__.startswith("0.60.0"):
        results.append(
            CheckResult(
                "NumPy/Numba compatibility",
                "warning",
                "NumPy >= 2.0 detected with numba 0.60.0. Downgrade NumPy to < 2.0 for GPU acceleration to remain stable.",
            )
        )
    return results


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

    results: List[CheckResult] = []
    results.extend(check_torch_environment())
    results.extend(check_tensorflow_environment())
    results.extend(check_numpy_numba())
    results.append(check_ffmpeg())
    results.append(check_ffprobe())
    results.append(check_env_tokens())
    results.extend(check_required_models())
    return results


def format_preflight_report(results: Iterable[CheckResult]) -> str:
    lines: List[str] = []
    status_emoji = {"ok": "✅", "warning": "⚠️", "error": "❌"}
    for res in results:
        emoji = status_emoji.get(res.status, "•")
        lines.append(f"{emoji} {res.name}: {res.message}")
    return "\n".join(lines)
