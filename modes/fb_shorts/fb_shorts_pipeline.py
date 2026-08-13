"""
====================================================================
  Pipeline v3.0
  File: modes/fb_shorts/fb_shorts_pipeline.py — Orchestrator
====================================================================
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from modes.fb_shorts.remix_mode import RemixInputs, run_remix_mode
from modes.fb_shorts.generative_mode import GenerativeInputs, run_generative_mode

logger = logging.getLogger(__name__)


@dataclass
class FBShortsInputs:
    sub_mode:         str               # "remix" | "generative"
    product_images:   list[str]         # 1-5 anh san pham
    price_text:       str               # "35,000 KHR"
    ad_text_url:      str               # URL bai quang cao
    ref_video_url:    Optional[str] = None
    pexels_api_key:   str = ""
    gemini_api_key:   str = ""
    tts_voice:        str = "km-KH-SreymomNeural"
    tts_rate:         str = "+0%"
    ugc_intensity:    str = "medium"
    price_color:      str = "red"
    search_keyword:   str = ""
    target_duration:  float = 20.0
    replicate_token:  str = ""
    transition_speed: str = "Bình thường (3.0s)"


def run_fb_shorts_pipeline(inputs: FBShortsInputs, output_dir: str) -> str:
    """
    Dispatch to remix or generative sub-mode.
    Returns path to final output MP4.
    """
    temp_dir = str(Path(output_dir).parent / "temp" / "fb_shorts")
    os.makedirs(temp_dir, exist_ok=True)

    logger.info("=" * 60)
    logger.info("  FB SHORTS ADS GENERATOR  v3.0")
    logger.info(f"  Sub-mode : {inputs.sub_mode.upper()}")
    logger.info(f"  Images   : {len(inputs.product_images)}")
    logger.info(f"  Price    : {inputs.price_text}")
    logger.info("=" * 60)

    try:
        if inputs.sub_mode == "remix":
            remix_inputs = RemixInputs(
                product_images=inputs.product_images,
                price_text=inputs.price_text,
                ad_text_url=inputs.ad_text_url,
                ref_video_url=inputs.ref_video_url,
                pexels_api_key=inputs.pexels_api_key,
                gemini_api_key=inputs.gemini_api_key,
                tts_voice=inputs.tts_voice,
                ugc_intensity=inputs.ugc_intensity,
                search_keyword=inputs.search_keyword,
                price_color=inputs.price_color,
            )
            return run_remix_mode(remix_inputs, output_dir, temp_dir)

        elif inputs.sub_mode == "generative":
            gen_inputs = GenerativeInputs(
                product_images=inputs.product_images,
                price_text=inputs.price_text,
                ad_text_url=inputs.ad_text_url,
                gemini_api_key=inputs.gemini_api_key,
                replicate_token=inputs.replicate_token,
                tts_voice=inputs.tts_voice,
                ugc_intensity=inputs.ugc_intensity,
                price_color=inputs.price_color,
                target_duration=inputs.target_duration,
            )
            return run_generative_mode(gen_inputs, output_dir, temp_dir)

        else:
            raise ValueError(f"Unknown sub_mode: {inputs.sub_mode!r}. Use 'remix' or 'generative'.")

    finally:
        # Clean temp
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"[CLEAN] Temp dir cleaned: {temp_dir}")
        except Exception:
            pass
