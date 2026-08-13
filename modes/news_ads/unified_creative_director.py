"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/news_ads/unified_creative_director.py
====================================================================

Generates the unified JSON script for Mode 8 (News Ads), adjusting
its internal prompt instructions based on the format_style:
- "pure_news": Standard news delivery, no sales.
- "direct_ad": Standard PAS-Proof-CTA ad (like pro_editor).
- "news_style_ad": Hybrid. News hook -> Transition -> Sales.

Output matches the common script_segments schema.
"""

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

def generate_unified_creative_script(
    source_type: str,
    source_content: str,
    product_name: str,
    price: str,
    benefits: list,
    pain_points: list,
    format_style: str,
    api_key: str,
    target_language: str = "khmer",
    num_hooks: int = 3,
) -> dict:
    """
    Calls Gemini to generate the unified script.
    """
    from google import genai
    from google.genai import types
    import os

    client = genai.Client(api_key=api_key)
    
    # ── 1. Gather Context ──────────────────────────────────────────────
    context_block = ""
    if source_type in ["topic", "article"] and source_content.strip():
        context_block += f"Source Material / Topic:\n{source_content}\n\n"
        if product_name:
            context_block += f"Product to promote (transition): {product_name}\n"
    elif source_type == "product":
        context_block += f"Product: {product_name or 'Sản phẩm'}\n"
        if price:
            context_block += f"Price: {price}\n"
        if benefits:
            context_block += f"Key Benefits: {', '.join(benefits)}\n"
        if pain_points:
            context_block += f"Pain Points: {', '.join(pain_points)}\n"
    else:
        context_block += f"Content: {source_content or product_name}\n"

    # ── 2. Format Instructions ──────────────────────────────────────────
    if format_style == "pure_news":
        format_instructions = (
            "You are a professional News Anchor.\n"
            "Style: Objective, informative, serious, pure news delivery. NO SALES PITCH.\n"
            "Do not include calls to action to buy products, nor price tags.\n"
            f"Generate exactly {num_hooks} hook variants (headlines).\n"
            "The body should simply report the news/topic objectively."
        )
    elif format_style == "direct_ad":
        format_instructions = (
            "You are an aggressive Direct-Response Copywriter for Social Media Ads.\n"
            "Style: High energy, problem-agitate-solution (PAS), social proof, strong CTA.\n"
            "Do NOT sound like a news broadcast. Sound like a viral TikTok/Reels ad.\n"
            f"Generate exactly {num_hooks} hook variants targeting the pain points directly.\n"
            "Include 'price_tag' and 'social_proof' overlays."
        )
    else:  # "news_style_ad" (hybrid)
        format_instructions = (
            "You are a clever marketer writing a 'News-Style Product Ad'.\n"
            "This video must open looking exactly like an objective news broadcast, then seamlessly transition into a product pitch.\n"
            "STRUCTURE RULES:\n"
            "1. HOOK (3-4 seconds): A sensational news headline or question related to the pain point. DO NOT MENTION THE PRODUCT OR BRAND HERE. Create the feel of a breaking news report.\n"
            f"   Generate exactly {num_hooks} hook variants (question, shock_fact, relatable_scenario).\n"
            "2. CONTEXT (News tone): 1-2 segments discussing the problem objectively ('Experts warn...', 'A recent study shows...'). This is the Problem/Agitate phase but disguised as a news report.\n"
            "3. TRANSITION: A natural pivot to the solution ('Fortunately, a new solution is gaining traction...').\n"
            "4. SOLUTION + PROOF (Sales tone): Introduce the product, benefits, and social proof.\n"
            "5. OFFER + CTA: Strong call to action and price display.\n"
            "For the 'news' segments, use visual_hints like 'news studio', 'reporter', 'breaking news'. For the 'sales' segments, use product-related visual_hints.\n"
        )

    # ── 3. Build Prompt ──────────────────────────────────────────────
    prompt = f"""
{format_instructions}

CONTEXT:
{context_block}

RULES:
1. All voiceover_text and on_screen_text MUST be strictly in {target_language}. DO NOT mix languages.
2. Provide 'channel_name' (e.g., 'KHMER NEWS DAILY') ONLY if format_style is not 'direct_ad'. Otherwise null.
3. visual_hint MUST be in English for stock footage search.
4. overlay_type MUST be one of: "none", "price_tag", "social_proof".
5. emotion MUST be one of: "concerned", "urgent", "confident", "upbeat", "energetic".

Return ONLY a valid JSON object matching this schema:
{{
  "title": "string (Video title)",
  "channel_name": "string or null",
  "hook_variants": [
    {{
      "variant_id": 1,
      "hook_type": "question | shock_fact | relatable_scenario",
      "voiceover_text": "string (Khmer)",
      "on_screen_text": "string (Khmer)",
      "visual_hint": "string (English)",
      "duration_hint_sec": 3.0
    }}
  ],
  "script_segments": [
    {{
      "id": 1,
      "act": "hook | context | solution | proof | cta",
      "emotion": "concerned | urgent | confident | upbeat | energetic",
      "voiceover_text": "string (Khmer)",
      "on_screen_text": "string (Khmer)",
      "visual_hint": "string (English)",
      "overlay_type": "none | price_tag | social_proof",
      "duration_hint_sec": 5.0
    }}
  ],
  "price_display": "string or null",
  "cta_text": "string or null",
  "output_quality": "1080p"
}}
"""

    # ── 4. Execute API Call ──────────────────────────────────────────
    logger.info(f"[UnifiedCreativeDirector] Calling Gemini for format_style={format_style}")
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
                    temperature=0.7,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                ),
            )
            break
        except Exception as exc:
            logger.debug(f"[UnifiedCreativeDirector] Model {model} failed: {exc}")
            continue

    if not response:
        raise RuntimeError("Failed to generate unified creative script from Gemini.")

    raw = re.sub(r"```[a-z]*\n?", "", response.text.strip()).strip()
    try:
        script_data = json.loads(raw)
        logger.info(f"[UnifiedCreativeDirector] Successfully parsed JSON script ({len(script_data.get('script_segments', []))} segments)")
        return script_data
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse Gemini output as JSON: {exc}\nRaw Output: {raw}")

