"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/news_pro/news_pro_pipeline.py
====================================================================

Phase A: analyze_image_and_research
Phase B: render_from_script
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict

from core.config import NewsProInputs
from core.product_intelligence import run_product_intelligence
from modes.news_pro.news_prompt_template_pro import build_prefilled_prompt

logger = logging.getLogger(__name__)

# Re-use the segment rendering logic from Mode 8 (news_ads)
def _render_segment_video(
    shot,
    product_images: list[str],
    broll_clips:   list[str],
    temp_dir:      str,
    out_w:         int,
    out_h:         int,
    transition_speed_str: str = "Bình thường (3.0s)",
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
            logger.warning(f"[NewsPro] UGC filter failed for seg {shot.segment_id}: {exc}")
            shutil.copy(src, seg_out)
    else:
        if product_images and all(os.path.isfile(img) for img in product_images):
            # Dynamic Ken Burns slideshow to avoid freeze-frame feel
            if "Rất nhanh" in transition_speed_str:
                clip_dur = 1.5
            elif "Nhanh" in transition_speed_str:
                clip_dur = 2.0
            elif "Chậm" in transition_speed_str:
                clip_dur = 4.0
            else:
                clip_dur = 3.0
            num_clips = max(1, int(shot.duration_sec / clip_dur) + 1)
            sub_clips = []
            
            for k in range(num_clips):
                img = product_images[(k + shot.segment_id) % len(product_images)]
                sub_out = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}_sub_{k}.mp4")
                
                # Alternate pan directions for dynamism
                dirs = [["left", "up"], ["right", "down"], ["center", "up"], ["left", "down"]]
                pan_dir = dirs[k % 4]
                
                apply_ken_burns(
                    image_path=img,
                    output_path=sub_out,
                    timestamps=[clip_dur],
                    total_duration=clip_dur,
                    out_w=out_w,
                    out_h=out_h,
                    zoom_start=1.0,
                    zoom_end=1.1,
                    pan_directions=pan_dir,
                    fps=30,
                    temp_dir=temp_dir,
                )
                sub_clips.append(sub_out)
                
            # Concat sub-clips
            concat_list = os.path.join(temp_dir, f"seg_{shot.segment_id:03d}_list.txt")
            with open(concat_list, "w", encoding="utf-8") as f:
                for c in sub_clips:
                    f.write(f"file '{os.path.abspath(c)}'\n")
            
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c:v", "copy",
                seg_out
            ]
            import subprocess
            subprocess.run(cmd, capture_output=True)
        else:
            try:
                from modes.news_auto.news_auto_pipeline import _create_news_title_clip
                _create_news_title_clip(
                    text=getattr(shot, "on_screen_text", "News"),
                    output_path=seg_out,
                    duration=shot.duration_sec,
                    out_w=out_w,
                    out_h=out_h,
                )
            except Exception as e:
                logger.warning(f"Fallback title clip failed: {e}")
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
    from core.ffmpeg_utils import get_video_duration
    if not audio_path or not os.path.exists(audio_path):
        # Generate and mux silent audio to guarantee audio stream exists
        dur = get_video_duration(video_path)
        silent = video_path + ".silent.m4a"
        cmd_s = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-t", str(dur), "-c:a", "aac", silent]
        subprocess.run(cmd_s, capture_output=True)
        audio_path = silent

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
    return re.sub(r"[^a-z0-9]", "_", text.lower())[:maxlen].strip("_") or "news_pro"

def analyze_image_and_research(image_path: str, api_key: str, temp_dir: str, hint_name: str = "") -> Dict[str, str]:
    """Phase A: Run product intelligence and return raw strings for the UI."""
    logger.info(f"[NewsPro Phase A] Running product intelligence (Hint: {hint_name})...")
    identity, research, _ = run_product_intelligence(
        image_path=image_path,
        api_key=api_key,
        product_name=hint_name,
        temp_dir=temp_dir
    )
    
    b_csv = ", ".join(research.benefits) if research.benefits else ""
    p_csv = ", ".join(research.common_complaints or research.suggested_pain_points)
    
    return {
        "product_name": identity.name_guess,
        "price": "",
        "benefits_csv": b_csv,
        "pain_points_csv": p_csv
    }


def render_from_script(inputs: NewsProInputs, output_dir: str, temp_dir: str) -> list[str]:
    """Phase B: Render video from the user-pasted JSON script."""
    from core.broll_aggregator import fetch_broll_clips
    from core.concat_helper import concatenate_clips
    from core.ffmpeg_utils import get_video_duration, burn_hardsub
    from core.music_library import mix_background_music
    from core.overlay_renderer import add_price_overlay
    from core.social_proof_overlay import add_social_proof_badge
    from core.prosody_mapper import synthesize_with_prosody, dominant_energy
    from core.subtitle_gen import generate_ass_file
    from core.tts_engine import get_audio_duration
    from modes.pro_editor.hook_variant_generator import generate_hook_clips, prepend_hook_to_body
    from modes.pro_editor.shotlist_planner import build_shotlist
    from modes.news_auto.watermark_injector import inject_channel_watermark

    pexels_key = os.getenv("PEXELS_API_KEY", "")
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    logger.info("=" * 60)
    logger.info("  MODE 9: NEWS PRO — Rendering Phase")
    logger.info("=" * 60)

    try:
        script = json.loads(inputs.script_json)
    except Exception as exc:
        raise ValueError(f"Invalid JSON provided to render_from_script: {exc}")

    stem_name = script.get("title", "news_pro")
    product_stem = _slug(stem_name)

    channel_name = script.get("channel_name") or inputs.channel_name
    price_display = script.get("price_display") or "HOT DEAL"

    # Hook Intro Clips
    logger.info("[Step 1] Generating hook variant intro clips using B-roll...")
    from core.broll_aggregator import fetch_broll_clips
    
    hook_clips = []
    for h in script.get("hook_variants", []):
        hid = h.get("variant_id", h.get("hook_id", "1"))
        logger.info(f"    -> Hook {hid}")
        hook_temp = os.path.join(temp_dir, f"hook_{hid}")
        os.makedirs(hook_temp, exist_ok=True)
        
        # 1. Fetch B-roll
        h_hint = h.get("visual_hint", "breaking news")
        h_broll = fetch_broll_clips(
            query_keywords=h_hint,
            product_category=_slug(inputs.product_name or "news"),
            duration_sec=3.0,
            pexels_api_key=pexels_key,
            pixabay_api_key=pixabay_key,
            temp_dir=hook_temp,
            n_clips=1,
        )
        
        # 2. TTS
        h_tts_path = os.path.join(hook_temp, f"hook_{hid}_voice.mp3")
        h_dur = 3.0
        if h.get("voiceover_text", "").strip():
            synthesize_with_prosody(
                script_text=h["voiceover_text"],
                output_path=h_tts_path,
                emotion="urgent",
                voice=inputs.tts_voice,
                base_rate=inputs.tts_rate,
            )
            h_dur = max(3.0, get_audio_duration(h_tts_path))
            
        # 3. Create dummy shot for visual render
        class DummyShot:
            def __init__(self, d): self.duration_sec = d; self.segment_id = int(str(hid).replace("hook_","").replace("_","")[:3]) or 999
        h_shot = DummyShot(h_dur)
        
        # 4. Render Visual (B-roll)
        h_visual = _render_segment_video(h_shot, "", h_broll, hook_temp, 1080, 1920, getattr(inputs, "transition_speed", "Bình thường (3.0s)"))
        
        # 5. Add Text Overlay
        from modes.pro_editor.hook_variant_generator import _burn_text_overlay
        h_texted = os.path.join(hook_temp, f"hook_{hid}_text.mp4")
        _burn_text_overlay(h_visual, h_texted, h.get("on_screen_text", ""))
        
        # 6. Mux Audio
        h_final = os.path.join(hook_temp, f"hook_{hid}_final.mp4")
        _mux_audio_to_clip(h_texted, h_tts_path if os.path.exists(h_tts_path) else "", h_final)
            
        hook_clips.append({"hook_id": f"hook_{hid}", "clip_path": h_final, "verbal": h.get("voiceover_text", "")})

    # Build Shotlist
    logger.info("[Step 2] Building validated shotlist...")
    shotlist = build_shotlist(script=script, product_category=inputs.product_name or "news")

    # Per-Segment Render
    logger.info(f"[Step 3] Rendering {len(shotlist)} segments...")
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
                try:
                    with open(words_json_path, "r", encoding="utf-8") as f_json:
                        seg_words = json.load(f_json)
                except Exception:
                    pass
            all_word_timestamps.append(seg_words)
        else:
            tts_path = None
            all_word_timestamps.append([])

        visual = _render_segment_video(shot, getattr(inputs, "product_images", []), broll, seg_temp, 1080, 1920, getattr(inputs, "transition_speed", "Bình thường (3.0s)"))

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
        else:
            muxed = os.path.join(seg_temp, f"seg_{shot.segment_id:03d}_muxed.mp4")
            _mux_audio_to_clip(visual, "", muxed)
            visual = muxed

        segment_clips.append(visual)
        all_voiceover_texts.append(shot.voiceover_text)
        all_emotions.append(shot.emotion)

    # Concatenate
    logger.info("[Step 4] Concatenating segments...")
    body_raw = os.path.join(temp_dir, f"{product_stem}_body_raw.mp4")
    concatenate_clips(segment_clips, body_raw)
    body_current = body_raw

    # Channel Watermark
    if channel_name:
        logger.info("[Step 5] Injecting channel watermark...")
        body_wm = os.path.join(temp_dir, f"{product_stem}_wm.mp4")
        try:
            body_wm = inject_channel_watermark(body_current, channel_name, body_wm)
            body_current = body_wm
        except Exception as exc:
            logger.warning(f"Watermark failed: {exc}")

    # Music Mix
    logger.info("[Step 6] Mixing background music...")
    energy = dominant_energy(all_emotions)
    body_dur = get_video_duration(body_current)
    body_music = os.path.join(temp_dir, f"{product_stem}_music.mp4")
    try:
        mix_background_music(body_current, body_music, energy, body_dur, temp_dir)
        body_current = body_music
    except Exception as exc:
        logger.warning(f"Music mix failed: {exc}")

    # Subtitles
    if getattr(inputs, "enable_subtitles", False):
        logger.info("[Step 7] Burning subtitles...")
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
    else:
        logger.info("[Step 7] Subtitles disabled (skipped).")

    # Assemble with Hooks
    logger.info("[Step 8] Assembling hook variants...")
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

    logger.info(f"\n[OK] NEWS PRO rendering complete — {len(output_paths)} variants generated.")
    return output_paths
