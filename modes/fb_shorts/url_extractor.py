"""
====================================================================
  Pipeline v3.0
  File: modes/fb_shorts/url_extractor.py — Ad Text from URL
====================================================================

Trich xuat noi dung quang cao tu URL (Facebook post, website, v.v.)
Su dung: BeautifulSoup + requests
"""

import logging
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,km-KH;q=0.8,en;q=0.7",
}

# Tags to remove before extracting text
JUNK_TAGS = [
    "script", "style", "nav", "footer", "header",
    "aside", "form", "button", "input", "select",
    "iframe", "noscript", "svg", "img",
]

# Selectors to try for main content (in priority order)
CONTENT_SELECTORS = [
    "article",
    "[role='main']",
    ".post-content",
    ".entry-content",
    ".article-body",
    "main",
    "#content",
    ".content",
]


def extract_ad_text(url: str, max_chars: int = 2000) -> str:
    """
    Fetch URL and extract the main text content.

    Returns cleaned plain text (up to max_chars characters).
    Raises ValueError if extraction fails.
    """
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError(f"Invalid URL: {url!r}")

    logger.info(f"[Extractor] Fetching: {_short(url)}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        raise ValueError(f"Cannot fetch URL ({_short(url)}): {exc}") from exc

    soup = BeautifulSoup(resp.content, "lxml")

    # Remove junk
    for tag in JUNK_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # Remove hidden elements
    for el in soup.find_all(style=re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden")):
        el.decompose()

    # Try to find main content block
    text = ""
    for sel in CONTENT_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 100:
                break

    # Fallback: body
    if len(text) < 100:
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)

    # Clean up whitespace
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)

    if not text:
        raise ValueError(f"No text content found at {_short(url)}")

    # Truncate
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    logger.info(f"[Extractor] Extracted {len(text)} chars from {_short(url)}")
    return text


def extract_key_selling_points(raw_text: str, max_points: int = 5) -> list[str]:
    """
    Simple heuristic to extract key selling points from raw ad text.
    Looks for bullet-like sentences, short impactful phrases.
    """
    sentences = re.split(r"[.!?।。\n]", raw_text)
    points = []

    for s in sentences:
        s = s.strip()
        if 10 < len(s) < 120:
            # Prefer sentences with marketing keywords
            score = 0
            keywords = [
                "mien phi", "giam gia", "khuyen mai", "tang kem",
                "chat luong", "bao hanh", "nhanh", "tiet kiem",
                # Khmer-like
                "ឥតគិតថ្លៃ", "ថ្លៃ", "ល្អ", "ផ្ញើ",
                # Common marketing
                "free", "discount", "quality", "fast", "save",
                "guarantee", "best", "new", "limited",
            ]
            for kw in keywords:
                if kw.lower() in s.lower():
                    score += 1
            if score > 0 or len(points) < max_points // 2:
                points.append(s)
        if len(points) >= max_points:
            break

    return points[:max_points]


def _short(url: str, n: int = 60) -> str:
    return url if len(url) <= n else url[:n] + "..."
