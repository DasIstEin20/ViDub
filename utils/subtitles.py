"""Subtitle utilities for ViDub."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pysubs2
from langdetect import detect


@dataclass
class SubtitleStreamInfo:
    index: int
    codec: Optional[str]
    language: Optional[str]
    title: Optional[str]


@dataclass
class SubtitleDocument:
    subs: pysubs2.SSAFile
    path: Path

    def sample_text(self, max_len: int = 500) -> str:
        chunks: List[str] = []
        length = 0
        for line in self.subs:
            text = line.plaintext.strip()
            if not text:
                continue
            chunks.append(text)
            length += len(text)
            if length >= max_len:
                break
        return " ".join(chunks)


class SubtitleProcessingError(RuntimeError):
    """Raised when subtitle operations fail."""


def detect_embedded_subs(video_path: Path) -> List[SubtitleStreamInfo]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=index,codec_name:stream_tags=language,title",
        "-of",
        "json",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:  # pylint: disable=broad-except
        raise SubtitleProcessingError(f"Unable to probe subtitles: {exc}") from exc

    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", [])
    detected: List[SubtitleStreamInfo] = []
    for stream in streams:
        detected.append(
            SubtitleStreamInfo(
                index=int(stream.get("index", 0)),
                codec=stream.get("codec_name"),
                language=(stream.get("tags") or {}).get("language"),
                title=(stream.get("tags") or {}).get("title"),
            )
        )
    return detected


def extract_subs(video_path: Path, index: int, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-map",
        f"0:s:{index}",
        "-c:s",
        "srt",
        out_path.as_posix(),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:  # pylint: disable=broad-except
        raise SubtitleProcessingError(f"Failed to extract subtitle stream {index}: {exc}") from exc
    return out_path


def read_subs(path: Path) -> SubtitleDocument:
    try:
        subs = pysubs2.load(path)
    except Exception as exc:  # pylint: disable=broad-except
        raise SubtitleProcessingError(f"Unable to read subtitles at {path}: {exc}") from exc
    return SubtitleDocument(subs=subs, path=path)


def detect_language(text: str) -> Optional[str]:
    if not text.strip():
        return None
    try:
        return detect(text)
    except Exception:  # pylint: disable=broad-except
        return None


def translate_subs(subs: pysubs2.SSAFile, src_lang: str, tgt_lang: str) -> pysubs2.SSAFile:
    if src_lang == tgt_lang:
        return subs

    try:
        from transformers import MarianMTModel, MarianTokenizer
    except ImportError as exc:  # pylint: disable=broad-except
        raise SubtitleProcessingError("transformers not installed; translation unavailable") from exc

    if src_lang == "zh-cn":
        model_name = f"Helsinki-NLP/opus-mt-zh-{tgt_lang}"
    elif tgt_lang == "zh-cn":
        model_name = f"Helsinki-NLP/opus-mt-{src_lang}-zh"
    else:
        model_name = f"Helsinki-NLP/opus-mt-{src_lang}-{tgt_lang}"

    try:
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)
    except Exception as exc:  # pylint: disable=broad-except
        raise SubtitleProcessingError(f"Unable to load translation model {model_name}: {exc}") from exc

    translated = subs.copy()
    for line in translated:
        text = line.plaintext.strip()
        if not text:
            continue
        inputs = tokenizer(text, return_tensors="pt", truncation=True)
        generated_tokens = model.generate(**inputs)
        line.text = tokenizer.decode(generated_tokens[0], skip_special_tokens=True)
    return translated


def subtitles_to_segments(subs: pysubs2.SSAFile) -> List[dict]:
    segments: List[dict] = []
    for line in subs:
        segments.append(
            {
                "start": line.start / 1000.0,
                "end": line.end / 1000.0,
                "text": line.plaintext.strip(),
            }
        )
    return segments
