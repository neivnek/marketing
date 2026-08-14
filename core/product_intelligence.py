"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/product_intelligence.py — Product Intelligence Module
====================================================================

Runs BEFORE creative_director.py (Mode 7 Step 0).
4 sub-steps:

  Step 0a — identify_product_from_image()
      Gemini multimodal (vision only, no search tool).
      Extracts: product name guess, brand, category, OCR text,
      visual description, confidence.

  Step 0b — research_product_web()
      Gemini with google_search grounding (Gemini 3.x only).
      Returns benefits, usage, ingredients, customer praise/complaints,
      pain points, and source URLs for traceability.

  Step 0c — search_related_videos()
      YouTube Data API v3 search.list.
      ALWAYS-OPTIONAL: skipped gracefully when YOUTUBE_API_KEY absent.

  Step 0d — meta_competitor_keyword()
      Returns keyword string for auto/scraper.py — caller decides
      whether to actually run scraper.

SQLite cache: temp/product_research_cache.db
Key: SHA256(name_guess + category), TTL 30 days.
"""

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)


def _strip_code_fence(text: str) -> str:
    """
    Gỡ ```json ... ``` quanh output của LLM.

    KHÔNG dùng str.strip("```json") — strip() nhận một TẬP KÝ TỰ, nên nó gặm
    mọi ký tự backtick/j/s/o/n ở hai đầu chuỗi chứ không chỉ hậu tố mong muốn.
    """
    return re.sub(r"^```[a-z]*\n?|```$", "", (text or "").strip()).strip()


CACHE_TTL_DAYS = 30
# Gemini 3.x model prefixes that support grounding
_GROUNDING_SUPPORTED_PREFIXES = ("gemini-3.", "gemini-flash-latest")


# ── Dataclasses ───────────────────────────────────────────────────

@dataclass
class ProductIdentity:
    name_guess:          str
    brand_guess:         str   = ""
    category:            str   = ""
    ocr_text:            str   = ""
    visual_description:  str   = ""
    confidence:          float = 0.0   # 0.0-1.0 — low means fallback to user-supplied name


@dataclass
class ProductResearch:
    benefits:               list  = field(default_factory=list)   # list[str]
    usage_instructions:     str   = ""
    ingredient_highlights:  list  = field(default_factory=list)   # list[str]
    common_praise:          list  = field(default_factory=list)   # list[str]
    common_complaints:      list  = field(default_factory=list)   # list[str]
    suggested_pain_points:  list  = field(default_factory=list)   # list[str]
    source_urls:            list  = field(default_factory=list)   # list[str] — grounding sources
    research_skipped:       bool  = False   # True when no search results found
    warning_message:        str   = ""


@dataclass
class VideoRef:
    title:          str
    video_id:       str
    channel:        str  = ""
    view_count:     int  = 0
    url:            str  = ""
    thumbnail_url:  str  = ""


# ── SQLite Cache ──────────────────────────────────────────────────

def _get_cache_db(temp_dir: str) -> sqlite3.Connection:
    os.makedirs(temp_dir, exist_ok=True)
    db_path = os.path.join(temp_dir, "product_research_cache.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_cache (
            cache_key    TEXT PRIMARY KEY,
            product_name TEXT NOT NULL DEFAULT '',
            category     TEXT NOT NULL DEFAULT '',
            identity_json TEXT NOT NULL,
            research_json TEXT NOT NULL,
            cached_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _build_cache_key(name_guess: str, category: str) -> str:
    raw = f"{name_guess.strip().lower()}::{category.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _load_cache(
    conn: sqlite3.Connection,
    cache_key: str,
) -> Optional[tuple[ProductIdentity, ProductResearch]]:
    cutoff = (datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)).isoformat()
    row = conn.execute(
        "SELECT identity_json, research_json FROM research_cache "
        "WHERE cache_key=? AND cached_at > ?",
        (cache_key, cutoff),
    ).fetchone()
    if not row:
        return None
    try:
        ident_dict    = json.loads(row[0])
        research_dict = json.loads(row[1])
        return (
            ProductIdentity(**ident_dict),
            ProductResearch(**research_dict),
        )
    except Exception as exc:
        logger.warning(f"[ProductIntel] Cache parse error: {exc}")
        return None


def _save_cache(
    conn: sqlite3.Connection,
    cache_key: str,
    identity: ProductIdentity,
    research: ProductResearch,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO research_cache
           (cache_key, product_name, category, identity_json, research_json, cached_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            cache_key,
            identity.name_guess,
            identity.category,
            json.dumps(asdict(identity), ensure_ascii=False),
            json.dumps(asdict(research), ensure_ascii=False),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()


# ── Gemini Client Helpers ─────────────────────────────────────────

DEFAULT_MODELS = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash",
]


def _model_supports_grounding(model: str) -> bool:
    """Check whether this model supports google_search grounding."""
    return any(model.startswith(p) for p in _GROUNDING_SUPPORTED_PREFIXES)


def _generate_with_fallback(client_unused, contents, config=None, tools=None):
    """
    Sử dụng gemini_pool để tự động luân phiên API Key và Model.
    """
    from google.genai import types
    from core.gemini_pool import generate_content_with_pool
    
    # Only attach grounding tools for Gemini 1.5/2.0 if supported, though currently grounding is mostly for pro
    effective_tools = tools

    if config:
        if effective_tools:
            config.tools = effective_tools
    elif effective_tools:
        config = types.GenerateContentConfig(tools=effective_tools)
        
    return generate_content_with_pool(prompt_contents=contents, config=config)


# ── Step 0a: Identify Product from Image ─────────────────────────

def identify_product_from_image(
    image_path:   str,
    api_key:      str,
    product_name: str = "",   # user-supplied override; if non-empty, raises confidence
) -> ProductIdentity:
    """
    Use Gemini multimodal (vision only, NO search) to identify the product.

    Parameters
    ----------
    image_path   : Path to product image.
    api_key      : GEMINI_API_KEY.
    product_name : User-supplied name (overrides Gemini guess if provided).

    Returns
    -------
    ProductIdentity dataclass.
    """
    from google import genai
    from google.genai import types

    client = get_pooled_client(api_key=api_key)

    prompt = (
        "You are an expert E-Commerce Marketing Analyst and Smart OCR AI. "
        "Analyze this product image or advertisement banner in extremely high detail. "
        "Your goal is to extract everything needed to write a high-converting video ad script.\n"
        "1. Identify the Product Name and Brand Name.\n"
        "2. Identify the Product Category (e.g., Stain Removal Cream, Skincare, Tech...)\n"
        "3. Multi-lingual OCR: Read ALL text visible on the image, including English, Chinese, Khmer, etc. Translate key foreign phrases to English/Khmer logically.\n"
        "4. Before & After Analysis: If the image shows a 'Before/After', explicitly describe the problem (e.g., dirty shirt) and the result (e.g., clean white shirt).\n"
        "5. Unique Selling Points (USPs): Extract all numbers, claims, and badges (e.g., '3x', '100%', 'free shipping', icons).\n"
        "6. Visual Description: Describe the packaging and color scheme.\n"
        "7. Confidence level (0.0-1.0).\n\n"
        "Put the Multi-lingual OCR, Before & After Analysis, and USPs combined into the 'ocr_text' field.\n\n"
        "Return ONLY a JSON object with these exact keys:\n"
        '{"name_guess": "...", "brand_guess": "...", "category": "...", '
        '"ocr_text": "...", "visual_description": "...", "confidence": 0.9}'
    )

    contents = [prompt]
    if image_path and os.path.isfile(image_path):
        import mimetypes
        mime, _ = mimetypes.guess_type(image_path)
        mime = mime or "image/jpeg"
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        img_part = types.Part.from_bytes(data=img_bytes, mime_type=mime)
        contents = [img_part, prompt]

    try:
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]
        
        response = _generate_with_fallback(
            client, contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=512,
                response_mime_type="application/json",
                safety_settings=safety_settings,
            ),
        )
        raw = _strip_code_fence(response.text)
        data = json.loads(raw)
        identity = ProductIdentity(
            name_guess         = data.get("name_guess", "")[:120],
            brand_guess        = data.get("brand_guess", "")[:80],
            category           = data.get("category", "")[:80],
            ocr_text           = data.get("ocr_text", "")[:500],
            visual_description = data.get("visual_description", "")[:300],
            confidence         = float(data.get("confidence", 0.5)),
        )
    except Exception as exc:
        logger.warning(f"[ProductIntel] Identify step failed: {exc}. Using fallback identity.")
        identity = ProductIdentity(
            name_guess=product_name or "product",
            category="general",
            confidence=0.3,
        )

    # If user provided name and Gemini confidence is low, override
    if product_name.strip() and identity.confidence < 0.5:
        logger.info(
            f"[ProductIntel] Low confidence ({identity.confidence:.2f}) — "
            f"using user-supplied name: '{product_name}'"
        )
        identity.name_guess = product_name.strip()
        identity.confidence = 0.7  # user-supplied = moderate-high confidence

    logger.info(
        f"[ProductIntel] Identity: '{identity.name_guess}' "
        f"({identity.category}) confidence={identity.confidence:.2f}"
    )
    return identity


# ── Step 0b: Research Product Web (Grounding) ─────────────────────

def research_product_web(
    identity: ProductIdentity,
    api_key:  str,
    market:   str = "Cambodia",
) -> ProductResearch:
    """
    Use Gemini with Google Search grounding to research the product.

    Grounding is activated only for Gemini 3.x models.
    Falls back to non-grounded generation if model doesn't support it.
    Always saves source_urls from grounding_metadata for traceability.

    Returns ProductResearch with research_skipped=True if no results found.
    """
    from google import genai
    from google.genai import types

    client  = get_pooled_client(api_key=api_key)
    name    = identity.name_guess
    category = identity.category or "consumer product"

    prompt = (
        f"You are an expert marketing copywriter and product researcher. "
        f"Research the following product for the {market} market:\n\n"
        f"Product name: {name}\n"
        f"Category: {category}\n"
        f"OCR text from label: {identity.ocr_text or 'N/A'}\n\n"
        "Search for and compile real information about this product:\n"
        "1. Key benefits and claims (what the product promises)\n"
        "2. Usage instructions (how to use it)\n"
        "3. Notable ingredients or key components\n"
        "4. REAL customer reviews and praise (use their exact language)\n"
        "5. Common complaints or pain points this product solves\n"
        "6. Suggested marketing pain points for advertising\n\n"
        "IMPORTANT: Use real customer language from reviews, not generic marketing speak. "
        "If the product is niche or local and you can't find specific reviews, "
        "still provide your best research based on the product category.\n\n"
        "Return ONLY this JSON (no markdown fences):\n"
        "{\n"
        '  "benefits": ["benefit1", "benefit2"],\n'
        '  "usage_instructions": "how to use...",\n'
        '  "ingredient_highlights": ["ingredient1"],\n'
        '  "common_praise": ["customers say...", "love that..."],\n'
        '  "common_complaints": ["wish it had...", "the only issue..."],\n'
        '  "suggested_pain_points": ["pain_point1", "pain_point2"]\n'
        "}"
    )

    # Google Search grounding tool
    grounding_tool = {"google_search": {}}

    try:
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]
        
        response = _generate_with_fallback(
            client,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1500,
                response_mime_type="application/json",
                safety_settings=safety_settings,
            ),
            tools=[grounding_tool],
        )

        raw = _strip_code_fence(response.text)
        data = json.loads(raw)

        # Extract grounding source URLs for traceability (Rule 13)
        source_urls = []
        try:
            meta = getattr(response, "candidates", [{}])
            if meta:
                grounding_meta = getattr(meta[0], "grounding_metadata", None)
                if grounding_meta:
                    for chunk in getattr(grounding_meta, "grounding_chunks", []):
                        web = getattr(chunk, "web", None)
                        if web and getattr(web, "uri", None):
                            source_urls.append(web.uri)
        except Exception:
            pass   # grounding metadata extraction is best-effort

        research = ProductResearch(
            benefits              = data.get("benefits", [])[:8],
            usage_instructions    = data.get("usage_instructions", "")[:400],
            ingredient_highlights = data.get("ingredient_highlights", [])[:6],
            common_praise         = data.get("common_praise", [])[:6],
            common_complaints     = data.get("common_complaints", [])[:4],
            suggested_pain_points = data.get("suggested_pain_points", [])[:5],
            source_urls           = source_urls,
        )

        if source_urls:
            logger.info(f"[ProductIntel] Research grounded on {len(source_urls)} source(s)")
        else:
            logger.info("[ProductIntel] Research complete (non-grounded or no sources returned)")

        if not research.benefits and not research.common_praise:
            research.research_skipped = True
            research.warning_message  = (
                f"No web results found for '{name}'. "
                "creative_director will use image + name only."
            )
            logger.warning(f"[ProductIntel] {research.warning_message}")

        return research

    except Exception as exc:
        logger.warning(f"[ProductIntel] Web research failed: {exc}. Returning empty research.")
        return ProductResearch(
            research_skipped=True,
            warning_message=f"Research failed: {exc!s:.100}",
        )


# ── Step 0c: YouTube Related Videos ──────────────────────────────

def search_related_videos(
    query:       str,
    api_key:     str,
    max_results: int = 5,
) -> list[VideoRef]:
    """
    Search YouTube Data API v3 for videos related to the product.

    ALWAYS-OPTIONAL: returns [] without error if api_key is absent.
    Uses 100 units per call (search.list quota cost).

    Parameters
    ----------
    query      : Search query, e.g. "hair gel Cambodia review".
    api_key    : YOUTUBE_API_KEY (from .env).
    max_results: Number of results (default 5, max 10).

    Returns
    -------
    list[VideoRef] — empty list if API key missing or request fails.
    """
    if not api_key:
        logger.debug("[ProductIntel] No YOUTUBE_API_KEY — skipping video search (always-optional).")
        return []

    import requests

    params = {
        "key":        api_key,
        "q":          query,
        "part":       "snippet",
        "type":       "video",
        "maxResults": min(max_results, 10),
        "relevanceLanguage": "km",   # Khmer-preferred, not enforced
        "regionCode": "KH",
    }

    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as exc:
        logger.warning(f"[ProductIntel] YouTube search failed (non-blocking): {exc}")
        return []

    refs = []
    for item in items:
        vid_id  = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        if not vid_id:
            continue
        refs.append(VideoRef(
            title         = snippet.get("title", ""),
            video_id      = vid_id,
            channel       = snippet.get("channelTitle", ""),
            url           = f"https://www.youtube.com/watch?v={vid_id}",
            thumbnail_url = snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
        ))

    logger.info(f"[ProductIntel] YouTube: {len(refs)} video(s) found for '{query}'")
    return refs


# ── Step 0d: Meta Competitor Keyword ─────────────────────────────

def build_meta_search_keyword(identity: ProductIdentity) -> str:
    """
    Build an auto-generated keyword for the Meta Ads Library scraper.
    Caller (pro_editor_pipeline) decides whether to actually run scraper.
    """
    if identity.name_guess and identity.name_guess != "product":
        keyword = f"{identity.name_guess} cambodia"
    elif identity.category:
        keyword = f"{identity.category} cambodia"
    else:
        keyword = "product cambodia"
    logger.info(f"[ProductIntel] Auto Meta keyword: '{keyword}'")
    return keyword


# ── Public API — run_product_intelligence ────────────────────────

def run_product_intelligence(
    image_path:             str,
    api_key:                str,
    product_name:           str  = "",
    temp_dir:               str  = "temp",
    force_refresh:          bool = False,
    youtube_api_key:        str  = "",
    market:                 str  = "Cambodia",
) -> tuple[ProductIdentity, ProductResearch, list[VideoRef]]:
    """
    Run all 4 product intelligence steps with caching.

    Parameters
    ----------
    image_path      : Path to product image.
    api_key         : GEMINI_API_KEY.
    product_name    : User-supplied name (boosts confidence if provided).
    temp_dir        : Temp directory for SQLite cache.
    force_refresh   : Ignore cache and re-run all steps.
    youtube_api_key : YouTube Data API key (optional).
    market          : Target market for research context.

    Returns
    -------
    (ProductIdentity, ProductResearch, list[VideoRef])
    VideoRef list is empty when YOUTUBE_API_KEY absent.
    """
    conn = _get_cache_db(temp_dir)

    # Step 0a — always run (fast, vision only)
    logger.info("[ProductIntel Step 0a] Identifying product from image...")
    identity = identify_product_from_image(image_path, api_key, product_name)

    cache_key = _build_cache_key(identity.name_guess, identity.category)

    # Check cache (skip 0b/0c if hit and not force_refresh)
    if not force_refresh:
        cached = _load_cache(conn, cache_key)
        if cached:
            logger.info(
                f"[ProductIntel] Cache HIT for '{identity.name_guess}' "
                f"— skipping web research (TTL {CACHE_TTL_DAYS} days)."
            )
            conn.close()
            cached_identity, cached_research = cached
            # Still run YouTube search (no-cost read, not cached — titles change frequently)
            yt_query = f"{identity.name_guess} review"
            videos = search_related_videos(yt_query, youtube_api_key)
            return cached_identity, cached_research, videos

    # Step 0b — web research
    logger.info(f"[ProductIntel Step 0b] Researching '{identity.name_guess}' on the web...")
    research = research_product_web(identity, api_key, market)

    # Save to cache (even if research_skipped — avoids re-querying for unknown products)
    _save_cache(conn, cache_key, identity, research)
    conn.close()

    # Step 0c — YouTube (always-optional)
    yt_query = f"{identity.name_guess} {identity.category} review"
    logger.info(f"[ProductIntel Step 0c] YouTube search: '{yt_query}'")
    videos = search_related_videos(yt_query, youtube_api_key)

    # Step 0d — Meta keyword (returned implicitly via identity)
    build_meta_search_keyword(identity)

    logger.info(
        f"[ProductIntel] Complete — "
        f"{len(research.benefits)} benefits, "
        f"{len(research.common_praise)} praise quotes, "
        f"{len(videos)} YT videos"
    )
    return identity, research, videos
