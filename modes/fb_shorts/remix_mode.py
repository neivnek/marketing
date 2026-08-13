"""
====================================================================
  Pipeline v3.0
  File: modes/fb_shorts/remix_mode.py — Sub-mode A: Remix CC Videos
====================================================================

Luong:
  1. Trich noi dung tu Ad_Text_URL
  2. Gemini viet kich ban Khmer ngan (15-30s) + keyword tim kiem
  3. Tim + tai video CC tu Pexels
  4. Phan tich nhip cat tu Ref_Video_URL
  5. Cat + ghep video CC theo nhip
  6. TTS Khmer
  7. Overlay gia tien
  8. Burn phu de Khmer
"""

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.tts_engine import synthesize_khmer
from core.subtitle_gen import generate_ass_file
from core.ffmpeg_utils import burn_hardsub, get_video_duration, assemble_video
from core.pexels_client import search_and_download_clips
from core.overlay_renderer import add_price_overlay
from core.ugc_filters import apply_ugc_filter
from modes.fb_shorts.url_extractor import extract_ad_text, extract_key_selling_points

logger = logging.getLogger(__name__)

OUT_W, OUT_H = 1080, 1920
TARGET_MIN, TARGET_MAX = 15, 30   # seconds


@dataclass
class RemixInputs:
    product_images:   list[str]         # 1-5 anh san pham
    price_text:       str               # "35,000 KHR" or "$5"
    ad_text_url:      str               # URL bai quang cao de trich xuat
    ref_video_url:    Optional[str]     # URL hoac duong dan file local
    pexels_api_key:   str               # Pexels API key
    gemini_api_key:   str               # Gemini API key
    tts_voice:        str = "km-KH-SreymomNeural"
    ugc_intensity:    str = "medium"    # subtle / medium / strong
    search_keyword:   str = ""          # tu khoa tim video (tu dong neu de trong)
    price_color:      str = "red"       # red / black / orange / white


def run_remix_mode(inputs: RemixInputs, output_dir: str, temp_dir: str) -> str:
    """
    Remix mode: tim video CC + ghep theo nhip + TTS + gia + sub.
    Returns duong dan file output.
    """
    logger.info("\n" + "-" * 50)
    logger.info("  FB SHORTS — Sub-mode A: Remix")
    logger.info("-" * 50)

    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # ── Step A.1: Extract ad text + generate Khmer script ─────────
    logger.info("[Step A.1] Extracting ad text from URL...")
    try:
        raw_text = extract_ad_text(inputs.ad_text_url)
        selling_points = extract_key_selling_points(raw_text, max_points=4)
        logger.info(f"    Key points: {selling_points}")
    except Exception as exc:
        logger.warning(f"    URL extraction failed: {exc}. Using fallback text.")
        raw_text = f"Product: {inputs.price_text}"
        selling_points = []

    logger.info("[Step A.2] Writing Khmer script via Gemini...")
    khmer_script = _generate_khmer_script(
        raw_text=raw_text,
        selling_points=selling_points,
        price=inputs.price_text,
        api_key=inputs.gemini_api_key,
    )
    logger.info(f"    Script ({len(khmer_script)} chars): {khmer_script[:80]}...")

    # ── Step A.2: TTS ─────────────────────────────────────────────
    logger.info("[Step A.3] Synthesizing Khmer voiceover...")
    tts_path = str(Path(temp_dir) / "remix_voice.mp3")
    synthesize_khmer(script_text=khmer_script, output_path=tts_path, voice=inputs.tts_voice, rate=inputs.tts_rate)
    audio_dur = min(audio_info, TARGET_MAX)
    logger.info(f"    Audio duration: {audio_dur:.1f}s")

    # ── Step A.3: Search + download Pexels CC clips ────────────────
    keyword = inputs.search_keyword or _extract_keyword(raw_text)
    logger.info(f"[Step A.4] Searching Pexels for: '{keyword}'")
    clips_dir = str(Path(temp_dir) / "pexels_clips")
    clip_paths = search_and_download_clips(
        query=keyword,
        api_key=inputs.pexels_api_key,
        output_dir=clips_dir,
        n_clips=8,
        min_dur=2,
        max_dur=15,
    )

    if not clip_paths:
        logger.warning("    No Pexels clips found. Using product image Ken Burns as fallback.")
        clip_paths = _ken_burns_from_images(inputs.product_images, temp_dir, audio_dur)

    # ── Step A.4: Trim + assemble clips to match audio duration ───
    logger.info("[Step A.5] Assembling clips to match audio duration...")
    assembled_path = str(Path(temp_dir) / "remix_assembled.mp4")
    _assemble_clips(clip_paths, assembled_path, target_dur=audio_dur)

    # ── Step A.5: Merge audio ──────────────────────────────────────
    logger.info("[Step A.6] Merging TTS audio...")
    merged_path = str(Path(temp_dir) / "remix_merged.mp4")
    _merge_audio(assembled_path, tts_path, merged_path, audio_dur)

    # ── Step A.6: UGC filter ──────────────────────────────────────
    logger.info(f"[Step A.7] Applying UGC filter ({inputs.ugc_intensity})...")
    ugc_path = str(Path(temp_dir) / "remix_ugc.mp4")
    apply_ugc_filter(merged_path, ugc_path, intensity=inputs.ugc_intensity,
                     out_w=OUT_W, out_h=OUT_H)

    # ── Step A.7: Price overlay ────────────────────────────────────
    logger.info("[Step A.8] Adding price overlay...")
    overlaid_path = str(Path(temp_dir) / "remix_price.mp4")
    add_price_overlay(
        input_path=ugc_path,
        output_path=overlaid_path,
        price_text=inputs.price_text,
        tagline_text="[OK] ដឹកជញ្ជូនឥតគិតថ្លៃ",
        bg_color=inputs.price_color,
    )

    # ── Step A.8: Subtitle ─────────────────────────────────────────
    logger.info("[Step A.9] Burning Khmer subtitles...")
    ass_path = str(Path(temp_dir) / "remix_sub.ass")
    clip_timestamps = []
    curr = 0.0
    for d in durations:
        curr += d
        clip_timestamps.append(curr)

    generate_ass_file(
        script_text=khmer_script,
        timestamps=clip_timestamps,
        output_path=ass_path,
        font_name="Hanuman",
        )
    final_path = str(Path(output_dir) / "fb_remix_output.mp4")
    burn_hardsub(overlaid_path, ass_path, final_path)

    logger.info(f"\n[OK] Remix complete: {final_path}")
    return final_path


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _generate_khmer_script(raw_text: str, selling_points: list, price: str, api_key: str) -> str:
    """Call Gemini to write a 15-30s Khmer UGC ad script."""
    if not api_key:
        return _fallback_script(price)
    try:
        points_str = "\n".join(f"- {p}" for p in selling_points) if selling_points else raw_text[:300]
        prompt = f"""You are a Khmer copywriter. Write a natural, conversational 15-25 second UGC-style voiceover script in Khmer language.

Product info:
{points_str}
Price: {price}

Requirements:
- Sound like a real person sharing their experience, NOT a formal ad
- Use natural Khmer speech patterns with slight hesitations
- Include: hook (problem/curiosity) -> benefit -> price -> CTA
- End each sentence with ។
- Maximum 6 sentences total
- NO hashtags, NO emoji in the script

Return ONLY the Khmer script, nothing else."""

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.6-flash')
        response = model.generate_content(prompt)
        script = response.text.strip()
        logger.info(f"    Gemini script generated ({len(script)} chars)")
        return script
    except Exception as exc:
        logger.warning(f"    Gemini failed: {exc}. Using fallback.")
        return _fallback_script(price)


def _fallback_script(price: str) -> str:
    return (
        f"អ្នកណាមិនទាន់បានសាកល្បងផលិតផលនេះ? "
        f"ខ្ញុំប្រើរួចហើយ ល្អណាស់! "
        f"គុណភាពខ្ពស់ ប្រើបានយូរ។ "
        f"តម្លៃត្រឹមតែ {price} ប៉ុណ្ណោះ។ "
        f"ទទួលដឹកជញ្ជូនឥតគិតថ្លៃ! "
        f"ទំនាក់ទំនងមកភ្លាម មុនអស់ស្តុក!"
    )


def _extract_keyword(text: str) -> str:
    """Extract a simple English keyword for Pexels search from ad text."""
    # Very simple: take first 3 non-stopwords
    words = text.split()[:20]
    stops = {"the", "a", "an", "is", "are", "was", "to", "of", "and", "for", "in", "on"}
    keywords = [w for w in words if len(w) > 3 and w.lower() not in stops][:2]
    return " ".join(keywords) if keywords else "product lifestyle"


def _ken_burns_from_images(image_paths: list[str], temp_dir: str, duration: float) -> list[str]:
    """Fallback: create Ken Burns clips from product images."""
    from core.ffmpeg_utils import apply_ken_burns
    clips = []
    seg_dur = max(2.0, duration / max(len(image_paths), 1))
    for i, img in enumerate(image_paths[:5]):
        out = str(Path(temp_dir) / f"kb_img_{i:02d}.mp4")
        try:
            apply_ken_burns(
                image_path=img,
                output_path=out,
                total_duration=seg_dur,
                timestamps=[seg_dur],
                zoom_start=1.0, zoom_end=1.04,
                pan_directions=["center"],
                out_w=OUT_W, out_h=OUT_H,
                temp_dir=temp_dir,
            )
            clips.append(out)
        except Exception as exc:
            logger.warning(f"    Ken Burns fallback failed for {img}: {exc}")
    return clips


def _assemble_clips(clip_paths: list[str], output_path: str, target_dur: float):
    """Trim and assemble portrait clips to reach target_dur."""
    current_dur = 0.0
    used_clips = []

    for p in clip_paths * 3:   # repeat list if needed
        if current_dur >= target_dur:
            break
        try:
            clip_dur = get_video_duration(p)
        except Exception:
            continue

        remaining = target_dur - current_dur
        trim_dur = min(clip_dur, remaining, 5.0)   # max 5s per clip (UGC style)
        trimmed = str(Path(os.path.dirname(output_path)) / f"trim_{len(used_clips):03d}.mp4")
        _trim_and_resize(p, trimmed, trim_dur)
        used_clips.append(trimmed)
        current_dur += trim_dur

    if not used_clips:
        raise RuntimeError("No clips to assemble")

    from core.concat_helper import concatenate_clips
    concatenate_clips(used_clips, output_path)


def _trim_and_resize(input_path: str, output_path: str, duration: float):
    """Trim clip to duration and resize to 9:16 portrait."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(duration),
        "-vf", (
            f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},"
            f"setsar=1"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an",   # remove audio (will add TTS later)
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Trim failed: {result.stderr[-400:]}")


def _merge_audio(video_path: str, audio_path: str, output_path: str, duration: float):
    """Merge silent video with TTS audio."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Merge audio failed: {result.stderr[-400:]}")
