"""
====================================================================
  Multi-Variant Ad Engine  (Lấy cảm hứng từ Google ViGenAiR)
  File: core/multi_variant_engine.py
====================================================================
Tái hiện thuật toán chiến lược của ViGenAiR (cắt 1 nguồn B-roll
thành 3 biến thể video nhắm các mục tiêu khác nhau) hoàn toàn
bằng Python + Gemini + FFmpeg — không cần Google Cloud Platform.

3 Biến thể theo framework ABCDs của Google:
  • A — Awareness (15s): Hook gây ấn tượng → Show sản phẩm
  • B — Consideration (30s): Vấn đề → Giải pháp → Bằng chứng
  • C — Action (10s): Giá + CTA mạnh → Hành động khẩn cấp
"""

import os
import re
import json
import logging
import shutil
import subprocess
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Prompt Templates ─────────────────────────────────────────────

_VARIANT_PROMPT = """Bạn là chuyên gia marketing theo framework ABCDs của Google.
Dựa trên thông tin sản phẩm sau:

- Tên: {product_name}
- Giá: {price}
- Mô tả: {short_description}
- Tính năng: {features}
- Vấn đề giải quyết: {pain_points}
- Đối tượng: {target_audience}

Hãy viết script cho 3 biến thể video quảng cáo theo framework ABCDs. Trả về JSON thuần (không markdown):
{{
  "variant_awareness": {{
    "duration_sec": 15,
    "goal": "Awareness — Gây ấn tượng, tạo nhận biết thương hiệu",
    "voiceover": "Lời thoại tiếng Việt ngắn gọn (~15s, khoảng 35-40 từ)",
    "overlay_text": "Chữ nổi bật trên màn hình (dưới 6 từ)",
    "caption": "Caption cho Facebook/TikTok post",
    "hashtags": "#hashtag1 #hashtag2 #hashtag3"
  }},
  "variant_consideration": {{
    "duration_sec": 30,
    "goal": "Consideration — Thuyết phục, tạo nhu cầu",
    "voiceover": "Lời thoại tiếng Việt đầy đủ (~30s, khoảng 70-80 từ). Cấu trúc: Nêu vấn đề → Giới thiệu giải pháp → Bằng chứng / công dụng → CTA nhẹ",
    "overlay_text": "Chữ nổi bật (dưới 6 từ)",
    "caption": "Caption cho Facebook/TikTok post",
    "hashtags": "#hashtag1 #hashtag2 #hashtag3"
  }},
  "variant_action": {{
    "duration_sec": 10,
    "goal": "Action — Chốt đơn, kêu gọi hành động khẩn cấp",
    "voiceover": "Lời thoại tiếng Việt rất ngắn (~10s, khoảng 20-25 từ). Tập trung vào: Giá hấp dẫn + CTA mạnh (Mua ngay / Đặt hàng ngay / Inbox ngay)",
    "overlay_text": "GIÁ + CTA (dưới 6 từ)",
    "caption": "Caption ngắn gọn, urgent",
    "hashtags": "#hashtag1 #hashtag2"
  }}
}}"""


def _generate_variant_scripts(product_info: dict) -> Optional[dict]:
    """Dùng Gemini viết script cho 3 biến thể video."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = _VARIANT_PROMPT.format(
            product_name=product_info.get("product_name", "sản phẩm"),
            price=product_info.get("price", "Liên hệ"),
            short_description=product_info.get("short_description", ""),
            features=", ".join(product_info.get("key_features", [])),
            pain_points=", ".join(product_info.get("pain_points", [])),
            target_audience=product_info.get("target_audience", "Khách hàng phổ thông"),
        )

        response = None
        for model in ["gemini-3.6-flash", "gemini-flash-latest", "gemini-2.0-flash"]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=8192,
                        response_mime_type="application/json",
                    ),
                )
                if response and response.text:
                    break
            except Exception:
                continue

        if not response or not response.text:
            return None

        raw = response.text.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        return json.loads(raw.strip())

    except Exception as e:
        logger.error(f"[MultiVariant] Lỗi sinh script: {e}")
        return None


def _render_variant_video(
    variant_key: str,
    variant_data: dict,
    broll_clips: list,
    product_image: str,
    output_path: str,
    temp_dir: str,
) -> Optional[str]:
    """
    Render một biến thể video từ B-roll clips + TTS + chữ nổi.
    Dùng FFmpeg để:
    1. Cắt B-roll clip theo duration.
    2. Sinh TTS từ voiceover text.
    3. Ghép video + audio + overlay text.
    """
    from core.tts_engine import generate_tts

    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    duration = float(variant_data.get("duration_sec", 15))
    voiceover = variant_data.get("voiceover", "")
    overlay = variant_data.get("overlay_text", "")

    # 1. TTS
    tts_path = os.path.join(temp_dir, f"{variant_key}_tts.mp3")
    if voiceover:
        generate_tts(text=voiceover, output_path=tts_path, voice="vi-VN-HoaiMyNeural")

    # 2. Chọn B-roll source
    broll_src = None
    if broll_clips:
        broll_src = broll_clips[0]
    elif product_image and os.path.isfile(product_image):
        broll_src = product_image

    if not broll_src:
        logger.warning(f"[MultiVariant] Không có B-roll cho {variant_key}, dùng màn đen")
        broll_src = None

    # 3. Build FFmpeg command
    vf_filter = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    )
    if overlay:
        safe_overlay = overlay.replace("'", "\\'").replace(":", "\\:")
        vf_filter += (
            f",drawtext=text='{safe_overlay}'"
            ":fontfile=assets/fonts/Hanuman.ttf"
            ":fontcolor=white:fontsize=56"
            ":x=(w-text_w)/2:y=h-220"
            ":box=1:boxcolor=black@0.65:boxborderw=14"
        )

    tts_exists = os.path.isfile(tts_path)

    if broll_src and broll_src.endswith((".mp4", ".mov", ".avi", ".mkv")):
        # Video source
        cmd = [
            "ffmpeg", "-y",
            "-i", broll_src,
        ]
        if tts_exists:
            cmd += ["-i", tts_path]
        cmd += [
            "-vf", vf_filter,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
        ]
        if tts_exists:
            cmd += ["-c:a", "aac", "-shortest"]
        else:
            cmd += ["-an"]
        cmd.append(output_path)

    elif broll_src:
        # Image source → Ken Burns zoom
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", broll_src,
        ]
        if tts_exists:
            cmd += ["-i", tts_path]
        nframes = int(duration * 30)
        cmd += [
            "-vf",
            f"zoompan=z='min(zoom+0.0015,1.15)':d={nframes}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,{vf_filter}",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
        ]
        if tts_exists:
            cmd += ["-c:a", "aac", "-shortest"]
        else:
            cmd += ["-an"]
        cmd.append(output_path)

    else:
        # Black fallback
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=1080x1920:r=30:d={duration}",
        ]
        if tts_exists:
            cmd += ["-i", tts_path, "-c:a", "aac", "-shortest"]
        cmd += [
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.isfile(output_path):
            logger.info(f"[MultiVariant] ✓ Đã render {variant_key}: {output_path}")
            return output_path
        else:
            logger.error(f"[MultiVariant] FFmpeg lỗi {variant_key}: {result.stderr[-300:]}")
            return None
    except Exception as e:
        logger.error(f"[MultiVariant] Lỗi render {variant_key}: {e}")
        return None


def generate_multi_variants(
    product_info: dict,
    broll_clips: list,
    output_dir: str = "output",
    temp_dir: str = "temp/multi_variant",
) -> List[Dict]:
    """
    Hàm chính: Nhận thông tin sản phẩm + danh sách B-roll clips →
    Tạo ra 3 biến thể video (Awareness/Consideration/Action) + assets text.

    Trả về list[dict]:
    [
      {
        "variant": "awareness",
        "goal": "...",
        "video_path": "output/awareness_15s.mp4",
        "caption": "...",
        "hashtags": "...",
        "duration_sec": 15,
        "voiceover": "..."
      },
      ...
    ]
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    slug = re.sub(r"[^a-z0-9]", "_", product_info.get("product_name", "product").lower())[:20]

    logger.info("[MultiVariant] Đang sinh script 3 biến thể với Gemini...")
    scripts = _generate_variant_scripts(product_info)
    if not scripts:
        logger.error("[MultiVariant] Không thể sinh script.")
        return []

    product_image = product_info.get("image_path", "")

    results = []
    variant_map = {
        "awareness": ("variant_awareness", f"{slug}_awareness_15s.mp4"),
        "consideration": ("variant_consideration", f"{slug}_consideration_30s.mp4"),
        "action": ("variant_action", f"{slug}_action_10s.mp4"),
    }

    for variant_name, (script_key, filename) in variant_map.items():
        variant_data = scripts.get(script_key, {})
        if not variant_data:
            logger.warning(f"[MultiVariant] Thiếu script cho {variant_name}")
            continue

        output_path = os.path.join(output_dir, filename)
        # Dùng B-roll clip theo thứ tự
        broll_for_variant = broll_clips[:2] if broll_clips else []

        logger.info(f"[MultiVariant] Đang render biến thể: {variant_name.upper()}...")
        rendered = _render_variant_video(
            variant_key=variant_name,
            variant_data=variant_data,
            broll_clips=broll_for_variant,
            product_image=product_image,
            output_path=output_path,
            temp_dir=os.path.join(temp_dir, variant_name),
        )

        results.append({
            "variant": variant_name,
            "goal": variant_data.get("goal", ""),
            "video_path": rendered,
            "caption": variant_data.get("caption", ""),
            "hashtags": variant_data.get("hashtags", ""),
            "duration_sec": variant_data.get("duration_sec", 15),
            "voiceover": variant_data.get("voiceover", ""),
        })

    # Lưu text assets ra file
    text_assets_path = os.path.join(output_dir, f"{slug}_text_assets.txt")
    try:
        with open(text_assets_path, "w", encoding="utf-8") as f:
            f.write(f"=== TEXT ASSETS: {product_info.get('product_name')} ===\n\n")
            for r in results:
                f.write(f"[{r['variant'].upper()} — {r['duration_sec']}s]\n")
                f.write(f"Mục tiêu: {r['goal']}\n")
                f.write(f"Voiceover: {r['voiceover']}\n")
                f.write(f"Caption: {r['caption']}\n")
                f.write(f"Hashtags: {r['hashtags']}\n\n")
        logger.info(f"[MultiVariant] Text assets đã lưu: {text_assets_path}")
    except Exception as e:
        logger.warning(f"[MultiVariant] Không lưu được text assets: {e}")

    logger.info(f"[MultiVariant] Hoàn tất: {len([r for r in results if r['video_path']])} / 3 biến thể thành công.")
    return results
