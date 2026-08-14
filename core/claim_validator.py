"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/claim_validator.py — Script Safety & Claim Filter
====================================================================

Chặn các claim phóng đại (medical, absolute guarantee, miracle)
trong kịch bản AI-generated trước khi render — tránh vi phạm
chính sách quảng cáo Meta/TikTok.

Hỗ trợ 3 ngôn ngữ: Vietnamese (vi), Khmer (km), English (en).

Quy trình:
1. validate_script()  → (is_clean, violations_list)
2. Nếu có vi phạm     → rewrite_violations() gọi Gemini rewrite
   chỉ đoạn vi phạm, giữ nguyên tone persuasive nhưng bỏ claim tuyệt đối.
3. Pipeline nhận lại script đã cleaned → tiếp tục render.
"""

import json
import logging
import os
import re
from typing import Any, Optional
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Banned Pattern Registry
# ──────────────────────────────────────────────

# Each entry: (pattern, reason_tag, severity)
# severity: "block" (must rewrite) | "warn" (log only)
BANNED_PATTERNS: list[tuple[str, str, str]] = [
    # Vietnamese
    (r"\b(chữa\s*(khỏi|bệnh|hẳn)|trị\s*(dứt|khỏi|hẳn))\b",   "medical_cure_vi",     "block"),
    (r"\b(100\s*%\s*(đảm bảo|chắc chắn|hiệu quả))\b",          "absolute_guarantee",  "block"),
    (r"\b(kỳ diệu|thần kỳ|phép màu|thần dược)\b",              "miracle_claim_vi",    "block"),
    (r"\b(đảm bảo\s*(hoàn tiền|refund)\s*100\s*%)\b",           "refund_guarantee",    "warn"),
    (r"\b(số\s*1|đứng\s*đầu|tốt nhất thế giới|vô địch)\b",     "superlative_claim_vi","warn"),
    (r"\b(không có tác dụng phụ|hoàn toàn an toàn)\b",          "safety_absolute_vi",  "block"),

    # English
    (r"\b(cure[sd]?|guaranteed?\s+cure|definitive\s+treatment)\b", "medical_cure_en",  "block"),
    (r"\b(100\s*%\s*(guaranteed?|effective|safe))\b",             "absolute_guarantee","block"),
    (r"\b(miracle|magic\s+pill|wonder\s+drug|instant\s+fix)\b",   "miracle_claim_en",  "block"),
    (r"\b(no\s+side\s+effects|completely\s+safe)\b",              "safety_absolute_en","block"),
    (r"\b(#1\s+in\s+the\s+world|best\s+in\s+the\s+world)\b",     "superlative_en",    "warn"),

    # Khmer
    (r"ព្យាបាល|ជាសះស្បើយ|ជាទូទាត់",       "medical_cure_km",    "block"),
    (r"ធានា\s*១០០|ចាំបាច់\s*ជោគជ័យ",      "absolute_guarantee", "block"),
    (r"អស្ចារ្យ|អព្ភូតហេតុ|ឱសថ\s*វេទ",    "miracle_claim_km",   "block"),
    (r"គ្មាន\s*ផល\s*ប៉ះពាល់",             "safety_absolute_km", "block"),
]


# ──────────────────────────────────────────────
# Violation Dataclass (plain dict for JSON-serializable output)
# ──────────────────────────────────────────────

def _make_violation(
    segment_id: Any,
    field: str,
    matched_text: str,
    reason_tag: str,
    severity: str,
) -> dict:
    return {
        "segment_id": segment_id,
        "field":      field,
        "matched":    matched_text,
        "reason":     reason_tag,
        "severity":   severity,
    }


# ──────────────────────────────────────────────
# Core Validation
# ──────────────────────────────────────────────

def validate_script(
    script: dict,
    language: str = "khmer",
) -> tuple[bool, list[dict]]:
    """
    Scan all voiceover_text and on_screen_text fields in a script dict
    for banned patterns.

    Parameters
    ----------
    script   : Script dict as returned by the creative director
               (must contain 'script_segments' and optionally 'hook_variants').
    language : Hint for log messages. Pattern matching runs on all languages
               regardless of this setting.

    Returns
    -------
    (is_clean: bool, violations: list[dict])
        is_clean   — True if zero "block" severity violations found.
        violations — All violations including "warn" level.
    """
    violations: list[dict] = []
    fields_to_check = ["voiceover_text", "on_screen_text"]

    segments = script.get("script_segments", [])
    hooks    = script.get("hook_variants", [])

    for seg in segments + hooks:
        seg_id = seg.get("id") or seg.get("variant_id") or "?"
        for field in fields_to_check:
            text = seg.get(field, "") or ""
            for pattern, reason_tag, severity in BANNED_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    matched_str = match if isinstance(match, str) else " ".join(match)
                    violations.append(_make_violation(
                        segment_id=seg_id,
                        field=field,
                        matched_text=matched_str,
                        reason_tag=reason_tag,
                        severity=severity,
                    ))

    block_count = sum(1 for v in violations if v["severity"] == "block")
    warn_count  = sum(1 for v in violations if v["severity"] == "warn")

    if violations:
        logger.warning(
            f"[ClaimValidator] Found {block_count} BLOCK + {warn_count} WARN violations "
            f"in script (language={language})"
        )
        for v in violations:
            logger.warning(
                f"  [{v['severity'].upper()}] seg={v['segment_id']} field={v['field']} "
                f"match='{v['matched']}' reason={v['reason']}"
            )
    else:
        logger.info(f"[ClaimValidator] Script clean — no violations found (language={language})")

    is_clean = block_count == 0
    return is_clean, violations


# ──────────────────────────────────────────────
# Auto-Rewrite (Gemini)
# ──────────────────────────────────────────────

def rewrite_violations(
    script: dict,
    violations: list[dict],
    api_key: str,
    language: str = "khmer",
) -> dict:
    """
    For each segment with a "block" violation, call Gemini to rewrite
    ONLY that segment's voiceover_text / on_screen_text — removing
    the absolute claim while keeping the persuasive tone.

    Non-violated segments are untouched.

    Parameters
    ----------
    script     : Original script dict.
    violations : Output from validate_script().
    api_key    : Gemini API key.
    language   : Language for the rewrite instruction.

    Returns
    -------
    dict — Script dict with offending segments rewritten in-place.
    """
    import copy
    from google import genai
    from google.genai import types

    block_violations = [v for v in violations if v["severity"] == "block"]
    if not block_violations:
        return script

    # Collect segment IDs that need rewriting
    seg_ids_to_fix: set = {v["segment_id"] for v in block_violations}
    logger.info(f"[ClaimValidator] Rewriting {len(seg_ids_to_fix)} segments via Gemini...")

    client    = get_pooled_client(api_key=api_key)
    new_script = copy.deepcopy(script)

    all_segs  = new_script.get("script_segments", []) + new_script.get("hook_variants", [])

    for seg in all_segs:
        seg_id = seg.get("id") or seg.get("variant_id")
        if seg_id not in seg_ids_to_fix:
            continue

        # Collect which violations apply to this segment
        seg_viols = [v for v in block_violations if v["segment_id"] == seg_id]
        violation_summary = "; ".join(
            f"field='{v['field']}' matched='{v['matched']}' reason={v['reason']}"
            for v in seg_viols
        )

        prompt = f"""You are a professional ad copywriter. Rewrite the following ad script segment to remove absolute or medical claims while keeping the persuasive, energetic tone.

Language: {language}
Original voiceover_text: {seg.get('voiceover_text', '')}
Original on_screen_text: {seg.get('on_screen_text', '')}
Violations to fix: {violation_summary}

Rules:
- Do NOT use guaranteed, 100%, miracle, cure, no side effects, or any absolute claims.
- Keep the same emotional tone and approximate length.
- Return ONLY a JSON object: {{"voiceover_text": "...", "on_screen_text": "..."}}
"""

        fallback_models = [
            os.getenv("GEMINI_MODEL", "").strip(),
            "gemini-3.6-flash",
            "gemini-2.0-flash",
        ]

        for model in [m for m in fallback_models if m]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.5,
                        max_output_tokens=512,
                        response_mime_type="application/json",
                    ),
                )
                raw = re.sub(r"```[a-z]*\n?", "", response.text.strip()).strip()
                rewritten = json.loads(raw)
                seg["voiceover_text"] = rewritten.get("voiceover_text", seg["voiceover_text"])
                seg["on_screen_text"] = rewritten.get("on_screen_text", seg["on_screen_text"])
                logger.info(f"[ClaimValidator] Segment {seg_id} rewritten successfully.")
                break
            except Exception as exc:
                logger.debug(f"[ClaimValidator] Rewrite model {model} failed: {exc}")
                continue
        else:
            logger.warning(
                f"[ClaimValidator] Could not rewrite segment {seg_id} — all models failed. "
                "Leaving original text (pipeline will continue with warn)."
            )

    return new_script


# ──────────────────────────────────────────────
# Combined Helper: Validate + Auto-Rewrite
# ──────────────────────────────────────────────

def validate_and_clean(
    script: dict,
    api_key: Optional[str] = None,
    language: str = "khmer",
    auto_rewrite: bool = True,
) -> tuple[dict, list[dict]]:
    """
    Convenience function: validate the script and optionally auto-rewrite violations.

    Parameters
    ----------
    script       : Script dict from creative director.
    api_key      : Gemini API key (required if auto_rewrite=True).
    language     : Language hint.
    auto_rewrite : If True and violations found, call rewrite_violations().

    Returns
    -------
    (cleaned_script: dict, violations: list[dict])
    """
    is_clean, violations = validate_script(script, language=language)

    if not is_clean and auto_rewrite:
        if not api_key:
            logger.warning(
                "[ClaimValidator] auto_rewrite=True but no api_key provided. "
                "Skipping rewrite — script may contain policy violations."
            )
            return script, violations

        script = rewrite_violations(script, violations, api_key=api_key, language=language)
        # Re-validate after rewrite
        is_clean_2, violations_2 = validate_script(script, language=language)
        if not is_clean_2:
            logger.warning(
                f"[ClaimValidator] {sum(1 for v in violations_2 if v['severity'] == 'block')} "
                "block violations remain after rewrite. Proceeding with caution."
            )
        return script, violations_2

    return script, violations
