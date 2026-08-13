"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/auto/ai_analyzer.py — Gemini Flash Video Analyzer
====================================================================
"""

import base64
import json
import logging
import mimetypes
import os
import re
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ── Prompt Templates ─────────────────────────────────────────────

_TIMESTAMP_PROMPT = """\
You are a video production assistant. Analyze the provided reference advertisement video.

Your task:
1. Identify all significant scene cuts or pacing changes in the video.
2. Return a JSON object with ONLY the following structure — no markdown fences, no extra text:

{
  "timestamps": [<float seconds of each scene cut point>],
  "total_duration": <float total video duration in seconds>
}

Example: {"timestamps": [3.2, 7.5, 12.0, 18.3], "total_duration": 20.0}

Be precise to 1 decimal place. Include the final timestamp equal to total_duration.
"""

_SCRIPT_PROMPT = """\
You are a creative copywriter specializing in short-form video ads.

Given:
- A reference advertisement video showing competitor's pacing and style
- A product image

Write a compelling voiceover script that:
1. Matches the energy and pacing of the reference video
2. Is persuasive and uses natural advertising language for the target market
3. Total length should fit within {duration:.0f} seconds when spoken aloud
4. Includes emotional hooks and a clear call-to-action at the end

{style_injection}
Return ONLY the script text. No translation. No explanation. No formatting.
"""


# ── Core Functions ────────────────────────────────────────────────

DEFAULT_MODELS = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
]

def _get_client(api_key: str) -> genai.Client:
    """Initialize the Gemini client with the new google-genai SDK."""
    return genai.Client(api_key=api_key)


def _make_part(file_path: str) -> types.Part:
    """Read a local file and return a Gemini SDK Part object."""
    mime, _ = mimetypes.guess_type(file_path)
    if mime is None:
        mime = "application/octet-stream"
    with open(file_path, "rb") as f:
        data = f.read()
    return types.Part.from_bytes(data=data, mime_type=mime)


def _generate_content_with_fallback(
    client: genai.Client,
    contents: list,
    config: types.GenerateContentConfig = None
):
    models_to_try = []
    for m in DEFAULT_MODELS:
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_exc = None
    for model in models_to_try:
        try:
            kwargs = {"model": model, "contents": contents}
            if config:
                kwargs["config"] = config
            logger.info(f"[AI]  Trying Gemini model: {model}")
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            err_str = str(exc)
            if any(k in err_str.lower() for k in ["404", "not_found", "no longer available", "not supported"]):
                logger.warning(f"    Model '{model}' unavailable ({exc}). Trying next candidate...")
                last_exc = exc
                continue
            raise exc
    if last_exc:
        raise last_exc


def extract_timestamps(video_path: str, api_key: str) -> dict:
    """
    Send the reference video to Gemini Flash and extract scene timestamps.

    Parameters
    ----------
    video_path : Local path to the reference video file.
    api_key    : Google AI Studio API key.

    Returns
    -------
    dict with keys:
        - "timestamps": list[float] — scene cut points in seconds
        - "total_duration": float — total video duration
    """
    logger.info(f"[AI]  Gemini: extracting timestamps from {Path(video_path).name}")

    client = _get_client(api_key)

    video_part = _make_part(video_path)
    response = _generate_content_with_fallback(
        client=client,
        contents=[video_part, _TIMESTAMP_PROMPT],
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=512,
            response_mime_type="application/json"
        ),
    )

    raw = response.text.strip()
    logger.debug(f"Gemini timestamp response: {raw}")

    # Strip accidental markdown fences
    raw = re.sub(r"```[a-z]*\n?", "", raw).strip()

    try:
        data = json.loads(raw)
        timestamps     = [float(t) for t in data.get("timestamps", [])]
        total_duration = float(data.get("total_duration", timestamps[-1] if timestamps else 30.0))
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Gemini JSON parse failed ({e}), using fallback timestamps.")
        # Fallback: equally spaced timestamps every 5 seconds
        from core.ffmpeg_utils import get_video_duration
        total_duration = get_video_duration(video_path)
        timestamps = [float(i * 5) for i in range(1, int(total_duration // 5) + 1)]

    logger.info(f"    ✓ Timestamps: {timestamps}  (total {total_duration:.1f}s)")
    return {"timestamps": timestamps, "total_duration": total_duration}


def write_khmer_script(
    video_path:     str,
    product_image:  str,
    api_key:        str,
    duration:       float,
    style_profile:  dict = None,      # NEW: Style DNA dict from core/style_profile.py
) -> str:
    """
    Use Gemini Flash to write an advertising script based on the
    reference video style and product image.

    Parameters
    ----------
    video_path    : Path to the reference competitor video.
    product_image : Path to the product image.
    api_key       : Google AI Studio API key.
    duration      : Target voiceover duration in seconds.
    style_profile : Optional style profile dict. When provided, injects
                    the user's personal style DNA into the Gemini prompt.

    Returns
    -------
    str — Advertising script text in the style of the user's profile.
    """
    logger.info("[AI]  Gemini: writing advertising script...")

    client = _get_client(api_key)

    # Build style injection section
    style_injection = ""
    if style_profile:
        try:
            from core.style_profile import build_style_injection_prompt
            style_injection = build_style_injection_prompt(style_profile)
            logger.info(f"[AI]  Style profile injected: '{style_profile.get('profile_name', 'unknown')}'")
        except Exception as exc:
            logger.warning(f"[AI]  Style profile injection failed: {exc}")

    video_part = _make_part(video_path)
    image_part = _make_part(product_image)
    prompt     = _SCRIPT_PROMPT.format(duration=duration, style_injection=style_injection)

    response = _generate_content_with_fallback(
        client=client,
        contents=[video_part, image_part, prompt],
        config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=1024),
    )

    script = response.text.strip()
    logger.info(f"    ✓ Script generated ({len(script)} chars):\n{script[:200]}...")
    return script


def analyze_video_with_gemini(
    video_path:    str,
    product_image: str,
    api_key:       str,
    style_profile: dict = None,    # NEW: Optional style profile
) -> dict:
    """
    Full Gemini analysis pipeline — combines timestamp extraction and
    Khmer script writing in two sequential API calls.

    Parameters
    ----------
    video_path    : Reference video path.
    product_image : Product image path.
    api_key       : Gemini API key.

    Returns
    -------
    dict with keys:
        - "timestamps": list[float]
        - "total_duration": float
        - "script": str  (Khmer text)
    """
    timing_data = extract_timestamps(video_path, api_key)

    script = write_khmer_script(
        video_path=video_path,
        product_image=product_image,
        api_key=api_key,
        duration=timing_data["total_duration"],
        style_profile=style_profile,
    )

    return {
        "timestamps":     timing_data["timestamps"],
        "total_duration": timing_data["total_duration"],
        "script":         script,
    }

def generate_script_from_video(
    video_path: str,
    product_image_path: str,
    price: str,
    api_key: str
) -> dict:
    """
    Independent function to analyze a video and product image to generate a script.
    Does not depend on scraper.py.
    """
    logger.info(f"[AI] Generating script independently for {video_path}")
    timing_data = extract_timestamps(video_path, api_key)
    
    # We can pass price to the prompt if we want, or just rely on image.
    # For now, we just pass the default duration.
    script = write_khmer_script(
        video_path=video_path,
        product_image=product_image_path,
        api_key=api_key,
        duration=timing_data["total_duration"],
    )

    return {
        "timestamps":     timing_data["timestamps"],
        "total_duration": timing_data["total_duration"],
        "script":         script,
    }
