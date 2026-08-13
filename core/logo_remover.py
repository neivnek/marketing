"""
====================================================================
  Logo & Watermark Remover Engine
  File: core/logo_remover.py
====================================================================
Sử dụng FFmpeg Delogo & Spatial Blur Filter để xóa logo, watermark,
hoặc ID TikTok/Douyin nhảy góc trên video clip B-roll.
"""

import os
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

def _get_video_dimensions(video_path: str) -> tuple[int, int]:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            video_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            w_str, h_str = res.stdout.strip().split('x')
            return int(w_str), int(h_str)
    except Exception:
        pass
    return 1080, 1920

def remove_video_logo(
    input_video_path: str,
    output_video_path: str,
    x: int = 50,
    y: int = 50,
    w: int = 200,
    h: int = 100,
    mode: str = "auto_tiktok"
) -> Optional[str]:
    """
    Xóa logo/watermark khỏi video bằng FFmpeg.
    - mode="auto_tiktok": Tự động xóa watermark TikTok nhảy góc trên (Top-Left) & góc dưới (Bottom-Right).
    - mode="custom_box": Xóa vùng logo theo tọa độ x, y, w, h nhập vào.
    - mode="blur": Làm mờ nhẹ vùng logo.
    """
    if not os.path.isfile(input_video_path):
        logger.error(f"[LogoRemover] File không tồn tại: {input_video_path}")
        return None

    os.makedirs(os.path.dirname(output_video_path) or "output", exist_ok=True)

    if mode == "auto_tiktok":
        vid_w, vid_h = _get_video_dimensions(input_video_path)
        # Tính toán tọa độ tĩnh (delogo không hỗ trợ biểu thức biến như w, h)
        x2 = max(0, vid_w - 250)
        y2 = max(0, vid_h - 180)
        filter_str = f"delogo=x=30:y=50:w=220:h=120,delogo=x={x2}:y={y2}:w=220:h=120"
    elif mode == "blur":
        filter_str = f"crop=w={w}:h={h}:x={x}:y={y},boxblur=luma_radius=10:luma_power=2[blur];[0:v][blur]overlay=x={x}:y={y}"
    else:
        filter_str = f"delogo=x={x}:y={y}:w={w}:h={h}"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video_path,
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        output_video_path
    ]

    try:
        logger.info(f"[LogoRemover] Đang xóa logo (chế độ: {mode}): {input_video_path}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.isfile(output_video_path):
            return output_video_path
        else:
            logger.warning(f"[LogoRemover] FFmpeg lỗi: {res.stderr[-200:]}")
    except Exception as e:
        logger.error(f"[LogoRemover] Exception: {e}")

    # Fallback to original
    import shutil
    shutil.copy(input_video_path, output_video_path)
    return output_video_path
