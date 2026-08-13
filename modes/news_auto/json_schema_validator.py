"""
====================================================================
  Pipeline v3.0
  File: modes/news_auto/json_schema_validator.py — JSON Validator
====================================================================
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


def validate_and_sanitize_news_json(json_input: str) -> Dict[str, Any]:
    """
    Validate and sanitize input JSON payload for Mode 5 (News Auto).
    Accepts either raw JSON text or a local file path.
    Returns a standardized dictionary payload.
    """
    json_str = json_input.strip()

    # Check if input is a local file path
    if os.path.exists(json_str) and os.path.isfile(json_str):
        try:
            with open(json_str, "r", encoding="utf-8") as f:
                json_str = f.read().strip()
        except Exception as e:
            raise ValueError(f"Failed to read JSON file '{json_input}': {e}")

    # Strip accidental markdown code blocks
    json_str = re.sub(r"^```[a-zA-Z]*\n?", "", json_str).strip()
    json_str = re.sub(r"```$", "", json_str).strip()

    if not json_str:
        raise ValueError("JSON payload is empty.")

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")

    if not isinstance(data, dict):
        raise ValueError("JSON payload must be a JSON object ({...}).")

    # Validate Title
    title = str(data.get("title", "STORY AD")).strip() or "STORY AD"

    # Validate script_segments
    raw_segments = data.get("script_segments", [])
    if not isinstance(raw_segments, list) or len(raw_segments) == 0:
        raise ValueError("No script_segments provided in JSON payload.")

    sanitized_segments = []
    total_dur = 0.0
    beats_found = set()
    prev_camera_hint = ""
    prev_on_screen_text = ""
    visual_hints_seen = set()

    for idx, seg in enumerate(raw_segments, start=1):
        if not isinstance(seg, dict):
            continue
        
        narrative_beat = str(seg.get("narrative_beat", "setup")).strip().lower()
        emotion = str(seg.get("emotion", "neutral")).strip().lower()
        vo_text = str(seg.get("voiceover_text", "")).strip()
        screen_text = str(seg.get("on_screen_text", "")).strip()
        visual_hint = str(seg.get("visual_hint", "general")).strip()
        camera_hint = str(seg.get("camera_hint", "medium-shot")).strip()
        
        try:
            dur_hint = float(seg.get("duration_hint_sec", 4.0))
        except (ValueError, TypeError):
            dur_hint = 4.0
            
        # Micro-story rule: segments should be 3-6 seconds.
        if dur_hint > 7.0:
            logger.warning(f"Segment {idx} duration ({dur_hint}s) exceeds recommended 6s. Clamping to 6s.")
            dur_hint = 6.0
        if dur_hint < 2.0:
            dur_hint = 3.0
            
        # Deduplication rules
        if screen_text and screen_text == prev_on_screen_text:
            logger.warning(f"Segment {idx} on_screen_text is identical to previous. Stripping it to prevent static burn-in.")
            screen_text = ""
            
        if camera_hint == prev_camera_hint:
            camera_hint = "close-up" if prev_camera_hint == "wide-establishing" else "wide-establishing"
            
        if visual_hint in visual_hints_seen:
            visual_hint += " (variation)"
            
        visual_hints_seen.add(visual_hint)
        prev_camera_hint = camera_hint
        prev_on_screen_text = screen_text
        
        beats_found.add(narrative_beat)
        total_dur += dur_hint

        sanitized_segments.append({
            "id": int(seg.get("id", idx)),
            "narrative_beat": narrative_beat,
            "emotion": emotion,
            "voiceover_text": vo_text,
            "on_screen_text": screen_text,
            "visual_hint": visual_hint,
            "camera_hint": camera_hint,
            "duration_hint_sec": dur_hint,
        })

    if not sanitized_segments:
        raise ValueError("No valid script_segments found in JSON payload.")
        
    # Validation Rules
    required_beats = {"hook", "problem", "turning_point", "solution", "proof", "cta"}
    missing_beats = required_beats - beats_found
    if missing_beats:
        logger.warning(f"Missing recommended narrative beats: {missing_beats}. The story might lack structure.")
        
    if total_dur < 30.0 or total_dur > 180.0:
        logger.warning(f"Total duration ({total_dur}s) is outside the optimal 60-150s range for Micro-Story Ads.")

    # Validate Quality
    quality = str(data.get("output_quality", "1080p")).lower().strip()
    if quality not in ["720p", "1080p", "4k"]:
        quality = "1080p"

    product_price = str(data.get("product_price", "")).strip()

    sanitized = {
        "title": title,
        "script_segments": sanitized_segments,
        "product_price": product_price,
        "output_quality": quality,
    }

    logger.info(f"    ✓ JSON payload validated successfully: '{title}' ({len(sanitized_segments)} segments, {quality})")
    return sanitized
