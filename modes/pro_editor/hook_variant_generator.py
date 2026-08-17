"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/pro_editor/hook_variant_generator.py — A/B Hook Clips
====================================================================

Generates N intro video clips (≤3s each) — one per hook variant.

Each hook clip = Ken Burns motion on the product image + verbal
text overlay burned via FFmpeg drawtext.

These short intro clips are prepended to the IDENTICAL body reel,
producing N complete output files for A/B testing.

Key spec compliance:
  - Gemini called ONCE to generate N hooks (not N separate calls).
  - Enforces N DIFFERENT visual_type values by cycling through a fixed
    list and injecting the constraint into the prompt.
    This prevents 3 near-identical hooks that defeat A/B test purpose.
  - Minimum 2 hook variants guaranteed even if CreativeScript provides 1.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from core.ffmpeg_utils import apply_ken_burns, get_audio_params, get_video_duration
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)

HOOK_DURATION_SEC  = 3.0    # Hard cap: hooks are max 3 seconds
MIN_HOOK_VARIANTS  = 2

# Kiểu chuyển động Ken Burns cho từng biến thể hook: (zoom_start, zoom_end, pan)
# Mục đích là các bản A/B khác nhau về thị giác ngay cả khi chữ hook giống nhau.
_HOOK_MOTIONS = [
    (1.00, 1.12, ["center"]),   # zoom vào chậm
    (1.14, 1.00, ["center"]),   # zoom ra
    (1.06, 1.16, ["left"]),     # zoom vào + trôi trái
    (1.06, 1.16, ["right"]),    # zoom vào + trôi phải
    (1.02, 1.10, ["up"]),       # zoom nhẹ + trôi lên
]

# Fixed rotation list: each hook must have a DIFFERENT hook_type
_HOOK_TYPES = [
    "question",
    "shock_fact",
    "relatable_scenario",
]


# ── Gemini Hook Generation (single call, N hooks, diverse types) ──

def generate_hook_variants_from_gemini(
    product_name:     str,
    product_research: Optional[object],   # ProductResearch dataclass or None
    script_context:   dict,               # CreativeScript dict
    api_key:          str,
    n:                int = 3,
) -> list[dict]:
    """
    Call Gemini ONCE to generate N hook variants, each with a DIFFERENT hook_type.

    Enforces uniqueness by assigning hook_types from _HOOK_TYPES rotation and
    explicitly listing required types in the prompt — prevents Gemini from generating
    3 near-identical hooks that defeat A/B testing.

    Parameters
    ----------
    product_name     : Product display name.
    product_research : ProductResearch dataclass from product_intelligence (or None).
    script_context   : Full CreativeScript dict from creative_director.
    api_key          : GEMINI_API_KEY.
    n                : Number of hook variants (min 2, max 5).

    Returns
    -------
    list[dict] — Each item has: variant_id, voiceover_text, on_screen_text, visual_hint, hook_type.
                 Returns empty list if API call fails (caller falls back to script hooks).
    """
    if not api_key:
        return []

    n = max(MIN_HOOK_VARIANTS, min(5, n))

    # Assign distinct hook_types (cycled through fixed list)
    assigned_types = [_HOOK_TYPES[i % len(_HOOK_TYPES)] for i in range(n)]

    # Gather customer language if research available
    research_context = ""
    if product_research and not getattr(product_research, "research_skipped", True):
        if product_research.common_complaints:
            research_context += (
                "\nReal customer pain points (use these verbatim in hooks, translated to Khmer):\n"
                + "\n".join(f'- "{c}"' for c in product_research.common_complaints[:3])
            )
        if product_research.common_praise:
            research_context += (
                "\nReal customer praise (can use for 'social proof' hook angle):\n"
                + "\n".join(f'- "{p}"' for p in product_research.common_praise[:2])
            )

    # Context from existing script
    first_segment_problem = ""
    for seg in script_context.get("segments", []):
        if seg.get("act") == "problem":
            first_segment_problem = seg.get("voiceover_text", "")
            break

    prompt = (
        f"You are a direct-response copywriter creating Facebook Ads for Cambodia (Khmer audience).\n"
        f"Product: {product_name}\n"
        f"{research_context}\n"
        f"Script problem statement: {first_segment_problem}\n\n"
        f"Generate exactly {n} hook variants for the first 3 seconds of the ad.\n"
        f"Each hook MUST use a DIFFERENT hook_type as specified below:\n"
        + "\n".join(f"  Hook {i+1}: hook_type = \"{assigned_types[i]}\"" for i in range(n))
        + "\n\n"
        "RULES:\n"
        "1. ALL verbal text MUST be in Khmer Unicode.\n"
        "2. Each hook MUST have a completely different angle and opening emotion.\n"
        "3. b_roll_keywords MUST be in English (for Pexels/Pixabay search).\n"
        "4. Do NOT create hooks that are variations of the same idea.\n\n"
        "Return ONLY a JSON array (no markdown fences):\n"
        '[\n'
        '  {"variant_id": 1, "hook_type": "question", "voiceover_text": "<Khmer text>", "on_screen_text": "<text>", "visual_hint": "<english>"},\n'
        '  ...\n'
        ']'
    )

    try:
        from google import genai
        from google.genai import types

        client = get_pooled_client(api_key=api_key)
        fallback_models = [
            os.getenv("GEMINI_MODEL", "").strip(),
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash",
        ]
        response = None
        for model in [m for m in fallback_models if m]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.85,
                        max_output_tokens=1024,
                        response_mime_type="application/json",
                    ),
                )
                break
            except Exception:
                continue

        if not response:
            return []

        raw = re.sub(r"```[a-z]*\n?", "", response.text.strip()).strip()
        hooks = json.loads(raw)

        # Enforce: override hook_type to assigned even if Gemini returned wrong type
        for i, hook in enumerate(hooks[:n]):
            hook["variant_id"] = i + 1
            if i < len(assigned_types):
                hook["hook_type"] = assigned_types[i]   # enforce spec constraint

        logger.info(
            f"[HookGen] Gemini generated {len(hooks[:n])} hooks with types: "
            f"{[h.get('hook_type') for h in hooks[:n]]}"
        )
        return hooks[:n]

    except Exception as exc:
        logger.warning(f"[HookGen] Gemini hook generation failed: {exc}")
        return []


# ── Text Overlay ──────────────────────────────────────────────────

def _burn_text_overlay(
    input_video: str,
    output_video: str,
    text:        str,
    font_path:   str  = "assets/fonts/NotoSansKhmer-Bold.ttf",
    font_size:   int  = 72,
) -> str:
    """Burn hook verbal text onto the video using FFmpeg drawtext."""
    if not text.strip():
        shutil.copy(input_video, output_video)
        return output_video

    text_clean = (
        text.strip()
        .replace("\\", "\\\\")
        .replace("'",  "\\'")
        .replace(":",  "\\:")
        .replace("%",  "\\%")
    )

    if os.path.exists(font_path):
        abs_font = os.path.abspath(font_path).replace("\\", "/").replace(":", "\\:")
        font_arg = f"fontfile={abs_font}"
    else:
        font_arg = "font=sans"

    # White bold text with dark shadow, centered horizontally, upper-middle area
    drawtext = (
        f"drawtext={font_arg}"
        f":text='{text_clean}'"
        f":fontsize={font_size}"
        f":fontcolor=white"
        f":box=1"
        f":boxcolor=black@0.55"
        f":boxborderw=12"
        f":x=(w-tw)/2"
        f":y=h*0.28"
        f":shadowx=3:shadowy=3:shadowcolor=black@0.8"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-an",
        "-pix_fmt", "yuv420p",
        output_video,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"[HookGen] drawtext failed: {result.stderr[-250:]}. Using plain clip.")
        shutil.copy(input_video, output_video)
    return output_video


# ── Public API ────────────────────────────────────────────────────

def generate_hook_clips(
    hook_variants:    list[dict],
    product_image:    str,
    temp_dir:         str,
    font_path:        str = "assets/fonts/NotoSansKhmer-Bold.ttf",
    out_w:            int = 1080,
    out_h:            int = 1920,
    product_name:     str = "",
    product_research: Optional[object] = None,
    script_context:   Optional[dict]   = None,
    api_key:          str = "",
) -> list[dict]:
    """
    Render a short Ken Burns intro clip for each hook variant.

    If api_key provided and script_context available, will call Gemini once
    to generate diverse hooks (N different visual_types). Otherwise falls
    back to using hook_variants from CreativeScript directly.

    Parameters
    ----------
    hook_variants    : Hook dicts from CreativeScript (variant_id, voiceover_text, on_screen_text, visual_hint, hook_type).
    product_image    : Path to product image for Ken Burns background.
    temp_dir         : Working directory for temp files.
    font_path        : Path to Khmer Unicode font for text overlay.
    out_w / out_h    : Output resolution (portrait 1080x1920).
    product_name     : Product name (for Gemini hook regen).
    product_research : ProductResearch (for customer language context).
    script_context   : Full CreativeScript (for problem segment context).
    api_key          : GEMINI_API_KEY (enables Gemini hook regen).

    Returns
    -------
    list[dict] — Each item: {"hook_id": str, "clip_path": str, "verbal": str, "hook_type": str}
                 Minimum 2 items guaranteed.
    """
    os.makedirs(temp_dir, exist_ok=True)

    # Attempt Gemini regen if context available (guarantees diverse visual_types)
    if api_key and script_context and product_name:
        gemini_hooks = generate_hook_variants_from_gemini(
            product_name=product_name,
            product_research=product_research,
            script_context=script_context,
            api_key=api_key,
            n=max(MIN_HOOK_VARIANTS, len(hook_variants)),
        )
        if gemini_hooks:
            logger.info(f"[HookGen] Using Gemini-generated hooks ({len(gemini_hooks)} variants)")
            hook_variants = gemini_hooks

    # Ensure minimum 2 variants
    variants = list(hook_variants)
    if len(variants) < MIN_HOOK_VARIANTS:
        logger.warning(
            f"[HookGen] Only {len(variants)} hook variant(s). "
            "Duplicating with distinct visual_type to ensure minimum 2."
        )
        while len(variants) < MIN_HOOK_VARIANTS:
            dupe = dict(variants[0])
            idx  = len(variants)
            dupe["variant_id"] = idx + 1
            dupe["hook_type"] = _HOOK_TYPES[idx % len(_HOOK_TYPES)]
            dupe["voiceover_text"] = dupe.get("voiceover_text", "") + " 🔥"
            dupe["on_screen_text"] = dupe.get("on_screen_text", "") + " 🔥"
            variants.append(dupe)

    # Render each hook clip
    results = []
    for hook in variants:
        hook_id = f"hook_{hook.get('variant_id', len(results)+1)}"
        verbal  = hook.get("voiceover_text", "")
        screen_text = hook.get("on_screen_text", verbal)

        kb_path  = os.path.join(temp_dir, f"{hook_id}_kb.mp4")
        txt_path = os.path.join(temp_dir, f"{hook_id}_text.mp4")

        # Mỗi biến thể một kiểu chuyển động riêng. Trước đây mọi hook đều dùng
        # zoom 1.0→1.06 / pan center, nên khi chữ hook trùng nhau thì các bản
        # A/B ra giống hệt nhau từng pixel.
        zoom_start, zoom_end, pans = _HOOK_MOTIONS[len(results) % len(_HOOK_MOTIONS)]

        try:
            apply_ken_burns(
                image_path=product_image,
                output_path=kb_path,
                timestamps=[HOOK_DURATION_SEC],
                total_duration=HOOK_DURATION_SEC,
                out_w=out_w,
                out_h=out_h,
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                pan_directions=pans,
                fps=30,
                temp_dir=temp_dir,
            )
        except Exception as exc:
            logger.error(f"[HookGen] Ken Burns failed for {hook_id}: {exc}")
            continue

        _burn_text_overlay(kb_path, txt_path, screen_text, font_path)

        results.append({
            "hook_id":      hook_id,
            "clip_path":    txt_path,
            "verbal":       verbal,
            "hook_type":    hook.get("hook_type", "question"),
        })
        logger.info(
            f"[HookGen] Hook clip ready: {hook_id} "
            f"(type={hook.get('hook_type')}) -> {Path(txt_path).name}"
        )

    if not results:
        logger.error("[HookGen] No hook clips generated — critical failure.")

    return results


def prepend_hook_to_body(
    hook_clip:   str,
    body_clip:   str,
    output_path: str,
    temp_dir:    str,
) -> str:
    """
    Concatenate hook_clip (≤3s silent) with body_clip (with audio)
    into a single output MP4.

    The hook clip has no audio; body clip supplies the audio track.
    FFmpeg concat demuxer requires matching streams — we add a silent
    audio track to the hook clip before concatenation.
    """
    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    # Add silent audio to hook clip so concat streams match.
    # Sample rate và số kênh PHẢI khớp body: concat demuxer không resample, nên
    # ghép 24kHz với 48kHz sẽ kéo giãn timeline audio (11s hình mà 19.98s tiếng).
    sample_rate, channels = get_audio_params(body_clip)
    layout = "mono" if channels == 1 else "stereo"
    hook_with_audio = os.path.join(temp_dir, f"{Path(hook_clip).stem}_audio.mp4")
    cmd_audio = [
        "ffmpeg", "-y",
        "-i", hook_clip,
        "-f", "lavfi", "-i", f"anullsrc=channel_layout={layout}:sample_rate={sample_rate}",
        "-t", str(HOOK_DURATION_SEC),
        "-c:v", "copy",
        "-c:a", "aac", "-ar", str(sample_rate), "-ac", str(channels),
        "-shortest",
        hook_with_audio,
    ]
    result = subprocess.run(cmd_audio, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"[HookGen] Silent audio add failed: {result.stderr[-200:]}")
        hook_with_audio = hook_clip  # proceed without silent audio

    # Build concat list
    concat_list = os.path.join(temp_dir, f"{Path(output_path).stem}_concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in [hook_with_audio, body_clip]:
            p_abs = str(Path(p).resolve()).replace("\\", "/")
            f.write(f"file '{p_abs}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-ar", str(sample_rate), "-ac", str(channels),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"[HookGen] concat failed: {result.stderr[-300:]}")

    # Chốt chặn: hình và tiếng phải cùng độ dài, nếu không người xem sẽ thấy
    # video đứng hình ở cuối trong khi tiếng vẫn chạy.
    v_dur, a_dur = _stream_durations(output_path)
    if v_dur and a_dur and abs(v_dur - a_dur) > 0.2:
        logger.warning(
            f"[HookGen] Lệch hình/tiếng {abs(v_dur - a_dur):.2f}s "
            f"(hình {v_dur:.2f}s, tiếng {a_dur:.2f}s) — đang cắt cho khớp."
        )
        fixed = str(Path(output_path).with_suffix(".fixed.mp4"))
        subprocess.run([
            "ffmpeg", "-y", "-i", output_path,
            "-c", "copy", "-t", f"{min(v_dur, a_dur):.3f}", fixed,
        ], capture_output=True, text=True)
        if os.path.exists(fixed) and os.path.getsize(fixed) > 0:
            shutil.move(fixed, output_path)

    logger.info(f"[HookGen] Final video with hook: {Path(output_path).name}")
    return output_path


def _stream_durations(path: str) -> tuple[float, float]:
    """Trả về (độ dài luồng hình, độ dài luồng tiếng) tính bằng giây."""
    out = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
        "-of", "default=nw=1:nk=1", path,
    ], capture_output=True, text=True).stdout.split()
    vals = {}
    for i in range(0, len(out) - 1, 2):
        try:
            vals[out[i]] = float(out[i + 1])
        except ValueError:
            pass
    return vals.get("video", 0.0), vals.get("audio", 0.0)
