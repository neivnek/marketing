"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/auto/scraper.py — Meta Ads Scraper + yt-dlp Downloader
====================================================================
"""

import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

# ── Meta Ads Library ──────────────────────────────────────────────
META_ADS_BASE = "https://www.facebook.com/ads/library/"


def _build_search_url(keyword: str, country: str = "KH") -> str:
    """Build the Meta Ads Library search URL for a given keyword."""
    params = {
        "active_status": "all",
        "ad_type":       "all",
        "country":       country,
        "q":             keyword,
        "search_type":   "keyword_unordered",
        "media_type":    "video",
    }
    return META_ADS_BASE + "?" + urlencode(params)


def _extract_video_urls(page: Page, max_results: int = 1) -> list[str]:
    """
    Scrape video src URLs from Meta Ads Library result cards.

    Meta Ads Library is public (no login). We look for <video> tags
    inside ad cards after letting the page render.
    """
    urls: list[str] = []

    # Wait for ad cards to appear
    try:
        page.wait_for_selector(
            "div[data-testid='collection-ad-card'], div._8n8k, div[class*='_7jyg']",
            timeout=20_000,
        )
    except PWTimeout:
        logger.warning("Ads Library: card selector not found — trying generic video tag.")

    # Scroll to trigger lazy loading
    for _ in range(3):
        page.mouse.wheel(0, 1200)
        time.sleep(1.5)

    # Extract <video> src attributes
    videos = page.query_selector_all("video")
    for v in videos:
        src = v.get_attribute("src") or ""
        if src and src.startswith("http") and src not in urls:
            urls.append(src)
            if len(urls) >= max_results:
                break

    # Fallback: look for fbcdn.net video links in page source
    if not urls:
        content = page.content()
        found = re.findall(r'https://[^"\']+\.(?:mp4|mov)[^"\']*', content)
        for url in found:
            if url not in urls:
                urls.append(url)
                if len(urls) >= max_results:
                    break

    return urls


def scrape_meta_ads(keyword: str, output_dir: str, max_results: int = 1) -> list[str]:
    """
    Search Meta Ads Library for videos matching the keyword,
    then download them with yt-dlp.

    Parameters
    ----------
    keyword     : Search term (e.g., "shampoo cambodia").
    output_dir  : Directory to save downloaded videos.
    max_results : Maximum number of videos to download (default 1).

    Returns
    -------
    list[str] — Absolute paths of downloaded video files.
    """
    os.makedirs(output_dir, exist_ok=True)
    search_url = _build_search_url(keyword)
    logger.info(f"🔍  Meta Ads scrape: '{keyword}'")
    logger.info(f"    URL: {search_url}")

    video_urls: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            page.goto(search_url, wait_until="networkidle", timeout=30_000)
            video_urls = _extract_video_urls(page, max_results)
        except Exception as e:
            logger.error(f"Playwright error: {e}")
        finally:
            browser.close()

    if not video_urls:
        raise RuntimeError(
            f"No video ads found for keyword '{keyword}' on Meta Ads Library. "
            "Try a different keyword or switch to Manual Override mode."
        )

    logger.info(f"    Found {len(video_urls)} video URL(s). Downloading...")
    downloaded = []
    
    # Safe slug for filename
    safe_kw = re.sub(r'[^a-zA-Z0-9]+', '_', keyword).strip('_')
    
    for i, url in enumerate(video_urls[:max_results]):
        filename = f"{safe_kw}_ref_ad_{i:02d}.mp4" if safe_kw else f"ref_ad_{i:02d}.mp4"
        out_path = download_video(url, output_dir, filename=filename)
        downloaded.append(out_path)

    return downloaded


def download_video(url: str, output_dir: str, filename: str = "ref_video.mp4") -> str:
    """
    Download a video from any yt-dlp-supported URL (Facebook, YouTube, etc.)
    or a direct HTTP video URL.

    Parameters
    ----------
    url        : Video page URL or direct video stream URL.
    output_dir : Directory to save the file.
    filename   : Output filename.

    Returns
    -------
    str — Absolute path to the downloaded file.
    """
    import yt_dlp  # lazy import to avoid startup cost

    os.makedirs(output_dir, exist_ok=True)
    out_path = str(Path(output_dir) / filename)

    # yt-dlp options — best video quality, no playlist
    ydl_opts = {
        "outtmpl":        out_path.replace(".mp4", ".%(ext)s"),
        "format":         "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet":          False,
        "no_warnings":    False,
        "noplaylist":     True,
        "retries":        3,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # yt-dlp may add extension automatically — find the actual file
        for ext in ["mp4", "mkv", "webm", "mov"]:
            candidate = out_path.replace(".mp4", f".{ext}")
            if os.path.isfile(candidate):
                if candidate != out_path:
                    os.rename(candidate, out_path)
                break
    except Exception as e:
        # Fallback: direct HTTP download for bare video URLs
        logger.warning(f"yt-dlp failed ({e}), trying direct download...")
        import requests
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    if not os.path.isfile(out_path):
        raise RuntimeError(f"Download failed for URL: {url}")

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    logger.info(f"    ✓ Downloaded: {out_path} ({size_mb:.1f} MB)")
    return out_path
