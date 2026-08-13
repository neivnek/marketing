"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/language_resolver.py — Language → TTS Voice Resolver
====================================================================

Maps user-friendly language names (e.g. "vietnamese", "khmer") to
edge-tts neural voice codes and Gemini translation instructions.

Supports zero-cost compliance: all voices are Microsoft Edge TTS
neural voices available via the edge-tts library at no cost.

Supported languages (extensible — add any edge-tts locale):
  khmer, vietnamese, english, thai, indonesian, chinese,
  malay, tagalog, hindi, korean, japanese
====================================================================
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Voice Map ─────────────────────────────────────────────────────
# Format: language_key → (female_voice, male_voice)
# All voices are edge-tts Neural voices (Microsoft TTS, free tier)

LANGUAGE_VOICE_MAP: dict[str, tuple[str, str]] = {
    "khmer":        ("km-KH-SreymomNeural",   "km-KH-PisethNeural"),
    "vietnamese":   ("vi-VN-HoaiMyNeural",     "vi-VN-NamMinhNeural"),
    "english":      ("en-US-JennyNeural",      "en-US-GuyNeural"),
    "thai":         ("th-TH-PremwadeeNeural",  "th-TH-NiwatNeural"),
    "indonesian":   ("id-ID-GadisNeural",      "id-ID-ArdiNeural"),
    "chinese":      ("zh-CN-XiaoxiaoNeural",   "zh-CN-YunxiNeural"),
    "malay":        ("ms-MY-YasminNeural",     "ms-MY-OsmanNeural"),
    "tagalog":      ("fil-PH-BlessicaNeural",  "fil-PH-AngeloNeural"),
    "hindi":        ("hi-IN-SwaraNeural",      "hi-IN-MadhurNeural"),
    "korean":       ("ko-KR-SunHiNeural",      "ko-KR-InJoonNeural"),
    "japanese":     ("ja-JP-NanamiNeural",     "ja-JP-KeitaNeural"),
    "burmese":      ("my-MM-NilarNeural",      "my-MM-ThihaNeural"),
}

# Display names for UI dropdowns
LANGUAGE_DISPLAY_NAMES: dict[str, str] = {
    "khmer":        "🇰🇭 ភាសាខ្មែរ (Khmer)",
    "vietnamese":   "🇻🇳 Tiếng Việt (Vietnamese)",
    "english":      "🇺🇸 English",
    "thai":         "🇹🇭 ภาษาไทย (Thai)",
    "indonesian":   "🇮🇩 Bahasa Indonesia",
    "chinese":      "🇨🇳 中文 (Chinese)",
    "malay":        "🇲🇾 Bahasa Melayu (Malay)",
    "tagalog":      "🇵🇭 Filipino (Tagalog)",
    "hindi":        "🇮🇳 हिंदी (Hindi)",
    "korean":       "🇰🇷 한국어 (Korean)",
    "japanese":     "🇯🇵 日本語 (Japanese)",
    "burmese":      "🇲🇲 မြန်မာဘာသာ (Burmese)",
}

# Font recommendations per language (for subtitle rendering)
LANGUAGE_FONT_MAP: dict[str, str] = {
    "khmer":        "Hanuman",
    "vietnamese":   "Roboto",
    "english":      "Roboto",
    "thai":         "Roboto",      # TH Sarabun New is ideal but falls back to Roboto
    "indonesian":   "Roboto",
    "chinese":      "Roboto",
    "malay":        "Roboto",
    "tagalog":      "Roboto",
    "hindi":        "Roboto",
    "korean":       "Roboto",
    "japanese":     "Roboto",
    "burmese":      "Roboto",
}

# Gemini translation instruction per language
_TRANSLATE_PROMPTS: dict[str, str] = {
    "khmer":        "Translate and rewrite as a natural Khmer-language advertising voiceover. Use Khmer Unicode only.",
    "vietnamese":   "Dịch và viết lại thành lời thuyết minh quảng cáo tiếng Việt tự nhiên, hấp dẫn.",
    "english":      "Translate and rewrite as a natural, persuasive English advertising voiceover.",
    "thai":         "แปลและเขียนใหม่เป็นสคริปต์โฆษณาภาษาไทยที่เป็นธรรมชาติ",
    "indonesian":   "Terjemahkan dan tulis ulang sebagai skrip iklan Bahasa Indonesia yang alami dan persuasif.",
    "chinese":      "翻译并改写为自然、有说服力的中文广告旁白脚本。",
    "malay":        "Terjemahkan dan tulis semula sebagai skrip iklan Bahasa Melayu yang semula jadi.",
    "tagalog":      "Isalin at isulat muli bilang natural na script ng advertisement sa Filipino.",
    "hindi":        "अनुवाद करें और एक स्वाभाविक हिंदी विज्ञापन वॉयसओवर स्क्रिप्ट के रूप में फिर से लिखें।",
    "korean":       "자연스러운 한국어 광고 보이스오버 스크립트로 번역하고 다시 작성하세요.",
    "japanese":     "自然な日本語の広告ナレーションスクリプトに翻訳して書き直してください。",
    "burmese":      "သဘာဝကျသော မြန်မာဘာသာ ကြော်ငြာ script အဖြစ် ဘာသာပြန်ပြီး ပြန်ရေးပါ။",
}


# ── Public API ────────────────────────────────────────────────────

def resolve_voice(target_language: str, gender: str = "female") -> str:
    """
    Return the edge-tts voice code for a language + gender.

    Parameters
    ----------
    target_language : Language name key (case-insensitive), e.g. "vietnamese".
    gender          : "female" (default) or "male".

    Returns
    -------
    str — edge-tts voice name string.
         Falls back to Khmer female voice if language not found.
    """
    key = target_language.lower().strip()
    voices = LANGUAGE_VOICE_MAP.get(key)
    if voices is None:
        logger.warning(
            f"[LangResolver] Unknown language '{target_language}'. "
            "Falling back to Khmer female voice."
        )
        voices = LANGUAGE_VOICE_MAP["khmer"]
    return voices[0] if gender == "female" else voices[1]


def resolve_gemini_translate_prompt(target_language: str) -> str:
    """
    Return the Gemini instruction string for translating/rewriting
    a voiceover script into the target language.

    Parameters
    ----------
    target_language : Language name key, e.g. "english".

    Returns
    -------
    str — Instruction sentence for Gemini prompt.
    """
    key = target_language.lower().strip()
    prompt = _TRANSLATE_PROMPTS.get(key)
    if prompt is None:
        logger.warning(
            f"[LangResolver] No translation prompt for '{target_language}'. "
            "Using generic English instruction."
        )
        return _TRANSLATE_PROMPTS["english"]
    return prompt


def resolve_font(target_language: str) -> str:
    """Return recommended font name for subtitle rendering."""
    key = target_language.lower().strip()
    return LANGUAGE_FONT_MAP.get(key, "Roboto")


def get_supported_languages() -> list[str]:
    """Return list of all supported language keys."""
    return list(LANGUAGE_VOICE_MAP.keys())


def get_language_display_options() -> list[str]:
    """Return display name list for Gradio dropdowns."""
    return list(LANGUAGE_DISPLAY_NAMES.values())


def display_name_to_key(display_name: str) -> str:
    """Convert UI display name back to language key."""
    for key, name in LANGUAGE_DISPLAY_NAMES.items():
        if display_name == name or display_name == key:
            return key
    # Fallback: try raw lowercase match
    low = display_name.lower().strip()
    if low in LANGUAGE_VOICE_MAP:
        return low
    logger.warning(f"[LangResolver] Could not resolve display name '{display_name}' — defaulting to 'khmer'")
    return "khmer"
