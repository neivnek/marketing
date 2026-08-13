"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/sfx_fetcher.py — Mixkit SFX Rail Fetcher & Burner
====================================================================

Tải Sound Effects (SFX) từ Mixkit.co — hoàn toàn miễn phí,
commercial license, không cần attribution.

Mixkit SFX previews ARE the full clip (unlike their music previews).
Source: references/audio-sources.md from fb-ad-video-studio

SFX Catalog (proven for ads from 23 production iterations):
  whoosh  — scene transition / word reveal (0.6s, -2dB under VO)
  punch   — impact / emphasis stamp     (0.22s, -3dB)
  ding    — proof / CTA reveal          (0.65s, -8dB)
  stamp   — bold claim / number reveal  (0.5s,  -4dB)

Mixkit preview URL pattern:
  https://assets.mixkit.co/active_storage/sfx/{id}/{id}-preview.mp3

Usage in pipeline:
  1. sfx_fetcher.download_sfx_kit(assets_dir)  — download + trim once
  2. sfx_fetcher.burn_sfx_rail(video_path, sfx_events, output_path)
     where sfx_events = [{sfx_name, start_sec, volume_db}, ...]
     — anchored to whisper word starts for frame-accurate sync

Integration: Called from ultimate_ad_pipeline.py after subtitle step,
  before hook variant assembly.
"""

import json
import logging
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Mixkit SFX Catalog
# ──────────────────────────────────────────────

# Proven tight ad durations from fb-ad-video-studio/scripts/fetch-sfx.sh
SFX_CATALOG: dict[str, dict] = {
    "whoosh": {
        "url":      "https://assets.mixkit.co/active_storage/sfx/2308/2308-preview.mp3",
        "duration": 0.60,    # trim to this length (s)
        "vol_db":   -2,      # dB relative to VO
        "fade_out": 0.05,    # fade-out duration (s)
    },
    "punch": {
        "url":      "https://assets.mixkit.co/active_storage/sfx/2648/2648-preview.mp3",
        "duration": 0.22,
        "vol_db":   -3,
        "fade_out": 0.05,
    },
    "ding": {
        "url":      "https://assets.mixkit.co/active_storage/sfx/2870/2870-preview.mp3",
        "duration": 0.65,
        "vol_db":   -8,
        "fade_out": 0.05,
    },
    "stamp": {
        "url":      "https://assets.mixkit.co/active_storage/sfx/1655/1655-preview.mp3",
        "duration": 0.50,
        "vol_db":   -4,
        "fade_out": 0.05,
    },
}

# Default SFX rail pattern tied to 5-beat ad arc
# start_sec_ratio = fraction of total_duration for that beat
DEFAULT_SFX_RAIL_RATIOS: list[dict] = [
    {"sfx": "whoosh", "beat": "hook_in",      "ratio": 0.02},   # very start
    {"sfx": "stamp",  "beat": "problem_in",   "ratio": 0.18},   # problem beat
    {"sfx": "whoosh", "beat": "solution_in",  "ratio": 0.42},   # solution
    {"sfx": "ding",   "beat": "proof_in",     "ratio": 0.65},   # proof reveal
    {"sfx": "punch",  "beat": "cta_in",       "ratio": 0.85},   # CTA
]


# ──────────────────────────────────────────────
# Download & Trim
# ──────────────────────────────────────────────

def download_sfx_kit(
    assets_dir: str,
    force:      bool = False,
) -> dict[str, str]:
    """
    Download and tight-trim all SFX from Mixkit into assets_dir/sfx/.
    Skips download if files already exist (unless force=True).

    Returns
    -------
    dict[sfx_name, local_path] — paths to trimmed MP3 files.
    """
    sfx_dir = os.path.join(assets_dir, "sfx")
    os.makedirs(sfx_dir, exist_ok=True)

    result: dict[str, str] = {}

    for name, spec in SFX_CATALOG.items():
        out_path = os.path.join(sfx_dir, f"{name}.mp3")
        result[name] = out_path

        if os.path.isfile(out_path) and not force:
            logger.debug(f"[SFX] {name}.mp3 already exists — skipping download.")
            continue

        raw_path = os.path.join(sfx_dir, f".{name}-raw.mp3")

        # Download
        try:
            logger.info(f"[SFX] Downloading {name} from Mixkit...")
            urllib.request.urlretrieve(spec["url"], raw_path)
        except Exception as exc:
            logger.warning(f"[SFX] Failed to download {name}: {exc}. Skipping.")
            continue

        # Trim + gain + fade-out
        dur    = spec["duration"]
        fade_t = dur - spec["fade_out"]
        vol_db = spec["vol_db"]

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", raw_path,
            "-t", str(dur),
            "-af", f"afade=t=out:st={fade_t:.3f}:d={spec['fade_out']:.3f},volume={vol_db}dB",
            "-ac", "2",
            "-b:a", "192k",
            out_path,
        ]
        result_proc = subprocess.run(cmd, capture_output=True, text=True)
        if result_proc.returncode != 0:
            logger.warning(f"[SFX] Trim failed for {name}: {result_proc.stderr[-200:]}")
        else:
            logger.info(f"[SFX] {name}.mp3 ready ({dur}s, {vol_db}dB)")

        # Cleanup raw
        try:
            os.remove(raw_path)
        except FileNotFoundError:
            pass

    return result


# ──────────────────────────────────────────────
# SFX Event Builder
# ──────────────────────────────────────────────

def build_sfx_rail_from_words(
    words_json:     list[dict],
    total_duration: float,
    strategy:       str = "beat_arc",
) -> list[dict]:
    """
    Build an SFX event list anchored to whisper word timestamps.

    Strategy "beat_arc": attach SFX to the first word of each script beat
    (hook / problem / solution / proof / CTA) based on proportional ratios.

    Strategy "ratio": pure time-ratio placement (no word anchoring).

    Parameters
    ----------
    words_json     : Word timestamp list from faster-whisper (.words.json).
    total_duration : Total video duration in seconds.
    strategy       : "beat_arc" | "ratio".

    Returns
    -------
    list[dict] — [{sfx: str, start_sec: float}, ...]
    """
    events: list[dict] = []

    for rail_item in DEFAULT_SFX_RAIL_RATIOS:
        target_sec = rail_item["ratio"] * total_duration

        if strategy == "beat_arc" and words_json:
            # Find the word that starts closest to (but not before) target_sec
            candidates = [
                w for w in words_json
                if abs(w.get("start", 0) - target_sec) < 3.0
            ]
            if candidates:
                best = min(candidates, key=lambda w: abs(w.get("start", 0) - target_sec))
                target_sec = best.get("start", target_sec)

        events.append({
            "sfx":       rail_item["sfx"],
            "beat":      rail_item["beat"],
            "start_sec": round(target_sec, 3),
        })

    return events


def build_sfx_rail_from_script(
    script_segments: list[dict],
    total_duration:  float,
) -> list[dict]:
    """
    Build SFX events from script segment act labels.
    Maps act → SFX type → uses segment start time.

    Fallback when no words.json is available.
    """
    ACT_SFX_MAP = {
        "hook":     "whoosh",
        "problem":  "stamp",
        "solution": "whoosh",
        "proof":    "ding",
        "cta":      "punch",
    }

    events: list[dict] = []
    cumul = 0.0
    for seg in script_segments:
        act     = seg.get("act", "")
        sfx_key = ACT_SFX_MAP.get(act)
        dur     = seg.get("duration_sec", seg.get("duration_hint_sec", 5.0))
        if sfx_key:
            events.append({"sfx": sfx_key, "beat": act, "start_sec": round(cumul + 0.1, 3)})
        cumul += dur

    return events


# ──────────────────────────────────────────────
# SFX Burn into Video
# ──────────────────────────────────────────────

def burn_sfx_rail(
    video_path:  str,
    sfx_events:  list[dict],
    sfx_paths:   dict[str, str],
    output_path: str,
) -> str:
    """
    Mix SFX events into a video file at specified timestamps using FFmpeg.

    Parameters
    ----------
    video_path  : Input video with existing audio (VO + music).
    sfx_events  : List of {sfx, start_sec} dicts.
    sfx_paths   : Dict from download_sfx_kit() — {sfx_name: local_path}.
    output_path : Output video path.

    Returns
    -------
    str — output_path on success, video_path on failure (fallback).
    """
    # Filter to events where SFX file exists
    valid_events = [
        e for e in sfx_events
        if e["sfx"] in sfx_paths and os.path.isfile(sfx_paths[e["sfx"]])
    ]

    if not valid_events:
        logger.warning("[SFX] No valid SFX events to burn. Copying video unchanged.")
        import shutil
        shutil.copy(video_path, output_path)
        return output_path

    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    # Build FFmpeg filter_complex:
    # Each SFX is an additional input, delayed to its start_sec, then amixed with original audio
    inputs = ["-i", video_path]
    filter_parts = []
    sfx_labels = []

    for idx, event in enumerate(valid_events):
        sfx_path = sfx_paths[event["sfx"]]
        inputs  += ["-i", sfx_path]

        delay_ms = int(event["start_sec"] * 1000)
        label    = f"sfx{idx}"
        filter_parts.append(
            f"[{idx + 1}:a]adelay={delay_ms}|{delay_ms},apad[{label}]"
        )
        sfx_labels.append(f"[{label}]")

    # Mix original video audio with all SFX
    all_audio = f"[0:a]" + "".join(sfx_labels)
    n_inputs  = 1 + len(sfx_labels)
    filter_parts.append(
        f"{all_audio}amix=inputs={n_inputs}:duration=first:dropout_transition=0[aout]"
    )

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"[SFX] burn_sfx_rail failed: {result.stderr[-400:]}")
        import shutil
        shutil.copy(video_path, output_path)
        return video_path

    event_summary = ", ".join(f"{e['sfx']}@{e['start_sec']}s" for e in valid_events)
    logger.info(f"[SFX] Rail burned: {event_summary} → {Path(output_path).name}")
    return output_path
