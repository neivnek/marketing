"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/news_ads/news_ads_pipeline.py — Mode 8 Orchestrator
====================================================================

Orchestrates the "News Ads" pipeline:
1. Unified Creative Director
2. Hook A/B variants
3. Shotlist + B-Roll + TTS (Prosody) + FFmpeg segment render + Overlay
4. Concatenation
5. Channel Watermark (if applicable)
6. Music Mix
7. Subtitles
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from core.config import NewsAdsInputs

logger = logging.getLogger(__name__)

# Re-use the segment rendering logic from pro_editor (with minor tweaks for news_ads)
def _render_segment_video(
    shot,
    product_image: str,
    broll_clips:   list[str],
    temp_dir:      str,
    out_w:         int,
    out_h:         int,
) -> str:
    from core.ffmpeg_utils import apply_ken_burns
    from core.ugc_filters  import apply_ugc_filter

    seg_out = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}_raw.mp4")

    if broll_clips and not getattr(shot, "use_ken_burns", False):
        src = broll_clips[0]
        ugc_out = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}_ugc.mp4")
        try:
            apply_ugc_filter(src, ugc_out, intensity="subtle")
            shutil.copy(ugc_out, seg_out)
        except Exception as exc:
            logger.warning(f"[NewsAds] UGC filter failed for seg {shot.segment_id}: {exc}")
            shutil.copy(src, seg_out)
    else:
        # Fallback Ken Burns on product image (if provided) or a solid color if missing
        if product_image and os.path.isfile(product_image):
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
        else:
            # Create a dummy solid color fallback if no product image is provided for a topic
            import subprocess
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"color=c=black:s={out_w}x{out_h}:r=30:d={shot.duration_sec}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                seg_out
            ]
            subprocess.run(cmd, capture_output=True)

    return seg_out

def _mux_audio_to_clip(video_path: str, audio_path: str, output_path: str) -> str:
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
    subprocess.run(cmd, capture_output=True)
    return output_path

def _slug(text: str, maxlen: int = 20) -> str:
    import re
    return re.sub(r"[^a-z0-9]", "_", text.lower())[:maxlen].strip("_") or "news_ad"

def run_news_ads_pipeline(inputs: NewsAdsInputs, output_dir: str, temp_dir: str) -> list[str]:
    from core.config import APIConfig
    from core.broll_aggregator import fetch_broll_clips
    from core.concat_helper import concatenate_clips
    from core.ffmpeg_utils import get_video_duration, burn_hardsub
    from core.music_library import mix_background_music
    from core.overlay_renderer import add_price_overlay
    from core.social_proof_overlay import add_social_proof_badge
    from core.prosody_mapper import synthesize_with_prosody, dominant_energy
    from core.subtitle_gen import generate_ass_file
    from core.tts_engine import get_audio_duration
    
    from modes.news_ads.unified_creative_director import generate_unified_creative_script
    from modes.pro_editor.hook_variant_generator import generate_hook_clips, prepend_hook_to_body
    from modes.pro_editor.shotlist_planner import build_shotlist
    from modes.news_auto.watermark_injector import inject_channel_watermark

    api_cfg = APIConfig()
    pexels_key = os.getenv("PEXELS_API_KEY", "")
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    stem_name = inputs.product_name or inputs.source_content[:20]
    product_stem = _slug(stem_name)

    logger.info("=" * 60)
    logger.info("  MODE 8: NEWS ADS — News-Style Product Ads Pipeline")
    logger.info(f"  Source Type : {inputs.source_type}")
    logger.info(f"  Format Style: {inputs.format_style}")
    logger.info("=" * 60)

    # 1. Generate Script
    logger.info("[Step 1] Calling Unified Creative Director...")
    script = generate_unified_creative_script(
        source_type=inputs.source_type,
        source_content=inputs.source_content,
        product_name=inputs.product_name,
        price=inputs.price,
        benefits=inputs.key_benefits,
        pain_points=inputs.pain_points,
        format_style=inputs.format_style,
        api_key=api_cfg.gemini_api_key,
        target_language=inputs.target_language,
        num_hooks=inputs.num_hook_variants,
    )

    channel_name = script.get("channel_name") or inputs.channel_name
    price_display = script.get("price_display") or inputs.price or "HOT DEAL"

    # 2. Hook Intro Clips
    logger.info("[Step 2] Generating hook variant intro clips...")
    hook_clips = generate_hook_clips(
        hook_variants=script.get("hook_variants", []),
        product_image=inputs.product_image or "",
        temp_dir=temp_dir,
        font_path="assets/fonts/NotoSansKhmer-Bold.ttf",
    )

    # 3. Build Shotlist
    logger.info("[Step 3] Building validated shotlist...")
    shotlist = build_shotlist(script=script, product_category=inputs.product_name or "news")

    # 4-8. Per-Segment Render
    logger.info(f"[Steps 4-8] Rendering {len(shotlist)} segments...")
    segment_clips = []
    all_voiceover_texts = []
    all_emotions = []
    all_word_timestamps = []

    for i, shot in enumerate(shotlist):
        seg_temp = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}")
        os.makedirs(seg_temp, exist_ok=True)

        broll = fetch_broll_clips(
            query_keywords=shot.en_keywords,
            product_category=_slug(inputs.product_name or "news"),
            duration_sec=shot.duration_sec,
            pexels_api_key=pexels_key,
            pixabay_api_key=pixabay_key,
            temp_dir=temp_dir,
            n_clips=1,
        )

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
            shot.duration_sec = audio_dur
            
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

        visual = _render_segment_video(shot, inputs.product_image, broll, seg_temp, 1080, 1920)

        overlay = getattr(shot, "overlay_type", "none")
        if overlay == "price_tag":
            overlaid = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_price.mp4")
            try:
                add_price_overlay(visual, overlaid, price_display)
                visual = overlaid
            except Exception as exc:
                logger.warning(f"Price overlay failed: {exc}")
        elif overlay == "social_proof":
            overlaid = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_proof.mp4")
            try:
                add_social_proof_badge(visual, overlaid, "★★★★★ (4.9/5)")
                visual = overlaid
            except Exception as exc:
                logger.warning(f"Social proof overlay failed: {exc}")

        if not getattr(inputs, "enable_subtitles", False):
            on_screen = getattr(shot, "on_screen_text", "").strip()
            if on_screen and on_screen.lower() != "news":
                overlaid_title = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_title.mp4")
                try:
                    from core.overlay_renderer import add_title_overlay
                    add_title_overlay(visual, overlaid_title, on_screen, style=getattr(inputs, "title_style", "Khung Xanh (Mặc định)"))
                    visual = overlaid_title
                except Exception as exc:
                    logger.warning(f"Title overlay failed: {exc}")

        if tts_path and os.path.isfile(tts_path):
            muxed = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_muxed.mp4")
            _mux_audio_to_clip(visual, tts_path, muxed)
            visual = muxed

        segment_clips.append(visual)
        all_voiceover_texts.append(shot.voiceover_text)
        all_emotions.append(shot.emotion)

    # 9. Concatenate
    logger.info("[Step 9] Concatenating segments...")
    body_raw = os.path.join(temp_dir, f"{product_stem}_body_raw.mp4")
    concatenate_clips(segment_clips, body_raw)
    body_current = body_raw

    # 10. Channel Watermark
    if inputs.format_style != "direct_ad" and channel_name:
        logger.info("[Step 10] Injecting channel watermark...")
        body_wm = os.path.join(temp_dir, f"{product_stem}_wm.mp4")
        try:
            body_wm = inject_channel_watermark(body_current, channel_name, body_wm)
            body_current = body_wm
        except Exception as exc:
            logger.warning(f"Watermark failed: {exc}")

    # 11. Music Mix
    logger.info("[Step 11] Mixing background music...")
    energy = dominant_energy(all_emotions)
    body_dur = get_video_duration(body_current)
    body_music = os.path.join(temp_dir, f"{product_stem}_music.mp4")
    try:
        mix_background_music(body_current, body_music, energy, body_dur, temp_dir)
        body_current = body_music
    except Exception as exc:
        logger.warning(f"Music mix failed: {exc}")

    # 12. Subtitles
    logger.info("[Step 12] Burning subtitles...")
    full_script = " ".join(t for t in all_voiceover_texts if t.strip())
    if full_script.strip():
        ass_path = os.path.join(temp_dir, f"{product_stem}_subs.ass")
        subbed = os.path.join(temp_dir, f"{product_stem}_subbed.mp4")
        try:
            cumul = 0.0
            ts_list = []
            master_words = []
            for i, shot in enumerate(shotlist):
                for w in all_word_timestamps[i]:
                    shifted_w = w.copy()
                    shifted_w["start"] += cumul
                    shifted_w["end"] += cumul
                    master_words.append(shifted_w)
                cumul += shot.duration_sec
                ts_list.append(cumul)
            
            generate_ass_file(
                script_text=full_script,
                timestamps=ts_list,
                output_path=ass_path,
                preset_name="classic_box",
                word_timestamps=master_words,
                font_name="Noto Sans Khmer",
            )
            burn_hardsub(body_current, ass_path, "assets/fonts", subbed)
            body_current = subbed
        except Exception as exc:
            logger.warning(f"Subtitle burn failed: {exc}")

    # 13. Assemble with Hooks
    logger.info("[Final] Assembling hook variants...")
    output_paths = []
    for hook_info in hook_clips:
        hook_id = hook_info["hook_id"]
        hook_clip = hook_info["clip_path"]
        out_name = f"{product_stem}_{hook_id}.mp4"
        out_path = os.path.join(output_dir, out_name)
        try:
            prepend_hook_to_body(hook_clip, body_current, out_path, temp_dir)
            output_paths.append(out_path)
            logger.info(f"    ✓ Output: {out_name}")
        except Exception as exc:
            logger.error(f"Failed to produce {hook_id}: {exc}")
            shutil.copy(body_current, out_path)
            output_paths.append(out_path)

    logger.info(f"\n[OK] NEWS ADS complete — {len(output_paths)} variants generated.")
    return output_paths
