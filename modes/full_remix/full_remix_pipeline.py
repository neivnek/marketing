"""
====================================================================
  Pipeline v3.0
  File: modes/full_remix/full_remix_pipeline.py — Mode 4 Orchestrator
====================================================================

Changes v3.1:
  - Multi-language TTS support (target_language → voice auto-resolved)
  - Style Profile injection into AI translation prompt
  - Produces N remix variants (num_remixes) each with B-roll injection
  - Output files: [stem]_main.mp4, [stem]_remix_1.mp4, [stem]_remix_2.mp4
====================================================================
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from modes.full_remix.audio_replace import replace_video_audio
from modes.full_remix.text_mask_overlay import apply_text_mask_and_subtitles
from modes.full_remix.remix_cut_generator import generate_remix_recut
from core.music_library import mix_background_music
from core.ffmpeg_utils import get_video_duration

logger = logging.getLogger(__name__)


def run_full_remix_pipeline(
    dub_inputs: Any,
    output_dir: str = "output",
    temp_dir: str = "temp",
) -> str:
    """
    Run Mode 4: Full Remix Pipeline.

    Produces:
      1. [stem]_main.mp4       — Original video with new dubbed audio (target language)
      2. [stem]_remix_1.mp4    — Remix: B-roll replaces even-indexed segments
      3. [stem]_remix_2.mp4    — Remix: B-roll replaces odd-indexed segments
         (number of remixes controlled by dub_inputs.num_remixes)

    Parameters
    ----------
    dub_inputs : FullRemixInputs object (from core/router.py)
    output_dir : Destination output directory.
    temp_dir   : Temporary working directory.

    Returns
    -------
    str : Path to main rendered video (_main.mp4)
    """
    logger.info("\n" + "═" * 60)
    logger.info("  MODE 4: Full Remix Pipeline (Multi-Language + B-Roll)")
    logger.info("═" * 60)

    work_temp = os.path.join(temp_dir, "full_remix")
    os.makedirs(work_temp, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    source_video = dub_inputs.source_video
    if not os.path.exists(source_video):
        raise FileNotFoundError(f"Source video not found: {source_video}")

    base_name = Path(source_video).stem

    # ── Resolve language + TTS voice ─────────────────────────────
    target_language = getattr(dub_inputs, "target_language", "khmer")
    tts_voice = getattr(dub_inputs, "tts_voice", "")

    # ── Load Style Profile (if set) ───────────────────────────────
    style_notes = ""
    style_profile_id = getattr(dub_inputs, "style_profile_id", "")
    if style_profile_id:
        try:
            from core.style_profile import load_style_profile
            profile = load_style_profile(style_profile_id)
            if profile:
                style_notes = profile.get("gemini_style_notes", "")
                logger.info(f"[FR] Style profile '{style_profile_id}' loaded.")
        except Exception as exc:
            logger.warning(f"[FR] Could not load style profile '{style_profile_id}': {exc}")

    # ── Step 1: Replace original audio ────────────────────────────
    logger.info(f"\n[Step 1] Dubbing audio → language: {target_language}")
    audio_replaced_video = os.path.join(work_temp, "step1_audio_replaced.mp4")
    processed_video, dubbed_script = replace_video_audio(
        source_video=source_video,
        output_video=audio_replaced_video,
        audio_mode=dub_inputs.audio_mode,
        script=dub_inputs.script,
        tts_voice=tts_voice,
        tts_rate=dub_inputs.tts_rate,
        target_language=target_language,
        style_notes=style_notes,
        temp_dir=work_temp,
    )

    # ── Step 2: Mask original text + overlay subtitles ────────────
    logger.info("\n[Step 2] Masking original text / overlaying subtitles...")
    main_output_path = os.path.join(output_dir, f"{base_name}_main.mp4")

    # Use custom on_screen_text if provided, otherwise use dubbed script as subtitles
    final_text_to_burn = getattr(dub_inputs, "on_screen_text", "").strip()

    apply_text_mask_and_subtitles(
        input_video=processed_video,
        output_video=main_output_path,
        khmer_script=final_text_to_burn,
        mask_style=dub_inputs.mask_style,
        mask_color=dub_inputs.mask_color,
        temp_dir=work_temp,
    )

    # ── Step 2.5: Mix Background Music ────────────────────────────
    logger.info("\n[Step 2.5] Mixing background music...")
    music_energy = getattr(dub_inputs, "music_energy", "upbeat")
    final_with_music = os.path.join(work_temp, f"{base_name}_main_music.mp4")
    dur = get_video_duration(main_output_path)

    try:
        mix_background_music(
            video_path=main_output_path,
            output_path=final_with_music,
            energy=music_energy,
            duration_sec=dur,
            temp_dir=work_temp,
            music_volume=0.12,
        )
        if os.path.exists(final_with_music):
            shutil.move(final_with_music, main_output_path)
    except Exception as exc:
        logger.warning(f"[FR] Music mix failed (non-blocking): {exc}")

    logger.info(f"[OK] Main video complete: {main_output_path}")

    # ── Step 3: Generate Remix Variants (with B-roll) ─────────────
    num_remixes = getattr(dub_inputs, "num_remixes", 2) if dub_inputs.create_remix else 0

    if num_remixes < 1:
        logger.info("[FR] Remix creation skipped (create_remix=False or num_remixes=0).")
        _cleanup(work_temp)
        return main_output_path

    broll_query = getattr(dub_inputs, "broll_query", "")
    scrape_kw = getattr(dub_inputs, "scrape_broll_keyword", "").strip()
    pexels_key  = os.getenv("PEXELS_API_KEY", "")
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")
    ugc_intensity = dub_inputs.ugc_intensity
    product_category = base_name.replace(" ", "_").lower()

    if scrape_kw:
        broll_query = scrape_kw  # Force broll_query to match so the aggregator finds these files
        try:
            from modes.auto.scraper import scrape_meta_ads
            # Download to assets/local_broll/<product_category> so fetch_broll_clips picks it up automatically
            scrape_dir = os.path.join("assets", "local_broll", product_category)
            logger.info(f"[FR] Cào B-roll từ Meta Ads cho từ khoá: '{scrape_kw}' -> {scrape_dir}")
            scrape_meta_ads(keyword=scrape_kw, output_dir=scrape_dir, max_results=num_remixes * 2)
        except Exception as exc:
            logger.warning(f"[FR] Lỗi cào Meta Ads (bỏ qua & dùng Pexels/Pixabay): {exc}")

    output_paths = [main_output_path]

    for i in range(num_remixes):
        remix_label = i + 1
        remix_output = os.path.join(output_dir, f"{base_name}_remix_{remix_label}.mp4")
        remix_temp   = os.path.join(work_temp, f"remix_{remix_label}")
        os.makedirs(remix_temp, exist_ok=True)

        logger.info(f"\n[Step 3.{remix_label}] Generating Remix {remix_label}/{num_remixes}...")
        try:
            generate_remix_recut(
                processed_video=main_output_path,  # use dubbed main video as base
                output_remix_video=remix_output,
                variation_index=i,
                broll_query=broll_query,
                pexels_key=pexels_key,
                pixabay_key=pixabay_key,
                product_category=product_category,
                ugc_intensity=ugc_intensity,
                add_ai_label=True,
                temp_dir=remix_temp,
            )
            output_paths.append(remix_output)
            logger.info(f"[OK] Remix {remix_label} complete: {remix_output}")
        except Exception as exc:
            logger.error(f"[FR] Remix {remix_label} failed: {exc}")

    # ── Cleanup ───────────────────────────────────────────────────
    _cleanup(work_temp)

    logger.info(f"\n[OK] Full Remix Pipeline complete — {len(output_paths)} video(s):")
    for p in output_paths:
        logger.info(f"     → {p}")

    return main_output_path


def _cleanup(work_temp: str) -> None:
    """Remove temporary workspace directory."""
    try:
        shutil.rmtree(work_temp)
    except Exception:
        pass
