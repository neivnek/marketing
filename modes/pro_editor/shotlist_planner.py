"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/pro_editor/shotlist_planner.py — Shotlist Builder
====================================================================

Converts the raw CreativeScript segments into a validated ShotlistItem list.

Key responsibilities:
  1. Batch-translate all b_roll_keywords to English in ONE Gemini call (Rule 18).
     Not per-segment — saves quota and latency significantly.
  2. Validate minimum scene count (warn if <10 for 60-90s target).
  3. Enforce product-image interleave rule (Rule in Addendum 3, Section 5):
     product image must appear at least every 8-10 seconds.
     If 2+ consecutive B-roll slots exist without a product slot, insert a
     short product_image slot between them.
  4. Mark use_ken_burns=True for slots where no B-roll exists (yet).
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)

# Minimum scenes recommended for a 60-90s professional video
MIN_SCENES_FOR_60S   = 10
# Max consecutive B-roll segments without product image appearance
MAX_BROLL_CONSECUTIVE = 2
# If consecutive B-roll exceeds this seconds total, insert product shot
PRODUCT_INTERLEAVE_SEC = 8.0


# ── ShotlistItem Dataclass ────────────────────────────────────────

@dataclass
class ShotlistItem:
    """Represents one shot/scene in the final video."""
    segment_id:      int
    act:             str             # problem | agitate | solution | proof | cta
    voiceover_text:  str
    on_screen_text:  str
    overlay_type:    str             # price_tag | social_proof | none
    emotion:         str             # concerned | urgent | confident | upbeat | energetic
    visual_hint:     str             # English visual description
    en_keywords:     list            # English-only B-roll search terms
    duration_sec:    float
    source_tier:     str             # "stock" | "scraped" | "product_image"
    use_ken_burns:   bool = False    # True when B-roll unavailable → fallback to product image


# ── Static Keyword Translation Map ───────────────────────────────

_KH_VI_TO_EN: dict[str, str] = {
    # Khmer keywords
    "ប្ដូរ": "transform",
    "ផ្លាស់ប្ដូរ": "transformation",
    "ស្រស់ស្អាត": "beautiful",
    "ស្បែក": "skin",
    "សក់": "hair",
    "ក្ដៅ": "hot",
    "ត្រជាក់": "cool",
    "ទំនិញ": "product",
    "ថ្ងៃ": "day",
    "ផ្ទះ": "home",
    "ម្ហូប": "food",
    "ស្រស់": "fresh",
    "ពណ៌": "color",
    "រយៈពេល": "duration",
    "ល្ហែ": "gentle",
    "ស្ងាត់": "calm",
    # Vietnamese keywords
    "tóc": "hair",
    "da": "skin",
    "gel": "gel",
    "dưỡng": "nourishing",
    "tốt": "good",
    "đẹp": "beautiful",
    "nhanh": "fast",
    "bán chạy": "bestselling",
    "phụ nữ": "woman",
    "nam": "man",
    "gia đình": "family",
    "thực phẩm": "food",
    "nhà": "home",
    "thời trang": "fashion",
    "mỹ phẩm": "cosmetics",
}


def _static_translate(kw: str) -> str:
    """Translate via static map. Returns kw unchanged if not found."""
    return _KH_VI_TO_EN.get(kw.strip(), kw.strip())


def _is_english(text: str) -> bool:
    """Heuristic: True if text is predominantly ASCII (likely already English)."""
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return (ascii_count / max(len(text), 1)) > 0.7


# ── Batch Gemini Translation ──────────────────────────────────────

def _batch_translate_keywords(
    all_keyword_groups: list[list[str]],
    api_key: str,
) -> list[list[str]]:
    """
    Translate all b_roll_keywords across all segments in ONE Gemini call.

    Rule 18: batch call, not per-segment, to minimize quota usage.

    Parameters
    ----------
    all_keyword_groups : List of keyword lists, one per segment.
    api_key            : GEMINI_API_KEY.

    Returns
    -------
    Same-length list of translated keyword lists.
    Falls back to static map + original if Gemini call fails.
    """
    # Flatten into unique keywords that need translation
    flat = []
    seen = set()
    for group in all_keyword_groups:
        for kw in group:
            if kw not in seen and kw.strip():
                seen.add(kw)
                flat.append(kw)

    if not flat:
        return all_keyword_groups

    # Check which ones need translation (not already English)
    needs_translation = [kw for kw in flat if not _is_english(kw)]
    if not needs_translation:
        logger.debug("[Shotlist] All keywords already English — no Gemini call needed.")
        return all_keyword_groups

    if not api_key:
        logger.debug("[Shotlist] No API key — using static map for translation.")
        translation_map = {kw: _static_translate(kw) for kw in needs_translation}
    else:
        try:
            from google import genai
            from google.genai import types

            client = get_pooled_client(api_key=api_key)
            prompt = (
                "Translate these product ad keywords to concise English search terms "
                "(for Pexels/Pixabay stock video search). "
                "Return ONLY a JSON object: {\"original\": \"english_translation\", ...}\n\n"
                "Keywords:\n" +
                "\n".join(f'- "{kw}"' for kw in needs_translation)
            )

            # Try models in fallback order
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
                            temperature=0.1,
                            max_output_tokens=512,
                            response_mime_type="application/json",
                        ),
                    )
                    break
                except Exception:
                    continue

            if response:
                import json
                import re
                raw = re.sub(r"```[a-z]*\n?", "", response.text.strip()).strip()
                translation_map = json.loads(raw)
            else:
                translation_map = {}

        except Exception as exc:
            logger.warning(f"[Shotlist] Batch translation failed: {exc}. Using static map.")
            translation_map = {}

    # Apply translations
    def translate(kw: str) -> str:
        if kw in translation_map:
            return translation_map[kw]
        return _static_translate(kw)

    return [[translate(kw) for kw in group] for group in all_keyword_groups]


# ── Product Interleave Enforcement ────────────────────────────────

def _enforce_product_interleave(shotlist: list[ShotlistItem]) -> list[ShotlistItem]:
    """
    Ensure product image appears at least every 8-10 seconds.
    If 2+ consecutive non-product shots accumulate >=8s, insert a 2s product shot.
    """
    result = []
    consecutive_broll_sec = 0.0
    consecutive_count     = 0
    next_id               = max(s.segment_id for s in shotlist) + 100   # spare ID range

    for shot in shotlist:
        is_product_shot = (shot.source_tier == "product_image" or shot.use_ken_burns)

        if is_product_shot:
            consecutive_broll_sec = 0.0
            consecutive_count     = 0
            result.append(shot)
        else:
            consecutive_count     += 1
            consecutive_broll_sec += shot.duration_sec

            if (consecutive_count > MAX_BROLL_CONSECUTIVE
                    or consecutive_broll_sec >= PRODUCT_INTERLEAVE_SEC):
                # Insert a short product image shot (Ken Burns) before this shot
                product_insert = ShotlistItem(
                    segment_id=next_id,
                    act=shot.act,
                    voiceover_text="",   # silent — visual brand anchor only
                    on_screen_text=shot.on_screen_text,
                    overlay_type="none",
                    emotion=shot.emotion,
                    visual_hint="product closeup",
                    en_keywords=["product closeup"],
                    duration_sec=2.0,
                    source_tier="product_image",
                    use_ken_burns=True,
                )
                result.append(product_insert)
                next_id += 1
                consecutive_broll_sec = shot.duration_sec
                consecutive_count     = 1
                logger.debug(
                    f"[Shotlist] Inserted product anchor before seg {shot.segment_id} "
                    f"(brand visibility rule: every {PRODUCT_INTERLEAVE_SEC}s)"
                )

            result.append(shot)

    return result


# ── Public API ────────────────────────────────────────────────────

def build_shotlist(
    script:           dict,
    product_category: str  = "general",
    target_duration:  float = 60.0,
    gemini_api_key:   str  = "",
    enforce_interleave: bool = True,
) -> list[ShotlistItem]:
    """
    Convert a CreativeScript dict into a validated list of ShotlistItems.

    Parameters
    ----------
    script             : CreativeScript dict from creative_director.py.
    product_category   : Category label for B-roll dedup (e.g. "haircare").
    target_duration    : Expected total video duration in seconds.
    gemini_api_key     : GEMINI_API_KEY for batch translation (optional).
    enforce_interleave : Insert product image anchors to maintain brand visibility.

    Returns
    -------
    list[ShotlistItem] — ordered shots, keywords in English.
    """
    segments = script.get("script_segments", [])
    if not segments:
        logger.warning("[Shotlist] No script_segments in CreativeScript — using minimal fallback.")
        return _build_fallback_shotlist()

    # ── Step 1: Extract all keyword groups for batch translation
    # visual_hint is a string, we split it into a list for legacy compatibility
    raw_keyword_groups = [
        [seg.get("visual_hint", product_category)]
        for seg in segments
    ]
    logger.info(f"[Shotlist] Batch translating keywords for {len(segments)} segments...")
    translated_groups = _batch_translate_keywords(raw_keyword_groups, gemini_api_key)

    # ── Step 2: Build ShotlistItems
    shotlist: list[ShotlistItem] = []
    for i, seg in enumerate(segments):
        en_keywords = translated_groups[i] if i < len(translated_groups) else [product_category]

        shot = ShotlistItem(
            segment_id=int(seg.get("id", len(shotlist) + 1)),
            act=seg.get("act", "solution").lower(),
            voiceover_text=seg.get("voiceover_text", ""),
            on_screen_text=seg.get("on_screen_text", ""),
            overlay_type=seg.get("overlay_type", "none"),
            emotion=seg.get("emotion", "confident").lower(),
            visual_hint=seg.get("visual_hint", product_category),
            en_keywords=en_keywords,
            duration_sec=float(seg.get("duration_hint_sec", 5.0)),
            source_tier=seg.get("source_tier", "stock"),
            use_ken_burns=False,
        )
        shotlist.append(shot)

    # ── Step 3: Enforce product interleave (brand visibility rule)
    if enforce_interleave:
        shotlist = _enforce_product_interleave(shotlist)

    # ── Step 4: Validation
    total_dur = sum(s.duration_sec for s in shotlist)
    original_count = len(segments)
    final_count    = len(shotlist)

    if original_count < MIN_SCENES_FOR_60S and total_dur >= 50:
        logger.warning(
            f"[Shotlist] Only {original_count} original scenes for {total_dur:.0f}s video "
            f"(recommended: {MIN_SCENES_FOR_60S}). Add more segments for better viewer retention."
        )
    logger.info(
        f"[Shotlist] Built {final_count} shots ({original_count} original + "
        f"{final_count - original_count} product anchors), "
        f"estimated duration: {total_dur:.0f}s"
    )

    return shotlist


def _build_fallback_shotlist() -> list[ShotlistItem]:
    """Emergency fallback when no segments exist."""
    return [
        ShotlistItem(
            segment_id=1, act="problem", emotion="concerned", overlay_type="none",
            voiceover_text="", on_screen_text="", visual_hint="problem frustrated person",
            en_keywords=["problem", "frustrated person"],
            duration_sec=5.0, source_tier="stock", use_ken_burns=True,
        ),
        ShotlistItem(
            segment_id=2, act="solution", emotion="confident", overlay_type="none",
            voiceover_text="", on_screen_text="", visual_hint="product closeup",
            en_keywords=["product", "closeup"],
            duration_sec=6.0, source_tier="stock", use_ken_burns=True,
        ),
        ShotlistItem(
            segment_id=3, act="cta", emotion="energetic", overlay_type="price_tag",
            voiceover_text="", on_screen_text="", visual_hint="order now phone",
            en_keywords=["order now", "phone"],
            duration_sec=4.0, source_tier="stock", use_ken_burns=True,
        ),
    ]
