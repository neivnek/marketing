"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/manual/prompt_interpreter.py — Prompt -> FFmpeg Params
====================================================================
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Output dataclass
# ──────────────────────────────────────────────

@dataclass
class MotionStyle:
    """Parsed motion and color directives derived from a user prompt."""
    # Ken Burns
    zoom_start:     float       = 1.0
    zoom_end:       float       = 1.08
    pan_directions: list[str]   = field(default_factory=lambda: ["left", "right", "center"])
    zoom_speed:     str         = "normal"   # slow | normal | fast

    # Color grading
    color_filter:   str         = ""         # FFmpeg -vf filter string, empty = no filter
    color_preset:   str         = "neutral"  # preset name for logging

    # Display flags
    description:    str         = ""


# ──────────────────────────────────────────────
# Keyword Rule Tables
# ──────────────────────────────────────────────

# Zoom speed modifiers
_ZOOM_SPEEDS = {
    "slow":     {"zoom_end": 1.04, "zoom_speed": "slow"},
    "fast":     {"zoom_end": 1.15, "zoom_speed": "fast"},
    "quick":    {"zoom_end": 1.15, "zoom_speed": "fast"},
    "gentle":   {"zoom_end": 1.04, "zoom_speed": "slow"},
    "dramatic": {"zoom_end": 1.20, "zoom_speed": "fast"},
}

# Pan direction preferences
_PAN_STYLES = {
    "left":     ["left",   "center", "right"],
    "right":    ["right",  "center", "left"],
    "up":       ["up",     "center", "down"],
    "down":     ["down",   "center", "up"],
    "center":   ["center", "left",   "right"],
    "zoom in":  ["center", "center", "center"],
    "zoom-in":  ["center", "center", "center"],
}

# Color presets -> FFmpeg filter chains
_COLOR_PRESETS = {
    # Warm / golden hour
    "warm": (
        "eq=saturation=1.2:contrast=1.05,"
        "curves=r='0/0.05 1/1':g='0/0 0.9/0.9 1/1':b='0/0 0.8/0.75 1/0.9'"
    ),
    "golden": (
        "eq=saturation=1.3:brightness=0.04:contrast=1.1,"
        "curves=r='0/0.1 1/1':b='0/0 1/0.85'"
    ),
    # Cool / cinematic
    "cool": (
        "eq=saturation=0.9:contrast=1.05,"
        "curves=r='0/0 0.9/0.85 1/0.9':b='0/0.05 1/1'"
    ),
    "cinematic": (
        "eq=saturation=0.85:contrast=1.15,"
        "vignette=PI/4,"
        "curves=r='0/0 0.5/0.45 1/0.9':b='0/0.05 0.5/0.55 1/1'"
    ),
    # Vibrant / punchy
    "vibrant": (
        "eq=saturation=1.5:contrast=1.1:brightness=0.02"
    ),
    "punchy": (
        "eq=saturation=1.4:contrast=1.2,"
        "curves=all='0/0 0.5/0.55 1/1'"
    ),
    # Soft / pastel
    "soft": (
        "eq=saturation=0.8:brightness=0.05:contrast=0.95"
    ),
    "pastel": (
        "eq=saturation=0.7:brightness=0.08:contrast=0.9,"
        "curves=all='0/0.1 1/0.95'"
    ),
    # Dark / moody
    "dark": (
        "eq=saturation=0.9:brightness=-0.05:contrast=1.2"
    ),
    "moody": (
        "eq=saturation=0.85:brightness=-0.08:contrast=1.25,"
        "vignette=PI/3,"
        "curves=all='0/0 0.4/0.3 1/0.95'"
    ),
    # Neutral (no filter)
    "neutral": "",
    "natural": "",
    "clean":   "",
}


# ──────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────

def parse_motion_style(prompt_text: str) -> MotionStyle:
    """
    Parse a free-form user prompt into structured motion and color directives.

    Keyword matching is case-insensitive. Multiple keywords are combined
    (e.g., "warm cinematic slow zoom" applies both warm color + slow zoom).

    Parameters
    ----------
    prompt_text : Raw text from [Manual_Prompt] input field.

    Returns
    -------
    MotionStyle — dataclass with FFmpeg-ready parameters.
    """
    style = MotionStyle()
    lower = prompt_text.lower()

    # ── Zoom speed ──────────────────────────────────────────────
    for keyword, params in _ZOOM_SPEEDS.items():
        if keyword in lower:
            style.zoom_end   = params["zoom_end"]
            style.zoom_speed = params["zoom_speed"]
            logger.debug(f"Prompt matched zoom speed: '{keyword}'")
            break

    # ── Pan direction ────────────────────────────────────────────
    for keyword, dirs in _PAN_STYLES.items():
        if keyword in lower:
            style.pan_directions = dirs
            logger.debug(f"Prompt matched pan direction: '{keyword}'")
            break

    # ── Color preset ─────────────────────────────────────────────
    matched_preset = "neutral"
    for preset_name, filter_str in _COLOR_PRESETS.items():
        if preset_name in lower:
            matched_preset      = preset_name
            style.color_filter  = filter_str
            style.color_preset  = preset_name
            logger.debug(f"Prompt matched color preset: '{preset_name}'")
            break

    # ── Custom eq= override (advanced users) ────────────────────
    custom_eq = re.search(r"eq=[^\s,]+", prompt_text, re.IGNORECASE)
    if custom_eq:
        style.color_filter = custom_eq.group(0)
        style.color_preset = "custom"
        logger.debug(f"Prompt: custom FFmpeg filter: {style.color_filter}")

    # ── Summary ──────────────────────────────────────────────────
    style.description = (
        f"zoom_speed={style.zoom_speed}  "
        f"zoom={style.zoom_start:.2f}->{style.zoom_end:.2f}  "
        f"pan={style.pan_directions[0]}  "
        f"color={style.color_preset}"
    )
    logger.info(f"[COLOR]  Motion style parsed: {style.description}")

    return style
