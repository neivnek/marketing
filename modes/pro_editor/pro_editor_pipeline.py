"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/pro_editor/pro_editor_pipeline.py — Mode 7 Orchestrator
====================================================================

Implements the 11-step PRO EDITOR pipeline:

  1.  creative_director   → CreativeScript JSON (Hook-PAS-Proof-CTA)
  2.  hook_variant_generator → N silent hook intro clips
  3.  shotlist_planner    → ShotlistItem list (validated, English keywords)
  4.  broll_aggregator    → per-segment B-roll clips (local → Pexels → Pixabay)
  5.  prosody_mapper + tts_engine → per-segment Khmer voiceover with rate/volume
  6.  ffmpeg_utils        → Ken Burns (product image segments) or B-roll trim
  7.  text_mask_overlay   → mandatory mask for scraped footage
  8.  ugc_filters         → grain/shake on B-roll for visual consistency
  9.  concat_helper       → hard-cut assembly of all segments
  10. social_proof_overlay / overlay_renderer → badge overlays
  11. music_library       → background music mix
  12. subtitle_gen + burn_hardsub → ASS Khmer subtitles

Output: N files  [product_stem]_hook1.mp4, ..._hook2.mp4, ...
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Internal Helpers ──────────────────────────────────────────────

def _slug(text: str, maxlen: int = 20) -> str:
    """Create a filesystem-safe slug from text."""
    import re
    return re.sub(r"[^a-z0-9]", "_", text.lower())[:maxlen].strip("_") or "product"


def _render_segment_video(
    shot,
    product_image: str,
    broll_clips:   list[str],
    temp_dir:      str,
    out_w:         int,
    out_h:         int,
) -> str:
    """
    Render a silent portrait video clip for one ShotlistItem.
    Uses B-roll clip if available, otherwise Ken Burns on product image.
    """
    from core.ffmpeg_utils import apply_ken_burns
    from core.ugc_filters  import apply_ugc_filter

    seg_out = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}_raw.mp4")

    if broll_clips and not shot.use_ken_burns:
        # Use first available B-roll clip (already rescaled + trimmed by aggregator)
        src = broll_clips[0]

        # Apply light UGC filter to integrate with rest of video
        ugc_out = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}_ugc.mp4")
        try:
            apply_ugc_filter(src, ugc_out, intensity="subtle")
            shutil.copy(ugc_out, seg_out)
        except Exception as exc:
            logger.warning(f"[ProEditor] UGC filter failed for seg {shot.segment_id}: {exc}")
            shutil.copy(src, seg_out)
    else:
        # Fallback: Ken Burns on product image
        if not os.path.isfile(product_image):
            raise FileNotFoundError(f"Product image not found: {product_image}")
        apply_ken_burns(
            image_path=product_image,
            output_path=seg_out,
            timestamps=[shot.duration_sec],
            total_duration=shot.duration_sec,
            out_w=out_w,
            out_h=out_h,
            zoom_start=1.0,
            zoom_end=1.08,
            fps=30,
            temp_dir=temp_dir,
        )

    return seg_out


def _mux_audio_to_clip(video_path: str, audio_path: str, output_path: str) -> str:
    """Mux a silent video with a voiceover audio track."""
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"mux failed: {result.stderr[-300:]}")
    return output_path


# ── Main Orchestrator ────────────────────────────────────────────

def run_pro_editor_pipeline(inputs: Any, output_dir: str, temp_dir: str) -> list[str]:
    """
    Run the full Pro Editor pipeline and return list of output MP4 paths.

    Parameters
    ----------
    inputs     : ProEditorInputs dataclass from core/config.py.
    output_dir : Directory where final MP4 files will be written.
    temp_dir   : Temp workspace directory.

    Returns
    -------
    list[str] — Absolute paths to all generated hook variant MP4 files.
    """
    from core.config        import APIConfig
    from core.broll_aggregator import fetch_broll_clips
    from core.concat_helper    import concatenate_clips
    from core.ffmpeg_utils     import get_video_duration, burn_hardsub
    from core.music_library    import mix_background_music
    from core.overlay_renderer import add_price_overlay
    from core.prosody_mapper   import synthesize_with_prosody, dominant_energy
    from core.social_proof_overlay import add_social_proof_badge
    from core.subtitle_gen     import generate_ass_file
    from core.tts_engine       import get_audio_duration

    from modes.pro_editor.creative_director    import generate_creative_script
    from modes.pro_editor.hook_variant_generator import generate_hook_clips, prepend_hook_to_body
    from modes.pro_editor.shotlist_planner      import build_shotlist

    api_cfg = APIConfig()
    pexels_key  = os.getenv("PEXELS_API_KEY",  "")
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")
    youtube_key = os.getenv("YOUTUBE_API_KEY", "")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir,   exist_ok=True)

    product_stem = _slug(inputs.product_name or Path(inputs.product_image).stem)

    logger.info("=" * 60)
    logger.info("  MODE 7: PRO EDITOR — Professional Ads Pipeline")
    logger.info(f"  Product : {inputs.product_name or '(auto-detect from image)'}")
    logger.info(f"  Hooks   : {inputs.num_hook_variants}")
    logger.info(f"  Research: {'SKIP' if inputs.skip_product_research else 'AUTO'}")
    logger.info("=" * 60)

    # ── Step 0: Product Intelligence ─────────────────────────────
    product_identity = None
    product_research  = None
    youtube_videos    = []

    if inputs.skip_product_research:
        logger.info("[Step 0] Skipping product research (--skip-product-research set).")
        # Use user-supplied name and inputs directly
        effective_name    = inputs.product_name or Path(inputs.product_image).stem
        effective_benefits = inputs.key_benefits
        effective_pains    = inputs.pain_points
    else:
        logger.info("[Step 0] Running Product Intelligence (identify + research + YouTube)...")
        api_cfg.validate()
        try:
            from core.product_intelligence import run_product_intelligence
            product_identity, product_research, youtube_videos = run_product_intelligence(
                image_path=inputs.product_image,
                api_key=api_cfg.gemini_api_key,
                product_name=inputs.product_name,
                temp_dir=temp_dir,
                force_refresh=inputs.force_refresh_research,
                youtube_api_key=youtube_key,
            )
            effective_name = (
                inputs.product_name.strip()
                or product_identity.name_guess
                or Path(inputs.product_image).stem
            )
            # Merge: research supplements user-supplied inputs
            effective_benefits = inputs.key_benefits or product_research.benefits[:4]
            effective_pains    = inputs.pain_points  or product_research.suggested_pain_points[:3]

            logger.info(
                f"    ✓ Identity: '{product_identity.name_guess}' "
                f"(confidence={product_identity.confidence:.2f})"
            )
            if product_research.research_skipped:
                logger.warning(f"    ! Research skipped: {product_research.warning_message}")
            else:
                logger.info(
                    f"    ✓ Research: {len(product_research.benefits)} benefits, "
                    f"{len(product_research.common_praise)} praise quotes, "
                    f"{len(product_research.source_urls)} sources"
                )
            if youtube_videos:
                logger.info(f"    ✓ YouTube: {len(youtube_videos)} related videos found")
        except Exception as exc:
            logger.warning(
                f"[Step 0] Product intelligence failed (non-blocking): {exc}\n"
                "    Falling back to user-supplied inputs."
            )
            effective_name     = inputs.product_name or Path(inputs.product_image).stem
            effective_benefits = inputs.key_benefits
            effective_pains    = inputs.pain_points

    # Update product_stem now we have the effective name
    product_stem = _slug(effective_name)

    # ── Step 1: Generate CreativeScript via Gemini ─────────────────
    logger.info("[Step 1] Calling Gemini Creative Director...")
    script = generate_creative_script(
        product_image=inputs.product_image,
        product_name=effective_name,
        price=inputs.price,
        benefits=effective_benefits,
        pain_points=effective_pains,
        api_key=api_cfg.gemini_api_key,
        num_hooks=inputs.num_hook_variants,
        product_research=product_research,   # inject real customer data
    )

    # ── Step 2: Generate Hook Intro Clips ─────────────────────────
    logger.info("[Step 2] Generating hook variant intro clips...")
    hook_clips = generate_hook_clips(
        hook_variants=script.get("hook_variants", []),
        product_image=inputs.product_image,
        temp_dir=temp_dir,
        font_path="assets/fonts/Hanuman.ttf",
    )
    logger.info(f"    ✓ {len(hook_clips)} hook clips ready")

    # ── Step 3: Build Shotlist ────────────────────────────────────
    logger.info("[Step 3] Building validated shotlist...")
    shotlist = build_shotlist(
        script=script,
        product_category=inputs.product_name,
    )

    # ── Steps 4-8: Per-Segment Rendering ─────────────────────────
    logger.info(f"[Steps 4-8] Rendering {len(shotlist)} segments...")
    all_voiceover_texts: list[str] = []
    all_emotions: list[str] = []
    all_word_timestamps: list[list[dict]] = []

    price_display = script.get("price_display") or inputs.price or "SALE"
    social_proof_text = "★★★★★ (4.9/5)"

    for i, shot in enumerate(shotlist):
        seg_temp = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}")
        os.makedirs(seg_temp, exist_ok=True)

        # Step 4: Fetch B-roll clips for segment
        broll = []
        if not shot.use_ken_burns and shot.source_tier != "scraped":
            broll = fetch_broll_clips(
                query_keywords=shot.en_keywords,
                product_category=_slug(inputs.product_name),
                duration_sec=shot.duration_sec,
                pexels_api_key=pexels_key,
                pixabay_api_key=pixabay_key,
                temp_dir=temp_dir,
                n_clips=1,
            )
        elif shot.source_tier == "scraped" and not inputs.allow_scraped_footage:
            logger.warning(
                f"[Step 4] Seg {shot.segment_id}: source_tier='scraped' but "
                "--allow-scraped-footage not set. Using Ken Burns fallback."
            )
            shot.use_ken_burns = True

        if not broll:
            shot.use_ken_burns = True

        # Step 5: Synthesize per-segment TTS with prosody
        tts_path = os.path.join(seg_temp, f"voice_{shot.segment_id:03d}.mp3")
        if shot.voiceover_text.strip():
            synthesize_with_prosody(
                script_text=shot.voiceover_text,
                output_path=tts_path,
                emotion=shot.emotion,
                voice=inputs.tts_voice,
                base_rate=inputs.tts_rate,
            )
            audio_dur = get_audio_duration(tts_path)
            shot.duration_sec = audio_dur  # use REAL audio duration for clip trimming
            
            words_json_path = str(Path(tts_path).with_suffix(".words.json"))
            seg_words = []
            if os.path.exists(words_json_path):
                import json
                try:
                    with open(words_json_path, "r", encoding="utf-8") as f_json:
                        seg_words = json.load(f_json)
                except Exception:
                    pass
            all_word_timestamps.append(seg_words)
        else:
            tts_path = None
            all_word_timestamps.append([])

        # Step 6: Render silent visual clip
        visual = _render_segment_video(
            shot=shot,
            product_image=inputs.product_image,
            broll_clips=broll,
            temp_dir=seg_temp,
            out_w=1080,
            out_h=1920,
        )

        # Step 6b: Apply Overlays based on overlay_type
        if getattr(shot, "overlay_type", "none") == "price_tag":
            overlaid = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_price.mp4")
            try:
                add_price_overlay(visual, overlaid, price_display)
                visual = overlaid
            except Exception as exc:
                logger.warning(f"[Step 6b] Price overlay failed: {exc}")
        elif getattr(shot, "overlay_type", "none") == "social_proof":
            overlaid = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_proof.mp4")
            try:
                add_social_proof_badge(visual, overlaid, social_proof_text)
                visual = overlaid
            except Exception as exc:
                logger.warning(f"[Step 6b] Social proof overlay failed: {exc}")

        # Step 7: Text mask for scraped footage (mandatory per spec rule #8)
        if shot.source_tier == "scraped" and inputs.allow_scraped_footage:
            from modes.dub_remix.text_mask_overlay import apply_text_mask_and_subtitles
            masked = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_masked.mp4")
            try:
                apply_text_mask_and_subtitles(
                    input_video=visual,
                    output_video=masked,
                    khmer_script=shot.on_screen_text,
                    mask_style="box",
                    temp_dir=seg_temp,
                )
                visual = masked
            except Exception as exc:
                logger.warning(f"[Step 7] Text mask failed for seg {shot.segment_id}: {exc}")

        # Mux audio if voiceover exists
        if tts_path and os.path.isfile(tts_path):
            muxed = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_muxed.mp4")
            _mux_audio_to_clip(visual, tts_path, muxed)
            visual = muxed

        segment_clips.append(visual)
        all_voiceover_texts.append(shot.voiceover_text)
        all_emotions.append(shot.emotion)
        logger.info(f"    ✓ Segment {shot.segment_id} ({shot.act}): {shot.duration_sec:.1f}s")

    # ── Step 9: Concatenate All Segments ─────────────────────────
    logger.info("[Step 9] Hard-cut concatenation...")
    body_raw = os.path.join(temp_dir, f"{product_stem}_body_raw.mp4")
    concatenate_clips(segment_clips, body_raw)

    logger.info("[Step 11] Mixing background music...")
    energy = dominant_energy(all_emotions)
    body_dur = get_video_duration(body_raw)
    body_music = os.path.join(temp_dir, f"{product_stem}_music.mp4")
    try:
        mix_background_music(
            video_path=body_raw,
            output_path=body_music,
            energy=energy,
            duration_sec=body_dur,
            temp_dir=temp_dir,
        )
    except Exception as exc:
        logger.warning(f"[Step 11] Music mix failed: {exc}")
        shutil.copy(body_raw, body_music)

    # ── Step 11b: Subtitles ───────────────────────────────────────
    logger.info("[Step 11b] Generating and burning Khmer subtitles...")
    full_script = " ".join(t for t in all_voiceover_texts if t.strip())
    body_final  = body_music

    if full_script.strip():
        ass_path = os.path.join(temp_dir, f"{product_stem}_subs.ass")
        subbed   = os.path.join(temp_dir, f"{product_stem}_subbed.mp4")
        try:
            # Build timestamp list from cumulative segment durations
            cumul = 0.0
            ts_list = []
            master_word_timestamps = []
            for i, shot in enumerate(shotlist):
                seg_words = all_word_timestamps[i]
                for w in seg_words:
                    shifted_w = w.copy()
                    shifted_w["start"] += cumul
                    shifted_w["end"] += cumul
                    master_word_timestamps.append(shifted_w)

                cumul += shot.duration_sec
                ts_list.append(cumul)
            
            generate_ass_file(
                script_text=full_script,
                timestamps=ts_list,
                output_path=ass_path,
                preset_name=inputs.caption_style,
                word_timestamps=master_word_timestamps,
                font_name="Hanuman",
            )
            burn_hardsub(body_music, ass_path, "assets/fonts", subbed)
            body_final = subbed
        except Exception as exc:
            logger.warning(f"[Step 11b] Subtitle burn failed: {exc}")

    # ── Final: Prepend Hook Variants ──────────────────────────────
    logger.info("[Final] Assembling hook variants...")
    output_paths: list[str] = []

    for hook_info in hook_clips:
        hook_id    = hook_info["hook_id"]
        hook_clip  = hook_info["clip_path"]
        out_name   = f"{product_stem}_{hook_id}.mp4"
        out_path   = os.path.join(output_dir, out_name)

        try:
            prepend_hook_to_body(
                hook_clip=hook_clip,
                body_clip=body_final,
                output_path=out_path,
                temp_dir=temp_dir,
            )
            output_paths.append(out_path)
            logger.info(f"    ✓ Output: {out_name}")
        except Exception as exc:
            logger.error(f"[Final] Failed to produce {hook_id}: {exc}")
            # Fallback: copy body without hook
            shutil.copy(body_final, out_path)
            output_paths.append(out_path)

    logger.info(f"\n[OK] PRO EDITOR complete — {len(output_paths)} variants generated.")
    for p in output_paths:
        logger.info(f"     -> {p}")

    return output_paths
