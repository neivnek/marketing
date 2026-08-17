"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/polish/polish_pipeline.py — Polish Mode
====================================================================
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

from core.overlay_renderer import add_price_overlay, add_watermark_text
from core.social_proof_overlay import render_rating_stars, render_counter_badge
from modes.pro_editor.hook_variant_generator import generate_hook_clips, prepend_hook_to_body
from core.config import PolishInputs
from core.ffmpeg_utils import check_ffmpeg

logger = logging.getLogger(__name__)


def extract_first_frame(video_path: str, output_image: str):
    """Extracts the first frame of a video to use as a product image."""
    check_ffmpeg()
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_image
    ]
    subprocess.run(cmd, capture_output=True)


# Kho câu hook cho chế độ Polish, xếp theo góc tiếp cận khác nhau.
# Polish không có kịch bản nên trước đây mọi biến thể đều dùng chung chuỗi "🔥🔥🔥",
# khiến N bản A/B ra giống hệt nhau từng pixel — tức là test A/B vô nghĩa.
_POLISH_HOOK_ANGLES = [
    ("curiosity",    "XEM ĐẾN CUỐI NHÉ!"),
    ("question",     "BẠN ĐÃ THỬ CHƯA?"),
    ("urgency",      "SỐ LƯỢNG CÓ HẠN"),
    ("benefit",      "DÙNG LÀ MÊ NGAY"),
    ("shock_fact",   "ĐỪNG BỎ LỠ!"),
]


def _build_polish_hooks(inputs: PolishInputs) -> list[dict]:
    """
    Dựng danh sách hook khác nhau cho Polish, ưu tiên dữ liệu thật mà người dùng đã nhập
    (giá, lượt bán, đánh giá, tên thương hiệu) rồi mới tới các câu theo góc tiếp cận.
    """
    angles: list[tuple[str, str]] = []

    price = (inputs.price or "").strip()
    if inputs.add_price_badge and price:
        angles.append(("price", f"CHỈ {price}"))

    sold = str(getattr(inputs, "sold_count", "") or "").strip()
    if inputs.add_social_proof and sold:
        angles.append(("social_proof", f"ĐÃ BÁN {sold}"))

    rating = getattr(inputs, "rating", 0) or 0
    if inputs.add_social_proof and rating:
        angles.append(("rating", f"{rating:g} SAO ĐÁNH GIÁ"))

    brand = (inputs.watermark_text or "").strip()
    if brand:
        angles.append(("brand", brand.upper()))

    # Bổ sung từ kho câu chung cho tới khi đủ số biến thể, không lặp lại câu đã có
    seen = {text for _, text in angles}
    for angle, text in _POLISH_HOOK_ANGLES:
        if len(angles) >= inputs.hook_variants:
            break
        if text not in seen:
            angles.append((angle, text))
            seen.add(text)

    hooks = []
    for i in range(inputs.hook_variants):
        angle, text = angles[i % len(angles)]
        hooks.append({
            "variant_id":     i + 1,
            "hook_type":      angle,
            "voiceover_text": text,
            "on_screen_text": text,
        })
    logger.info(f"[POLISH] Hook variants: {[h['on_screen_text'] for h in hooks]}")
    return hooks


def run_polish_pipeline(inputs: PolishInputs, output_dir: str, temp_dir: str) -> list[str]:
    """
    Polish Mode:
    Takes an existing video (e.g., from dub_only or full_remix) and applies post-processing:
    - Watermark
    - Price badge
    - Social proof
    - Generates N hook variants and prepends them, yielding N outputs.
    """
    logger.info("=== STARTING POLISH PIPELINE ===")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    current_video = inputs.source_video_path
    base_name = Path(current_video).stem

    # 1. Color grading (light enhancement) and Watermark
    processed_video = os.path.join(temp_dir, "polish_step1.mp4")
    if inputs.watermark_text:
        logger.info(f"[POLISH] Adding watermark: {inputs.watermark_text}")
        add_watermark_text(current_video, processed_video, text=inputs.watermark_text)
        current_video = processed_video
    else:
        # Just color grade lightly
        cmd = [
            "ffmpeg", "-y",
            "-i", current_video,
            "-vf", "eq=saturation=1.1:contrast=1.05",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            processed_video
        ]
        subprocess.run(cmd, capture_output=True)
        current_video = processed_video

    # 2. Price Badge
    if inputs.add_price_badge and inputs.price:
        logger.info(f"[POLISH] Adding price badge: {inputs.price}")
        price_video = os.path.join(temp_dir, "polish_step2.mp4")
        add_price_overlay(current_video, price_video, price_text=inputs.price)
        current_video = price_video

    # 3. Social Proof
    if inputs.add_social_proof:
        logger.info(f"[POLISH] Adding social proof: rating={inputs.rating}, sold={inputs.sold_count}")
        social_video_1 = os.path.join(temp_dir, "polish_step3a.mp4")
        social_video_2 = os.path.join(temp_dir, "polish_step3b.mp4")
        
        # Apply rating
        render_rating_stars(
            current_video, social_video_1,
            badge_text=f"★★★★★ {inputs.rating}/5",
            position="top_center"
        )
        # Apply counter
        render_counter_badge(
            social_video_1, social_video_2,
            badge_text=f"{inputs.sold_count} ĐÃ MUA",
            position="upper_third"
        )
        current_video = social_video_2

    final_outputs = []

    # 4. Hook Variants
    if inputs.hook_variants > 0:
        logger.info(f"[POLISH] Generating {inputs.hook_variants} hook variants...")
        first_frame = os.path.join(temp_dir, "first_frame.jpg")
        extract_first_frame(current_video, first_frame)
        
        hook_clips = generate_hook_clips(
            hook_variants=_build_polish_hooks(inputs),
            product_image=first_frame,
            temp_dir=temp_dir,
        )

        for i, clip_info in enumerate(hook_clips):
            hook_clip = clip_info["clip_path"]
            out_file = os.path.join(output_dir, f"{base_name}_hook{i+1}_polished.mp4")
            prepend_hook_to_body(hook_clip, current_video, out_file, temp_dir)
            final_outputs.append(out_file)
    else:
        out_file = os.path.join(output_dir, f"{base_name}_polished.mp4")
        shutil.copy(current_video, out_file)
        final_outputs.append(out_file)

    logger.info(f"=== FINISHED POLISH PIPELINE: generated {len(final_outputs)} video(s) ===")
    return final_outputs
