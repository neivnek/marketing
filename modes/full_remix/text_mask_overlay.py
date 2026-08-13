"""
====================================================================
  Pipeline v3.0
  File: modes/dub_remix/text_mask_overlay.py — Step 2: Text Masking
====================================================================
"""

import logging
import os
import subprocess
from pathlib import Path

from core.subtitle_gen import generate_ass_file
from core.ffmpeg_utils import burn_hardsub, get_video_duration

logger = logging.getLogger(__name__)


def apply_text_mask_and_subtitles(
    input_video: str,
    output_video: str,
    khmer_script: str,
    mask_style: str = "box",        # "box" | "blur" | "branded_title_frame" | "none"
    mask_color: str = "black",      # "black" | "white" | "darkblue" | "red" | "orange"
    title_text: str = "",           # Only used if mask_style="branded_title_frame"
    temp_dir: str = "temp",
) -> str:
    """
    Step 2: Mask/cover original text area on video (box or blur) and overlay new Khmer subtitles.
    """
    logger.info(f"[STEP 6.2] Masking original text (style={mask_style}, color={mask_color})...")

    if mask_style == "none":
        masked_video = input_video
    else:
        masked_video = os.path.join(temp_dir, "masked_intermediate.mp4")
        _apply_mask_filter(input_video, masked_video, mask_style, mask_color, title_text)

    if not khmer_script.strip():
        import shutil
        shutil.copy(masked_video, output_video)
        logger.info(f"    ✓ Text masked (no subtitles added): {output_video}")
    else:
        # Generate & burn new Khmer subtitles
        ass_path = os.path.join(temp_dir, "dub_remix_sub.ass")
        dur = get_video_duration(masked_video)

        generate_ass_file(
            script_text=khmer_script,
            timestamps=[dur],
            output_path=ass_path,
            font_name="Hanuman",
        )

        burn_hardsub(masked_video, ass_path, "assets/fonts", output_video)
        logger.info(f"    ✓ Text masked and Khmer subtitles burned: {output_video}")
    return output_video


def _apply_mask_filter(input_video: str, output_video: str, mask_style: str, mask_color: str, title_text: str = ""):
    """Apply FFmpeg box overlay, boxblur, or branded_title_frame over bottom text region."""
    
    if mask_style == "branded_title_frame":
        # Reuse overlay_renderer's logic to draw a nice background bar with text
        from core.overlay_renderer import add_price_overlay
        try:
            # If title_text is empty, just use a generic title
            display_text = title_text if title_text else "SPECIAL OFFER"
            add_price_overlay(
                input_path=input_video,
                output_path=output_video,
                price_text=display_text,
                position="bottom",
                bg_color=mask_color
            )
            return
        except Exception as e:
            logger.warning(f"Branded title frame failed ({e}), falling back to box mask.")
            mask_style = "box"

    color_hex_map = {
        "black":    "0x000000@0.9",
        "white":    "0xFFFFFF@0.9",
        "darkblue": "0x0f172a@0.9",
        "red":      "0xCC0000@0.9",
        "orange":   "0xE65100@0.9",
    }
    bg_color = color_hex_map.get(mask_color, "0x000000@0.9")

    if mask_style == "blur":
        # Apply Gaussian blur over lower text area (y = 70% to 92% of height)
        vf = "crop=w=iw:h=ih*0.22:x=0:y=ih*0.70,boxblur=15:5[b];[0:v][b]overlay=x=0:y=H*0.70"
    else:  # box
        # Draw solid background rectangle covering lower text area
        vf = f"drawbox=x=0:y=ih*0.70:w=iw:h=ih*0.22:color={bg_color}:t=fill"

    filter_flag = "-filter_complex" if mask_style == "blur" else "-vf"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        filter_flag, vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        output_video,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"Mask filter failed: {result.stderr[-300:]}. Proceeding without mask.")
        import shutil
        shutil.copy(input_video, output_video)
