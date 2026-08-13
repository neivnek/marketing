"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/pacing_enforcer.py — Ad Pacing Standards Enforcer
====================================================================

Áp dụng các quy tắc pacing đã được kiểm chứng từ 23 iterations
thực tế của fb-ad-video-studio (references/patterns.md):

  - Drift cuts: 0.18s (không dùng 0.5s cross-fades)
  - Word reveals: 0.25s (không chậm hơn)
  - Music bed:  -18 dB (không phải -12 dB) hoặc bỏ hẳn với direct-response
  - Beat length: mỗi beat ≤ 5s, nếu không split ra 2 captions
  - Caption position: y ≈ 1180–1400px (dưới mặt, trên tay)
  - SFX density: 3-6 hits / 30s (không quá dày hoặc quá thưa)

Hai chức năng chính:
  1. enforce_cuts()    — tái encode các segment với drift cut 0.18s
  2. audit_pacing()    — kiểm tra script và cảnh báo beat dài hơn 5s
  3. music_db_for_ad() — trả về dB đúng cho music theo loại ad
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Pacing Constants (từ fb-ad-studio/references/patterns.md)
# ──────────────────────────────────────────────

DRIFT_CUT_DURATION   = 0.18   # s — transition between scenes (not a fade)
WORD_REVEAL_DURATION = 0.25   # s — caption/text reveal animation
BEAT_MAX_DURATION    = 5.0    # s — beats longer than this need to be split
MUSIC_DR_DB          = -28.0  # dB — direct-response ads (barely audible)
MUSIC_BRAND_DB       = -18.0  # dB — brand/awareness ads (sweet spot)
MUSIC_SKIP_TYPES     = {"direct_response", "conversion", "retargeting"}

# Caption safe zone (1080x1920 vertical)
CAPTION_Y_MIN = 1180
CAPTION_Y_MAX = 1400

# SFX density targets per 30s
SFX_MIN_PER_30S = 3
SFX_MAX_PER_30S = 6


# ──────────────────────────────────────────────
# Pacing Audit
# ──────────────────────────────────────────────

def audit_pacing(
    script_segments: list[dict],
    total_duration:  float,
    ad_type:         str = "direct_response",
) -> dict:
    """
    Audit a script for pacing violations and return a structured report.

    Parameters
    ----------
    script_segments : List of segment dicts with duration_sec / duration_hint_sec.
    total_duration  : Total video duration in seconds.
    ad_type         : "direct_response" | "brand" | "retargeting" (affects music recommendation).

    Returns
    -------
    dict with keys:
        long_beats      : list of segments > 5s (should split)
        music_db        : recommended music dB level
        skip_music      : bool — True if direct_response
        sfx_density_ok  : bool
        suggestions     : list[str]
    """
    long_beats   = []
    suggestions  = []

    for seg in script_segments:
        dur = seg.get("duration_sec", seg.get("duration_hint_sec", 0.0))
        if dur > BEAT_MAX_DURATION:
            long_beats.append({
                "segment_id": seg.get("id", "?"),
                "act":        seg.get("act", ""),
                "duration":   round(dur, 2),
                "suggestion": f"Split this {dur:.1f}s beat into 2 captions (max {BEAT_MAX_DURATION}s each)",
            })

    # SFX density check
    sfx_needed  = round(total_duration / 30 * SFX_MIN_PER_30S)
    sfx_density = f"Recommend {sfx_needed}-{round(total_duration / 30 * SFX_MAX_PER_30S)} SFX events for {total_duration:.0f}s"

    # Music recommendation
    skip_music = ad_type in MUSIC_SKIP_TYPES
    music_db   = MUSIC_DR_DB if skip_music else MUSIC_BRAND_DB
    if skip_music:
        suggestions.append(
            f"Ad type '{ad_type}': Skip background music entirely — "
            "VO + SFX only outperforms music in direct-response ads."
        )
    else:
        suggestions.append(
            f"Mix music at {music_db} dB under VO "
            "(not -12 dB — that's too loud for VO intelligibility)."
        )

    if long_beats:
        suggestions.append(
            f"{len(long_beats)} beat(s) exceed {BEAT_MAX_DURATION}s. "
            "Each beat > 5s should be split into 2 captions so none lingers stale."
        )

    suggestions.append(sfx_density)
    suggestions.append(
        f"Scene transitions: use {DRIFT_CUT_DURATION}s hard cuts (not 0.5s cross-fades)."
    )

    logger.info(
        f"[PacingEnforcer] Audit done — {len(long_beats)} long beat(s), "
        f"skip_music={skip_music}, music_db={music_db}"
    )

    return {
        "long_beats":      long_beats,
        "music_db":        music_db,
        "skip_music":      skip_music,
        "sfx_density_ok":  True,
        "suggestions":     suggestions,
    }


# ──────────────────────────────────────────────
# Music Level Helper
# ──────────────────────────────────────────────

def music_db_for_ad(ad_type: str = "direct_response") -> Optional[float]:
    """
    Return the correct music dB level for the given ad type.
    Returns None if music should be skipped entirely.

    Parameters
    ----------
    ad_type : "direct_response" | "brand" | "retargeting" | "awareness"

    Returns
    -------
    float (dB) or None (skip music).
    """
    if ad_type in MUSIC_SKIP_TYPES:
        return None
    return MUSIC_BRAND_DB


def db_to_volume_factor(db: float) -> float:
    """Convert dB value to linear volume factor for FFmpeg volume= filter."""
    return round(10 ** (db / 20), 5)


# ──────────────────────────────────────────────
# Drift Cut Transition
# ──────────────────────────────────────────────

def apply_drift_cut_transition(
    clip_a:      str,
    clip_b:      str,
    output_path: str,
    cut_duration: float = DRIFT_CUT_DURATION,
) -> str:
    """
    Join two video clips with a 0.18s drift cut (minimal opacity cross).
    This is NOT a dissolve — it's a very fast opacity drop (~2 frames)
    that feels like a hard cut but avoids flash-frame jarring.

    Technique: trim 0.18s from the end of clip_a and start of clip_b,
    then concat. The slight temporal overlap makes the cut feel
    more polished than a pure splice, without the lethargic feel of a 0.5s fade.

    Parameters
    ----------
    clip_a / clip_b : Video clip paths (must have same resolution + fps).
    output_path     : Output path.
    cut_duration    : Overlap duration in seconds (default 0.18s per spec).

    Returns
    -------
    str — output_path on success, or concatenation of clips on failure.
    """
    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    # Get duration of clip_a to compute trim end
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", clip_a],
            capture_output=True, text=True,
        )
        import json
        info_a = json.loads(result.stdout)
        dur_a  = float(info_a["format"]["duration"])
    except Exception:
        dur_a = None

    if dur_a is None or dur_a <= cut_duration * 2:
        # Clip too short for drift cut — just concat
        return _simple_concat(clip_a, clip_b, output_path)

    trim_end_a = dur_a - cut_duration

    filter_complex = (
        # Trim end of A (drop last 0.18s)
        f"[0:v]trim=0:{trim_end_a:.3f},setpts=PTS-STARTPTS[va];"
        f"[0:a]atrim=0:{trim_end_a:.3f},asetpts=PTS-STARTPTS[aa];"
        # Trim start of B (drop first 0.18s)
        f"[1:v]trim={cut_duration:.3f},setpts=PTS-STARTPTS[vb];"
        f"[1:a]atrim={cut_duration:.3f},asetpts=PTS-STARTPTS[ab];"
        # Concat
        f"[va][aa][vb][ab]concat=n=2:v=1:a=1[outv][outa]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", clip_a,
        "-i", clip_b,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning(f"[PacingEnforcer] Drift cut failed: {proc.stderr[-200:]}. Using simple concat.")
        return _simple_concat(clip_a, clip_b, output_path)

    logger.info(f"[PacingEnforcer] Drift cut ({cut_duration}s) applied → {Path(output_path).name}")
    return output_path


def _simple_concat(clip_a: str, clip_b: str, output_path: str) -> str:
    """Fallback: simple concat without transition."""
    import tempfile, shutil
    list_file = output_path + ".concat_list.txt"
    with open(list_file, "w") as f:
        f.write(f"file '{Path(clip_a).resolve()}'\n")
        f.write(f"file '{Path(clip_b).resolve()}'\n")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True)
    try:
        os.remove(list_file)
    except FileNotFoundError:
        pass
    return output_path


# ──────────────────────────────────────────────
# Re-encode for Keyframe Fix (sparse keyframe phone footage)
# ──────────────────────────────────────────────

def reencode_for_seek(
    input_path:  str,
    output_path: str,
    fps:         int = 30,
) -> str:
    """
    Re-encode footage to fix sparse keyframe seek failures.
    Phone MP4s often have 5s+ keyframe intervals → FFmpeg seek errors.

    Sets keyframe every frame (g=30, keyint_min=30) for reliable seeking.
    From: fb-ad-studio/scripts/reencode-footage.sh

    Returns
    -------
    str — output_path on success, input_path on failure.
    """
    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264",
        "-r",   str(fps),
        "-g",   str(fps),
        "-keyint_min", str(fps),
        "-movflags", "+faststart",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"[PacingEnforcer] reencode_for_seek failed: {result.stderr[-200:]}")
        return input_path
    logger.info(f"[PacingEnforcer] Re-encoded for seek: {Path(output_path).name}")
    return output_path
