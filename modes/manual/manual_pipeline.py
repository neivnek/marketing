"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/manual/manual_pipeline.py — Mode 2 Orchestrator
====================================================================

Steps:
  2.1  pacing_analyzer    -> timestamps from [Manual_Ref_Video]
  2.2  tts_engine         -> voiceover.mp3 from [Manual_Script]
  2.3  prompt_interpreter -> MotionStyle from [Manual_Prompt]
  2.4  FFmpeg (Ken Burns) -> visual_raw.mp4
       FFmpeg (Color)     -> visual_graded.mp4  (if color filter set)
       FFmpeg (Assembly)  -> merged.mp4
       subtitle_gen       -> subtitles.ass
       FFmpeg (Hardsub)   -> final.mp4
"""

import logging
import os
from pathlib import Path

from core.config import PipelineConfig
from core.router import PipelineInputs
from core.tts_engine import synthesize_khmer, get_audio_duration
from core.subtitle_gen import generate_ass_file
from core.ffmpeg_utils import (
    apply_ken_burns,
    apply_color_filter,
    assemble_video,
    burn_hardsub,
    cleanup_temp,
)
from modes.manual.pacing_analyzer import extract_scene_timestamps
from modes.manual.prompt_interpreter import parse_motion_style

logger = logging.getLogger(__name__)


def run_manual_pipeline(inputs: PipelineInputs, cfg: PipelineConfig) -> str:
    """
    Execute the Manual Override pipeline (Mode 2).

    Returns
    -------
    str — Absolute path to the final .mp4 file.
    """
    temp_dir   = cfg.temp_dir
    output_dir = cfg.output_dir
    os.makedirs(temp_dir,   exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    manual = inputs.manual

    logger.info("\n" + "─" * 50)
    logger.info("  MODE 2: Manual Override Pipeline")
    logger.info("─" * 50)

    # ── Step 2.1: Extract pacing / timestamps from ref video ─────
    logger.info(f"[Step 2.1] Extracting scene timestamps from reference video...")
    timestamps = extract_scene_timestamps(
        video_path=manual.ref_video_path,
        threshold=0.3,
        min_gap_sec=1.5,
    )
    logger.info(f"    Timestamps: {timestamps}")

    # ── Step 2.2: TTS from [Manual_Script] ───────────────────────
    logger.info("\n[Step 2.2] Synthesizing voiceover from manual script (edge-tts)...")
    voiceover_path = os.path.join(temp_dir, "voiceover.mp3")
    synthesize_khmer(
        script_text=manual.script,
        output_path=voiceover_path,
        voice=cfg.constraints.tts_voice,
        rate=cfg.constraints.tts_rate,
    )
    audio_duration = get_audio_duration(voiceover_path)
    logger.info(f"    Audio duration: {audio_duration:.1f}s")

    # Re-scale timestamps to match actual TTS duration
    ref_total = timestamps[-1] if timestamps else audio_duration
    if abs(audio_duration - ref_total) > 0.5:
        scale = audio_duration / ref_total
        timestamps = [round(t * scale, 2) for t in timestamps]
        logger.info(f"    Timestamps rescaled x{scale:.3f} -> {timestamps}")

    # Ensure final timestamp = audio duration
    if not timestamps or timestamps[-1] != audio_duration:
        timestamps = [t for t in timestamps if t < audio_duration]
        timestamps.append(round(audio_duration, 2))

    # ── Step 2.3: Parse [Manual_Prompt] -> motion style ───────────
    logger.info("\n[Step 2.3] Parsing motion style from user prompt...")
    motion = parse_motion_style(manual.prompt)
    logger.info(f"    Style: {motion.description}")

    # ── Step 2.4a: Ken Burns with prompt-driven parameters ────────
    logger.info("\n[Step 2.4] Rendering Ken Burns visual...")
    visual_raw = os.path.join(temp_dir, "visual_raw.mp4")
    apply_ken_burns(
        image_path=inputs.product_image,
        output_path=visual_raw,
        timestamps=timestamps,
        total_duration=audio_duration,
        out_w=cfg.constraints.output_width,
        out_h=cfg.constraints.output_height,
        zoom_start=motion.zoom_start,
        zoom_end=motion.zoom_end,
        pan_directions=motion.pan_directions,
        fps=cfg.constraints.framerate,
        temp_dir=temp_dir,          # ← explicit: avoids temp\temp double-path
    )

    # ── Step 2.4b: Apply color grade (if prompt requested one) ────
    visual_final = visual_raw
    if motion.color_filter:
        logger.info(f"    Applying color filter: {motion.color_preset}...")
        visual_graded = os.path.join(temp_dir, "visual_graded.mp4")
        apply_color_filter(
            input_video=visual_raw,
            output_path=visual_graded,
            filter_str=motion.color_filter,
        )
        visual_final = visual_graded

    # ── Step 2.4c: Mux audio + video ─────────────────────────────
    logger.info("    Assembling audio + visual...")
    merged_path = os.path.join(temp_dir, "merged.mp4")
    assemble_video(
        visual_path=visual_final,
        audio_path=voiceover_path,
        output_path=merged_path,
        video_codec=cfg.constraints.video_codec,
        audio_codec=cfg.constraints.audio_codec,
        crf=cfg.constraints.crf,
    )

    # ── Step 2.4d: Generate ASS subtitles ────────────────────────
    logger.info("    Generating Khmer subtitles...")
    ass_path = os.path.join(temp_dir, "subtitles.ass")
    generate_ass_file(
        script_text=manual.script,
        timestamps=timestamps,
        output_path=ass_path,
        font_name=cfg.subtitle.font_name,
        alignment=cfg.subtitle.alignment,
        margin_v=cfg.subtitle.margin_v,
        res_x=cfg.constraints.output_width,
        res_y=cfg.constraints.output_height,
    )

    # ── Step 2.4e: Burn hardsub -> final.mp4 ──────────────────────
    logger.info("    Burning hardcoded Khmer subtitles...")
    final_name = f"manual_{Path(inputs.product_image).stem}_output.mp4"
    final_path = os.path.join(output_dir, final_name)
    burn_hardsub(
        input_video=merged_path,
        ass_path=ass_path,
        fonts_dir=cfg.fonts_dir,
        output_path=final_path,
        crf=cfg.constraints.crf,
    )

    # ── Cleanup ───────────────────────────────────────────────────
    cleanup_temp(temp_dir)

    logger.info(f"\n[OK]  Manual pipeline complete: {final_path}")
    return final_path
