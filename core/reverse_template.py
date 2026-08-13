"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/reverse_template.py — Video Ad Reverse-Template Analyzer
====================================================================

Phân tích cấu trúc của một video quảng cáo thắng cuộc và trích xuất
ra một "template thông số" có thể tái sử dụng — hoàn toàn miễn phí.

Quy trình (từ fb-ad-video-studio/references/reverse-template.md):
  1. Tải/đọc video reference (local hoặc URL via yt-dlp)
  2. Extract frame storyboard (ffmpeg fps=2)
  3. Transcribe với Whisper → word timestamps
  4. Map scene arc (hook/problem/solution/proof/CTA) theo timestamps
  5. Đo pacing: cut cadence, beat length, SFX density
  6. Xuất ra TemplateBlueprint JSON (có thể feed vào creative director)

QUAN TRỌNG về đạo đức:
  Chỉ trích xuất CẤU TRÚC và PACING — không copy footage, VO, music,
  logo, hay copy của đối thủ. Deliverable là "shape" (hình dạng ad),
  không phải clone.

Output: TemplateBlueprint dict với:
  - scene_arc: [{beat, start_sec, end_sec, duration}, ...]
  - pacing: {avg_beat_sec, cut_cadence_hz, sfx_density_per_30s}
  - device: "kinetic_type" | "talking_head" | "split_screen" | ...
  - recommended_template: tên template fb-ad-studio phù hợp nhất
  - word_timestamps: raw words list (để anchor captions mới)
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Template Blueprint Type
# ──────────────────────────────────────────────

def _empty_blueprint() -> dict:
    return {
        "source":               "",
        "total_duration_sec":   0.0,
        "scene_arc":            [],
        "pacing": {
            "avg_beat_sec":        0.0,
            "cut_cadence_hz":      0.0,
            "sfx_density_per_30s": 0.0,
            "has_music":           False,
            "has_voiceover":       True,
        },
        "device":               "kinetic_type",
        "recommended_template": "motion-graphics-spot",
        "word_timestamps":      [],
        "transcript":           "",
        "notes":                [],
    }


# ──────────────────────────────────────────────
# Video Download (yt-dlp, optional)
# ──────────────────────────────────────────────

def download_reference_video(
    url:      str,
    temp_dir: str,
) -> Optional[str]:
    """
    Download a reference video from a URL using yt-dlp.
    Returns local path or None if download fails.

    Requirements: yt-dlp (already in requirements.txt)
    """
    os.makedirs(temp_dir, exist_ok=True)
    out_template = os.path.join(temp_dir, "ref_video.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--format", "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--output", out_template,
        "--quiet",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"[ReverseTemplate] yt-dlp failed: {result.stderr[:200]}")
        return None

    # Find the downloaded file
    for f in os.listdir(temp_dir):
        if f.startswith("ref_video."):
            return os.path.join(temp_dir, f)

    return None


# ──────────────────────────────────────────────
# Frame Extraction (Visual Storyboard)
# ──────────────────────────────────────────────

def extract_storyboard_frames(
    video_path: str,
    output_dir: str,
    fps:        float = 2.0,
) -> list[str]:
    """
    Extract frames at `fps` rate for visual storyboard review.
    Returns list of frame image paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"fps={fps}",
        os.path.join(output_dir, "frame_%04d.jpg"),
        "-loglevel", "error",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"[ReverseTemplate] Frame extraction failed: {result.stderr[:200]}")
        return []

    frames = sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    )
    logger.info(f"[ReverseTemplate] Extracted {len(frames)} storyboard frames.")
    return frames


# ──────────────────────────────────────────────
# Transcription + Word Timestamps
# ──────────────────────────────────────────────

def transcribe_reference(video_path: str) -> tuple[str, list[dict]]:
    """
    Transcribe video audio using faster-whisper.
    Returns (full_transcript, word_timestamps_list).
    """
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small.en", compute_type="int8")
        segments, info = model.transcribe(
            video_path,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            word_timestamps=True,
        )

        words = []
        transcript_parts = []
        for seg in segments:
            transcript_parts.append(seg.text)
            for w in (seg.words or []):
                words.append({"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)})

        transcript = " ".join(transcript_parts).strip()
        logger.info(f"[ReverseTemplate] Transcribed {len(words)} words from reference video.")
        return transcript, words

    except ImportError:
        logger.warning("[ReverseTemplate] faster-whisper not installed. Transcript unavailable.")
        return "", []
    except Exception as exc:
        logger.warning(f"[ReverseTemplate] Transcription failed: {exc}")
        return "", []


# ──────────────────────────────────────────────
# Scene Arc Mapping (Gemini AI)
# ──────────────────────────────────────────────

def map_scene_arc_with_ai(
    transcript:      str,
    word_timestamps: list[dict],
    total_duration:  float,
    api_key:         str,
) -> list[dict]:
    """
    Use Gemini to identify the scene arc beats (hook/problem/solution/proof/CTA)
    and their timestamps from the transcript.

    Returns
    -------
    list of {beat, start_sec, end_sec, duration, summary, voiceover_excerpt}
    """
    if not transcript.strip() or not api_key:
        return _fallback_scene_arc(total_duration)

    try:
        from google import genai
        from google.genai import types

        prompt = f"""Analyze this ad video transcript and identify the scene arc beats.

Total video duration: {total_duration:.1f} seconds
Transcript with approximate timing:
{_format_transcript_with_times(word_timestamps)}

Identify these beats in the transcript:
- hook: Opening pattern interrupt (first 0-4s)
- problem: Problem/pain being presented
- solution: Product/solution introduction
- proof: Social proof, numbers, testimonials
- cta: Call to action / offer

For each beat, extract the START word and END word from the transcript to infer timing.

Return ONLY a JSON array:
[
  {{
    "beat": "hook",
    "start_sec": 0.2,
    "end_sec": 3.5,
    "summary": "brief description of what happens",
    "voiceover_excerpt": "first few words of this beat"
  }}
]
Only include beats that are clearly present. Skip if absent."""

        client = genai.Client(api_key=api_key)
        fallback_models = [
            os.getenv("GEMINI_MODEL", "").strip(),
            "gemini-3.6-flash",
            "gemini-2.0-flash",
        ]
        for model in [m for m in fallback_models if m]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=1024,
                        response_mime_type="application/json",
                    ),
                )
                raw = re.sub(r"```[a-z]*\n?", "", response.text.strip()).strip()
                arc = json.loads(raw)
                # Enrich with duration
                for beat in arc:
                    beat["duration"] = round(beat["end_sec"] - beat["start_sec"], 2)
                logger.info(f"[ReverseTemplate] Scene arc: {len(arc)} beats identified.")
                return arc
            except Exception as exc:
                logger.debug(f"[ReverseTemplate] Model {model} arc mapping failed: {exc}")
                continue

    except Exception as exc:
        logger.warning(f"[ReverseTemplate] AI arc mapping failed: {exc}")

    return _fallback_scene_arc(total_duration)


def _format_transcript_with_times(words: list[dict], max_words: int = 200) -> str:
    """Format first max_words words with timestamps for AI prompt."""
    lines = []
    for w in words[:max_words]:
        lines.append(f"[{w['start']:.1f}s] {w['w']}")
    return " ".join(lines)


def _fallback_scene_arc(total_duration: float) -> list[dict]:
    """Proportional fallback when AI mapping is unavailable."""
    ratios = [
        ("hook",     0.00, 0.17),
        ("problem",  0.17, 0.40),
        ("solution", 0.40, 0.65),
        ("proof",    0.65, 0.85),
        ("cta",      0.85, 1.00),
    ]
    return [
        {
            "beat":              beat,
            "start_sec":         round(s * total_duration, 2),
            "end_sec":           round(e * total_duration, 2),
            "duration":          round((e - s) * total_duration, 2),
            "summary":           f"{beat} beat (proportional estimate)",
            "voiceover_excerpt": "",
        }
        for beat, s, e in ratios
    ]


# ──────────────────────────────────────────────
# Device Detection
# ──────────────────────────────────────────────

def detect_device(transcript: str, notes: list[str]) -> tuple[str, str]:
    """
    Heuristically detect the creative device and recommend a template.

    Returns
    -------
    (device: str, recommended_template: str)
    """
    # Kinetic-type indicators: short punchy phrases, no presenter mentions
    if len(transcript.split()) < 60:
        return "kinetic_type", "motion-graphics-spot"

    # iMessage indicators
    if any(kw in transcript.lower() for kw in ["hey ", "omg", "lol", "text me", "dm me"]):
        return "imessage", "imessage-conversation"

    # List indicators
    if re.search(r"\b(reason[s]?|tip[s]?|step[s]?|number [1-5]|#[1-5])\b", transcript, re.I):
        return "listicle", "listicle-top5"

    # Long transcript → likely talking head
    if len(transcript.split()) > 100:
        return "talking_head", "talking-head-founder-ad"

    return "kinetic_type", "motion-graphics-spot"


# ──────────────────────────────────────────────
# Pacing Measurement
# ──────────────────────────────────────────────

def measure_pacing(
    scene_arc:       list[dict],
    total_duration:  float,
    word_timestamps: list[dict],
) -> dict:
    """Compute pacing metrics from scene arc and word timestamps."""
    beats = len(scene_arc)
    avg_beat = round(total_duration / beats, 2) if beats else 0.0

    # Cut cadence: beats per second
    cut_hz = round(beats / total_duration, 3) if total_duration else 0.0

    # Word density (proxy for VO speed)
    word_count    = len(word_timestamps)
    words_per_min = round(word_count / total_duration * 60, 0) if total_duration else 0.0

    # Rough SFX density estimate (1 per beat transition)
    sfx_density = round(beats / total_duration * 30, 1) if total_duration else 0.0

    return {
        "avg_beat_sec":        avg_beat,
        "cut_cadence_hz":      cut_hz,
        "words_per_min":       words_per_min,
        "sfx_density_per_30s": sfx_density,
        "has_music":           False,  # cannot detect from transcript alone
        "has_voiceover":       bool(word_timestamps),
        "beat_count":          beats,
    }


# ──────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────

def analyze_reference(
    source:   str,          # local file path OR URL
    temp_dir: str,
    api_key:  str = "",
    extract_frames: bool = True,
) -> dict:
    """
    Full reverse-template analysis pipeline.

    Parameters
    ----------
    source    : Path to video file OR public URL (YouTube, etc.).
    temp_dir  : Temp directory for frames and downloads.
    api_key   : Gemini API key for AI arc mapping (optional — uses proportional fallback).
    extract_frames : If True, extract storyboard JPEG frames into temp_dir/frames/.

    Returns
    -------
    TemplateBlueprint dict — ready to save as JSON and feed to creative director.

    ETHICS NOTE: Only structure and pacing are extracted — never footage, audio,
    or copy from the reference. The output is a parametric shape, not a clone.
    """
    blueprint = _empty_blueprint()
    blueprint["source"] = source

    # ── Step 1: Resolve video path ─────────────────────────────────
    video_path = source
    if source.startswith("http"):
        logger.info(f"[ReverseTemplate] Downloading reference: {source[:60]}...")
        video_path = download_reference_video(source, temp_dir)
        if not video_path:
            blueprint["notes"].append("ERROR: Could not download reference video.")
            return blueprint

    if not os.path.isfile(video_path):
        blueprint["notes"].append(f"ERROR: Video not found: {video_path}")
        return blueprint

    # ── Step 2: Get total duration ──────────────────────────────────
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
            capture_output=True, text=True,
        )
        total_dur = float(json.loads(result.stdout)["format"]["duration"])
        blueprint["total_duration_sec"] = round(total_dur, 2)
    except Exception as exc:
        blueprint["notes"].append(f"Could not read duration: {exc}")
        total_dur = 30.0

    # ── Step 3: Storyboard frames ───────────────────────────────────
    if extract_frames:
        frames_dir = os.path.join(temp_dir, "reverse_frames")
        frames = extract_storyboard_frames(video_path, frames_dir, fps=2.0)
        blueprint["notes"].append(f"Storyboard: {len(frames)} frames in {frames_dir}")

    # ── Step 4: Transcribe ──────────────────────────────────────────
    transcript, word_timestamps = transcribe_reference(video_path)
    blueprint["transcript"]     = transcript
    blueprint["word_timestamps"] = word_timestamps

    # ── Step 5: Map scene arc ───────────────────────────────────────
    scene_arc = map_scene_arc_with_ai(transcript, word_timestamps, total_dur, api_key)
    blueprint["scene_arc"] = scene_arc

    # ── Step 6: Detect device ───────────────────────────────────────
    device, recommended = detect_device(transcript, blueprint["notes"])
    blueprint["device"]               = device
    blueprint["recommended_template"] = recommended

    # ── Step 7: Measure pacing ──────────────────────────────────────
    blueprint["pacing"] = measure_pacing(scene_arc, total_dur, word_timestamps)

    # ── Step 8: Pacing notes ────────────────────────────────────────
    avg_beat = blueprint["pacing"]["avg_beat_sec"]
    if avg_beat > 5.0:
        blueprint["notes"].append(
            f"Average beat {avg_beat:.1f}s is > 5s. "
            "Split long beats for tighter pacing when using this as a template."
        )

    blueprint["notes"].append(
        f"Recommended template: {recommended} ({device}). "
        "Use scene_arc ratios to time your new beats proportionally."
    )
    blueprint["notes"].append(
        "ETHICS: Only structure extracted — never reuse reference footage, VO, music, or copy."
    )

    logger.info(
        f"[ReverseTemplate] Analysis complete — "
        f"device={device}, template={recommended}, "
        f"beats={len(scene_arc)}, duration={total_dur:.0f}s"
    )

    return blueprint


def save_blueprint(blueprint: dict, output_path: str) -> str:
    """Save a template blueprint to a JSON file."""
    os.makedirs(str(Path(output_path).parent), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(blueprint, f, ensure_ascii=False, indent=2)
    logger.info(f"[ReverseTemplate] Blueprint saved → {output_path}")
    return output_path
