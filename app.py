"""Gradio one-click launcher for ViDub."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import gradio as gr

from inference import PipelineConfig, SubtitleAwarePipeline, load_defaults, merge_config, save_defaults
from utils.logging_setup import attach_gui_handler, setup_logging
from utils.preflight import format_preflight_report, run_preflight_checks
from utils.subtitles import SubtitleProcessingError, detect_embedded_subs


def _pick_path(file_input: Optional[Any], text_input: str) -> Optional[str]:
    if text_input and text_input.strip():
        return text_input.strip()
    if file_input is not None:
        return file_input.name
    return None


def _build_pipeline_config(values: Dict[str, Any]) -> PipelineConfig:
    defaults = load_defaults()
    namespace = SimpleNamespace(**values)
    namespace._explicit_flags = {
        key
        for key, value in values.items()
        if isinstance(value, bool)
    }
    return merge_config(defaults, namespace)  # type: ignore[arg-type]


def _start_pipeline(
    video_file: Optional[Any],
    video_path: str,
    output_dir: str,
    source_language: str,
    target_language: str,
    whisper_model: str,
    LipSync: bool,
    Bg_sound: bool,
    subs_file: Optional[Any],
    subs_path: str,
    subs_lang: str,
    use_embedded_subs: bool,
    preferred_subs_index: float,
    embedded_stream_choice: Optional[str],
    skip_translation_if_lang_matches: bool,
    force_stt: bool,
    use_diarization_with_subs: bool,
    log: bool,
) -> tuple[str, str, str]:
    video_path = _pick_path(video_file, video_path)
    if not video_path:
        return "Please provide an input video path or file.", "", ""

    subs_path = _pick_path(subs_file, subs_path)
    preferred_index_value = embedded_stream_choice or preferred_subs_index

    config_dict = {
        "input_video": video_path,
        "output_dir": output_dir or "results",
        "source_language": source_language,
        "target_language": target_language,
        "whisper_model": whisper_model or "medium",
        "LipSync": bool(LipSync),
        "Bg_sound": bool(Bg_sound),
        "subs_file": subs_path,
        "use_embedded_subs": bool(use_embedded_subs),
        "preferred_subs_index": int(preferred_index_value or 0),
        "subs_lang": subs_lang or None,
        "skip_translation_if_lang_matches": bool(skip_translation_if_lang_matches),
        "force_stt": bool(force_stt),
        "use_diarization_with_subs": bool(use_diarization_with_subs),
        "log": bool(log),
    }

    try:
        config = _build_pipeline_config(config_dict)
    except Exception as exc:  # pylint: disable=broad-except
        return f"Configuration error: {exc}", "", ""

    logging_context = setup_logging(config.log)
    logger = logging_context.logger
    gui_handler, handler = attach_gui_handler(logger)

    pipeline = SubtitleAwarePipeline(config, logger)

    status = ""
    try:
        output_path = pipeline.run()
        status = f"Success! Subtitles ready at {output_path}" + (
            f" | Log saved to {logging_context.log_path}" if logging_context.log_path else ""
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Pipeline failed: %s", exc)
        status = f"Pipeline failed: {exc}"
    finally:
        log_text = gui_handler.consume()
        logger.removeHandler(handler)

    return status, log_text, str(logging_context.log_path) if logging_context.log_path else ""


def _save_defaults_from_gui(
    video_file: Optional[Any],
    video_path: str,
    output_dir: str,
    source_language: str,
    target_language: str,
    whisper_model: str,
    LipSync: bool,
    Bg_sound: bool,
    subs_file: Optional[Any],
    subs_path: str,
    subs_lang: str,
    use_embedded_subs: bool,
    preferred_subs_index: float,
    skip_translation_if_lang_matches: bool,
    force_stt: bool,
    use_diarization_with_subs: bool,
    log: bool,
) -> str:
    video_path_value = _pick_path(video_file, video_path) or ""
    subs_path_value = _pick_path(subs_file, subs_path) or ""
    namespace = SimpleNamespace(
        input_video=video_path_value,
        output_dir=output_dir,
        source_language=source_language,
        target_language=target_language,
        whisper_model=whisper_model,
        LipSync=bool(LipSync),
        Bg_sound=bool(Bg_sound),
        subs_file=subs_path_value,
        use_embedded_subs=bool(use_embedded_subs),
        preferred_subs_index=int(preferred_subs_index or 0),
        subs_lang=subs_lang,
        skip_translation_if_lang_matches=bool(skip_translation_if_lang_matches),
        force_stt=bool(force_stt),
        use_diarization_with_subs=bool(use_diarization_with_subs),
        log=bool(log),
        save_defaults=True,
    )
    namespace._explicit_flags = {
        "LipSync",
        "Bg_sound",
        "use_embedded_subs",
        "skip_translation_if_lang_matches",
        "force_stt",
        "use_diarization_with_subs",
        "log",
    }
    save_defaults(namespace)  # type: ignore[arg-type]
    return "Defaults saved."


def _refresh_embedded_streams(video_file: Optional[Any], video_path: str) -> tuple[gr.Dropdown, str]:
    path = _pick_path(video_file, video_path)
    if not path:
        return gr.Dropdown.update(), "Provide a video file/path first."

    try:
        streams = detect_embedded_subs(Path(path))
    except SubtitleProcessingError as exc:
        return gr.Dropdown.update(), f"Subtitle probing failed: {exc}"
    except FileNotFoundError:
        return gr.Dropdown.update(), "Video file not found."

    if not streams:
        return gr.Dropdown.update(choices=[], value=None), "No embedded subtitles detected."

    choices = [str(i) for i, _ in enumerate(streams)]
    info_lines = [
        f"#{i} -> container stream {stream.index}, codec={stream.codec or 'unknown'}, lang={stream.language or 'und'}"
        for i, stream in enumerate(streams)
    ]
    info = "\n".join(info_lines)
    return gr.Dropdown.update(choices=choices, value=choices[0]), info


def launch_app() -> gr.Blocks:
    defaults = load_defaults()

    with gr.Blocks(title="ViDub One-Click") as demo:
        gr.Markdown("# ViDub One-Click\nMinimal interface for subtitle-aware dubbing.")

        with gr.Row():
            video_file = gr.File(label="Input video", file_types=[".mp4", ".mkv", ".mov", ".avi"])
            video_path = gr.Textbox(label="Video path or URL", value=defaults.get("input_video", ""))
        output_dir = gr.Textbox(label="Output directory", value=defaults.get("output_dir", "results"))

        with gr.Row():
            source_language = gr.Textbox(label="Source language", value=defaults.get("source_language", "en"))
            target_language = gr.Textbox(label="Target language", value=defaults.get("target_language", "en"))
            whisper_model = gr.Dropdown(
                label="Whisper model",
                choices=["tiny", "base", "small", "medium", "large-v2"],
                value=defaults.get("whisper_model", "medium"),
            )

        with gr.Row():
            lipsync = gr.Checkbox(label="Enable LipSync", value=defaults.get("LipSync", False))
            bg_sound = gr.Checkbox(label="Keep background sound", value=defaults.get("Bg_sound", False))
            diarization = gr.Checkbox(
                label="Use diarization with subtitles",
                value=defaults.get("use_diarization_with_subs", False),
            )

        gr.Markdown("## Subtitles")
        with gr.Row():
            subs_file = gr.File(label="External subtitles", file_types=[".srt", ".vtt", ".ass"], elem_id="subs_file")
            subs_path = gr.Textbox(label="Subtitle path", value=defaults.get("subs_file", ""))
            subs_lang = gr.Textbox(label="Subtitle language (optional)", value=defaults.get("subs_lang", ""))

        with gr.Row():
            use_embedded_subs = gr.Checkbox(
                label="Use embedded subtitles if available",
                value=defaults.get("use_embedded_subs", False),
            )
            preferred_subs_index = gr.Number(
                label="Preferred subtitle index",
                value=defaults.get("preferred_subs_index", 0),
                precision=0,
            )
            embedded_stream_choice = gr.Dropdown(label="Detected embedded streams", choices=[])
            refresh_streams = gr.Button("Detect embedded streams")
            embedded_info = gr.Textbox(label="Embedded subtitle info", interactive=False)

        with gr.Row():
            skip_translation = gr.Checkbox(
                label="Skip translation if languages match",
                value=defaults.get("skip_translation_if_lang_matches", True),
            )
            force_stt = gr.Checkbox(label="Force Whisper STT", value=defaults.get("force_stt", False))
            save_log = gr.Checkbox(label="Save run log", value=defaults.get("log", False))

        with gr.Row():
            preflight_btn = gr.Button("Pre-flight check", variant="secondary")
            start_btn = gr.Button("Start", variant="primary")
            save_defaults_btn = gr.Button("Save as default")

        preflight_output = gr.Textbox(label="Pre-flight report", lines=6)
        status_output = gr.Textbox(label="Status", lines=2)
        log_output = gr.Textbox(label="Log", lines=12)
        log_path_output = gr.Textbox(label="Log file", interactive=False)

        refresh_streams.click(
            _refresh_embedded_streams,
            inputs=[video_file, video_path],
            outputs=[embedded_stream_choice, embedded_info],
        )

        preflight_btn.click(
            lambda: format_preflight_report(run_preflight_checks()),
            inputs=None,
            outputs=preflight_output,
        )

        start_btn.click(
            _start_pipeline,
            inputs=[
                video_file,
                video_path,
                output_dir,
                source_language,
                target_language,
                whisper_model,
                lipsync,
                bg_sound,
                subs_file,
                subs_path,
                subs_lang,
                use_embedded_subs,
                preferred_subs_index,
                embedded_stream_choice,
                skip_translation,
                force_stt,
                diarization,
                save_log,
            ],
            outputs=[status_output, log_output, log_path_output],
        )

        save_defaults_btn.click(
            _save_defaults_from_gui,
            inputs=[
                video_file,
                video_path,
                output_dir,
                source_language,
                target_language,
                whisper_model,
                lipsync,
                bg_sound,
                subs_file,
                subs_path,
                subs_lang,
                use_embedded_subs,
                preferred_subs_index,
                skip_translation,
                force_stt,
                diarization,
                save_log,
            ],
            outputs=status_output,
        )

    return demo


if __name__ == "__main__":
    launch_app().queue().launch()
