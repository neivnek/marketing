"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/manual/pacing_analyzer.py — Scene Cut Extractor
====================================================================
"""

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_ffprobe(args: list[str]) -> dict | list:
    """Execute an ffprobe command and return parsed JSON output."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr}")
    return json.loads(result.stdout)


def get_video_info(video_path: str) -> dict:
    """
    Return basic video metadata: duration, fps, width, height.

    Parameters
    ----------
    video_path : Path to the video file.

    Returns
    -------
    dict with keys: duration, fps, width, height
    """
    info = _run_ffprobe(["-show_streams", "-show_format", video_path])
    fmt = info.get("format", {})
    duration = float(fmt.get("duration", 0))

    video_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
        {},
    )
    width  = int(video_stream.get("width",  1080))
    height = int(video_stream.get("height", 1920))

    # Parse FPS from avg_frame_rate field (e.g., "30/1" or "29.97")
    fps_str = video_stream.get("avg_frame_rate", "30/1")
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(fps_str)
    except ValueError:
        fps = 30.0

    return {"duration": duration, "fps": fps, "width": width, "height": height}


def extract_scene_timestamps(
    video_path:  str,
    threshold:   float = 0.3,
    min_gap_sec: float = 1.5,
) -> list[float]:
    """
    Detect scene cuts in a reference video using FFmpeg's scene filter.

    If the file is audio-only (e.g. MP3), falls back to evenly-spaced
    timestamps derived from the audio duration so the pipeline keeps working.

    Parameters
    ----------
    video_path  : Path to the reference video (or audio) file.
    threshold   : Scene change sensitivity 0-1 (lower = more cuts). Default 0.3.
    min_gap_sec : Minimum seconds between consecutive timestamps. Default 1.5.

    Returns
    -------
    list[float]
        Sorted list of scene cut timestamps in seconds, including
        the total duration as the final element.
    """
    logger.info(f"[pacing] Analyzing: {Path(video_path).name}")

    info = get_video_info(video_path)
    total_duration = info["duration"]

    # ── Guard: audio-only file has no video stream -> skip scene detect ──
    has_video = info.get("width", 0) > 0 and info.get("height", 0) > 0
    if not has_video:
        logger.warning(
            f"'{Path(video_path).name}' has no video stream (audio-only file). "
            "Using evenly spaced timestamps (every 4 s) based on audio duration."
        )
        interval = 4.0
        timestamps = []
        t = interval
        while t < total_duration:
            timestamps.append(round(t, 2))
            t += interval
        timestamps.append(round(total_duration, 2))
        logger.info(f"    [OK] {len(timestamps)} fallback timestamps: {timestamps}")
        return timestamps

    # ── Scene detection (video files only) ────────────────────────────
    # Use ffmpeg scene filter for detection
    scene_cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select=gt(scene\\,{threshold}),showinfo",
        "-an", "-f", "null", "-",
    ]

    result = subprocess.run(scene_cmd, capture_output=True, text=True)
    # Parse timestamps from showinfo output (stderr)
    output = result.stderr

    timestamps: list[float] = []
    last_ts = -999.0

    for line in output.split("\n"):
        if "pts_time" in line:
            # Extract pts_time value from showinfo output
            # Format: "... pts_time:3.500000 ..."
            for part in line.split():
                if part.startswith("pts_time:"):
                    try:
                        t = float(part.split(":")[1])
                        if t - last_ts >= min_gap_sec:
                            timestamps.append(round(t, 2))
                            last_ts = t
                    except (ValueError, IndexError):
                        pass

    # Fallback: if no cuts detected, create evenly spaced timestamps
    if not timestamps:
        logger.warning(
            "No scene cuts detected. Using evenly spaced timestamps (every 4s)."
        )
        interval = 4.0
        t = interval
        while t < total_duration:
            timestamps.append(round(t, 2))
            t += interval

    # Ensure final timestamp equals total duration
    timestamps = sorted(set(timestamps))
    if not timestamps or timestamps[-1] < total_duration - 0.5:
        timestamps.append(round(total_duration, 2))

    logger.info(f"    [OK] {len(timestamps)} cut points: {timestamps}")
    logger.info(f"    Total duration: {total_duration:.1f}s")

    return timestamps
