"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/ultimate_ad/ultimate_creative_director.py
====================================================================

Gemini-powered creative director for ULTIMATE_AD mode.

Extends unified_creative_director.py with:
  - Explicit target_language (no default — must be set by caller)
  - template_hint per segment (drives fb-ad-studio template selection)
  - motion-graphics-spot as the priority template
  - claim_validator integration (validate_and_clean before returning)

Output schema is a superset of the standard script_segments schema
used by news_ads mode, so existing rendering helpers are reusable.
"""

import json
import logging
import os
import re
from typing import Any, Optional
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Template-specific prompt guidance
# ──────────────────────────────────────────────

_TEMPLATE_GUIDANCE: dict[str, str] = {
    "motion-graphics-spot": (
        "Format: Kinetic-typography motion-graphics video (15-30s). "
        "NO on-camera talent needed. ALL visuals are AI-generated B-Roll + text animation. "
        "Structure: Hook (0-3s) → Problem (3-8s) → Solution (8-18s) → Proof (18-25s) → CTA (25-30s). "
        "Keep each voiceover_text short and punchy (max 15 words per segment). "
        "visual_hint must be specific enough for stock footage search (e.g., 'close-up glowing skincare serum bottle')."
    ),
    "talking-head-founder-ad": (
        "Format: Founder talking-head video (45-75s). Authentic, personal tone. "
        "Structure: Cold-open hook → Personal story (problem) → Discovery → Solution reveal → Social proof → CTA. "
        "voiceover_text should sound natural when spoken aloud (no bullet points). "
        "visual_hint for non-talking segments only."
    ),
    "split-screen": (
        "Format: Split-screen comparison video (~15s). Two panels: Claim vs Proof, Before vs After. "
        "Structure: Hook → Problem (top panel) → Solution (bottom panel) → CTA. "
        "Keep script tight — viewer reads TWO panels simultaneously."
    ),
    "imessage-conversation": (
        "Format: Animated iMessage thread (~10-14s). Social-proof 'friend recommends' format. "
        "voiceover_text is the spoken transcript of the conversation. "
        "on_screen_text is the actual message bubbles (short, conversational). "
        "Max 4-5 message exchanges total."
    ),
    "listicle-top5": (
        "Format: Top-5 reasons/benefits listicle (15-30s). Fast-cut, numbered items. "
        "Structure: Title card → Item 1 → Item 2 → Item 3 → Item 4 → Item 5 → CTA. "
        "Each item: 1 sentence voiceover + 1-line on_screen_text."
    ),
    "revid-story": (
        "Format: Full-bleed story video (~25s). Big word-synced kinetic captions over AI scene backgrounds. "
        "voiceover_text must be short impactful phrases that work as large on-screen text. "
        "Structure: Hook question → Problem stat → Solution teaser → Reveal → CTA."
    ),
    "whiteboard": (
        "Format: Hand-drawn whiteboard explainer (~55s). Doodle-style visual storytelling. "
        "Structure: Concept intro → Step 1 → Step 2 → Step 3 → Result → CTA. "
        "Explain the 'how it works' concisely, like teaching a friend."
    ),
}


# ──────────────────────────────────────────────
# Main Generator
# ──────────────────────────────────────────────

def generate_ultimate_script(
    product_name:    str,
    target_language: str,
    ad_template:     str   = "motion-graphics-spot",
    script_text:     str   = "",
    key_benefits:    list  = None,
    pain_points:     list  = None,
    price:           str   = "",
    num_hooks:       int   = 3,
    api_key:         str   = "",
    auto_rewrite_violations: bool = True,
) -> dict:
    """
    Generate a complete ad script using Gemini, tailored for the chosen template.

    If script_text is provided and non-empty, it is used as the voiceover content
    directly (structured into segments by Gemini) instead of generating from scratch.

    Parameters
    ----------
    product_name    : Product name / description.
    target_language : REQUIRED — "vietnamese" | "khmer" | "english".
    ad_template     : Template key matching fb-ad-studio templates folder name.
    script_text     : Optional pre-written script to structure (skips creative gen).
    key_benefits    : List of benefit strings.
    pain_points     : List of pain point strings.
    price           : Price string (e.g. "299.000đ").
    num_hooks       : Number of A/B hook variants to generate.
    api_key         : Gemini API key.
    auto_rewrite_violations: Run claim_validator and auto-rewrite on output.

    Returns
    -------
    dict — Script dict with hook_variants, script_segments, price_display, cta_text.
    """
    from google import genai
    from google.genai import types
    from core.claim_validator import validate_and_clean

    if key_benefits is None:
        key_benefits = []
    if pain_points is None:
        pain_points = []

    template_guidance = _TEMPLATE_GUIDANCE.get(
        ad_template,
        _TEMPLATE_GUIDANCE["motion-graphics-spot"]
    )

    # ── Build context block ────────────────────────────────────────
    context_parts = [f"Product: {product_name}"]
    if price:
        context_parts.append(f"Price: {price}")
    if key_benefits:
        context_parts.append(f"Key Benefits: {', '.join(key_benefits)}")
    if pain_points:
        context_parts.append(f"Pain Points: {', '.join(pain_points)}")
    if script_text.strip():
        context_parts.append(
            f"\nPre-written script (structure this into segments — do NOT rewrite the core message):\n{script_text}"
        )
    context_block = "\n".join(context_parts)

    # ── Build prompt ───────────────────────────────────────────────
    prompt = f"""You are a world-class direct-response ad copywriter and video director.
Create a complete ad script for this product and video template.

TEMPLATE: {ad_template}
TEMPLATE RULES: {template_guidance}

CONTEXT:
{context_block}

LANGUAGE: ALL voiceover_text and on_screen_text MUST be strictly in {target_language}.
DO NOT mix languages. visual_hint MUST be in English (for stock footage search).

OUTPUT RULES:
1. Generate exactly {num_hooks} hook_variants (types: question, shock_fact, relatable_scenario).
2. overlay_type must be one of: "none", "price_tag", "social_proof".
3. emotion must be one of: "concerned", "urgent", "confident", "upbeat", "energetic".
4. template_hint per segment: brief English note for the motion designer (e.g., "zoom-in text reveal", "whip-pan cut").
5. NEVER use absolute claims: no "100% guaranteed", "miracle", "cure", "no side effects".
6. duration_hint_sec for each segment should sum to 15-30s (motion-graphics) or 45-75s (talking-head).

Return ONLY a valid JSON object:
{{
  "title": "string",
  "hook_variants": [
    {{
      "variant_id": 1,
      "hook_type": "question | shock_fact | relatable_scenario",
      "voiceover_text": "string ({target_language})",
      "on_screen_text": "string ({target_language})",
      "visual_hint": "string (English)",
      "template_hint": "string (English motion note)",
      "duration_hint_sec": 3.0
    }}
  ],
  "script_segments": [
    {{
      "id": 1,
      "act": "hook | problem | solution | proof | cta",
      "emotion": "concerned | urgent | confident | upbeat | energetic",
      "voiceover_text": "string ({target_language})",
      "on_screen_text": "string ({target_language})",
      "visual_hint": "string (English)",
      "template_hint": "string (English motion note)",
      "overlay_type": "none | price_tag | social_proof",
      "duration_hint_sec": 5.0
    }}
  ],
  "price_display": "string or null",
  "cta_text": "string ({target_language}) or null"
}}
"""

    # ── Call Gemini ────────────────────────────────────────────────
    logger.info(f"[UltimateCreativeDirector] Generating script: template={ad_template}, lang={target_language}")

    client = get_pooled_client(api_key=api_key)
    fallback_models = [
        os.getenv("GEMINI_MODEL", "").strip(),
        "gemini-3.6-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
    ]

    response = None
    for model in [m for m in fallback_models if m]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=0.72,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as exc:
            logger.debug(f"[UltimateCreativeDirector] Model {model} failed: {exc}")
            continue

    if not response:
        raise RuntimeError("[UltimateCreativeDirector] All Gemini models failed.")

    raw = re.sub(r"```[a-z]*\n?", "", response.text.strip()).strip()
    try:
        script = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"[UltimateCreativeDirector] Failed to parse Gemini JSON: {exc}\nRaw: {raw[:500]}"
        )

    seg_count = len(script.get("script_segments", []))
    logger.info(f"[UltimateCreativeDirector] Script generated: {seg_count} segments, {num_hooks} hooks.")

    # ── Claim Validation + Auto-Rewrite ───────────────────────────
    if auto_rewrite_violations and api_key:
        script, violations = validate_and_clean(
            script=script,
            api_key=api_key,
            language=target_language,
            auto_rewrite=True,
        )
        if violations:
            script["_claim_violations"] = violations  # carry for render_report
    else:
        script["_claim_violations"] = []

    return script
