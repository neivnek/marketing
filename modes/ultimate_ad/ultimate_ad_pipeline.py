"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/ultimate_ad/ultimate_ad_pipeline.py — Orchestrator
====================================================================

ULTIMATE_AD mode: High-conversion video ad pipeline combining:
  Pipeline (Gemini AI, FFmpeg, hooks, music, subtitles)
  NTD-Labs (AI-generated image/video B-Roll)
  FB-Ad-Video-Studio (ElevenLabs VO, Whisper sync, SFX, templates)

Luồng 10 bước:
  1.  generate_ultimate_script() → kịch bản + claim validation
  2a. run_tts() per segment → VO + provider tracking
  2b. build_ntd_index() + resolve_shot_assets() per shot
  3.  variation_engine.apply_shot_variation() per shot
  4.  _render_segment() → visual + mux VO
  5.  concatenate_clips()
  6.  mix_background_music()
  7.  master_audio_pass() → -14 LUFS normalization
  8.  inject watermark + price/social overlays
  9.  Subtitle routing (template vs pipeline_ass)
  10. generate_hook_clips() → N hook variants → final MP4s
  + render_report.json (TTS provider, quota, violations, durations)
"""

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from core.config import UltimateAdInputs
from core.sfx_fetcher import download_sfx_kit, build_sfx_rail_from_script, burn_sfx_rail
from core.pacing_enforcer import audit_pacing, music_db_for_ad

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _slug(text: str, maxlen: int = 24) -> str:
    return re.sub(r"[^a-z0-9]", "_", text.lower())[:maxlen].strip("_") or "ultimate_ad"


def _mux_audio(video: str, audio: str, output: str) -> str:
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-i", video, "-i", audio,
        "-c:v", "copy", "-c:a", "aac", "-shortest", output,
    ]
    subprocess.run(cmd, capture_output=True)
    return output


def _render_segment_visual(
    shot:          Any,
    broll_clips:   list[str],
    product_image: str,
    temp_dir:      str,
    out_w:         int,
    out_h:         int,
) -> str:
    """Render the visual track for one shot segment."""
    from core.ffmpeg_utils import apply_ken_burns
    from core.ugc_filters  import apply_ugc_filter

    seg_id  = shot.get("id", 0)
    dur     = shot.get("duration_sec", shot.get("duration_hint_sec", 5.0))
    seg_out = os.path.join(temp_dir, f"seg_{seg_id:03d}_raw.mp4")

    if broll_clips:
        src     = broll_clips[0]
        ext     = Path(src).suffix.lower()
        ugc_out = os.path.join(temp_dir, f"seg_{seg_id:03d}_ugc.mp4")

        if ext in {".jpg", ".jpeg", ".png"}:
            # Still image → Ken Burns
            apply_ken_burns(
                image_path=src,
                output_path=seg_out,
                timestamps=[dur],
                total_duration=dur,
                out_w=out_w,
                out_h=out_h,
                zoom_start=1.0,
                zoom_end=1.08,
                fps=30,
                temp_dir=temp_dir,
            )
        else:
            # Video clip → UGC filter
            try:
                apply_ugc_filter(src, ugc_out, intensity="subtle",
                                 out_w=out_w, out_h=out_h)
                shutil.copy(ugc_out, seg_out)
            except Exception as exc:
                logger.warning(f"[UltimatePipeline] UGC filter seg {seg_id}: {exc}")
                shutil.copy(src, seg_out)
    elif product_image and os.path.isfile(product_image):
        apply_ken_burns(
            image_path=product_image,
            output_path=seg_out,
            timestamps=[dur],
            total_duration=dur,
            out_w=out_w,
            out_h=out_h,
            fps=30,
            temp_dir=temp_dir,
        )
    else:
        # Black fallback
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s={out_w}x{out_h}:r=30:d={dur}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", seg_out,
        ], capture_output=True)

    return seg_out


# ──────────────────────────────────────────────
# Main Orchestrator
# ──────────────────────────────────────────────

def run_ultimate_ad_pipeline(
    inputs:     UltimateAdInputs,
    output_dir: str,
    temp_dir:   str,
) -> list[str]:
    """
    Run the ULTIMATE_AD pipeline end-to-end.

    Returns
    -------
    list[str] — Absolute paths to final MP4 variants (one per hook).
    """
    from core.config import APIConfig
    from core.broll_aggregator  import fetch_broll_clips
    from core.concat_helper     import concatenate_clips
    from core.ffmpeg_utils      import (
        get_video_duration, burn_hardsub, master_audio_pass
    )
    from core.music_library     import mix_background_music
    from core.overlay_renderer  import add_price_overlay
    from core.prosody_mapper    import dominant_energy
    from core.social_proof_overlay import add_social_proof_badge
    from core.subtitle_gen      import generate_ass_file
    from core.tts_engine        import get_audio_duration
    from core.variation_engine  import apply_shot_variation, profile_for_hook
    from modes.news_auto.watermark_injector import inject_channel_watermark
    from modes.pro_editor.hook_variant_generator import generate_hook_clips, prepend_hook_to_body
    from modes.ultimate_ad.ultimate_creative_director import generate_ultimate_script
    from modes.ultimate_ad.ntd_asset_bridge   import build_ntd_index, resolve_shot_assets
    from modes.ultimate_ad.fb_studio_bridge   import (
        ElevenLabsQuotaTracker, run_tts, run_whisper_sync
    )

    api_cfg     = APIConfig()
    pexels_key  = os.getenv("PEXELS_API_KEY", "")
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir,   exist_ok=True)

    slug        = _slug(inputs.product_name)
    out_w, out_h = 1080, 1920
    sub_source  = inputs.resolve_subtitle_source()

    # Shared quota tracker (single instance for entire pipeline run)
    quota_tracker = ElevenLabsQuotaTracker()

    render_report: dict = {
        "product_name":    inputs.product_name,
        "target_language": inputs.target_language,
        "ad_template":     inputs.ad_template,
        "subtitle_source": sub_source,
        "tts_segments":    [],
        "quota":           {},
        "violations":      [],
        "output_files":    [],
    }

    logger.info("═" * 60)
    logger.info("  ULTIMATE AD PIPELINE")
    logger.info(f"  Product   : {inputs.product_name}")
    logger.info(f"  Language  : {inputs.target_language}")
    logger.info(f"  Template  : {inputs.ad_template}")
    logger.info(f"  SubSource : {sub_source}")
    logger.info(f"  Hooks     : {inputs.num_hook_variants}")
    logger.info("═" * 60)

    # ── STEP 0: Vision Indexing (2-Tier Visual Search) ─────────────
    if inputs.product_image and os.path.isfile(inputs.product_image):
        logger.info("[Step 0] Phân tích ảnh sản phẩm (Vision Index & Bbox Crop)...")
        from core.product_vision_index import process_uploaded_poster
        vision_meta = process_uploaded_poster(inputs.product_image, api_key=api_cfg.gemini_api_key)
        if vision_meta and "error" not in vision_meta:
            # Auto-fill missing inputs if needed
            extracted_name = vision_meta.get("product_name")
            if extracted_name and (not inputs.product_name or inputs.product_name == "Unknown"):
                inputs.product_name = extracted_name
            extracted_claims = vision_meta.get("key_claims", [])
            if extracted_claims and not inputs.key_benefits:
                inputs.key_benefits = ", ".join(extracted_claims)
            logger.info(f"  ↳ Nhận diện thành công: {inputs.product_name}")

    # ── STEP 1: Generate Script ────────────────────────────────────
    logger.info("[Step 1] Generating script via Ultimate Creative Director...")
    script = generate_ultimate_script(
        product_name    = inputs.product_name,
        target_language = inputs.target_language,
        ad_template     = inputs.ad_template,
        script_text     = inputs.script_text,
        key_benefits    = inputs.key_benefits,
        pain_points     = inputs.pain_points,
        price           = inputs.price,
        num_hooks       = inputs.num_hook_variants,
        api_key         = api_cfg.gemini_api_key,
    )
    render_report["violations"] = script.pop("_claim_violations", [])
    price_display = script.get("price_display") or inputs.price or ""

    # ── STEP 2a: Hook VO (per hook variant) ────────────────────────
    logger.info("[Step 2a] Synthesizing hook voiceovers...")
    hook_vo_paths: list[str] = []
    for hv in script.get("hook_variants", []):
        vid  = hv.get("variant_id", 1)
        text = hv.get("voiceover_text", "").strip()
        if not text:
            hook_vo_paths.append("")
            continue
        hv_dir   = os.path.join(temp_dir, f"hook_{vid:02d}")
        os.makedirs(hv_dir, exist_ok=True)
        vo_path  = os.path.join(hv_dir, f"hook_{vid:02d}_vo.mp3")
        _, provider = run_tts(
            text         = text,
            output_path  = vo_path,
            voice_id_el  = inputs.tts_voice_el,
            voice_edge   = inputs.tts_voice_edge,
            tts_rate     = inputs.tts_rate,
            tracker      = quota_tracker,
        )
        hook_vo_paths.append(vo_path)
        render_report["tts_segments"].append({"type": "hook", "variant_id": vid, "provider": provider})

    # ── STEP 2b: Pre-scan NTD-Labs assets ──────────────────────────
    logger.info("[Step 2b] Building NTD-Labs asset index...")
    ntd_index = build_ntd_index(inputs.ntd_assets_dir)

    # ── STEPS 3-4: Per-segment render ─────────────────────────────
    segments            = script.get("script_segments", [])
    segment_clips:      list[str]   = []
    all_voiceover_texts: list[str]  = []
    all_emotions:       list[str]   = []
    all_word_timestamps: list[list] = []
    cumul_duration      = 0.0

    logger.info(f"[Steps 3-4] Rendering {len(segments)} segments...")

    for shot in segments:
        seg_id  = shot.get("id", 0)
        emotion = shot.get("emotion", "confident")
        vo_text = shot.get("voiceover_text", "").strip()
        v_hint  = shot.get("visual_hint", inputs.product_name)
        dur_hint = float(shot.get("duration_hint_sec", 5.0))

        seg_temp = os.path.join(temp_dir, f"seg_{seg_id:03d}")
        os.makedirs(seg_temp, exist_ok=True)

        # 2b: Resolve assets for this shot
        broll = resolve_shot_assets(
            segment_id      = seg_id,
            visual_hint     = v_hint,
            duration_sec    = dur_hint,
            ntd_dir         = inputs.ntd_assets_dir,
            ntd_index       = ntd_index,
            pexels_api_key  = pexels_key,
            pixabay_api_key = pixabay_key,
            temp_dir        = temp_dir,
        )

        # 2a: Synthesize segment VO
        tts_path: Optional[str] = None
        seg_words: list = []
        if vo_text:
            tts_path = os.path.join(seg_temp, f"vo_{seg_id:03d}.mp3")
            _, provider = run_tts(
                text        = vo_text,
                output_path = tts_path,
                voice_id_el = inputs.tts_voice_el,
                voice_edge  = inputs.tts_voice_edge,
                tts_rate    = inputs.tts_rate,
                tracker     = quota_tracker,
            )
            render_report["tts_segments"].append({"type": "segment", "id": seg_id, "provider": provider})

            # Update duration from actual audio
            actual_dur = get_audio_duration(tts_path)
            shot["duration_sec"] = actual_dur

            # Load word timestamps
            words_json = str(Path(tts_path).with_suffix(".words.json"))
            if os.path.isfile(words_json):
                try:
                    with open(words_json, "r", encoding="utf-8") as f:
                        seg_words = json.load(f)
                except Exception:
                    pass

        all_word_timestamps.append(seg_words)
        seg_dur = shot.get("duration_sec", dur_hint)

        # 3: Render visual with UGC filter
        visual = _render_segment_visual(
            shot=shot, broll_clips=broll,
            product_image=inputs.product_image,
            temp_dir=seg_temp, out_w=out_w, out_h=out_h,
        )

        # 4: Overlays (price / social proof)
        overlay_type = shot.get("overlay_type", "none")
        if overlay_type == "price_tag" and price_display:
            overlaid = os.path.join(seg_temp, f"seg_{seg_id:03d}_price.mp4")
            try:
                add_price_overlay(visual, overlaid, price_display)
                visual = overlaid
            except Exception as exc:
                logger.warning(f"Price overlay seg {seg_id}: {exc}")
        elif overlay_type == "social_proof":
            overlaid = os.path.join(seg_temp, f"seg_{seg_id:03d}_proof.mp4")
            try:
                add_social_proof_badge(visual, overlaid, "★★★★★ (4.9/5)")
                visual = overlaid
            except Exception as exc:
                logger.warning(f"Social proof overlay seg {seg_id}: {exc}")

        # On-screen text title (when not using template captions)
        if sub_source == "pipeline_ass":
            on_screen = shot.get("on_screen_text", "").strip()
            if on_screen and on_screen.lower() not in ("none", ""):
                title_out = os.path.join(seg_temp, f"seg_{seg_id:03d}_title.mp4")
                try:
                    from core.overlay_renderer import add_title_overlay
                    add_title_overlay(visual, title_out, on_screen)
                    visual = title_out
                except Exception as exc:
                    logger.warning(f"Title overlay seg {seg_id}: {exc}")

        # Mux VO audio
        if tts_path and os.path.isfile(tts_path):
            muxed = os.path.join(seg_temp, f"seg_{seg_id:03d}_muxed.mp4")
            _mux_audio(visual, tts_path, muxed)
            visual = muxed

        segment_clips.append(visual)
        all_voiceover_texts.append(vo_text)
        all_emotions.append(emotion)
        cumul_duration += seg_dur

    # ── STEP 5: Concatenate ────────────────────────────────────────
    logger.info("[Step 5] Concatenating segments...")
    body_raw = os.path.join(temp_dir, f"{slug}_body_raw.mp4")
    concatenate_clips(segment_clips, body_raw)
    body_current = body_raw

    # ── STEP 6: Music Mix ─────────────────────────────────────────
    logger.info("[Step 6] Mixing background music...")
    energy   = dominant_energy(all_emotions)
    body_dur = get_video_duration(body_current)
    body_music = os.path.join(temp_dir, f"{slug}_music.mp4")
    # Use pacing-correct music level (-18dB for DR, None=skip for conversion)
    music_db = music_db_for_ad("direct_response")
    try:
        if music_db is not None:
            mix_background_music(body_current, body_music, energy, body_dur, temp_dir)
            body_current = body_music
        else:
            logger.info("[Step 6] Skipping music (direct-response mode — VO+SFX only).")
    except Exception as exc:
        logger.warning(f"[Step 6] Music mix failed: {exc}")

    # ── STEP 7: Audio Master Pass (-14 LUFS) ──────────────────────
    logger.info(f"[Step 7] Normalizing audio to {inputs.master_lufs} LUFS...")
    body_mastered = os.path.join(temp_dir, f"{slug}_mastered.mp4")
    try:
        master_audio_pass(body_current, body_mastered, target_lufs=inputs.master_lufs)
        body_current = body_mastered
    except Exception as exc:
        logger.warning(f"[Step 7] Audio master pass failed: {exc}")

    # ── STEP 8: Watermark + Branding ──────────────────────────────
    if inputs.channel_name:
        logger.info(f"[Step 8] Injecting watermark: {inputs.channel_name}...")
        body_wm = os.path.join(temp_dir, f"{slug}_wm.mp4")
        try:
            inject_channel_watermark(body_current, inputs.channel_name, body_wm)
            body_current = body_wm
        except Exception as exc:
            logger.warning(f"[Step 8] Watermark failed: {exc}")

    # ── STEP 9: Subtitles (routing by subtitle_source) ────────────
    if sub_source == "pipeline_ass":
        logger.info("[Step 9] Burning pipeline ASS subtitles...")
        full_script_text = " ".join(t for t in all_voiceover_texts if t.strip())
        if full_script_text.strip():
            ass_path = os.path.join(temp_dir, f"{slug}_subs.ass")
            subbed   = os.path.join(temp_dir, f"{slug}_subbed.mp4")
            try:
                # Shift word timestamps by cumulative offset
                master_words: list = []
                cumul = 0.0
                for i, shot in enumerate(segments):
                    for w in all_word_timestamps[i]:
                        shifted = dict(w)
                        shifted["start"] = shifted.get("start", 0) + cumul
                        shifted["end"]   = shifted.get("end",   0) + cumul
                        master_words.append(shifted)
                    cumul += shot.get("duration_sec", shot.get("duration_hint_sec", 5.0))
                ts_list = [
                    sum(s.get("duration_sec", s.get("duration_hint_sec", 5.0))
                        for s in segments[:i+1])
                    for i in range(len(segments))
                ]
                generate_ass_file(
                    script_text     = full_script_text,
                    timestamps      = ts_list,
                    output_path     = ass_path,
                    preset_name     = "classic_box",
                    word_timestamps = master_words,
                    font_name       = "Hanuman",
                )
                burn_hardsub(body_current, ass_path, "assets/fonts", subbed)
                body_current = subbed
            except Exception as exc:
                logger.warning(f"[Step 9] Subtitle burn failed: {exc}")
    else:
        logger.info(
            f"[Step 9] subtitle_source='{sub_source}' — "
            "subtitles handled by template; skipping pipeline burn."
        )

    # ── STEP 9b: SFX Rail (Mixkit — free, commercial license) ─────
    logger.info("[Step 9b] Burning Mixkit SFX rail...")
    sfx_dir = os.path.join(os.path.dirname(temp_dir), "assets", "sfx")
    try:
        sfx_paths = download_sfx_kit(os.path.dirname(sfx_dir) or "assets")
        # Build SFX events from script segments (word timestamps if available)
        flat_words = [w for wl in all_word_timestamps for w in wl]
        if flat_words:
            from core.sfx_fetcher import build_sfx_rail_from_words
            sfx_events = build_sfx_rail_from_words(flat_words, body_dur)
        else:
            sfx_events = build_sfx_rail_from_script(segments, body_dur)

        sfx_out = os.path.join(temp_dir, f"{slug}_sfx.mp4")
        burn_sfx_rail(body_current, sfx_events, sfx_paths, sfx_out)
        body_current = sfx_out
        logger.info(f"[Step 9b] SFX rail burned: {len(sfx_events)} events.")
    except Exception as exc:
        logger.warning(f"[Step 9b] SFX rail failed (non-fatal): {exc}")

    # ── STEP 10: Hook Variants ─────────────────────────────────────
    logger.info(f"[Step 10] Generating {inputs.num_hook_variants} hook variant(s)...")

    hook_clips = generate_hook_clips(
        hook_variants  = script.get("hook_variants", []),
        product_image  = inputs.product_image or "",
        temp_dir       = temp_dir,
        font_path      = "assets/fonts/Hanuman.ttf",
    )

    output_paths: list[str] = []
    for idx, hook_info in enumerate(hook_clips):
        hook_id   = hook_info["hook_id"]
        hook_clip = hook_info["clip_path"]
        out_name  = f"{slug}_{hook_id}.mp4"
        out_path  = os.path.join(output_dir, out_name)

        # Apply variation profile to the BODY for this hook variant
        # (seed = idx → reproducible visual treatment per hook)
        profile  = profile_for_hook(idx)
        var_body = os.path.join(temp_dir, f"{slug}_body_var{idx:02d}.mp4")
        try:
            apply_shot_variation(body_current, var_body, profile=profile, seed=idx)
            body_for_hook = var_body
        except Exception as exc:
            logger.warning(f"[Variation] hook {idx} profile={profile}: {exc}. Using unmodified body.")
            body_for_hook = body_current

        # Prepend hook to body
        try:
            prepend_hook_to_body(hook_clip, body_for_hook, out_path, temp_dir)
            output_paths.append(out_path)
            logger.info(f"  ✓ {out_name}  (profile={profile})")
        except Exception as exc:
            logger.error(f"  ✗ {hook_id} failed: {exc}")
            shutil.copy(body_for_hook, out_path)
            output_paths.append(out_path)

    # ── Render Report ─────────────────────────────────────────────
    render_report["quota"]        = quota_tracker.get_report()
    render_report["output_files"] = output_paths
    render_report["total_duration_sec"] = round(body_dur, 2)

    report_path = os.path.join(output_dir, f"{slug}_render_report.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(render_report, f, ensure_ascii=False, indent=2)
        logger.info(f"[Report] Saved → {report_path}")
    except Exception as exc:
        logger.warning(f"[Report] Could not save render report: {exc}")

    logger.info(f"\n[OK] ULTIMATE AD complete — {len(output_paths)} variant(s) generated.")
    return output_paths
