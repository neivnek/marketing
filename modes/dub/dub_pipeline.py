"""
====================================================================
  Pipeline v3.0
  File: modes/dub/dub_pipeline.py — Dub Only Mode
====================================================================

Nhan vao:
  - Video goc (bat ky ngon ngu)
  - Kich ban tieng Khmer

Xuat ra:
  - Video goc co giong doc tieng Khmer thay the hoac overlay
  - Phu de Khmer tu dong
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.tts_engine import synthesize_khmer
from core.subtitle_gen import generate_ass_file
from core.ffmpeg_utils import burn_hardsub, get_video_duration

logger = logging.getLogger(__name__)


@dataclass
class DubInputs:
    source_video:  str          # Duong dan video goc
    script:        str          # Kich ban tieng Khmer
    tts_voice:     str = "km-KH-SreymomNeural"
    tts_rate:      str = "+0%"
    mix_mode:      str = "replace"   # "replace" | "mix" (overlay on original)
    mix_volume:    float = 0.08      # Volume goc khi o che do mix
    with_subtitles: bool = True


def run_dub_pipeline(inputs: DubInputs, output_dir: str, temp_dir: str) -> str:
    """
    Luong chay:
      1. Lay thong tin video goc
      2. TTS tieng Khmer tu script
      3. Dieu chinh toc do TTS khop voi do dai video (neu can)
      4. Ghep audio moi vao video
      5. Burn phu de Khmer
      6. Xuat file MP4

    Returns: duong dan file output
    """
    logger.info("\n" + "-" * 50)
    logger.info("  MODE 3: Dub Only Pipeline")
    logger.info("-" * 50)

    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    src = Path(inputs.source_video)
    if not src.exists():
        raise FileNotFoundError(f"Source video not found: {src}")

    # ── Step 1: Get video info ─────────────────────────────────────
    video_duration = get_video_duration(str(src))
    logger.info(f"    Duration: {video_duration:.1f}s")

    # ── Step 2: TTS ────────────────────────────────────────────────
    logger.info("[Step 3.2] Synthesizing Khmer voiceover...")
    tts_path = str(Path(temp_dir) / "dub_voice.mp3")
    synthesize_khmer(
        script_text=inputs.script,
        output_path=tts_path,
        voice=inputs.tts_voice,
        rate=inputs.tts_rate,
    )
    tts_duration = get_video_duration(tts_path)
    logger.info(f"    TTS duration: {tts_duration:.1f}s  |  Video: {video_duration:.1f}s")

    # ── Step 3: Speed-adjust TTS to match video if needed ─────────
    adjusted_tts = tts_path
    if abs(tts_duration - video_duration) > 1.5:
        speed = tts_duration / video_duration
        speed = max(0.5, min(2.0, speed))   # clamp to safe range
        logger.info(f"    Adjusting TTS speed x{speed:.2f} to fit video...")
        adjusted_tts = str(Path(temp_dir) / "dub_voice_adj.mp3")
        _adjust_audio_speed(tts_path, adjusted_tts, speed)

    # ── Step 4: Merge audio into video ────────────────────────────
    logger.info("[Step 3.3] Merging voiceover with video...")
    merged_path = str(Path(temp_dir) / "dub_merged.mp4")

    if inputs.mix_mode == "mix":
        _merge_mix(str(src), adjusted_tts, merged_path, inputs.mix_volume)
    else:
        _merge_replace(str(src), adjusted_tts, merged_path)

    # ── Step 5: Subtitle ──────────────────────────────────────────
    final_path = str(Path(output_dir) / f"dub_{src.stem}_output.mp4")

    if inputs.with_subtitles:
        logger.info("[Step 3.4] Generating Khmer subtitles...")
        ass_path = str(Path(temp_dir) / "dub_sub.ass")
        # Simple split: divide script into equal chunks per sentence
        generate_ass_file(
            script_text=inputs.script,
            timestamps=[video_duration],
            output_path=ass_path,
            font_name="Hanuman",
            )
        logger.info("[Step 3.5] Burning subtitles...")
        burn_hardsub(merged_path, ass_path, final_path)
    else:
        import shutil
        shutil.copy2(merged_path, final_path)

    logger.info(f"\n[OK] Dub pipeline complete: {final_path}")
    return final_path


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

def _merge_replace(video_path: str, audio_path: str, output_path: str):
    """Replace video's audio track with new TTS audio."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",    # video from source
        "-map", "1:a:0",    # audio from TTS
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Merge-replace failed:\n{result.stderr[-600:]}")


def _merge_mix(video_path: str, audio_path: str, output_path: str, orig_vol: float = 0.08):
    """Mix TTS on top of original audio (original audio at low volume)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex",
        f"[0:a]volume={orig_vol}[orig];"
        f"[1:a]volume=1.0[tts];"
        f"[orig][tts]amix=inputs=2:duration=shortest[aout]",
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Merge-mix failed:\n{result.stderr[-600:]}")


def _adjust_audio_speed(input_path: str, output_path: str, speed: float):
    """Adjust audio playback speed using atempo (0.5x - 2.0x)."""
    # atempo is limited to 0.5-2.0, chain if needed
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    af = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-filter:a", af,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Speed adjust failed:\n{result.stderr[-400:]}")
