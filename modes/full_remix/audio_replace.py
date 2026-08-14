"""
====================================================================
  Pipeline v3.0
  File: modes/full_remix/audio_replace.py — Step 1: Audio Replacement
====================================================================

Changes v3.1:
  - Added multi-language support via core/language_resolver.py
  - TTS voice auto-resolved from target_language if not explicitly set
  - Gemini translation prompt now adapts to target_language
  - Style profile notes injected into translation prompt when available
====================================================================
"""

import logging
import os
import subprocess
from pathlib import Path

from core.tts_engine import synthesize_khmer
from core.ffmpeg_utils import get_video_duration
from core.language_resolver import resolve_voice, resolve_gemini_translate_prompt
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)


def replace_video_audio(
    source_video: str,
    output_video: str,
    audio_mode: str = "translate",        # "translate" | "custom"
    script: str = "",                      # Custom script text
    tts_voice: str = "",                   # Empty = auto-resolve from target_language
    tts_rate: str = "+0%",
    target_language: str = "khmer",        # NEW: output language key
    style_notes: str = "",                 # NEW: freeform style guide from Style Profile
    temp_dir: str = "temp",
) -> tuple[str, str]:
    """
    Step 1: Remove original audio track and synthesize new audio in the target language.

    Parameters
    ----------
    source_video     : Path to source MP4.
    output_video     : Output MP4 path.
    audio_mode       : "translate" (AI generates script from video) | "custom" (use `script`).
    script           : Custom script text (used when audio_mode == "custom").
    tts_voice        : Edge-TTS voice name. Auto-resolved from target_language if empty.
    tts_rate         : TTS speech rate (e.g. "+10%").
    target_language  : Target language key (e.g. "vietnamese", "khmer", "english").
    style_notes      : Optional style guide from Style Profile (injected into AI prompt).
    temp_dir         : Temp workspace directory.

    Returns
    -------
    tuple[str, str] : (path to processed video with new audio, generated script text)
    """
    logger.info(f"[STEP FR.1] Replacing audio — target language: {target_language}")
    os.makedirs(temp_dir, exist_ok=True)

    # Resolve TTS voice from target_language if not explicitly provided
    if not tts_voice:
        tts_voice = resolve_voice(target_language, gender="female")
        logger.info(f"    Auto-resolved voice: {tts_voice}")

    video_dur = get_video_duration(source_video)

    # Determine script text
    final_script = script.strip()

    if audio_mode == "translate" and not final_script:
        logger.info(f"    Translating video audio to '{target_language}' via Gemini AI...")
        final_script = _translate_audio(
            video_path=source_video,
            target_language=target_language,
            style_notes=style_notes,
        )

    if not final_script:
        # Ultimate fallback: generic script in the target language
        final_script = _get_fallback_script(target_language)
        logger.warning(f"    Using fallback script for language '{target_language}'.")

    # Generate TTS audio
    tts_audio_path = os.path.join(temp_dir, "dub_remix_tts.mp3")
    synthesize_khmer(
        script_text=final_script,
        output_path=tts_audio_path,
        voice=tts_voice,
        rate=tts_rate,
    )
    audio_dur = get_video_duration(tts_audio_path)
    logger.info(f"    ✓ New TTS audio: {audio_dur:.1f}s  (video: {video_dur:.1f}s)  voice: {tts_voice}")

    # Strip original audio and mux new TTS audio
    cmd_merge = [
        "ffmpeg", "-y",
        "-i", source_video,
        "-i", tts_audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        output_video,
    ]
    result = subprocess.run(cmd_merge, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio merge failed: {result.stderr[-400:]}")
    logger.info(f"    ✓ Audio replaced: {output_video}")

    return output_video, final_script


# ── AI Translation ────────────────────────────────────────────────

def _translate_audio(
    video_path: str,
    target_language: str = "khmer",
    style_notes: str = "",
) -> str:
    """
    Use Gemini Flash to listen to/analyze video and generate a new voiceover
    script in the specified target language.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("[FR.1] No GEMINI_API_KEY — using fallback script.")
        return _get_fallback_script(target_language)

    try:
        from google import genai
        from google.genai import types as gtypes
        from modes.auto.ai_analyzer import _make_part, _generate_content_with_fallback

        client = get_pooled_client(api_key=api_key)

        # Build language-specific translation instruction
        lang_instruction = resolve_gemini_translate_prompt(target_language)

        # Build prompt with optional style notes injection
        style_section = ""
        if style_notes.strip():
            style_section = f"\n\n## CREATOR STYLE GUIDE (Follow this closely):\n{style_notes}\n"

        prompt = (
            "Analyze the speech/narration in this video advertisement.\n"
            "Extract the key message, product benefits, and call-to-action.\n\n"
            f"{lang_instruction}\n"
            "The script should:\n"
            "1. Match the energy and emotional tone of the original\n"
            "2. Be persuasive and use natural advertising language\n"
            "3. Include a clear call-to-action at the end\n"
            "4. Be written for spoken delivery (voiceover), not reading\n"
            f"{style_section}"
            "\nReturn ONLY the script text. No labels, no translation notes, no explanation."
        )

        video_part = _make_part(video_path)
        response = _generate_content_with_fallback(
            client=client,
            contents=[video_part, prompt],
            config=gtypes.GenerateContentConfig(
                temperature=0.65,
                max_output_tokens=1024,
            ),
        )
        script = response.text.strip()
        logger.info(f"    ✓ AI translation complete ({len(script)} chars)")
        return script

    except Exception as exc:
        logger.warning(f"[FR.1] Translation failed ({exc}). Using fallback script.")
        return _get_fallback_script(target_language)


# ── Fallback Scripts per Language ─────────────────────────────────

_FALLBACK_SCRIPTS: dict[str, str] = {
    "khmer":
        "នេះគឺជាផលិតផលដ៏ល្អបំផុតសម្រាប់អ្នក! "
        "គុណភាពខ្ពស់ ប្រើបានយូរ ។ ទិញឥឡូវនេះ!",
    "vietnamese":
        "Đây là sản phẩm tuyệt vời dành cho bạn! "
        "Chất lượng cao, bền đẹp. Đặt hàng ngay hôm nay!",
    "english":
        "This is the product you've been looking for! "
        "Premium quality that lasts. Order yours today!",
    "thai":
        "นี่คือสินค้าที่ดีที่สุดสำหรับคุณ! "
        "คุณภาพสูง ทนทาน สั่งซื้อเลยตอนนี้!",
    "indonesian":
        "Ini adalah produk terbaik untuk Anda! "
        "Kualitas premium dan tahan lama. Pesan sekarang!",
    "chinese":
        "这是最适合您的产品！高品质，耐用。立即下单！",
}


def _get_fallback_script(target_language: str) -> str:
    key = target_language.lower().strip()
    return _FALLBACK_SCRIPTS.get(key, _FALLBACK_SCRIPTS["english"])
