"""
====================================================================
  Pipeline v3.0
  File: modes/full_remix/remix_cut_generator.py — Step 3: Remix Re-Cut
====================================================================

Changes v3.1:
  - Added variation_index parameter: generates distinct remix variants
    (Remix 1 swaps segments 0+2 with B-roll; Remix 2 swaps segments 1+3)
  - Added broll_query param: AI auto-analyzes video for keywords if empty
  - Integrated fetch_broll_clips() from core/broll_aggregator.py
  - B-roll clips are trimmed to EXACT duration of replaced segment
    to ensure perfect audio sync after concatenation
====================================================================
"""

import logging
import os
import subprocess
from pathlib import Path

from core.concat_helper import concatenate_clips
from core.ugc_filters import apply_ugc_filter
from core.ffmpeg_utils import get_video_duration

logger = logging.getLogger(__name__)


def generate_remix_recut(
    processed_video: str,
    output_remix_video: str,
    variation_index: int = 0,             # 0 = remix_1 (swap 0+2), 1 = remix_2 (swap 1+3)
    broll_query: str = "",                # B-roll keyword; empty = AI auto-analyzes
    pexels_key: str = "",
    pixabay_key: str = "",
    product_category: str = "product",
    ugc_intensity: str = "medium",
    add_ai_label: bool = True,
    temp_dir: str = "temp",
) -> str:
    """
    Create a remix variant of the processed video by interleaving B-roll footage.

    Two distinct variations are produced based on variation_index:
      - variation_index=0: Replace segments 0 & 2 with B-roll
      - variation_index=1: Replace segments 1 & 3 with B-roll

    Audio from `processed_video` is always preserved unchanged.

    Parameters
    ----------
    processed_video    : Path to the main dubbed video (with new audio).
    output_remix_video : Output path for this remix variant.
    variation_index    : 0 or 1 — determines which segments get B-roll.
    broll_query        : Keyword for B-roll search. AI-generated if empty.
    pexels_key         : Pexels API key from env.
    pixabay_key        : Pixabay API key from env.
    product_category   : Category slug for B-roll SQLite dedup tracking.
    ugc_intensity      : UGC filter intensity: subtle | medium | strong.
    add_ai_label       : Show small "Lồng tiếng AI" badge.
    temp_dir           : Temp workspace.

    Returns
    -------
    str — Path to output remix video.
    """
    logger.info(f"[STEP FR.3] Generating Remix variant {variation_index + 1}...")
    os.makedirs(temp_dir, exist_ok=True)

    total_dur = get_video_duration(processed_video)

    # ── Step 1: Split video into 4 segments ──────────────────────
    seg_dur = max(2.5, total_dur / 4.0)
    segment_clips: list[str] = []
    segment_durations: list[float] = []

    for i in range(4):
        start_t = i * seg_dur
        if start_t >= total_dur:
            break
        trim_dur = min(seg_dur, total_dur - start_t)
        seg_file = os.path.join(temp_dir, f"remix{variation_index}_seg_{i:02d}.mp4")
        _trim_clip_with_audio(processed_video, seg_file, start_t, trim_dur)
        segment_clips.append(seg_file)
        segment_durations.append(trim_dur)
        logger.info(f"    Segment {i}: {start_t:.1f}s → {start_t + trim_dur:.1f}s ({trim_dur:.1f}s)")

    if not segment_clips:
        logger.warning("[FR.3] No segments extracted — copying original.")
        import shutil
        shutil.copy(processed_video, output_remix_video)
        return output_remix_video

    # ── Step 2: Resolve B-roll keywords ──────────────────────────
    resolved_query = broll_query.strip()
    if not resolved_query:
        resolved_query = _auto_resolve_broll_query(processed_video)

    # Variation determines which segments get replaced by B-roll
    # variation_index=0: replace segments 0, 2  (even indices)
    # variation_index=1: replace segments 1, 3  (odd indices)
    broll_indices = [i for i in range(len(segment_clips)) if i % 2 == variation_index % 2]
    logger.info(f"    B-roll indices for variation {variation_index}: {broll_indices}")
    logger.info(f"    B-roll query: '{resolved_query}'")

    # ── Step 3: Fetch B-roll clips ────────────────────────────────
    broll_clips_needed = len(broll_indices)
    fetched_broll: list[str] = []

    try:
        from core.broll_aggregator import fetch_broll_clips
        # Use variation_index as a prefix category to avoid dedup collisions between variants
        dedup_category = f"{product_category}_v{variation_index}"
        fetched_broll = fetch_broll_clips(
            query_keywords=[resolved_query],
            product_category=dedup_category,
            duration_sec=seg_dur,
            pexels_api_key=pexels_key,
            pixabay_api_key=pixabay_key,
            temp_dir=temp_dir,
            n_clips=broll_clips_needed,
            out_w=1080,
            out_h=1920,
        )
        logger.info(f"    ✓ Fetched {len(fetched_broll)} B-roll clips")
    except Exception as exc:
        logger.warning(f"    B-roll fetch failed: {exc} — using original segments only.")

    # ── Step 4: Assemble final clip list ─────────────────────────
    final_clips: list[str] = []
    broll_cursor = 0

    for i, seg_path in enumerate(segment_clips):
        if i in broll_indices and broll_cursor < len(fetched_broll):
            # Replace this segment with B-roll (video only — mux original audio from segment)
            broll_src = fetched_broll[broll_cursor]
            broll_cursor += 1
            merged_broll = os.path.join(
                temp_dir, f"remix{variation_index}_broll_{i:02d}_merged.mp4"
            )
            # Mux B-roll video + original segment's audio for perfect sync
            success = _mux_broll_with_audio(
                broll_video=broll_src,
                audio_source=seg_path,
                output=merged_broll,
                duration=segment_durations[i],
            )
            if success:
                final_clips.append(merged_broll)
                logger.info(f"    Segment {i} → B-roll substituted")
            else:
                final_clips.append(seg_path)  # Fallback to original
                logger.warning(f"    Segment {i} → B-roll mux failed, using original")
        else:
            final_clips.append(seg_path)

    # ── Step 5: Concatenate all segments ─────────────────────────
    concat_out = os.path.join(temp_dir, f"remix{variation_index}_concat.mp4")
    concatenate_clips(final_clips, concat_out)

    # ── Step 6: Apply UGC filter for authentic look ───────────────
    ugc_out = os.path.join(temp_dir, f"remix{variation_index}_ugc.mp4")
    try:
        apply_ugc_filter(
            input_path=concat_out,
            output_path=ugc_out,
            intensity=ugc_intensity,
            out_w=1080,
            out_h=1920,
        )
    except Exception as exc:
        logger.warning(f"    UGC filter failed: {exc} — using unfiltered concat.")
        ugc_out = concat_out

    # ── Step 7: Add AI dub transparency badge ─────────────────────
    if add_ai_label:
        _add_ai_dub_badge(ugc_out, output_remix_video)
    else:
        import shutil
        shutil.copy(ugc_out, output_remix_video)

    logger.info(f"    ✓ Remix variant {variation_index + 1} complete: {output_remix_video}")
    return output_remix_video


# ── AI B-roll Keyword Resolution ──────────────────────────────────

def _auto_resolve_broll_query(video_path: str) -> str:
    """
    Use Gemini Vision to analyze the video and suggest B-roll search keywords.
    Returns a single compact English search string.
    Falls back to "lifestyle product" if Gemini is unavailable.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return "lifestyle product advertisement"

    try:
        from google import genai
        from google.genai import types as gtypes
        from modes.auto.ai_analyzer import _make_part, _generate_content_with_fallback

        client = genai.Client(api_key=api_key)
        video_part = _make_part(video_path)

        prompt = (
            "Watch this advertisement video. Based on the product being advertised and "
            "the visual style, suggest the BEST single English search query (2-5 words) "
            "to find relevant B-roll stock footage on Pexels or Pixabay.\n"
            "Focus on the core product category, lifestyle context, or visual theme.\n"
            "Return ONLY the search query — no explanation, no quotes.\n"
            "Examples: 'skincare routine morning', 'fashion woman walking', 'food cooking kitchen'"
        )

        response = _generate_content_with_fallback(
            client=client,
            contents=[video_part, prompt],
            config=gtypes.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=50,
            ),
        )
        query = response.text.strip().strip('"').strip("'").lower()
        logger.info(f"    AI B-roll query: '{query}'")
        return query if query else "lifestyle product"

    except Exception as exc:
        logger.warning(f"    AI B-roll query failed ({exc}) — using generic fallback.")
        return "lifestyle product advertisement"


# ── FFmpeg Helpers ─────────────────────────────────────────────────

def _trim_clip_with_audio(
    input_video: str,
    output_clip: str,
    start_sec: float,
    duration: float,
) -> None:
    """Trim segment with both video and audio tracks preserved."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(round(start_sec, 3)),
        "-i", input_video,
        "-t", str(round(duration, 3)),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        output_clip,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"_trim_clip_with_audio failed: {result.stderr[-300:]}")


def _mux_broll_with_audio(
    broll_video: str,
    audio_source: str,
    output: str,
    duration: float,
) -> bool:
    """
    Replace the video track of `audio_source` with `broll_video`,
    keeping the audio from `audio_source` for perfect sync.

    Both are trimmed to `duration` seconds.
    Returns True on success, False on failure.
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", broll_video,      # input 0: B-roll video (video track)
            "-i", audio_source,     # input 1: original segment (audio track)
            "-map", "0:v:0",        # take video from B-roll
            "-map", "1:a:0",        # take audio from original segment
            "-t", str(round(duration, 3)),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            output,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"    _mux_broll_with_audio stderr: {result.stderr[-200:]}")
            return False
        return True
    except Exception as exc:
        logger.warning(f"    _mux_broll_with_audio exception: {exc}")
        return False


def _add_ai_dub_badge(input_video: str, output_video: str) -> None:
    """Add small transparent 'Lồng tiếng AI' label for transparency."""
    label_filter = (
        "drawtext=fontfile='assets/fonts/Hanuman.ttf':"
        "text='Lồng tiếng AI':"
        "fontsize=24:fontcolor=white@0.75:"
        "box=1:boxcolor=black@0.45:boxborderw=6:"
        "x=30:y=30"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", label_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        output_video,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        import shutil
        logger.warning(f"    Badge overlay failed — copying without badge: {result.stderr[-200:]}")
        shutil.copy(input_video, output_video)
