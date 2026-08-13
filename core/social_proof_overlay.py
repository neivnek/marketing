"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/social_proof_overlay.py — Social Proof Badge Renderer
====================================================================

Renders social proof overlays using FFmpeg drawtext/drawbox,
matching the visual convention of overlay_renderer.py (consistent look).

3 style variants:
  - rating_stars    : "★★★★★ 4.8/5" — only use real numbers from ProductResearch
  - counter         : "5000+ ĐÃ MUA" — only use real numbers from ProductResearch
  - testimonial_quote: short customer quote (distinct style, clearly labelled as customer)

RULE 21: Any number displayed MUST come from ProductResearch (real data).
         If no real number is available, use a qualitative phrase instead.
         Never display made-up statistics.

Falls back gracefully (copies input) if FFmpeg drawtext fails.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Font path used across all overlay types — must match overlay_renderer.py
_DEFAULT_FONT = "assets/fonts/Hanuman.ttf"


def _font_arg(font_path: str) -> str:
    """Return FFmpeg fontfile= arg or fallback to sans."""
    if os.path.exists(font_path):
        abs_path = os.path.abspath(font_path).replace("\\", "/").replace(":", "\\:")
        return f"fontfile={abs_path}"
    return "font=sans"


def _escape(text: str) -> str:
    """Escape FFmpeg drawtext special chars."""
    return (
        text
        .replace("\\", "\\\\")
        .replace("'",  "\\'")
        .replace(":",  "\\:")
        .replace("%",  "\\%")
    )


def _y_expr(position: str) -> str:
    y_map = {
        "top_center":    "h*0.06",
        "center":        "(h-th)/2",
        "bottom_center": "h-th-h*0.06",
        "upper_third":   "h*0.20",
    }
    return y_map.get(position, "h*0.06")


# ── Style: rating_stars ───────────────────────────────────────────

def render_rating_stars(
    input_video:    str,
    output_video:   str,
    badge_text:     str,
    position:       str = "top_center",
    font_path:      str = _DEFAULT_FONT,
    font_size:      int = 48,
    start_sec:      float = 0.5,
    duration_sec:   float = 0.0,
) -> str:
    """
    Render a star rating badge, e.g. "★★★★★  4.8/5".

    The badge_text MUST come from ProductResearch.common_praise or verified data.
    If no real rating is available, use a qualitative phrase like "Được nhiều khách tin dùng".

    RULE 21: Never pass made-up numbers to this function.
    """
    return _render_badge(
        input_video=input_video,
        output_video=output_video,
        badge_text=badge_text,
        position=position,
        font_path=font_path,
        font_size=font_size,
        box_color="0x1a1a2e@0.88",   # same dark navy as overlay_renderer badges
        font_color="white",
        box_border=14,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )


# ── Style: counter ────────────────────────────────────────────────

def render_counter_badge(
    input_video:    str,
    output_video:   str,
    badge_text:     str,
    position:       str = "top_center",
    font_path:      str = _DEFAULT_FONT,
    font_size:      int = 52,
    start_sec:      float = 0.5,
    duration_sec:   float = 0.0,
) -> str:
    """
    Render a counter badge, e.g. "5000+ ĐÃ MUA" or "ខ្ញុំ+ បានទិញ".

    RULE 21: badge_text number MUST be from ProductResearch.
    If unknown, use qualitative text: "ម្ចាស់ជាច្រើននិយម" / "Nhiều khách yêu thích".
    """
    return _render_badge(
        input_video=input_video,
        output_video=output_video,
        badge_text=badge_text,
        position=position,
        font_path=font_path,
        font_size=font_size,
        box_color="0x0d1117@0.90",
        font_color="#FFD700",   # gold text for counter — stands out visually
        box_border=16,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )


# ── Style: testimonial_quote ──────────────────────────────────────

def render_testimonial_quote(
    input_video:    str,
    output_video:   str,
    quote_text:     str,
    position:       str = "upper_third",
    font_path:      str = _DEFAULT_FONT,
    font_size:      int = 38,
    start_sec:      float = 1.0,
    duration_sec:   float = 0.0,
) -> str:
    """
    Render a short customer testimonial quote (< 15 words), paraphrased from
    ProductResearch.common_praise. Styled distinctly from subtitles so viewers
    clearly recognize this as "customer voice", not ad copy.

    Uses italic-style contrast via different box color (teal/cyan background).
    """
    # Ensure quote does not exceed 15 words
    words = quote_text.strip().split()
    if len(words) > 15:
        quote_text = " ".join(words[:15]) + "…"

    return _render_badge(
        input_video=input_video,
        output_video=output_video,
        badge_text=f"\" {quote_text} \"",   # wrap in quotes to signal it's a testimonial
        position=position,
        font_path=font_path,
        font_size=font_size,
        box_color="0x006064@0.85",   # teal — distinct from subtitle (black) and price (navy)
        font_color="white",
        box_border=12,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )


# ── Smart Badge Selector ──────────────────────────────────────────

def render_proof_badge(
    input_video:    str,
    output_video:   str,
    badge_text:     str,
    style:          str   = "counter",   # "rating_stars" | "counter" | "testimonial_quote"
    position:       str   = "top_center",
    duration_sec:   float = 0.0,
    font_path:      str   = _DEFAULT_FONT,
) -> str:
    """
    Smart selector — routes to the right style function based on `style` param.

    Parameters
    ----------
    badge_text  : Text to display. MUST be real data (Rule 21).
    style       : "rating_stars" | "counter" | "testimonial_quote"
    position    : Placement: "top_center" | "center" | "bottom_center" | "upper_third"
    duration_sec: 0 = show entire video, >0 = show for duration_sec seconds.

    Returns
    -------
    str — output_video path.
    """
    if not badge_text or not badge_text.strip():
        if input_video != output_video:
            shutil.copy(input_video, output_video)
        return output_video

    os.makedirs(str(Path(output_video).parent), exist_ok=True)

    style = style.lower()
    if style == "rating_stars":
        return render_rating_stars(input_video, output_video, badge_text, position, font_path,
                                   duration_sec=duration_sec)
    elif style == "testimonial_quote":
        return render_testimonial_quote(input_video, output_video, badge_text, position, font_path,
                                        duration_sec=duration_sec)
    else:
        # default: counter
        return render_counter_badge(input_video, output_video, badge_text, position, font_path,
                                    duration_sec=duration_sec)


# ── Legacy wrapper kept for backward-compat with pro_editor_pipeline ─

def add_social_proof_badge(
    input_video:  str,
    output_video: str,
    badge_text:   str,
    font_path:    str   = _DEFAULT_FONT,
    font_size:    int   = 52,
    position:     str   = "top_center",
    start_sec:    float = 0.5,
    duration_sec: float = 0.0,
) -> str:
    """
    Backward-compatible entry point used by pro_editor_pipeline.py.
    Delegates to render_counter_badge (default style).
    """
    return render_counter_badge(
        input_video=input_video,
        output_video=output_video,
        badge_text=badge_text,
        position=position,
        font_path=font_path,
        font_size=font_size,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )


# ── Core Renderer (shared by all styles) ─────────────────────────

def _render_badge(
    input_video:  str,
    output_video: str,
    badge_text:   str,
    position:     str,
    font_path:    str,
    font_size:    int,
    box_color:    str,
    font_color:   str,
    box_border:   int,
    start_sec:    float,
    duration_sec: float,
) -> str:
    """Shared FFmpeg drawtext renderer for all badge styles."""
    os.makedirs(str(Path(output_video).parent), exist_ok=True)
    font_arg  = _font_arg(font_path)
    text_clean = _escape(badge_text)
    y_expr    = _y_expr(position)

    if duration_sec > 0:
        enable_expr = f"between(t,{start_sec:.2f},{start_sec + duration_sec:.2f})"
    else:
        enable_expr = f"gte(t,{start_sec:.2f})"

    drawtext = (
        f"drawtext={font_arg}"
        f":text='{text_clean}'"
        f":fontsize={font_size}"
        f":fontcolor={font_color}"
        f":box=1"
        f":boxcolor={box_color}"
        f":boxborderw={box_border}"
        f":x=(w-tw)/2"
        f":y={y_expr}"
        f":enable='{enable_expr}'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        output_video,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            f"[SocialProof] drawtext failed (copying original): {result.stderr[-250:]}"
        )
        shutil.copy(input_video, output_video)
        return output_video

    logger.info(f"[SocialProof] Badge burned -> {Path(output_video).name}")
    return output_video
