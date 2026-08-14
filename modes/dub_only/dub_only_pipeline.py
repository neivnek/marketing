"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/dub_only/dub_only_pipeline.py — Dub Only Mode
====================================================================
"""

import logging
import os
from pathlib import Path
from core.tts_engine import synthesize_khmer
from core.ffmpeg_utils import get_video_duration, burn_hardsub, adjust_audio_speed
from core.subtitle_gen import generate_ass_file
from core.config import DubOnlyInputs

logger = logging.getLogger(__name__)

def run_dub_only_pipeline(inputs: DubOnlyInputs, output_dir: str, temp_dir: str) -> str:
    """
    Dub Only Mode:
    1. Generates TTS audio from script_text (or uses AI to generate script if empty).
    2. Adjusts audio speed to match video duration.
    3. Replaces original video audio with the new TTS audio.
    4. Conditionally burns subtitles.
    """
    logger.info("=== STARTING DUB ONLY PIPELINE ===")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    source_video = inputs.source_video_path
    video_dur = get_video_duration(source_video)

    script_text = inputs.script_text.strip()
    if not script_text:
        # Fallback to AI generation if empty
        logger.info("[DUB ONLY] Script is empty, generating via AI...")
        from modes.auto.ai_analyzer import generate_script_from_video
        api_key = os.getenv("GEMINI_API_KEY", "")
        # Dummy product image path and price since they might not be provided in this mode
        res = generate_script_from_video(source_video, "assets/placeholder.jpg", "", api_key)
        script_text = res["script"]
        logger.info(f"Generated script: {script_text[:100]}...")

    # Step 1: Synthesize Audio
    raw_tts_path = os.path.join(temp_dir, "dub_only_raw_tts.mp3")
    synthesize_khmer(script_text, raw_tts_path, voice=inputs.voice, rate=inputs.tts_rate)

    # Step 2: Adjust Prosody (Speed matching)
    adjusted_tts_path = os.path.join(temp_dir, "dub_only_adjusted_tts.mp3")
    adjust_audio_speed(raw_tts_path, adjusted_tts_path, target_duration=video_dur)

    # Step 3: Replace Audio in Video
    # We can reuse audio_replace but we need to pass the adjusted audio.
    # audio_replace currently calls synthesize_khmer inside it if we use it directly.
    # To be precise, let's just do the muxing here since we already have the adjusted audio.
    import subprocess
    muxed_video = os.path.join(temp_dir, "dub_only_muxed.mp4")
    cmd_merge = [
        "ffmpeg", "-y",
        "-i", source_video,
        "-i", adjusted_tts_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        muxed_video,
    ]
    subprocess.run(cmd_merge, capture_output=True, check=True)
    logger.info(f"    ✓ Original audio stripped and replaced.")

    final_output = os.path.join(output_dir, f"dub_only_{Path(source_video).name}")

    # Step 4: Optional Subtitles
    if inputs.burn_subtitle:
        logger.info("[DUB ONLY] Burning subtitles...")
        ass_path = os.path.join(temp_dir, "dub_only_sub.ass")
        generate_ass_file(script_text, [video_dur], ass_path, font_name="Noto Sans Khmer")
        burn_hardsub(muxed_video, ass_path, "assets/fonts", final_output)
    else:
        import shutil
        shutil.copy(muxed_video, final_output)

    logger.info(f"=== FINISHED DUB ONLY PIPELINE: {final_output} ===")
    return final_output
