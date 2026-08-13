"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/news_pro/news_prompt_template_pro.py
====================================================================

Generates the prefilled prompt for Mode 9 (News Pro).
It combines the dynamic product info gathered from core/product_intelligence
with the enhanced schema instructions.
"""

def build_prefilled_prompt(
    product_name: str,
    price: str,
    benefits_csv: str,
    pain_points_csv: str,
    target_language: str,
    target_duration_sec: int,
    hook_variants: int,
) -> str:
    
    # 1. Parse CSV lists
    benefits = [b.strip() for b in benefits_csv.split(",") if b.strip()]
    pain_points = [p.strip() for p in pain_points_csv.split(",") if p.strip()]

    # 2. Build the prefilled data block
    if not benefits and not pain_points:
        research_block = (
            "THÔNG TIN SẢN PHẨM (đã thu thập tự động, dùng làm dữ liệu nguồn):\n"
            f"- Tên sản phẩm nhận diện: {product_name}\n"
            f"- Giá: {price if price.strip() else 'Không có'}\n"
            f"- (Lưu ý: Không tìm được nguồn dữ liệu web tự động — hãy dựa vào "
            f"tên sản phẩm để viết công dụng/vấn đề hợp lý, chung chung, không bịa số liệu cụ thể.)\n"
        )
    else:
        research_block = (
            "THÔNG TIN SẢN PHẨM (đã thu thập tự động, dùng làm dữ liệu nguồn):\n"
            f"- Tên sản phẩm nhận diện: {product_name}\n"
            f"- Giá: {price if price.strip() else 'Không có'}\n"
            f"- Công dụng tìm được từ nguồn web: {', '.join(benefits)}\n"
            f"- Vấn đề khách hàng thường gặp: {', '.join(pain_points)}\n\n"
            "LƯU Ý QUAN TRỌNG: Thông tin trên hoặc tên sản phẩm trên bao bì có thể bằng tiếng Việt, Anh, Thái, Trung...\n"
            "Nhưng bạn PHẢI hiểu ý nghĩa của chúng và viết TOÀN BỘ kịch bản (voiceover, on_screen_text) bằng tiếng Khmer.\n"
            "Hãy dùng thông tin trên làm dữ kiện thật để viết kịch bản, không bịa thêm số liệu ngoài những gì được liệt kê.\n"
        )

    # 2. Build the main prompt template (Extended Schema)
    prompt_template = f"""
{research_block}

You are a clever marketer writing a 'News-Style Product Ad'.
This video must open looking exactly like an objective news broadcast, then seamlessly transition into a product pitch.

STRUCTURE RULES:
1. HOOK (3-4 seconds): A sensational news headline or question related to the pain point. DO NOT MENTION THE PRODUCT OR BRAND HERE. Create the feel of a breaking news report.
   Generate exactly {hook_variants} hook variants (question, shock_fact, relatable_scenario).
2. CONTEXT (News tone): 1-2 segments discussing the problem objectively ("Experts warn...", "A recent study shows..."). This is the Problem/Agitate phase but disguised as a news report.
3. TRANSITION: A natural pivot to the solution ("Fortunately, a new solution is gaining traction...").
4. SOLUTION + PROOF (Sales tone): Introduce the product, benefits, and social proof based ON THE DATA PROVIDED ABOVE.
5. OFFER + CTA: Strong call to action and price display (if provided).
6. Target Duration: Enough segments to reach approx {target_duration_sec} seconds.

RULES:
1. All voiceover_text and on_screen_text MUST be strictly in {target_language.upper()} (Khmer). DO NOT mix languages. Translate any source information into natural {target_language.upper()}.
2. Provide 'channel_name' (e.g., 'KHMER NEWS DAILY').
3. visual_hint MUST be in English for stock footage search.
4. overlay_type MUST be one of: "none", "price_tag", "social_proof".
5. emotion MUST be one of: "concerned", "urgent", "confident", "upbeat", "energetic".

Return ONLY a valid JSON object matching this schema EXACTLY:
{{
  "title": "string (Video title)",
  "channel_name": "string (e.g., KHMER NEWS DAILY)",
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
    return prompt_template
