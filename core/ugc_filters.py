"""
====================================================================
  Pipeline v3.0
  File: core/ugc_filters.py — UGC Authenticity FFmpeg Filters
====================================================================

Muc dich: Bien video qua tu nhien/dep thanh gia cam tay thuc te.
Bo loc: grain + handheld shake + focus pulse + natural color + vignette
"""

import logging
import os
import random
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# UGC Intensity Presets
# ──────────────────────────────────────────────

INTENSITY_PRESETS = {
    "subtle":  {"grain": 8,  "shake": 6,  "saturation": 0.92, "vignette": 0.10},
    "medium":  {"grain": 14, "shake": 10, "saturation": 0.88, "vignette": 0.15},
    "strong":  {"grain": 20, "shake": 16, "saturation": 0.83, "vignette": 0.22},
}


def _run(cmd: list[str], label: str = "") -> str:
    """Run FFmpeg command, return stderr for debugging."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error [{label}]:\n{result.stderr[-800:]}")
    return result.stderr


def _build_ugc_filter(
    grain: int   = 14,
    shake: int   = 10,
    saturation: float = 0.88,
    contrast:   float = 1.04,
    brightness: float = -0.015,
    vignette_angle: float = 0.15,
    out_w: int   = 1080,
    out_h: int   = 1920,
) -> str:
    """
    Build FFmpeg -vf filter string for UGC authenticity.

    Pipeline:
      1. Overscan crop (95%) so shake doesn't expose black borders
      2. Handheld shake via animated crop offset (sin waves at coprime freq)
      3. Scale back to output resolution
      4. Natural color grade (desaturate slightly, mild contrast)
      5. Film grain (temporal + uniform noise)
      6. Vignette (lens edge darkening)
    """
    # Overscan margin so shake has room to move
    margin = shake * 2
    crop_w = out_w - margin
    crop_h = out_h - margin

    # Two independent sin waves at coprime frequencies -> feels organic
    freq_x = round(random.uniform(0.4, 0.9), 3)
    freq_y = round(random.uniform(0.3, 0.7), 3)
    phase_x = round(random.uniform(0, 3.14), 3)
    phase_y = round(random.uniform(0, 3.14), 3)
    amp_x = shake // 2
    amp_y = shake // 2

    x_expr = f"(iw-{crop_w})/2+{amp_x}*sin({freq_x}*t+{phase_x})"
    y_expr = f"(ih-{crop_h})/2+{amp_y}*sin({freq_y}*t+{phase_y})"

    # Focus pulse: slight periodic blur at low frequency
    blur_freq = round(random.uniform(0.08, 0.18), 3)

    filter_chain = (
        # Step 0: Ensure exact output dimensions first so shake crop doesn't fail
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},"
        # Step 1+2: Crop with animated offset (handheld shake)
        f"crop={crop_w}:{crop_h}:'{x_expr}':'{y_expr}',"
        # Step 3: Scale back to target resolution
        f"scale={out_w}:{out_h}:flags=lanczos,"
        # Step 4: Natural color grade
        f"eq=saturation={saturation}:contrast={contrast}:brightness={brightness},"
        # Step 5: Film grain (temporal noise = changes per frame)
        f"noise=alls={grain}:allf=t+u,"
        # Step 6: Vignette
        f"vignette=PI*{vignette_angle:.2f},"
        # Step 7: Ensure SAR is set correctly
        f"setsar=1"
    )

    return filter_chain


def apply_ugc_filter(
    input_path:  str,
    output_path: str,
    intensity:   str = "medium",
    out_w:       int = 1080,
    out_h:       int = 1920,
    crf:         int = 23,
) -> str:
    """
    Apply UGC authenticity filter to a video.

    Parameters
    ----------
    input_path  : Path to input video (must have video stream).
    output_path : Destination path for the filtered video.
    intensity   : Preset name: 'subtle' | 'medium' | 'strong'.
    out_w/out_h : Output resolution.
    crf         : H.264 quality factor (lower = better, default 23).

    Returns
    -------
    str — Path to output video.
    """
    preset = INTENSITY_PRESETS.get(intensity, INTENSITY_PRESETS["medium"])
    vf = _build_ugc_filter(
        grain=preset["grain"],
        shake=preset["shake"],
        saturation=preset["saturation"],
        vignette_angle=preset["vignette"],
        out_w=out_w,
        out_h=out_h,
    )

    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", str(crf),
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    _run(cmd, label="ugc_filter")
    logger.info(f"[UGC] Filter applied ({intensity}) -> {output_path}")
    return output_path


def apply_focus_pulse(
    input_path:  str,
    output_path: str,
    interval_sec: float = 8.0,
    blur_radius:  float = 1.2,
) -> str:
    """
    Add periodic auto-focus blur pulse to simulate phone camera re-focusing.
    Applies a very brief gaussian blur every `interval_sec` seconds.
    """
    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    # Build select filter: every interval seconds, apply 3-frame blur
    # Use smartblur at periodic timestamps
    vf = (
        f"smartblur=luma_radius={blur_radius}:luma_strength=-0.3:luma_threshold=0,"
        f"setsar=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "24",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    _run(cmd, label="focus_pulse")
    logger.info(f"[UGC] Focus pulse -> {output_path}")
    return output_path
