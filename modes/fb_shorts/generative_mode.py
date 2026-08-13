"""
====================================================================
  Pipeline v3.0
  File: modes/fb_shorts/generative_mode.py — Sub-mode B: AI Video
====================================================================

Luong:
  1. Gemini doc URL -> viet kich ban Khmer ngan (15-30s)
  2. Replicate SVD (stable-video-diffusion) bien anh -> video 3-5s
     Fallback: Ken Burns neu khong co Replicate key
  3. TTS tieng Khmer
  4. Ghep cac doan video + audio
  5. UGC filter
  6. Overlay gia tien
  7. Burn phu de Khmer
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.tts_engine import synthesize_khmer
from core.subtitle_gen import generate_ass_file
from core.ffmpeg_utils import (
    burn_hardsub, get_video_duration,
    apply_ken_burns, assemble_video,
)
from core.overlay_renderer import add_price_overlay
from core.ugc_filters import apply_ugc_filter
from modes.fb_shorts.url_extractor import extract_ad_text

logger = logging.getLogger(__name__)

OUT_W, OUT_H = 1080, 1920
TARGET_MIN, TARGET_MAX = 15, 30


@dataclass
class GenerativeInputs:
    product_images:    list[str]         # 1-5 anh san pham
    price_text:        str               # "35,000 KHR" / "$5"
    ad_text_url:       str               # URL bai quang cao
    gemini_api_key:    str
    replicate_token:   str = ""          # Optional — fallback to Ken Burns if empty
    tts_voice:         str = "km-KH-SreymomNeural"
    tts_rate:          str = "+0%"
    ugc_intensity:     str = "medium"
    price_color:       str = "red"
    target_duration:   float = 20.0     # seconds (15-30)
    transition_speed:  str = "Bình thường (3.0s)"


def run_generative_mode(inputs: GenerativeInputs, output_dir: str, temp_dir: str) -> str:
    """
    Generative AI mode: Anh -> Video + TTS Khmer + UGC + Gia + Sub.
    """
    logger.info("\n" + "-" * 50)
    logger.info("  FB SHORTS — Sub-mode B: Generative AI")
    logger.info("-" * 50)

    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    target_dur = max(TARGET_MIN, min(TARGET_MAX, inputs.target_duration))

    # ── Step B.1: Extract ad text + Khmer script ──────────────────
    logger.info("[Step B.1] Extracting ad text + writing Khmer script...")
    try:
        raw_text = extract_ad_text(inputs.ad_text_url)
    except Exception as exc:
        logger.warning(f"    URL extraction failed: {exc}")
        raw_text = f"Best product at {inputs.price_text}"

    khmer_script = _generate_khmer_script(
        raw_text=raw_text,
        price=inputs.price_text,
        api_key=inputs.gemini_api_key,
        target_sec=int(target_dur),
    )
    logger.info(f"    Script ({len(khmer_script)} chars): {khmer_script[:80]}...")

    # ── Step B.2: TTS ─────────────────────────────────────────────
    logger.info("[Step B.2] Synthesizing Khmer voiceover...")
    tts_path = str(Path(temp_dir) / "gen_voice.mp3")
    synthesize_khmer(script_text=khmer_script, output_path=tts_path, voice=inputs.tts_voice, rate=inputs.tts_rate)
    audio_dur = get_video_duration(tts_path)
    target_dur = max(TARGET_MIN, min(TARGET_MAX, audio_dur + 1.0))
    logger.info(f"    Audio: {audio_dur:.1f}s  |  Target video: {target_dur:.1f}s")

    # ── Step B.3: Image -> Video ───────────────────────────────────
    logger.info("[Step B.3] Generating video clips from product images...")
    clip_dur = target_dur / max(len(inputs.product_images), 1)
    clip_dur = max(2.5, min(6.0, clip_dur))
    if "Rất nhanh" in inputs.transition_speed:
        clip_dur = 1.5
    elif "Nhanh" in inputs.transition_speed:
        clip_dur = 2.0
    elif "Chậm" in inputs.transition_speed:
        clip_dur = 4.0
    elif "Bình thường" in inputs.transition_speed:
        clip_dur = 3.0

    video_clips = []
    for i, img_path in enumerate(inputs.product_images[:5]):
        out_clip = str(Path(temp_dir) / f"gen_clip_{i:02d}.mp4")
        if inputs.replicate_token:
            try:
                _image_to_video_replicate(
                    image_path=img_path,
                    output_path=out_clip,
                    api_token=inputs.replicate_token,
                    duration=min(clip_dur, 4.0),
                )
                video_clips.append(out_clip)
                logger.info(f"    Replicate SVD: clip {i+1} done")
                continue
            except Exception as exc:
                logger.warning(f"    Replicate failed for image {i+1}: {exc}. Fallback to Ken Burns.")

        # Fallback: Ken Burns
        _ken_burns_single(img_path, out_clip, clip_dur, temp_dir, i)
        video_clips.append(out_clip)
        logger.info(f"    Ken Burns fallback: clip {i+1} done")

    # Repeat clips if not enough to cover audio
    while _total_dur(video_clips) < target_dur - 0.5:
        video_clips = video_clips + video_clips
    video_clips = video_clips[:int(target_dur / clip_dur) + 2]

    # ── Step B.4: Concatenate clips ────────────────────────────────
    logger.info("[Step B.4] Concatenating clips...")
    concat_path = str(Path(temp_dir) / "gen_concat.mp4")
    from core.concat_helper import concatenate_clips
    concatenate_clips(video_clips[:10], concat_path)

    # ── Step B.5: Merge TTS audio ──────────────────────────────────
    logger.info("[Step B.5] Merging TTS audio...")
    merged_path = str(Path(temp_dir) / "gen_merged.mp4")
    _merge_audio(concat_path, tts_path, merged_path, target_dur)

    # ── Step B.6: UGC filter ──────────────────────────────────────
    logger.info(f"[Step B.6] UGC filter ({inputs.ugc_intensity})...")
    ugc_path = str(Path(temp_dir) / "gen_ugc.mp4")
    apply_ugc_filter(merged_path, ugc_path, intensity=inputs.ugc_intensity,
                     out_w=OUT_W, out_h=OUT_H)

    # ── Step B.7: Price overlay ────────────────────────────────────
    logger.info("[Step B.7] Price overlay...")
    overlaid_path = str(Path(temp_dir) / "gen_price.mp4")
    add_price_overlay(
        input_path=ugc_path,
        output_path=overlaid_path,
        price_text=inputs.price_text,
        tagline_text="ដឹកជញ្ជូនឥតគិតថ្លៃ",
        bg_color=inputs.price_color,
    )

    # ── Step B.8: Burn subtitles ───────────────────────────────────
    logger.info("[Step B.8] Burning Khmer subtitles...")
    sub_ass = str(Path(temp_dir) / "gen_sub.ass")
    clip_timestamps = []
    curr = 0.0
    for _ in video_clips[:10]:
        curr += clip_dur
        clip_timestamps.append(curr)

    generate_ass_file(
        script_text=khmer_script,
        timestamps=clip_timestamps,
        output_path=sub_ass,
        font_name="Hanuman",
        )
    final_path = str(Path(output_dir) / "fb_gen_output.mp4")
    burn_hardsub(overlaid_path, sub_ass, "assets/fonts", final_path)

    logger.info(f"\n[OK] Generative pipeline complete: {final_path}")
    return final_path


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _generate_khmer_script(raw_text: str, price: str, api_key: str, target_sec: int = 20) -> str:
    if not api_key:
        return (
            f"ចូលមកសាកល្បង! ផលិតផលនេះល្អបំផុតសម្រាប់ខ្ញុំ។ "
            f"តម្លៃពិសេស {price}។ "
            f"ទទួលដឹកជញ្ជូនឥតគិតថ្លៃ ភ្លាមៗ!"
        )
    try:
        prompt = f"""Write a {target_sec}-second UGC voiceover script in Khmer for this product.

Product description: {raw_text[:500]}
Price: {price}

Style: Natural, conversational, like a real customer review video.
Structure: Hook (2s) -> Personal story/benefit (10-15s) -> Price reveal -> Quick CTA
Rules:
- End each sentence with ។
- Sound like a real person, not a formal ad
- Include natural hesitation words (ហ្មង, ចឹង, ដូចជា)
- Maximum {target_sec // 3} sentences
- Return ONLY the Khmer script"""

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.6-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as exc:
        logger.warning(f"Gemini script error: {exc}")
        return (
            f"ហ្មង... ខ្ញុំមិននឹកស្មានថា ផលិតផលនេះល្អម្ល៉េះ! "
            f"ដូចជា... ណាស់ ខ្ញុំប្រើជាច្រើនខែហើយ មិនដែលខក់ចិត្ត។ "
            f"តម្លៃ {price} ប៉ុណ្ណោះ ទទួលដឹកជញ្ជូនឥតគិតថ្លៃ!"
        )


def _image_to_video_replicate(image_path: str, output_path: str, api_token: str, duration: float = 4.0):
    """Call Replicate Stable Video Diffusion API."""
    import replicate
    import base64

    # Encode image
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = Path(image_path).suffix.lower().replace(".", "")
    data_url = f"data:image/{ext};base64,{b64}"

    client = replicate.Client(api_token=api_token)
    output = client.run(
        "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
        input={
            "input_image": data_url,
            "video_length": "14_frames_with_svd_xt",  # ~2s
            "sizing_strategy": "crop_to_16_9",
            "frames_per_second": 7,
            "motion_bucket_id": 80,
            "cond_aug": 0.02,
        },
    )

    # Download result
    video_url = str(output)
    import requests
    resp = requests.get(video_url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=131072):
            f.write(chunk)

    # Scale to portrait 9:16
    portrait_path = output_path.replace(".mp4", "_portrait.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", output_path,
        "-vf", f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-an",
        portrait_path,
    ]
    subprocess.run(cmd, capture_output=True)
    import shutil
    shutil.move(portrait_path, output_path)


def _ken_burns_single(image_path: str, output_path: str, duration: float, temp_dir: str, idx: int):
    """Create a Ken Burns clip from a single image."""
    apply_ken_burns(
        image_path=image_path,
        output_path=output_path,
        total_duration=duration,
        timestamps=[duration],
        zoom_start=1.0,
        zoom_end=1.05,
        pan_directions=[["center", "left", "right", "up"][idx % 4]],
        out_w=OUT_W,
        out_h=OUT_H,
        temp_dir=str(Path(temp_dir) / f"kb_{idx}"),
    )


def _total_dur(clip_paths: list[str]) -> float:
    total = 0.0
    for p in clip_paths:
        try:
            total += get_video_duration(p)
        except Exception:
            pass
    return total


def _merge_audio(video_path: str, audio_path: str, output_path: str, duration: float):
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
