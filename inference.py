"""Subtitle-aware ViDub inference CLI."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pysubs2
import yaml

from utils.logging_setup import setup_logging
from utils.subtitles import (
    SubtitleDocument,
    SubtitleProcessingError,
    detect_embedded_subs,
    detect_language,
    extract_subs,
    read_subs,
    subtitles_to_segments,
    translate_subs,
)

CONFIG_PATH = Path("config/defaults.yaml")


@dataclass
class PipelineConfig:
    input_video: str
    output_dir: str
    source_language: str
    target_language: str
    whisper_model: str
    LipSync: bool
    Bg_sound: bool
    subs_file: Optional[str]
    use_embedded_subs: bool
    preferred_subs_index: int
    subs_lang: Optional[str]
    skip_translation_if_lang_matches: bool
    force_stt: bool
    use_diarization_with_subs: bool
    log: bool


class SubtitleAwarePipeline:
    """Main orchestration logic for subtitle-aware dubbing."""

    def __init__(self, cfg: PipelineConfig, logger: logging.Logger) -> None:
        self.cfg = cfg
        self.logger = logger
        self.output_dir = Path(cfg.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _prepare_subtitles(self) -> Optional[SubtitleDocument]:
        cfg = self.cfg

        if not cfg.input_video:
            raise SubtitleProcessingError("No input video provided.")

        if cfg.force_stt:
            self.logger.info("Force STT flag enabled – skipping subtitle reuse.")
            return None

        # 1. External subtitles
        if cfg.subs_file:
            path = Path(cfg.subs_file)
            if not path.exists():
                raise SubtitleProcessingError(f"Subtitle file not found: {path}")
            self.logger.info("Using external subtitles from %s", path)
            return read_subs(path)

        # 2. Embedded subtitles
        if cfg.use_embedded_subs:
            video_path = Path(cfg.input_video)
            streams = detect_embedded_subs(video_path)
            if not streams:
                self.logger.warning("No embedded subtitle streams detected – falling back to STT.")
                return None
            selected_index = cfg.preferred_subs_index
            if selected_index >= len(streams) or selected_index < 0:
                self.logger.warning(
                    "Preferred subtitle index %s is out of range. Defaulting to stream 0.",
                    selected_index,
                )
                selected_index = 0
            stream = streams[selected_index]
            self.logger.info(
                "Using embedded subtitle stream %s (%s, language=%s)",
                stream.index,
                stream.codec,
                stream.language or "unknown",
            )
            extracted_path = self.output_dir / f"embedded_subs_{stream.index}.srt"
            extract_subs(video_path, selected_index, extracted_path)
            return read_subs(extracted_path)

        return None

    def _maybe_translate(self, doc: SubtitleDocument) -> SubtitleDocument:
        cfg = self.cfg
        language = cfg.subs_lang or detect_language(doc.sample_text())
        if language:
            self.logger.info("Detected subtitle language: %s", language)
        else:
            self.logger.warning("Unable to detect subtitle language automatically.")

        if cfg.skip_translation_if_lang_matches and language == cfg.target_language:
            self.logger.info("Subtitle language matches target language – skipping translation.")
            return doc

        src_lang = language or cfg.source_language
        self.logger.info("Translating subtitles from %s to %s", src_lang, cfg.target_language)
        try:
            translated = translate_subs(doc.subs, src_lang, cfg.target_language)
        except SubtitleProcessingError as exc:
            self.logger.error("Translation failed: %s", exc)
            return doc

        translated_path = self.output_dir / "subtitles_translated.srt"
        translated.save(translated_path)
        self.logger.info("Translated subtitles saved to %s", translated_path)
        return SubtitleDocument(subs=translated, path=translated_path)

    def _run_whisper(self) -> SubtitleDocument:
        from faster_whisper import WhisperModel  # Lazy import to improve CLI startup

        self.logger.info("Running Whisper STT using model %s", self.cfg.whisper_model)
        model = WhisperModel(self.cfg.whisper_model, device="cuda" if self._has_cuda() else "cpu")
        segments, _ = model.transcribe(self.cfg.input_video, beam_size=5, word_timestamps=False)

        # Convert to subtitle file for downstream pipeline
        subs = pysubs2.SSAFile()
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            line = pysubs2.SSAEvent()
            line.start = int(segment.start * 1000)
            line.end = int(segment.end * 1000)
            line.text = text
            subs.append(line)

        output_path = self.output_dir / "transcript.srt"
        subs.save(output_path)
        self.logger.info("Transcription saved to %s", output_path)
        return SubtitleDocument(subs=subs, path=output_path)

    @staticmethod
    def _has_cuda() -> bool:
        try:
            import torch

            return torch.cuda.is_available()
        except Exception:  # pylint: disable=broad-except
            return False

    def run(self) -> Path:
        """Execute the pipeline and return the path to the generated subtitles."""

        video_path = Path(self.cfg.input_video)
        if not video_path.exists():
            raise FileNotFoundError(f"Input video not found: {video_path}")

        subtitle_doc = None
        try:
            subtitle_doc = self._prepare_subtitles()
        except SubtitleProcessingError as exc:
            self.logger.error("Subtitle preparation failed: %s", exc)
            subtitle_doc = None

        if subtitle_doc is None:
            self.logger.info("No usable subtitles found – invoking Whisper STT.")
            subtitle_doc = self._run_whisper()

        final_doc = self._maybe_translate(subtitle_doc)
        final_segments = subtitles_to_segments(final_doc.subs)
        segments_path = self.output_dir / "segments.json"
        with segments_path.open("w", encoding="utf-8") as f:
            json.dump(final_segments, f, ensure_ascii=False, indent=2)
        self.logger.info("Segments exported to %s", segments_path)

        # TODO: Integrate with the remaining dubbing pipeline (TTS, lip-sync, etc.).
        self.logger.info(
            "Subtitle-aware preprocessing complete. Downstream dubbing should consume %s.",
            segments_path,
        )

        if self.cfg.use_diarization_with_subs:
            self.logger.info(
                "Diarization with subtitles requested – integrate diarization heuristics in downstream stages."
            )
        return final_doc.path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Subtitle-aware ViDub inference")
    parser.add_argument("--input_video", type=str, default=None, help="Path to input video file")
    parser.add_argument("--output_dir", type=str, default=None, help="Directory for outputs")
    parser.add_argument("--source_language", type=str, default=None, help="Source language code")
    parser.add_argument("--target_language", type=str, default=None, help="Target language code")
    parser.add_argument("--whisper_model", type=str, default=None, help="Whisper model size")
    parser.add_argument("--LipSync", action="store_true", help="Enable lip-sync stage")
    parser.add_argument("--Bg_sound", action="store_true", help="Mix original background audio")
    parser.add_argument("--subs_file", type=str, default=None, help="External subtitles (SRT/VTT/ASS)")
    parser.add_argument("--use_embedded_subs", action="store_true", help="Use embedded subtitles if present")
    parser.add_argument(
        "--preferred_subs_index",
        type=int,
        default=0,
        help="Preferred subtitle stream index when extracting embedded subtitles",
    )
    parser.add_argument("--subs_lang", type=str, default=None, help="Language code of provided subtitles")
    parser.add_argument(
        "--skip_translation_if_lang_matches",
        dest="skip_translation_if_lang_matches",
        action="store_true",
        help="Skip translation when subtitle language matches target",
    )
    parser.add_argument(
        "--no-skip_translation_if_lang_matches",
        dest="skip_translation_if_lang_matches",
        action="store_false",
        help="Force translation even if subtitle language equals target",
    )
    parser.set_defaults(skip_translation_if_lang_matches=None)
    parser.add_argument("--force_stt", action="store_true", help="Force Whisper STT even if subtitles exist")
    parser.add_argument(
        "--use_diarization_with_subs",
        action="store_true",
        help="Attempt diarization when subtitles are used",
    )
    parser.add_argument("--log", action="store_true", help="Persist run log to logs/run_*.log")
    parser.add_argument(
        "--save_defaults",
        action="store_true",
        help="Persist provided arguments into config/defaults.yaml",
    )
    return parser


def load_defaults() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def merge_config(defaults: Dict[str, Any], args: argparse.Namespace) -> PipelineConfig:
    data = defaults.copy()
    cli_updates: Dict[str, Any] = {}
    namespace = vars(args)
    explicit_flags = set(getattr(args, "_explicit_flags", set()))
    for key, value in namespace.items():
        if key == "save_defaults":
            continue
        if key == "skip_translation_if_lang_matches":
            if value is not None:
                cli_updates[key] = value
            continue
        if isinstance(value, bool):
            if value or key in explicit_flags:
                cli_updates[key] = value
        elif value is not None:
            cli_updates[key] = value

    data.update(cli_updates)

    data.setdefault("output_dir", "results")
    data.setdefault("whisper_model", "medium")
    data.setdefault("LipSync", False)
    data.setdefault("Bg_sound", False)
    data.setdefault("use_embedded_subs", False)
    data.setdefault("skip_translation_if_lang_matches", True)
    data.setdefault("force_stt", False)
    data.setdefault("use_diarization_with_subs", False)
    data.setdefault("log", False)

    required = ["input_video", "source_language", "target_language"]
    missing = [name for name in required if not data.get(name)]
    if missing:
        raise ValueError(f"Missing required configuration values: {', '.join(missing)}")

    return PipelineConfig(
        input_video=str(data["input_video"]),
        output_dir=str(data.get("output_dir", "results")),
        source_language=str(data["source_language"]),
        target_language=str(data["target_language"]),
        whisper_model=str(data.get("whisper_model", "medium")),
        LipSync=bool(data.get("LipSync", False)),
        Bg_sound=bool(data.get("Bg_sound", False)),
        subs_file=(str(data.get("subs_file")) if data.get("subs_file") else None),
        use_embedded_subs=bool(data.get("use_embedded_subs", False)),
        preferred_subs_index=int(data.get("preferred_subs_index", 0)),
        subs_lang=(str(data.get("subs_lang")) if data.get("subs_lang") else None),
        skip_translation_if_lang_matches=bool(data.get("skip_translation_if_lang_matches", True)),
        force_stt=bool(data.get("force_stt", False)),
        use_diarization_with_subs=bool(data.get("use_diarization_with_subs", False)),
        log=bool(data.get("log", False)),
    )


def save_defaults(args: argparse.Namespace) -> None:
    to_save = {
        k: v
        for k, v in vars(args).items()
        if k not in {"save_defaults"} and v is not None
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(to_save, f)


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    parsed = parser.parse_args(argv_list)

    provided_flags = _extract_explicit_flags(argv_list)
    setattr(parsed, "_explicit_flags", provided_flags)

    defaults = load_defaults()
    if parsed.save_defaults:
        save_defaults(parsed)
        print(f"Defaults saved to {CONFIG_PATH}")
        return

    try:
        config = merge_config(defaults, parsed)
    except ValueError as exc:
        parser.error(str(exc))
    logging_context = setup_logging(config.log)
    logger = logging_context.logger
    logger.info("Starting ViDub pipeline with config: %s", config)

    pipeline = SubtitleAwarePipeline(config, logger)
    try:
        output = pipeline.run()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)

    logger.info("Pipeline complete. Generated subtitles at %s", output)
    if logging_context.log_path:
        logger.info("Log file written to %s", logging_context.log_path)


if __name__ == "__main__":  # pragma: no cover
    main()
def _extract_explicit_flags(argv: List[str]) -> set[str]:
    flag_names = {
        "--LipSync": "LipSync",
        "--Bg_sound": "Bg_sound",
        "--use_embedded_subs": "use_embedded_subs",
        "--skip_translation_if_lang_matches": "skip_translation_if_lang_matches",
        "--no-skip_translation_if_lang_matches": "skip_translation_if_lang_matches",
        "--force_stt": "force_stt",
        "--use_diarization_with_subs": "use_diarization_with_subs",
        "--log": "log",
    }
    provided: set[str] = set()
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in flag_names:
            provided.add(flag_names[token])
            i += 1
            continue
        if token.startswith("--"):
            name = token.split("=", 1)[0]
            normalized = name.lstrip("-").replace("-", "_")
            provided.add(normalized)
            if "=" not in token and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                i += 1
        i += 1
    return provided

