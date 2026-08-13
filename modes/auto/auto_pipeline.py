"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/auto/auto_pipeline.py — Mode 1 Orchestrator
====================================================================

Steps:
  1.1  Playwright + yt-dlp  -> ref_video.mp4
  1.2  Gemini Flash          -> timestamps + Khmer script
  1.3  edge-tts              -> voiceover.mp3
  1.4  FFmpeg (Ken Burns)    -> visual.mp4
       FFmpeg (Assembly)     -> merged.mp4
       FFmpeg (Hardsub)      -> final.mp4
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
    assemble_video,
    burn_hardsub,
    cleanup_temp,
)
from modes.auto.scraper import scrape_meta_ads
from modes.auto.ai_analyzer import analyze_video_with_gemini

logger = logging.getLogger(__name__)


def run_auto_pipeline(inputs: PipelineInputs, cfg: PipelineConfig) -> str:
    """
    Execute the fully autonomous pipeline (Mode 1).

    Returns
    -------
    str — Absolute path to the final .mp4 file.
    """
    temp_dir   = cfg.temp_dir
    output_dir = cfg.output_dir
    os.makedirs(temp_dir,   exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    logger.info("\n" + "─" * 50)
    logger.info("  MODE 1: Auto-Autonomous Pipeline")
    logger.info("─" * 50)

    # ── Step 1.1: Scrape & download reference video ──────────────
    logger.info("\n[Step 1.1] Scraping Meta Ads Library...")
    ref_videos = scrape_meta_ads(
        keyword=inputs.auto.category_keyword,
        output_dir=os.path.join(temp_dir, "scraped"),
        max_results=1,
    )
    ref_video_path = ref_videos[0]

    # ── Step 1.2: Gemini analysis -> timestamps + Khmer script ────
    logger.info("\n[Step 1.2] Gemini Flash analysis...")
    analysis = analyze_video_with_gemini(
        video_path=ref_video_path,
        product_image=inputs.product_image,
        api_key=cfg.apis.gemini_api_key,
    )
    timestamps     = analysis["timestamps"]
    total_duration = analysis["total_duration"]
    khmer_script   = analysis["script"]

    logger.info(f"    Timestamps : {timestamps}")
    logger.info(f"    Duration   : {total_duration:.1f}s")

    # ── Step 1.3: TTS -> voiceover.mp3 ────────────────────────────
    logger.info("\n[Step 1.3] Synthesizing Khmer voiceover (edge-tts)...")
    voiceover_path = os.path.join(temp_dir, "voiceover.mp3")
    synthesize_khmer(
        script_text=khmer_script,
        output_path=voiceover_path,
        voice=cfg.constraints.tts_voice,
        rate=cfg.constraints.tts_rate,
    )

    # Recalibrate duration to match actual voiceover length
    audio_duration = get_audio_duration(voiceover_path)
    logger.info(f"    Actual audio duration: {audio_duration:.1f}s")

    # Re-scale timestamps proportionally if TTS duration differs
    if abs(audio_duration - total_duration) > 1.0:
        scale = audio_duration / total_duration
        timestamps = [round(t * scale, 2) for t in timestamps]
    timestamps_final = timestamps + [audio_duration]

    # ── Step 1.4a: FFmpeg Ken Burns -> visual_raw.mp4 ─────────────
    logger.info("\n[Step 1.4] FFmpeg: Ken Burns effect...")
    visual_raw = os.path.join(temp_dir, "visual_raw.mp4")
    apply_ken_burns(
        image_path=inputs.product_image,
        output_path=visual_raw,
        timestamps=timestamps_final,
        total_duration=audio_duration,
        out_w=cfg.constraints.output_width,
        out_h=cfg.constraints.output_height,
        zoom_start=cfg.ken_burns.zoom_start,
        zoom_end=cfg.ken_burns.zoom_end,
        pan_directions=cfg.ken_burns.pan_directions,
        fps=cfg.constraints.framerate,
    )

    # ── Step 1.4b: Mux audio + video ─────────────────────────────
    logger.info("    Assembling audio + visual...")
    merged_path = os.path.join(temp_dir, "merged.mp4")
    assemble_video(
        visual_path=visual_raw,
        audio_path=voiceover_path,
        output_path=merged_path,
        video_codec=cfg.constraints.video_codec,
        audio_codec=cfg.constraints.audio_codec,
        crf=cfg.constraints.crf,
    )

    # ── Step 1.4c: Generate ASS subtitles ────────────────────────
    logger.info("    Generating Khmer subtitles...")
    ass_path = os.path.join(temp_dir, "subtitles.ass")
    generate_ass_file(
        script_text=khmer_script,
        timestamps=timestamps_final,
        output_path=ass_path,
        font_name=cfg.subtitle.font_name,
        alignment=cfg.subtitle.alignment,
        margin_v=cfg.subtitle.margin_v,
        res_x=cfg.constraints.output_width,
        res_y=cfg.constraints.output_height,
    )

    # ── Step 1.4d: Burn hardsub -> final.mp4 ──────────────────────
    logger.info("    Burning hardcoded Khmer subtitles...")
    final_name = f"auto_{Path(inputs.product_image).stem}_output.mp4"
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

    logger.info(f"\n[OK]  Auto pipeline complete: {final_path}")
    return final_path
