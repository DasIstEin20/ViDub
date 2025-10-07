#!/usr/bin/env python3
"""Pick a working dependency matrix for Windows + Python 3.10."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"


@dataclass(frozen=True)
class TorchCandidate:
    name: str
    torch: str
    torchvision: str
    torchaudio: str
    cuda_tag: str

    @property
    def extra_index_url(self) -> str:
        return f"https://download.pytorch.org/whl/{self.cuda_tag}"

    def triplet(self) -> Sequence[str]:
        return (self.torch, self.torchvision, self.torchaudio)


TORCH_CANDIDATES: List[TorchCandidate] = [
    TorchCandidate(
        name="Set A (preferred)",
        torch="torch==2.5.1+cu121",
        torchvision="torchvision==0.20.1+cu121",
        torchaudio="torchaudio==2.5.1+cu121",
        cuda_tag="cu121",
    ),
    TorchCandidate(
        name="Set B",
        torch="torch==2.2.2+cu118",
        torchvision="torchvision==0.17.2+cu118",
        torchaudio="torchaudio==2.2.2+cu118",
        cuda_tag="cu118",
    ),
    TorchCandidate(
        name="Set C",
        torch="torch==2.1.2+cu121",
        torchvision="torchvision==0.16.2+cu121",
        torchaudio="torchaudio==2.1.2+cu121",
        cuda_tag="cu121",
    ),
]

SMOKE_IMPORTS = [
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "numpy",
    "numba",
    "onnxruntime",
    "gradio",
    "pysubs2",
    "langdetect",
    "pyannote.audio",
    "speechbrain",
]


def detect_python_environment() -> dict[str, str]:
    info = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "executable": sys.executable,
    }
    if shutil.which("nvidia-smi"):
        try:
            output = subprocess.check_output(["nvidia-smi", "-L"], text=True, stderr=subprocess.STDOUT)
            info["nvidia_smi"] = output.strip()
        except subprocess.CalledProcessError as exc:  # pragma: no cover
            info["nvidia_smi"] = f"nvidia-smi failed: {exc}"
    else:
        info["nvidia_smi"] = "nvidia-smi not detected"
    return info


def _venv_executable(venv_path: Path, executable: str) -> Path:
    if platform.system().lower().startswith("win"):
        return venv_path / "Scripts" / executable
    return venv_path / "bin" / executable


def _run(cmd: Sequence[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    cmd_display = " ".join(cmd)
    print(f"[cmd] {cmd_display}")
    subprocess.run(cmd, check=True, env=env, cwd=cwd)


def _load_requirement_lines() -> List[str]:
    if not REQUIREMENTS_FILE.exists():
        raise FileNotFoundError(f"requirements.txt not found at {REQUIREMENTS_FILE}")
    lines: List[str] = []
    seen = set()
    with REQUIREMENTS_FILE.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            normalized = line.lower()
            if normalized.startswith("tensorflow"):
                continue
            if normalized.startswith("torch") or normalized.startswith("torchvision") or normalized.startswith("torchaudio"):
                continue
            if normalized.startswith("numpy"):
                continue
            if normalized.startswith("numba"):
                continue
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)
    return lines


def _smoke_test(python_exe: Path) -> None:
    module_list = ", ".join(SMOKE_IMPORTS)
    print(f"[smoke] Importing: {module_list}")
    code = "\n".join(
        [
            "import importlib",
            "modules = %r" % SMOKE_IMPORTS,
            "failed = []",
            "for name in modules:",
            "    try:",
            "        importlib.import_module(name)",
            "    except Exception as exc:  # pylint: disable=broad-except",
            "        failed.append(f'{name}: {exc}')",
            "if failed:",
            "    raise SystemExit('Smoke test failed: ' + '; '.join(failed))",
        ]
    )
    _run([str(python_exe), "-c", code])


def _pip_install(pip_exe: Path, packages: Sequence[str], *, extra_args: Sequence[str] | None = None) -> None:
    if not packages:
        return
    args = [str(pip_exe), "install"]
    if extra_args:
        args.extend(extra_args)
    args.extend(packages)
    _run(args)


def try_candidate(candidate: TorchCandidate, lock_out: Path, requirements: Sequence[str]) -> bool:
    print(f"\n=== Trying {candidate.name} ===")
    with tempfile.TemporaryDirectory(prefix="vidub-matrix-") as tmp_dir:
        venv_path = Path(tmp_dir) / "venv"
        print(f"[venv] Creating temporary environment at {venv_path}")
        _run([sys.executable, "-m", "venv", str(venv_path)])
        python_exe = _venv_executable(venv_path, "python.exe" if platform.system().lower().startswith("win") else "python")
        pip_exe = _venv_executable(venv_path, "pip.exe" if platform.system().lower().startswith("win") else "pip")

        _run([str(pip_exe), "install", "--upgrade", "pip", "setuptools", "wheel"])

        torch_packages = list(candidate.triplet())
        _pip_install(pip_exe, torch_packages, extra_args=["--extra-index-url", candidate.extra_index_url])

        _pip_install(pip_exe, ["tensorflow==2.10.1"])
        _pip_install(pip_exe, ["numpy<2.0"])
        _pip_install(pip_exe, ["numba==0.60.0"])
        _pip_install(pip_exe, list(requirements))

        _run([str(pip_exe), "check"])
        _smoke_test(python_exe)

        print("[freeze] Writing lock file")
        freeze_result = subprocess.run(
            [str(pip_exe), "freeze"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        header = [
            "# Generated by scripts/win/pick_env_matrix.py",
            f"# Selected matrix: {candidate.name}",
            f"--extra-index-url {candidate.extra_index_url}",
        ]
        lock_out.parent.mkdir(parents=True, exist_ok=True)
        lock_out.write_text("\n".join(header) + "\n" + freeze_result.stdout)
        print(f"[success] Candidate {candidate.name} succeeded.")
        report = {
            "torch": candidate.torch,
            "torchvision": candidate.torchvision,
            "torchaudio": candidate.torchaudio,
            "tensorflow": "2.10.1",
        }
        print("[report] " + json.dumps(report))
        return True
    return False


def detect_existing_candidate() -> TorchCandidate | None:
    try:
        import torch  # type: ignore
        import torchvision  # type: ignore
        import torchaudio  # type: ignore
    except Exception:  # pragma: no cover - optional path
        return None
    versions = {
        "torch": getattr(torch, "__version__", ""),
        "torchvision": getattr(torchvision, "__version__", ""),
        "torchaudio": getattr(torchaudio, "__version__", ""),
    }
    for cand in TORCH_CANDIDATES:
        if (
            versions["torch"] == cand.torch.split("==", 1)[1]
            and versions["torchvision"] == cand.torchvision.split("==", 1)[1]
            and versions["torchaudio"] == cand.torchaudio.split("==", 1)[1]
        ):
            return cand
    return None


def order_candidates(prefer_existing: bool) -> List[TorchCandidate]:
    candidates = list(TORCH_CANDIDATES)
    if prefer_existing:
        existing = detect_existing_candidate()
        if existing:
            print(f"[info] Prefer existing torch: prioritising {existing.name}")
            candidates = [existing] + [c for c in candidates if c is not existing]
        else:
            print("[info] --prefer-existing-torch provided but no matching installation detected.")
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve a working dependency matrix for Windows + Python 3.10")
    parser.add_argument("--lock-out", default=str(REPO_ROOT / "requirements-lock-win-py310.txt"), help="Path to write the lock file")
    parser.add_argument("--prefer-existing-torch", action="store_true", help="Try to reuse currently installed torch first")
    args = parser.parse_args()

    env_info = detect_python_environment()
    print("[env] " + json.dumps(env_info, indent=2))

    lock_out = Path(args.lock_out).resolve()
    requirements = _load_requirement_lines()
    print(f"[info] Loaded {len(requirements)} dependency entries from requirements.txt")

    for candidate in order_candidates(args.prefer_existing_torch):
        try:
            if try_candidate(candidate, lock_out, requirements):
                print(f"[done] Lock file written to {lock_out}")
                return 0
        except subprocess.CalledProcessError as exc:
            print(f"[error] Command failed for {candidate.name}: {exc}")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[error] Unexpected failure for {candidate.name}: {exc}")
    print("[fatal] No candidate matrix succeeded.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
