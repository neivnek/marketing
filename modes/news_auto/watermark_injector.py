"""
====================================================================
  Pipeline v3.0
  File: modes/news_auto/watermark_injector.py — Channel Watermark
====================================================================
"""

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def inject_channel_watermark(
    input_video: str,
    output_video: str,
    channel_name: str,
    position: str = "bottom_right",
) -> str:
    """
    Burn a channel name watermark onto the input video using FFmpeg drawtext.
    If channel_name is empty, simply copies input_video to output_video.
    """
    if not channel_name or not channel_name.strip():
        if input_video != output_video:
            import shutil
            shutil.copy(input_video, output_video)
        return output_video

    logger.info(f"[WATERMARK] Injecting channel watermark: '{channel_name}'")

    # Escape special FFmpeg drawtext characters
    text_clean = channel_name.replace(":", "\\:").replace("'", "").strip()

    # Font path lookup
    font_path = "assets/fonts/Hanuman.ttf"
    if not os.path.exists(font_path):
        font_arg = "font=sans"
    else:
        # Normalize Windows path for FFmpeg
        fp_escaped = os.path.abspath(font_path).replace("\\", "/").replace(":", "\\:")
        font_arg = f"fontfile={fp_escaped}"

    # Drawtext filter string
    drawtext_filter = (
        f"drawtext={font_arg}:text='{text_clean}':"
        f"fontsize=36:fontcolor=white@0.8:box=1:boxcolor=black@0.5:"
        f"boxborderw=8:x=w-tw-40:y=h-th-60"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", drawtext_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        output_video,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"Watermark injection failed: {result.stderr[-300:]}. Using original video.")
        import shutil
        shutil.copy(input_video, output_video)
        return output_video

    logger.info(f"    ✓ Watermark injected: {output_video}")
    return output_video
