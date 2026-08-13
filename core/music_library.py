"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/music_library.py — Background Music Manager
====================================================================

Manages royalty-free background music stored locally in:
    assets/local_music/calm/
    assets/local_music/upbeat/
    assets/local_music/urgent/

Tracks must be manually downloaded once from royalty-free sources:
  - Pixabay Music   : https://pixabay.com/music/
  - YouTube Audio   : https://studio.youtube.com/channel/UC.../music
  - ccMixter        : http://ccmixter.org/

After downloading, place MP3/WAV files in the correct energy folder.
See assets/local_music/README_MUSIC.txt for details.

== MIXING STRATEGY ==

Default (robust, recommended — Rule 19):
  volume=0.15 fixed approach with stream_loop + amix duration=first.
  Simple, no threshold tuning, works reliably across all tracks.

Optional (--enable-ducking codepattern):
  sidechaincompress — requires per-track threshold in .meta.json
  (e.g. calm_01.meta.json: {"duck_threshold": 0.03}).
  NOT used by default because threshold varies per track's loudness.

== FFmpeg command (default) ==

ffmpeg -i video.mp4 -stream_loop -1 -i music.mp3 \\
  -filter_complex "[1:a]volume=0.15[bg];[0:a][bg]amix=inputs=2:duration=first[a]" \\
  -map 0:v -map "[a]" -shortest -c:v copy -c:a aac out.mp4

  -stream_loop -1    : auto-loops music if shorter than video
  -shortest          : audio stops when shortest input (video) ends
  duration=first     : amix matches length of first input (video audio)
  volume=0.15        : ≈ 15-18 dB below voice — safe starting point
"""

import glob
import json
import logging
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MUSIC_BASE_DIR  = "assets/local_music"
SUPPORTED_EXTS  = (".mp3", ".wav", ".m4a", ".ogg", ".flac")
DEFAULT_VOLUME  = 0.15   # volume= factor (0.15 ≈ -16dB relative)


# ── Track Selection ───────────────────────────────────────────────

def _list_tracks(energy: str) -> list[str]:
    """Return all music files in assets/local_music/<energy>/."""
    folder = os.path.join(MUSIC_BASE_DIR, energy)
    if not os.path.isdir(folder):
        logger.debug(f"[Music] Folder not found: {folder}")
        return []
    tracks = []
    for ext in SUPPORTED_EXTS:
        tracks.extend(glob.glob(os.path.join(folder, f"*{ext}")))
    return tracks


def pick_track(energy: str, used_recently: set = None) -> Optional[str]:
    """
    Randomly pick a music track for the given energy level.
    Avoids recently used tracks (set of filenames).
    Falls back to any other energy folder if requested energy is empty.

    Parameters
    ----------
    energy        : "calm" | "upbeat" | "urgent"
    used_recently : Set of track filenames used recently (avoid repeat).

    Returns
    -------
    str path or None if no tracks found at all.
    """
    if used_recently is None:
        used_recently = set()

    tracks = _list_tracks(energy)
    candidates = [t for t in tracks if Path(t).name not in used_recently]
    if not candidates:
        candidates = tracks   # if all recently used, allow repeats

    if candidates:
        return random.choice(candidates)

    # Fallback: try other energies
    for alt in ("upbeat", "calm", "urgent"):
        if alt == energy:
            continue
        alt_tracks = _list_tracks(alt)
        if alt_tracks:
            logger.warning(f"[Music] No '{energy}/' tracks — using '{alt}/' instead.")
            return random.choice(alt_tracks)

    return None


def _load_track_meta(track_path: str) -> dict:
    """Load optional .meta.json next to a track file for per-track config."""
    meta_path = Path(track_path).with_suffix(".meta.json")
    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ── Mix Implementations ───────────────────────────────────────────

def mix_under_voice(
    video_path:    str,
    music_path:    str,
    output_path:   str,
    duration_sec:  float,
    music_volume:  float = DEFAULT_VOLUME,
    method:        str   = "volume",
) -> str:
    """
    Mix background music under the video's existing audio track.

    Default method: "volume" (fixed ratio, robust, recommended).
    Optional method: "ducking" (sidechaincompress — requires .meta.json threshold).

    Parameters
    ----------
    video_path   : Input video with voice audio already muxed.
    music_path   : Music track file path.
    output_path  : Output video with background music mixed in.
    music_volume : Volume factor for music (0.15 = ~-16dB, safe default).
    method       : "volume" (default) | "ducking" (needs per-track .meta.json).

    Returns
    -------
    str — output_path.
    """
    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    if method == "ducking":
        return _mix_ducking(video_path, music_path, output_path, duration_sec, music_volume)
    else:
        return _mix_volume_fixed(video_path, music_path, output_path, duration_sec, music_volume)


def _mix_volume_fixed(
    video_path:   str,
    music_path:   str,
    output_path:  str,
    duration_sec: float,
    music_volume: float,
) -> str:
    """
    Default robust mix: volume= fixed ratio, stream_loop -1, amix duration=first.

    FFmpeg flow (single pass):
      -stream_loop -1 -i music          : loops music input infinitely
      [1:a]volume=X[bg]                 : attenuate music
      [0:a][bg]amix=inputs=2:duration=first[a] : mix, stop when video audio ends
      -map 0:v -map [a] -shortest       : output video track + mixed audio
    """
    cmd = [
        "ffmpeg", "-y",
        "-i",           video_path,
        "-stream_loop", "-1",
        "-i",           music_path,
        "-filter_complex",
        (
            f"[1:a]volume={music_volume:.4f}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=longest:dropout_transition=2[a]"
        ),
        "-map", "0:v",
        "-map", "[a]",
        "-t", str(duration_sec),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"[Music] mix_volume_fixed failed: {result.stderr[-300:]}")
    logger.info(f"[Music] Fixed-volume mix ({music_volume}) -> {Path(output_path).name}")
    return output_path


def _mix_ducking(
    video_path:   str,
    music_path:   str,
    output_path:  str,
    duration_sec: float,
    music_volume: float,
) -> str:
    """
    Optional sidechaincompress ducking mix.
    Threshold loaded from .meta.json; falls back to _mix_volume_fixed if missing.
    """
    meta = _load_track_meta(music_path)
    threshold = meta.get("duck_threshold", None)

    if threshold is None:
        logger.warning(
            f"[Music] No duck_threshold in .meta.json for '{Path(music_path).name}'. "
            "Falling back to fixed-volume mix."
        )
        return _mix_volume_fixed(video_path, music_path, output_path, duration_sec, music_volume)

    # sidechaincompress: voice sidechain compresses the music
    cmd = [
        "ffmpeg", "-y",
        "-i",           video_path,
        "-stream_loop", "-1",
        "-i",           music_path,
        "-filter_complex",
        (
            f"[0:a]asplit=2[voice][sidechain];"
            f"[1:a]volume={music_volume:.4f}[music_att];"
            f"[music_att][sidechain]sidechaincompress="
            f"threshold={threshold}:ratio=4:attack=200:release=1000[bg];"
            f"[voice][bg]amix=inputs=2:duration=longest:dropout_transition=2[a]"
        ),
        "-map", "0:v",
        "-map", "[a]",
        "-t", str(duration_sec),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            f"[Music] sidechaincompress failed ({result.stderr[-200:]}). "
            "Falling back to fixed-volume mix."
        )
        return _mix_volume_fixed(video_path, music_path, output_path, duration_sec, music_volume)

    logger.info(f"[Music] Ducking mix (threshold={threshold}) -> {Path(output_path).name}")
    return output_path


# ── Public API ────────────────────────────────────────────────────

def mix_background_music(
    video_path:    str,
    output_path:   str,
    energy:        str,
    duration_sec:  float,
    temp_dir:      str   = "temp",
    music_volume:  float = DEFAULT_VOLUME,
    enable_ducking: bool = False,
) -> str:
    """
    Select, loop, and mix a background music track into the video.

    Parameters
    ----------
    video_path    : Input video (with voice audio already muxed in).
    output_path   : Output video with background music.
    energy        : "calm" | "upbeat" | "urgent"
    duration_sec  : Total video duration in seconds (used only for logging).
    temp_dir      : Temp workspace.
    music_volume  : Volume factor (default 0.15). Tune per-track if needed.
    enable_ducking: If True + .meta.json has threshold, use sidechaincompress.

    Returns
    -------
    str — output_path.
         If no music tracks found, copies video to output_path unchanged.
    """
    track = pick_track(energy)
    if not track:
        logger.warning(
            "[Music] No local music tracks found. "
            "Add MP3 files to assets/local_music/calm|upbeat|urgent/. "
            "Copying video without background music."
        )
        shutil.copy(video_path, output_path)
        return output_path

    logger.info(f"[Music] Track selected: {Path(track).name}  energy={energy}  dur={duration_sec:.0f}s")

    os.makedirs(temp_dir, exist_ok=True)
    method = "ducking" if enable_ducking else "volume"

    try:
        return mix_under_voice(
            video_path=video_path,
            music_path=track,
            output_path=output_path,
            duration_sec=duration_sec,
            music_volume=music_volume,
            method=method,
        )
    except Exception as exc:
        logger.warning(f"[Music] Mix failed — copying video without music: {exc}")
        shutil.copy(video_path, output_path)
        return output_path
