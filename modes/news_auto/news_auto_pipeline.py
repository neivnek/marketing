"""
====================================================================
  Pipeline v3.0
  File: modes/news_auto/news_auto_pipeline.py — Mode 5 Orchestrator
====================================================================
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from core.tts_engine import synthesize_khmer
from core.subtitle_gen import generate_ass_file
from core.ffmpeg_utils import burn_hardsub, get_video_duration, apply_ken_burns
from core.broll_aggregator import fetch_broll_clips
from core.concat_helper import concatenate_clips
from modes.news_auto.json_schema_validator import validate_and_sanitize_news_json
from core.overlay_renderer import add_price_overlay

logger = logging.getLogger(__name__)

# Resolution mapping
RESOLUTION_MAP = {
    "720p":  (720, 1280),
    "1080p": (1080, 1920),
    "4k":    (2160, 3840),
}


def run_news_auto_pipeline(
    news_inputs: Any,
    output_dir: str = "output",
    temp_dir: str = "temp",
) -> str:
    """
    Run Mode 5: Auto News Video rendering from JSON payload.

    Parameters
    ----------
    news_inputs : NewsAutoInputs object (from core/router.py)
    output_dir  : Destination output directory
    temp_dir    : Temporary working directory

    Returns
    -------
    str : Path to rendered output MP4
    """
    logger.info("\n" + "═" * 60)
    logger.info("  MODE 5: Auto News Video Pipeline")
    logger.info("═" * 60)

    work_temp = os.path.join(temp_dir, "news_auto")
    os.makedirs(work_temp, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # ── Step 1: Validate & Sanitize JSON ──────────────────────────
    logger.info("[Step 5.1] Validating and sanitizing JSON payload...")
    payload = validate_and_sanitize_news_json(news_inputs.json_payload)

    title           = payload["title"]
    segments        = payload["script_segments"]
    product_price   = news_inputs.product_price or payload.get("product_price", "")
    output_quality  = news_inputs.output_quality or payload["output_quality"]
    out_w, out_h    = RESOLUTION_MAP.get(output_quality, (1080, 1920))

    logger.info(f"    Title   : '{title}'")
    logger.info(f"    Segments: {len(segments)}")
    logger.info(f"    Quality : {output_quality} ({out_w}x{out_h})")

    # ── Step 2: Generate TTS per segment & merged audio ────────────
    logger.info("[Step 5.2] Synthesizing voiceover per segment...")
    segment_audio_paths = []
    segment_durations   = []
    full_script_lines   = []

    for seg in segments:
        seg_id   = seg["id"]
        vo_text  = seg["voiceover_text"]
        scr_text = seg["on_screen_text"]
        full_script_lines.append(scr_text)

        seg_audio = os.path.join(work_temp, f"seg_{seg_id:02d}.mp3")
        try:
            synthesize_khmer(
                script_text=vo_text,
                output_path=seg_audio,
                voice=news_inputs.tts_voice,
                rate=getattr(news_inputs, "tts_rate", "+0%")
            )
            dur = get_video_duration(seg_audio)
        except Exception as exc:
            logger.warning(f"    TTS failed for segment {seg_id} ({exc}). Using estimated duration.")
            dur = float(seg.get("duration_hint_sec", 4.0))

        segment_audio_paths.append(seg_audio)
        segment_durations.append(dur)

    # Concatenate all TTS segment audios into one master audio file
    master_audio = os.path.join(work_temp, "master_voice.mp3")
    _concat_audio_files(segment_audio_paths, master_audio)
    total_audio_duration = get_video_duration(master_audio)
    logger.info(f"    ✓ Master voiceover generated: {total_audio_duration:.1f}s")

    # ── Step 3: Fetch Stock Visuals or generate fallback clips ──────
    logger.info("[Step 5.3] Generating visual clips for segments...")
    segment_video_clips = []
    pexels_key = os.getenv("PEXELS_API_KEY", "")

    for seg, dur in zip(segments, segment_durations):
        seg_id     = seg["id"]
        
        # Combine hints for better Pexels search
        beat       = seg.get("narrative_beat", "")
        emotion    = seg.get("emotion", "")
        cam        = seg.get("camera_hint", "")
        visual     = seg.get("visual_hint", "")
        combined_query = f"{beat} {emotion} {cam} {visual}".strip()
        
        out_clip   = os.path.join(work_temp, f"clip_{seg_id:02d}.mp4")

        clip_fetched = False
        try:
            downloaded = fetch_broll_clips(
                query_keywords=[combined_query, visual, beat],
                product_category="news",
                duration_sec=dur,
                pexels_api_key=pexels_key,
                temp_dir=work_temp,
                n_clips=1,
                out_w=out_w,
                out_h=out_h
            )
            if downloaded:
                import shutil
                shutil.copy(downloaded[0], out_clip)
                clip_fetched = True
        except Exception as exc:
            logger.warning(f"    B-roll search failed for segment {seg_id} ('{combined_query}'): {exc}")

        if not clip_fetched:
            # Fallback: create Ken Burns visual clip from a generated colored canvas/text tile
            _create_news_title_clip(
                text=seg.get("on_screen_text", ""),
                output_path=out_clip,
                duration=dur,
                out_w=out_w,
                out_h=out_h,
            )

        segment_video_clips.append(out_clip)

    # Concatenate segment video clips
    concat_video = os.path.join(work_temp, "concat_visual.mp4")
    concatenate_clips(segment_video_clips, concat_video)

    # ── Step 4: Merge Master Audio & Video ────────────────────────
    logger.info("[Step 5.4] Merging audio and visual track...")
    merged_raw = os.path.join(work_temp, "merged_raw.mp4")
    cmd_merge = [
        "ffmpeg", "-y",
        "-i", concat_video,
        "-i", master_audio,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(total_audio_duration),
        merged_raw,
    ]
    subprocess.run(cmd_merge, capture_output=True, check=True)

    # ── Step 5: Subtitle / Caption ASS generation ──────────────────
    logger.info("[Step 5.5] Generating news caption subtitles...")
    ass_path = os.path.join(work_temp, "news_captions.ass")

    # Cumulative timestamps for ASS cues
    timestamps = []
    curr = 0.0
    for d in segment_durations:
        curr += d
        timestamps.append(curr)

    full_script_text = ". ".join(full_script_lines) + "."
    generate_ass_file(
        script_text=full_script_text,
        timestamps=timestamps,
        output_path=ass_path,
        font_name="Hanuman",
    )

    subbed_video = os.path.join(work_temp, "subbed.mp4")
    burn_hardsub(merged_raw, ass_path, "assets/fonts", subbed_video)

    logger.info("[Step 5.6] Injecting price overlay...")
    final_output = os.path.join(output_dir, f"news_{_safe_filename(title)}.mp4")
    
    if product_price:
        try:
            add_price_overlay(
                input_path=subbed_video,
                output_path=final_output,
                price_text=product_price,
            )
        except Exception as exc:
            logger.warning(f"Price overlay failed: {exc}")
            shutil.copy(subbed_video, final_output)
    else:
        shutil.copy(subbed_video, final_output)

    # Cleanup temporary workspace
    try:
        shutil.rmtree(work_temp)
    except Exception:
        pass

    logger.info(f"\n[OK]  Auto News Video complete: {final_output}")
    return final_output


# ──────────────────────────────────────────────
# Helper Utilities
# ──────────────────────────────────────────────

def _concat_audio_files(audio_files: list[str], output_path: str):
    """Concatenate a list of MP3 audio files into a single master MP3."""
    concat_list_file = output_path + ".txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for p in audio_files:
            fp = Path(p).resolve().as_posix()
            f.write(f"file '{fp}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_file,
        "-c", "copy",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    if os.path.exists(concat_list_file):
        os.remove(concat_list_file)


def _trim_and_scale(input_path: str, output_path: str, duration: float, out_w: int, out_h: int):
    """Trim input video clip to duration and scale to portrait out_w x out_h."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(duration),
        "-vf", (
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},"
            f"setsar=1"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-an",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def _create_news_title_clip(text: str, output_path: str, duration: float, out_w: int, out_h: int):
    """Fallback: Generate a stylish news visual clip with background gradient and text."""
    clean_text = text.replace(":", "\\:").replace("'", "").strip()[:50]
    vf = (
        f"color=c=0x0f172a:s={out_w}x{out_h}:d={duration},"
        f"drawtext=fontfile='assets/fonts/Hanuman.ttf':text='{clean_text}':"
        f"fontsize=48:fontcolor=white:x=(w-tw)/2:y=(h-th)/2:box=1:boxcolor=0x1e293b@0.8:boxborderw=20"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def _safe_filename(text: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in text.strip())
    return cleaned[:30] or "video"
