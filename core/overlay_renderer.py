"""
====================================================================
  Pipeline v3.0
  File: core/overlay_renderer.py — Price + Text Overlay via FFmpeg
====================================================================

Ve gia tien va text quang cao len video dung FFmpeg drawtext filter.
Ho tro font Khmer (Noto Sans Khmer) va tieng Viet (Noto Sans).
"""

import logging
import os
import subprocess
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Font paths (auto-download if missing)
# ──────────────────────────────────────────────

FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"
FONT_KHMER = FONT_DIR / "NotoSansKhmer-Bold.ttf"
FONT_LATIN = FONT_DIR / "NotoSans-Bold.ttf"

FONT_URLS = {
    "NotoSansKhmer-Bold.ttf": (
        "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansKhmer/NotoSansKhmer-Bold.ttf"
    ),
    "NotoSans-Bold.ttf": (
        "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf"
    ),
}


def _ensure_fonts():
    """Download Noto fonts if they don't exist."""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for fname, url in FONT_URLS.items():
        dest = FONT_DIR / fname
        if not dest.exists():
            logger.info(f"[Overlay] Downloading font: {fname}")
            try:
                urllib.request.urlretrieve(url, str(dest))
                logger.info(f"[Overlay] Font ready: {fname}")
            except Exception as exc:
                logger.warning(f"[Overlay] Font download failed ({fname}): {exc}")


def _run(cmd: list[str], label: str = ""):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error [{label}]:\n{result.stderr[-800:]}")


def add_price_overlay(
    input_path:   str,
    output_path:  str,
    price_text:   str,
    tagline_text: str = "",
    position:     str = "bottom",   # "bottom" | "top" | "center"
    bg_color:     str = "red",      # "red" | "black" | "white" | "orange"
) -> str:
    """
    Overlay a bold price badge + optional tagline onto a video.

    Layout (bottom):
      - Background bar at bottom 18% of screen
      - Price text (large, bold, white) centered
      - Tagline text (smaller) above price
    """
    _ensure_fonts()

    font_path = str(FONT_KHMER).replace("\\", "/").replace(":", "\\:") if FONT_KHMER.exists() else ""
    font_latin = str(FONT_LATIN).replace("\\", "/").replace(":", "\\:") if FONT_LATIN.exists() else ""

    w, h = 1080, 1920

    # Position config
    POS = {
        "bottom": {"bar_y": int(h * 0.78), "bar_h": int(h * 0.22)},
        "top":    {"bar_y": 0,             "bar_h": int(h * 0.18)},
        "center": {"bar_y": int(h * 0.40), "bar_h": int(h * 0.20)},
    }
    pos = POS.get(position, POS["bottom"])
    bar_y    = pos["bar_y"]
    bar_h    = pos["bar_h"]
    bar_btm  = bar_y + bar_h

    # Color config
    COLORS = {
        "red":    ("0xCC0000@0.92", "0xFFFFFF"),
        "black":  ("0x000000@0.88", "0xFFFFFF"),
        "white":  ("0xFFFFFF@0.90", "0x111111"),
        "orange": ("0xE65100@0.92", "0xFFFFFF"),
    }
    bg_hex, txt_hex = COLORS.get(bg_color, COLORS["red"])

    price_y   = bar_y + bar_h // 2 + (20 if tagline_text else 0)
    tagline_y = bar_y + 30

    # Build drawbox + drawtext filters
    filters = []

    # Background bar
    filters.append(
        f"drawbox=x=0:y={bar_y}:w={w}:h={bar_h}:"
        f"color={bg_hex}:t=fill"
    )

    # Tagline (optional)
    if tagline_text and font_path:
        filters.append(
            f"drawtext=fontfile='{font_path}'"
            f":text='{_escape(tagline_text)}'"
            f":fontcolor={txt_hex}@0.85"
            f":fontsize=42"
            f":x=(w-text_w)/2"
            f":y={tagline_y}"
            f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
        )

    # Price text
    price_font = font_latin if font_latin else font_path
    if price_font:
        filters.append(
            f"drawtext=fontfile='{price_font}'"
            f":text='{_escape(price_text)}'"
            f":fontcolor={txt_hex}"
            f":fontsize=72"
            f":x=(w-text_w)/2"
            f":y={price_y}"
            f":shadowcolor=black@0.6:shadowx=3:shadowy=3"
        )

    vf = ",".join(filters) if filters else "null"

    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    _run(cmd, label="price_overlay")
    logger.info(f"[Overlay] Price overlay done -> {Path(output_path).name}")
    return output_path


def add_watermark_text(
    input_path:  str,
    output_path: str,
    text:        str,
    position:    str = "top_right",
) -> str:
    """
    Add small semi-transparent watermark text (e.g. brand name).
    """
    _ensure_fonts()
    font_path = str(FONT_LATIN).replace("\\", "/").replace(":", "\\:") if FONT_LATIN.exists() else ""

    POS_MAP = {
        "top_right":    ("w-text_w-30", "30"),
        "top_left":     ("30", "30"),
        "bottom_right": ("w-text_w-30", "h-text_h-30"),
        "bottom_left":  ("30", "h-text_h-30"),
    }
    x, y = POS_MAP.get(position, POS_MAP["top_right"])

    vf = (
        f"drawtext=fontfile='{font_path}'"
        f":text='{_escape(text)}'"
        f":fontcolor=FFFFFF@0.55"
        f":fontsize=32"
        f":x={x}:y={y}"
    ) if font_path else "null"

    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", "-pix_fmt", "yuv420p",
        output_path,
    ]
    _run(cmd, label="watermark")
    return output_path


def add_title_overlay(
    input_path:  str,
    output_path: str,
    text:        str,
    style:       str = "Khung Xanh (Mặc định)",
) -> str:
    """Add a clean, bold title overlay at the top (used for on_screen_text)."""
    _ensure_fonts()
    font_path = str(FONT_KHMER).replace("\\", "/").replace(":", "\\:") if FONT_KHMER.exists() else ""
    if not font_path:
        import shutil
        shutil.copy(input_path, output_path)
        return output_path

    STYLES = {
        "Khung Xanh (Mặc định)": ("white", "box=1:boxcolor=0x22c55e@0.9:boxborderw=20"),
        "Khung Đỏ": ("white", "box=1:boxcolor=0xef4444@0.9:boxborderw=20"),
        "Khung Đen Chữ Vàng": ("0xfacc15", "box=1:boxcolor=0x000000@0.8:boxborderw=20"),
        "Chữ Xanh Viền Trắng": ("0x22c55e", "box=0:borderw=5:bordercolor=white"),
        "Chữ Trắng Viền Đen": ("white", "box=0:borderw=5:bordercolor=black"),
    }
    
    fontcolor, box_style = STYLES.get(style, STYLES["Khung Xanh (Mặc định)"])

    vf = (
        f"drawtext=fontfile='{font_path}'"
        f":text='{_escape(text)}'"
        f":fontcolor={fontcolor}"
        f":fontsize=52"
        f":{box_style}"
        f":x=(w-text_w)/2:y=h*0.10"
        f":shadowcolor=black@0.4:shadowx=2:shadowy=2"
    )

    os.makedirs(str(Path(output_path).parent), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", "-pix_fmt", "yuv420p",
        output_path,
    ]
    _run(cmd, label="title_overlay")
    return output_path


def _escape(text: str) -> str:
    """Escape special chars for FFmpeg drawtext."""
    return (
        text
        .replace("'", "\u2019")
        .replace(":", "\\:")
        .replace("%", "\\%")
        .replace("\\", "/")
    )
