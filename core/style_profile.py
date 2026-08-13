"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/style_profile.py — User Video Style Profile System
====================================================================

Allows users to upload 1-5 sample videos that reflect their personal
video-making style. Gemini Vision analyzes them and extracts a
"Style DNA" JSON profile that is persisted locally and injected into
all auto-mode Gemini prompts.

Storage: assets/style_profiles/<profile_id>.json
         No external DB — plain JSON, instantly portable.

Zero-cost compliance:
  - Only Gemini Flash free tier is used for analysis
  - Videos are sent as inline bytes (no File API upload needed)
  - All storage is local JSON

Style DNA schema:
  profile_id, created_at, analyzed_videos, style_dna{...},
  gemini_style_notes (freeform Gemini prompt injection string)
====================================================================
"""

import json
import logging
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROFILE_DIR_DEFAULT = "assets/style_profiles"
MAX_VIDEO_SIZE_MB = 50  # skip videos larger than this to avoid API limits

# ── Gemini helpers ────────────────────────────────────────────────

_DEFAULT_MODELS = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
]


def _generate_with_fallback(client, contents, config=None):
    """Standard Gemini model fallback chain."""
    from google.genai import types as gtypes
    models = [m for m in _DEFAULT_MODELS if m]
    last_exc = None
    for model in models:
        try:
            kwargs = {"model": model, "contents": contents}
            if config:
                kwargs["config"] = config
            logger.info(f"[StyleProfile] Trying Gemini model: {model}")
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            err = str(exc).lower()
            if any(k in err for k in ["404", "not_found", "no longer", "not supported"]):
                logger.warning(f"  Model '{model}' unavailable — trying next...")
                last_exc = exc
                continue
            raise exc
    if last_exc:
        raise last_exc


def _make_video_part(video_path: str):
    """Read a local video file and return a Gemini Part object. Returns None if too large."""
    from google.genai import types as gtypes
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        logger.warning(
            f"[StyleProfile] Video '{Path(video_path).name}' is {size_mb:.1f}MB "
            f"(> {MAX_VIDEO_SIZE_MB}MB limit) — skipping."
        )
        return None
    mime, _ = mimetypes.guess_type(video_path)
    if mime is None:
        mime = "video/mp4"
    with open(video_path, "rb") as f:
        data = f.read()
    return gtypes.Part.from_bytes(data=data, mime_type=mime)


# ── Analysis Prompt ───────────────────────────────────────────────

_ANALYSIS_PROMPT = """\
You are an expert video marketing analyst. Analyze the provided sample video(s) and extract the creator's personal video-making "Style DNA".

Carefully observe and extract:
1. **avg_segment_duration_sec** (float): Average duration per scene/cut in seconds
2. **pacing** (string): "slow" | "normal" | "fast" based on cut frequency
3. **hook_style** (string): "question" | "shock_fact" | "relatable_scenario" | "before_after" | "product_reveal"
4. **dominant_emotion** (string): The main emotional tone: "calm" | "frustrated" | "excited" | "urgent" | "curious" | "confident"
5. **narrative_structure** (string): "PAS" (Problem-Agitate-Solution) | "AIDA" | "storytelling" | "listicle" | "review"
6. **color_preset** (string): "neutral" | "warm" | "cool" | "cinematic" | "vibrant" | "dark" | "pastel"
7. **caption_style** (string): "classic_box" | "outline_bold" | "karaoke_highlight" | "minimal_clean" | "none"
8. **music_energy** (string): "calm" | "upbeat" | "urgent"
9. **avg_cuts_per_10sec** (float): How many cuts happen per 10 seconds of video
10. **uses_broll** (boolean): Does the creator intercut B-roll footage between main shots?
11. **ugc_authenticity_level** (string): "low" (polished/professional) | "medium" | "high" (raw/UGC feel)
12. **cta_style** (string): "soft" (gentle suggestion) | "direct" (clear call-to-action) | "countdown" (urgency)
13. **language_detected** (string): Primary language spoken in the video (e.g. "vietnamese", "khmer", "english")
14. **style_summary** (string): A 1-2 sentence description of the creator's style in Vietnamese, starting with "Phong cách:"

Return ONLY a valid JSON object (no markdown fences) with EXACTLY these keys:
{
  "avg_segment_duration_sec": 3.5,
  "pacing": "fast",
  "hook_style": "question",
  "dominant_emotion": "excited",
  "narrative_structure": "PAS",
  "color_preset": "vibrant",
  "caption_style": "karaoke_highlight",
  "music_energy": "upbeat",
  "avg_cuts_per_10sec": 4.2,
  "uses_broll": true,
  "ugc_authenticity_level": "high",
  "cta_style": "direct",
  "language_detected": "vietnamese",
  "style_summary": "Phong cách: Video nhanh, câu hỏi gây tò mò ở đầu, cắt 3-4 giây/cảnh, màu rực rỡ và CTA thẳng thắn."
}
"""

_STYLE_NOTES_PROMPT = """\
Based on the Style DNA you extracted, write a SHORT instruction paragraph (in English, 3-5 sentences) 
that can be directly prepended to a Gemini creative script generation prompt to make the output match 
this creator's style. Be specific about pacing, hook approach, emotional arc, and CTA style.
Return ONLY the instruction paragraph, no JSON, no labels.
"""


# ── Public API ────────────────────────────────────────────────────

def analyze_style_from_videos(
    video_paths: list[str],
    api_key: str,
    profile_id: str = "",
    profile_name: str = "",
    profile_dir: str = PROFILE_DIR_DEFAULT,
) -> dict:
    """
    Analyze 1-5 sample videos with Gemini Vision and extract Style DNA.
    Saves the profile JSON to assets/style_profiles/<profile_id>.json.

    Parameters
    ----------
    video_paths  : List of local video file paths (max 5 recommended).
    api_key      : GEMINI_API_KEY.
    profile_id   : Unique ID string. Auto-generated from timestamp if empty.
    profile_name : Human-readable display name (e.g. "Phong cách TikTok 2024").
    profile_dir  : Directory to save profile JSON files.

    Returns
    -------
    dict — Full profile dict including style_dna and gemini_style_notes.
           Also written to disk as JSON.
    """
    from google import genai
    from google.genai import types as gtypes

    if not video_paths:
        raise ValueError("At least one video path is required for style analysis.")

    os.makedirs(profile_dir, exist_ok=True)

    # Auto-generate profile_id from timestamp
    if not profile_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        profile_id = f"style_{ts}"

    if not profile_name:
        profile_name = f"Style Profile {profile_id}"

    client = genai.Client(api_key=api_key)

    # Build contents: [video_part_1, video_part_2, ..., prompt]
    logger.info(
        f"[StyleProfile] Analyzing {len(video_paths)} video(s) for profile '{profile_id}'..."
    )
    contents = []
    valid_videos = []
    for vp in video_paths[:5]:  # Cap at 5
        if not os.path.isfile(vp):
            logger.warning(f"[StyleProfile] Video not found, skipping: {vp}")
            continue
        part = _make_video_part(vp)
        if part:
            contents.append(part)
            valid_videos.append(vp)

    if not contents:
        raise FileNotFoundError("No valid video files could be loaded for analysis.")

    contents.append(_ANALYSIS_PROMPT)

    # Step 1: Extract Style DNA JSON
    logger.info("[StyleProfile] Step 1/2: Extracting Style DNA...")
    style_dna: dict = {}
    try:
        response = _generate_with_fallback(
            client,
            contents,
            config=gtypes.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=800,
                response_mime_type="application/json",
            ),
        )
        raw = response.text.strip().strip("```json").strip("```").strip()
        style_dna = json.loads(raw)
        logger.info(f"[StyleProfile] Style DNA extracted: pacing={style_dna.get('pacing')}, "
                    f"hook={style_dna.get('hook_style')}, "
                    f"lang={style_dna.get('language_detected')}")
    except Exception as exc:
        logger.warning(f"[StyleProfile] Style DNA extraction failed: {exc}. Using defaults.")
        style_dna = _default_style_dna()

    # Step 2: Generate freeform style notes for prompt injection
    logger.info("[StyleProfile] Step 2/2: Generating style notes for prompt injection...")
    gemini_style_notes = ""
    try:
        notes_contents = list(contents[:-1])  # re-use video parts
        notes_contents.append(
            _STYLE_NOTES_PROMPT + f"\n\nExtracted Style DNA: {json.dumps(style_dna, ensure_ascii=False)}"
        )
        notes_response = _generate_with_fallback(
            client,
            notes_contents,
            config=gtypes.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=400,
            ),
        )
        gemini_style_notes = notes_response.text.strip()
        logger.info(f"[StyleProfile] Style notes: {gemini_style_notes[:100]}...")
    except Exception as exc:
        logger.warning(f"[StyleProfile] Style notes generation failed: {exc}")
        gemini_style_notes = _default_style_notes(style_dna)

    # Assemble full profile
    profile = {
        "profile_id": profile_id,
        "profile_name": profile_name,
        "created_at": datetime.now().isoformat(),
        "analyzed_videos": [Path(v).name for v in valid_videos],
        "style_dna": style_dna,
        "gemini_style_notes": gemini_style_notes,
    }

    # Save to disk
    profile_path = os.path.join(profile_dir, f"{profile_id}.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    logger.info(f"[StyleProfile] ✓ Profile saved: {profile_path}")

    return profile


def load_style_profile(
    profile_id: str,
    profile_dir: str = PROFILE_DIR_DEFAULT,
) -> Optional[dict]:
    """
    Load a saved style profile by ID.

    Returns None if not found.
    """
    profile_path = os.path.join(profile_dir, f"{profile_id}.json")
    if not os.path.isfile(profile_path):
        logger.warning(f"[StyleProfile] Profile not found: {profile_path}")
        return None
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error(f"[StyleProfile] Failed to load profile '{profile_id}': {exc}")
        return None


def list_style_profiles(profile_dir: str = PROFILE_DIR_DEFAULT) -> list[dict]:
    """
    List all saved style profiles.

    Returns list of dicts with 'profile_id', 'profile_name', 'created_at'.
    """
    if not os.path.isdir(profile_dir):
        return []
    profiles = []
    for json_file in sorted(Path(profile_dir).glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles.append({
                "profile_id":   data.get("profile_id", json_file.stem),
                "profile_name": data.get("profile_name", json_file.stem),
                "created_at":   data.get("created_at", ""),
                "style_summary": data.get("style_dna", {}).get("style_summary", ""),
            })
        except Exception as exc:
            logger.warning(f"[StyleProfile] Could not read {json_file}: {exc}")
    return profiles


def delete_style_profile(profile_id: str, profile_dir: str = PROFILE_DIR_DEFAULT) -> bool:
    """Delete a profile JSON file. Returns True if deleted."""
    profile_path = os.path.join(profile_dir, f"{profile_id}.json")
    if os.path.isfile(profile_path):
        os.remove(profile_path)
        logger.info(f"[StyleProfile] Deleted: {profile_path}")
        return True
    return False


def build_style_injection_prompt(profile: dict) -> str:
    """
    Build a text block to inject into any Gemini script-generation prompt.
    Combines structured style_dna fields + freeform gemini_style_notes.

    Parameters
    ----------
    profile : Full profile dict as returned by load_style_profile().

    Returns
    -------
    str — Prompt injection block (prepend to existing prompts).
    """
    if not profile:
        return ""

    dna = profile.get("style_dna", {})
    notes = profile.get("gemini_style_notes", "")
    name = profile.get("profile_name", "User Style")

    injection = f"""
══════════════════════════════════════════════════
USER VIDEO STYLE PROFILE: "{name}"
══════════════════════════════════════════════════
You MUST replicate the following creative style in your output:

📐 STRUCTURE:
  - Narrative: {dna.get('narrative_structure', 'PAS')}
  - Hook style: {dna.get('hook_style', 'question')}
  - CTA style: {dna.get('cta_style', 'direct')}
  - Uses B-roll cutaways: {dna.get('uses_broll', True)}

⏱ PACING:
  - Overall pacing: {dna.get('pacing', 'fast')}
  - Avg segment duration: ~{dna.get('avg_segment_duration_sec', 3.5):.1f}s
  - Avg cuts per 10s: ~{dna.get('avg_cuts_per_10sec', 4.0):.1f}

🎭 TONE & EMOTION:
  - Dominant emotion: {dna.get('dominant_emotion', 'excited')}
  - Color/visual tone: {dna.get('color_preset', 'vibrant')}
  - UGC authenticity: {dna.get('ugc_authenticity_level', 'high')}

🎵 AUDIO:
  - Music energy: {dna.get('music_energy', 'upbeat')}

📝 STYLE NOTES:
{notes}

IMPORTANT: Do NOT default to your generic style. The output must feel
like it was created by this specific creator. Match their rhythm,
emotional arc, hook type, and CTA approach exactly.
══════════════════════════════════════════════════
"""
    return injection.strip()


# ── Defaults ──────────────────────────────────────────────────────

def _default_style_dna() -> dict:
    """Default style DNA when Gemini analysis fails."""
    return {
        "avg_segment_duration_sec": 4.0,
        "pacing": "normal",
        "hook_style": "question",
        "dominant_emotion": "excited",
        "narrative_structure": "PAS",
        "color_preset": "vibrant",
        "caption_style": "classic_box",
        "music_energy": "upbeat",
        "avg_cuts_per_10sec": 3.0,
        "uses_broll": True,
        "ugc_authenticity_level": "medium",
        "cta_style": "direct",
        "language_detected": "khmer",
        "style_summary": "Phong cách: Video quảng cáo chuẩn với hook câu hỏi, pacing bình thường và CTA trực tiếp.",
    }


def _default_style_notes(style_dna: dict) -> str:
    """Generate basic style notes from style_dna dict."""
    return (
        f"Use a {style_dna.get('pacing', 'normal')}-paced structure with approximately "
        f"{style_dna.get('avg_segment_duration_sec', 4.0):.1f}s per segment. "
        f"Open with a {style_dna.get('hook_style', 'question')}-style hook. "
        f"Maintain a {style_dna.get('dominant_emotion', 'excited')} emotional tone throughout. "
        f"Follow a {style_dna.get('narrative_structure', 'PAS')} narrative structure. "
        f"End with a {style_dna.get('cta_style', 'direct')} call-to-action."
    )
