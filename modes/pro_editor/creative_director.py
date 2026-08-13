"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/pro_editor/creative_director.py — Gemini Creative Script
====================================================================

Calls Gemini Flash (with model fallback) to generate a structured
CreativeScript JSON following the Hook-Problem-Agitate-Solution-Proof-CTA
copywriting framework optimised for Khmer-language short-form video ads.
"""

import json
import logging
import os
import re
from typing import Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Reuse the same model fallback list from ai_analyzer.py
DEFAULT_MODELS = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
]

# ── Creative Script Prompt ────────────────────────────────────────

_CREATIVE_SCRIPT_PROMPT = """
Bạn là biên kịch phim ngắn quảng cáo (UGC micro-drama) cho thị trường Campuchia, viết bằng tiếng Khmer tự nhiên.
KHÔNG viết như tin tức. KHÔNG liệt kê tính năng sản phẩm.

═══════════════════════════════════════
INPUT
═══════════════════════════════════════
product_name: {product_name}
price: {price}
benefits: {benefits}
pain_points: {pain_points}
TARGET_LANGUAGE: "khmer"
NUM_HOOK_VARIANTS: {num_hooks}

Viết một câu chuyện dài 60-150 giây (chia thành 15-35 segment, mỗi segment 3-6 giây), theo cấu trúc:

1. HOOK (1 segment, 3-5 giây): một câu hỏi/tình huống gây tò mò khiến người xem dừng lướt ngay giây đầu.
2. SETUP (1-2 segment): giới thiệu nhân vật/bối cảnh đời thường một cách tự nhiên, KHÔNG vội vào vấn đề ngay.
3. PROBLEM (3-5 segment): nhân vật trải qua vấn đề mà sản phẩm giải quyết — kể chi tiết qua NHIỀU tình huống/khoảnh khắc nhỏ khác nhau (không lặp lại 1 câu than phiền), có cảm xúc thật tăng dần (bực bội -> lo lắng -> gần như bỏ cuộc).
4. TURNING POINT (1-2 segment): khoảnh khắc phát hiện ra giải pháp — điểm ngoặt cảm xúc rõ rệt, đổi hẳn tông giọng.
5. SOLUTION (3-6 segment): giải thích/thể hiện sản phẩm hoạt động ra sao qua nhiều bước/góc nhìn cụ thể — như đang trải nghiệm cùng nhân vật, không phải liệt kê tính năng.
6. PROOF (2-4 segment): bằng chứng cụ thể (trước/sau, phản ứng người xung quanh, con số, cảm nhận thật).
7. CTA (1 segment, 3-5 giây): lời kêu gọi hành động ngắn gọn, tự nhiên như bạn bè mách nhau.

Với mỗi segment, trả về visual_hint mô tả CẢNH ĐIỆN ẢNH cụ thể (ai, làm gì, biểu cảm nào, góc máy nào). Mỗi segment trong cùng beat (đặc biệt PROBLEM và SOLUTION) phải có visual_hint và camera_hint KHÁC NHAU — tuyệt đối không lặp lại cùng một cảnh hai lần.

═══════════════════════════════════════
HOOK VARIANTS
═══════════════════════════════════════
Generate NUM_HOOK_VARIANTS distinct hook options for A/B testing.

═══════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════
Return ONLY a valid JSON object matching exactly this structure:

{
  "product_name": "string",
  "hook_variants": [
    {
      "variant_id": 1,
      "hook_type": "question | shock_fact | relatable_scenario",
      "voiceover_text": "string",
      "on_screen_text": "string",
      "visual_hint": "string",
      "duration_hint_sec": 4.0
    }
  ],
  "script_segments": [
    {
      "id": 1,
      "narrative_beat": "hook | setup | problem | turning_point | solution | proof | cta",
      "emotion": "curious | frustrated | worried | relieved | excited | confident | urgent",
      "voiceover_text": "string (Khmer)",
      "on_screen_text": "string (Khmer)",
      "visual_hint": "string",
      "camera_hint": "close-up | medium-shot | POV | over-shoulder | wide-establishing",
      "overlay_type": "none | price_tag | social_proof",
      "duration_hint_sec": 4.0
    }
  ],
  "price_display": "string",
  "cta_text": "string",
  "output_quality": "1080p"
}
"""

# Supplemental section added when ProductResearch is available
_RESEARCH_SUPPLEMENT = """

## REAL CUSTOMER INTELLIGENCE (from actual web research — use this to write authentic copy)

### Verified Product Benefits:
{benefits}

### Ingredient / Key Highlights:
{ingredient_highlights}

### Actual Customer Praise (REAL quotes — use their exact language/sentiment in proof/CTA):
{common_praise}

### Actual Customer Complaints / Pain Points (use these for problem/agitate acts):
{common_complaints}

### Suggested Pain Points for Advertising:
{suggested_pain_points}

### Usage Instructions:
{usage_instructions}

IMPORTANT: The segments for 'problem' and 'agitate' acts MUST reflect the real complaints above.
The 'proof' segment MUST echo real customer praise using Khmer phrasing.
Do NOT invent generic benefits — use the specific ones listed above.
"""


# ── Gemini Fallback Helper ────────────────────────────────────────

def _generate_content_with_fallback(
    client:   genai.Client,
    contents: list,
    config:   Optional[types.GenerateContentConfig] = None,
):
    models = [m for m in DEFAULT_MODELS if m]
    last_exc = None
    for model in models:
        try:
            kwargs = {"model": model, "contents": contents}
            if config:
                kwargs["config"] = config
            logger.info(f"[CreativeDir] Trying Gemini model: {model}")
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            if any(k in str(exc).lower() for k in ["404", "not_found", "no longer", "not supported"]):
                logger.warning(f"    Model '{model}' unavailable. Trying next...")
                last_exc = exc
                continue
            raise exc
    if last_exc:
        raise last_exc





# ── Public API ────────────────────────────────────────────────────

def generate_creative_script(
    product_image:    str,
    product_name:     str,
    price:            str,
    benefits:         list,
    pain_points:      list,
    api_key:          str,
    num_hooks:        int  = 3,
    product_research: Optional[object] = None,   # ProductResearch dataclass
    style_profile:    Optional[dict]   = None,   # NEW: User style profile
) -> dict:
    """
    Call Gemini to produce a CreativeScript JSON for the product.

    Parameters
    ----------
    product_image    : Path to product image (sent as visual context).
    product_name     : Product display name.
    price            : Price string (e.g. "15,000 KHR").
    benefits         : List of 2-4 key product benefits.
    pain_points      : List of 1-3 audience pain points.
    api_key          : Google AI Studio API key.
    num_hooks        : Number of hook variants to request (min 2, max 5).
    product_research : Optional ProductResearch from product_intelligence module.
                       When provided, injects real customer language into the prompt.

    Returns
    -------
    dict — Parsed CreativeScript JSON conforming to the schema above.
    """
    client = genai.Client(api_key=api_key)

    num_hooks = max(2, min(5, num_hooks))

    # Build effective benefits + pain points (ProductResearch overrides CLI inputs if richer)
    effective_benefits    = list(benefits)
    effective_pain_points = list(pain_points)

    if product_research and not getattr(product_research, 'research_skipped', True):
        # Merge research data: research first (more specific), then user-supplied as fallback
        if product_research.benefits:
            effective_benefits    = product_research.benefits[:6] + [b for b in benefits if b not in product_research.benefits]
        if product_research.suggested_pain_points:
            effective_pain_points = product_research.suggested_pain_points[:5] + [p for p in pain_points if p not in product_research.suggested_pain_points]

    # Build style injection block
    style_injection_block = ""
    if style_profile:
        try:
            from core.style_profile import build_style_injection_prompt
            style_injection_block = build_style_injection_prompt(style_profile)
            logger.info(
                f"[CreativeDir] Style profile injected: "
                f"'{style_profile.get('profile_name', 'unknown')}'"
            )
        except Exception as exc:
            logger.warning(f"[CreativeDir] Style profile injection failed: {exc}")

    prompt = style_injection_block + "\n\n" + _CREATIVE_SCRIPT_PROMPT.format(
        product_name=product_name,
        price=price,
        benefits=", ".join(effective_benefits) or "Product benefits",
        pain_points=", ".join(effective_pain_points) or "Common consumer problems",
        num_hooks=num_hooks,
    )

    # Inject research supplement when real customer data is available
    if product_research and not getattr(product_research, 'research_skipped', True):
        def _fmt(lst): return "\n".join(f'  - "{x}"' for x in lst) if lst else "  (not available)"
        supplement = _RESEARCH_SUPPLEMENT.format(
            benefits            = _fmt(product_research.benefits),
            ingredient_highlights = _fmt(product_research.ingredient_highlights),
            common_praise       = _fmt(product_research.common_praise),
            common_complaints   = _fmt(product_research.common_complaints),
            suggested_pain_points = _fmt(product_research.suggested_pain_points),
            usage_instructions  = product_research.usage_instructions or "(not available)",
        )
        prompt = prompt + supplement
        logger.info(
            f"[CreativeDir] Research injected: {len(product_research.benefits)} benefits, "
            f"{len(product_research.common_praise)} praise, "
            f"{len(product_research.common_complaints)} complaints."
        )
    else:
        logger.info("[CreativeDir] No product research available — using image + inputs only.")

    # Build contents — product image for visual context + text prompt
    contents = [prompt]
    if product_image and os.path.isfile(product_image):
        import mimetypes
        mime, _ = mimetypes.guess_type(product_image)
        mime = mime or "image/jpeg"
        with open(product_image, "rb") as f:
            img_data = f.read()
        img_part = types.Part.from_bytes(data=img_data, mime_type=mime)
        contents = [img_part, prompt]

    response = _generate_content_with_fallback(
        client=client,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.75,
            max_output_tokens=3000,
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip()
    raw = re.sub(r"```[a-z]*\n?", "", raw).strip()

    try:
        script = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(f"[CreativeDir] JSON parse failed: {exc}. Building minimal fallback script.")
        script = _build_fallback_script(product_name, price, benefits, pain_points)

    # Enforce minimum 2 hook variants
    if len(script.get("hook_variants", [])) < 2:
        script["hook_variants"] = _build_fallback_hooks(product_name)

    logger.info(
        f"[CreativeDir] Script ready: {len(script.get('script_segments', []))} segments, "
        f"{len(script.get('hook_variants', []))} hooks"
    )
    return script


def _build_fallback_script(
    product_name: str,
    price: str,
    benefits: list[str],
    pain_points: list[str],
) -> dict:
    """Minimal fallback CreativeScript when Gemini JSON parse fails."""
    ben_text = ", ".join(benefits[:2]) if benefits else product_name
    pain_text = pain_points[0] if pain_points else "everyday problem"
    return {
        "product_name": product_name,
        "hook_variants": _build_fallback_hooks(product_name),
        "script_segments": [
            {
                "id": 1, "act": "problem", "emotion": "concerned", "overlay_type": "none",
                "voiceover_text": f"តើអ្នកជួបបញ្ហា{pain_text}ទេ?",
                "on_screen_text": f"បញ្ហា{pain_text}",
                "visual_hint": "problem lifestyle frustrated person",
                "duration_hint_sec": 5
            },
            {
                "id": 2, "act": "solution", "emotion": "confident", "overlay_type": "none",
                "voiceover_text": f"សាកល្បង{product_name}ថ្ងៃនេះ! {ben_text}",
                "on_screen_text": product_name,
                "visual_hint": "product closeup beauty product",
                "duration_hint_sec": 6
            },
            {
                "id": 3, "act": "cta", "emotion": "energetic", "overlay_type": "price_tag",
                "voiceover_text": "ណាត់ទំនិញឥឡូវនេះ! ការដឹកជញ្ជូនឥតគិតថ្លៃ!",
                "on_screen_text": "ណាត់ទំនិញឥឡូវ!",
                "visual_hint": "online order phone shopping",
                "duration_hint_sec": 4
            },
        ],
        "price_display": price,
        "cta_text": "BUY NOW",
    }


def _build_fallback_hooks(product_name: str) -> list[dict]:
    return [
        {
            "variant_id": 1,
            "hook_type": "question",
            "voiceover_text": f"តើអ្នកធ្លាប់ដឹងអំពី{product_name}ទេ?",
            "on_screen_text": f"ដឹងអំពី{product_name}ទេ?",
            "visual_hint": "surprised face attention grabbing",
            "duration_hint_sec": 3
        },
        {
            "variant_id": 2,
            "hook_type": "shock_fact",
            "voiceover_text": f"អ្នកកំពុងខ្ជះខ្ជាយលុយ! {product_name}ផ្លាស់ប្ដូរអ្វីៗ!",
            "on_screen_text": "ខ្ជះខ្ជាយលុយ!",
            "visual_hint": "before after transformation wow reaction",
            "duration_hint_sec": 3
        },
    ]
