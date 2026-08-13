"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/ffmpeg_utils.py — FFmpeg Wrapper (Ken Burns + Assembly)
====================================================================
"""

import json
import logging
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _run(cmd: list[str], label: str = "") -> None:
    """Run an FFmpeg command and raise on non-zero exit."""
    logger.debug(f"FFmpeg [{label}]: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg error [{label}]:\n{result.stderr}"
        )


def check_ffmpeg() -> None:
    """Verify that ffmpeg is installed and available in PATH."""
    if shutil.which("ffmpeg") is None:
        raise EnvironmentError(
            "ffmpeg not found in PATH. "
            "Install it from https://ffmpeg.org/download.html"
        )


# ──────────────────────────────────────────────
# Ken Burns Effect
# ──────────────────────────────────────────────

def _build_ken_burns_filter(
    timestamps: list[float],
    total_duration: float,
    zoom_start: float,
    zoom_end:   float,
    pan_directions: list[str],
    out_w: int,
    out_h: int,
) -> str:
    """
    Build a complex FFmpeg zoompan filter string that creates Ken Burns
    motion segmented by the provided timestamps.

    Each segment between timestamps gets a unique pan direction so
    the motion matches the pacing of the reference video.
    """
    segments = []
    prev = 0.0

    if not timestamps:
        timestamps = []

    # Ensure we always have a final segment endpoint
    cut_points = [t for t in timestamps if 0 < t < total_duration] + [total_duration]

    for i, end_t in enumerate(cut_points):
        seg_dur = end_t - prev
        if seg_dur <= 0:
            continue

        direction = pan_directions[i % len(pan_directions)]
        frames    = int(seg_dur * 30)  # 30 fps

        # Pan direction vectors (normalised to ±1 % of image size)
        pan_map = {
            "left":   ("zoom*iw-ow",         "(ih-oh)/2"),
            "right":  ("0",                  "(ih-oh)/2"),
            "up":     ("(iw-ow)/2",          "zoom*ih-oh"),
            "down":   ("(iw-ow)/2",          "0"),
            "center": ("(iw-ow)/2",          "(ih-oh)/2"),
        }
        x_expr, y_expr = pan_map.get(direction, pan_map["center"])

        seg_filter = (
            f"zoompan=z='min(zoom+{(zoom_end - zoom_start) / max(frames, 1):.6f},1.5)':"
            f"x='{x_expr}':y='{y_expr}':d={frames}:s={out_w}x{out_h}:fps=30"
        )
        segments.append(seg_filter)
        prev = end_t

    # Chain segments with concat
    if len(segments) == 1:
        return segments[0]

    # Each segment needs to be a separate filter stream, then concatenated
    # For simplicity we build a single zoompan with the full duration
    # More sophisticated multi-segment approach uses trim+zoompan+concat
    return segments[0]  # fallback to first segment for single-image Ken Burns


def apply_ken_burns(
    image_path:     str,
    output_path:    str,
    timestamps:     list[float],
    total_duration: float,
    out_w:          int   = 1080,
    out_h:          int   = 1920,
    zoom_start:     float = 1.0,
    zoom_end:       float = 1.08,
    pan_directions: Optional[list[str]] = None,
    fps:            int   = 30,
    temp_dir:       Optional[str] = None,
) -> str:
    """
    Apply Ken Burns (zoom + pan) motion to a still image using FFmpeg.

    Produces a silent MP4 video at the given duration, segmented by
    the pacing timestamps from the reference video.

    Parameters
    ----------
    image_path     : Path to the product image (jpg/png).
    output_path    : Destination MP4 path.
    timestamps     : Scene cut timestamps in seconds (from reference video).
    total_duration : Total video duration to produce (matches voiceover length).
    out_w / out_h  : Output resolution (default 1080x1920).
    zoom_start     : Zoom level at start of each segment.
    zoom_end       : Zoom level at end of each segment (creates push-in effect).
    pan_directions : List of pan directions to cycle through per segment.
    fps            : Output frame rate.

    Returns
    -------
    str — Path to the rendered silent MP4.
    """
    check_ffmpeg()

    if pan_directions is None:
        pan_directions = ["left", "right", "up", "down", "center"]
        random.shuffle(pan_directions)

    # Resolve output dir and temp dir independently (avoids temp\temp double-path)
    out_parent = str(Path(output_path).parent)
    os.makedirs(out_parent, exist_ok=True)

    if temp_dir is None:
        temp_dir = out_parent
    os.makedirs(temp_dir, exist_ok=True)

    # Build per-segment Ken Burns using concat demuxer approach:
    # For multi-segment we create individual clips then concatenate.
    segments_paths = []
    prev = 0.0
    cut_points = [t for t in timestamps if 0 < t < total_duration] + [total_duration]

    for idx, end_t in enumerate(cut_points):
        seg_dur = round(end_t - prev, 3)
        if seg_dur <= 0.0:
            continue

        direction   = pan_directions[idx % len(pan_directions)]
        frames      = max(int(seg_dur * fps), 2)
        seg_out     = os.path.join(temp_dir, f"kb_seg_{idx:03d}.mp4")

        pan_map = {
            "left":   ("trunc(if(lte(zoom,1.0),(iw-ow)/2,max(0,min(iw-ow,x+1))))", "trunc((ih-oh)/2)"),
            "right":  ("trunc(if(lte(zoom,1.0),(iw-ow)/2,max(0,min(iw-ow,x-1))))", "trunc((ih-oh)/2)"),
            "up":     ("trunc((iw-ow)/2)", "trunc(if(lte(zoom,1.0),(ih-oh)/2,max(0,min(ih-oh,y+1))))"),
            "down":   ("trunc((iw-ow)/2)", "trunc(if(lte(zoom,1.0),(ih-oh)/2,max(0,min(ih-oh,y-1))))"),
            "center": ("trunc((iw-ow)/2)", "trunc((ih-oh)/2)"),
        }
        x_expr, y_expr = pan_map.get(direction, pan_map["center"])

        zoom_step = (zoom_end - zoom_start) / max(frames - 1, 1)

        zp_filter = (
            f"scale=8000:-1,"
            f"zoompan="
            f"z='min({zoom_start:.4f}+on*{zoom_step:.6f},{zoom_end:.4f})':"
            f"x='{x_expr}':"
            f"y='{y_expr}':"
            f"d={frames}:"
            f"s={out_w}x{out_h}:"
            f"fps={fps},"
            f"setsar=1"
        )

        _run([
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", zp_filter,
            "-t", str(seg_dur),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            seg_out,
        ], label=f"ken_burns_seg_{idx}")

        segments_paths.append(seg_out)
        prev = end_t

    # Concatenate all segments
    if len(segments_paths) == 1:
        shutil.copy(segments_paths[0], output_path)
    else:
        concat_list = os.path.join(temp_dir, "kb_concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in segments_paths:
                # Use absolute, forward-slash paths so FFmpeg resolves them
                # regardless of the working directory
                abs_p = str(Path(p).resolve()).replace("\\", "/")
                f.write(f"file '{abs_p}'\n")
        _run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output_path,
        ], label="ken_burns_concat")

    logger.info(f"[VIDEO]  Ken Burns visual: {output_path}  ({total_duration:.1f}s, {len(segments_paths)} segments)")
    return output_path


# ──────────────────────────────────────────────
# Color Filter Application (for Manual Prompt)
# ──────────────────────────────────────────────

def apply_color_filter(
    input_video: str,
    output_path: str,
    filter_str:  str,
) -> str:
    """
    Apply an FFmpeg color-grading filter chain to a video.

    Parameters
    ----------
    input_video : Path to the silent Ken Burns video.
    output_path : Destination path.
    filter_str  : FFmpeg -vf filter string (e.g., 'eq=saturation=1.3,curves=...').

    Returns
    -------
    str — Path to the color-graded video.
    """
    check_ffmpeg()
    _run([
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        output_path,
    ], label="color_filter")
    logger.info(f"[COLOR]  Color filter applied -> {output_path}")
    return output_path


# ──────────────────────────────────────────────
# Final Assembly
# ──────────────────────────────────────────────

def assemble_video(
    visual_path:   str,
    audio_path:    str,
    output_path:   str,
    video_codec:   str = "libx264",
    audio_codec:   str = "aac",
    crf:           int = 23,
) -> str:
    """
    Mux a silent video with an audio track.
    The output duration is determined by the shorter of the two streams
    (audio voiceover drives the cut, video loops if needed).

    Returns
    -------
    str — Path to the muxed MP4.
    """
    check_ffmpeg()
    _run([
        "ffmpeg", "-y",
        "-i", visual_path,
        "-i", audio_path,
        "-c:v", video_codec,
        "-c:a", audio_codec,
        "-crf", str(crf),
        "-shortest",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ], label="assemble")
    logger.info(f"[LINK]  Assembled AV: {output_path}")
    return output_path


# ──────────────────────────────────────────────
# Hardcoded Subtitle Burn
# ──────────────────────────────────────────────

def burn_hardsub(
    input_video: str,
    ass_path:    str,
    fonts_dir:   str,
    output_path: str,
    crf:         int = 23,
) -> str:
    """
    Burn ASS subtitles permanently into the video (hardsub).
    Khmer Unicode fonts are loaded from fonts_dir.

    Returns
    -------
    str — Path to the final hardsubbed MP4.
    """
    check_ffmpeg()

    # Normalise path separators for FFmpeg on Windows
    ass_path_ff   = ass_path.replace("\\", "/").replace(":", "\\:")
    fonts_dir_ff  = fonts_dir.replace("\\", "/")

    sub_filter = f"subtitles='{ass_path_ff}':fontsdir='{fonts_dir_ff}'"

    _run([
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", sub_filter,
        "-c:v", "libx264",
        "-c:a", "copy",
        "-crf", str(crf),
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ], label="hardsub")
    logger.info(f"[SUB]  Hardsubbed video: {output_path}")
    return output_path


# ──────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────

def cleanup_temp(temp_dir: str) -> None:
    """Remove the entire temp directory and all its contents."""
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"[CLEAN]  Temp directory cleaned: {temp_dir}")


# ──────────────────────────────────────────────
# Probe Utilities
# ──────────────────────────────────────────────

def get_video_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def normalize_segment_cfr(
    input_path: str,
    output_path: str,
    fps: int = 30
) -> str:
    """
    Normalize a video segment to Constant Frame Rate (CFR) before concatenation.
    This prevents stuttering and freezes at scene cuts.
    """
    check_ffmpeg()
    _run([
        "ffmpeg", "-y",
        "-i", input_path,
        "-vsync", "cfr",
        "-r", str(fps),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        output_path,
    ], label="normalize_cfr")
    logger.debug(f"[CFR] Normalized {input_path} -> {output_path} at {fps}fps")
    return output_path

def adjust_audio_speed(input_audio: str, output_audio: str, target_duration: float):
    """Adjust audio speed to match a target duration."""
    from core.tts_engine import get_audio_duration
    dur = get_audio_duration(input_audio)
    if dur <= 0:
        return
    ratio = dur / target_duration
    
    # ffpmeg atempo filter is limited between 0.5 and 2.0
    # we can chain them if we need, but for simplicity a single ratio or capping it works for most minor adjustments.
    if ratio < 0.5: ratio = 0.5
    if ratio > 2.0: ratio = 2.0

    _run([
        "ffmpeg", "-y",
        "-i", input_audio,
        "-filter:a", f"atempo={ratio}",
        output_audio
    ], label="adjust_audio_speed")


# ──────────────────────────────────────────────
# Audio Master Pass — Loudness Normalization
# ──────────────────────────────────────────────

def master_audio_pass(
    video_path:   str,
    output_path:  str,
    target_lufs:  float = -14.0,
    true_peak:    float = -1.5,
    lra:          float = 11.0,
) -> str:
    """
    Normalise loudness of a video to broadcast/social-media standard
    using FFmpeg's EBU R128 loudnorm filter.

    Target defaults (-14 LUFS / -1.5 dBTP / LRA 11) match the
    Meta Ads and TikTok auto-normalization targets, ensuring consistent
    perceived volume across all hook variants regardless of which TTS
    engine or audio pipeline produced the source audio.

    This is a LINEAR 2-pass implementation:
      Pass 1  — probe actual loudness statistics (print_format=json).
      Pass 2  — apply linear normalization with measured stats.
    Linear mode preserves dynamic range better than the default
    non-linear mode for speech+music mixes.

    Parameters
    ----------
    video_path  : Input video (must have audio stream).
    output_path : Destination path for normalized video.
    target_lufs : Integrated loudness target in LUFS (default -14.0).
    true_peak   : Maximum true peak in dBTP (default -1.5).
    lra         : Loudness range target in LU (default 11.0).

    Returns
    -------
    str — output_path on success. Copies input unchanged on failure.
    """
    import json as _json
    import shutil as _shutil

    check_ffmpeg()
    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    # ── Pass 1: Measure ────────────────────────────────────────────────
    probe_filter = (
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}"
        ":print_format=json"
    )
    probe_cmd = [
        "ffmpeg", "-y",
        "-i",          video_path,
        "-filter:a",   probe_filter,
        "-f",          "null",
        "-",
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)

    # loudnorm stats are written to stderr
    stderr_text = probe_result.stderr
    stats: dict = {}
    try:
        # Extract JSON block from ffmpeg stderr output
        json_start = stderr_text.rfind("{")
        json_end   = stderr_text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            stats = _json.loads(stderr_text[json_start:json_end])
    except Exception as exc:
        logger.warning(f"[AudioMaster] Could not parse loudnorm stats: {exc}. Copying unchanged.")
        _shutil.copy(video_path, output_path)
        return output_path

    if not stats:
        logger.warning("[AudioMaster] No loudnorm stats returned. Copying video unchanged.")
        _shutil.copy(video_path, output_path)
        return output_path

    measured_I   = stats.get("input_i",   "-23")
    measured_TP  = stats.get("input_tp",  "-2")
    measured_LRA = stats.get("input_lra", "7")
    measured_thresh = stats.get("input_thresh", "-33")
    offset       = stats.get("target_offset", "0")

    # ── Pass 2: Apply normalized loudness ─────────────────────────────
    normalize_filter = (
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}"
        f":measured_I={measured_I}"
        f":measured_TP={measured_TP}"
        f":measured_LRA={measured_LRA}"
        f":measured_thresh={measured_thresh}"
        f":offset={offset}"
        ":linear=true"
        ":print_format=none"
    )

    _run([
        "ffmpeg", "-y",
        "-i",        video_path,
        "-filter:a", normalize_filter,
        "-c:v",      "copy",
        "-c:a",      "aac",
        "-b:a",      "192k",
        "-ar",       "48000",
        output_path,
    ], label="master_audio_pass")

    logger.info(
        f"[AudioMaster] Normalized to {target_lufs} LUFS / {true_peak} dBTP → "
        f"{Path(output_path).name}"
    )
    return output_path
