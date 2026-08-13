"""
====================================================================
  Pipeline v3.0
  File: core/pexels_client.py — Pexels CC Video Search & Download
====================================================================

Lay API key mien phi tai: https://www.pexels.com/api/
Them vao .env: PEXELS_API_KEY=your_key_here
"""

import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
HEADERS = {"User-Agent": "KhmerAdsGenerator/3.0"}


def search_cc_videos(
    query:        str,
    api_key:      str,
    per_page:     int  = 8,
    orientation:  str  = "portrait",   # portrait = 9:16
    min_duration: int  = 3,
    max_duration: int  = 30,
) -> list[dict]:
    """
    Search Pexels for Creative Commons videos.

    Returns list of dicts:
        [{
            "id": ...,
            "duration": ...,
            "url": "https://...",   # best quality download link
            "width": ..., "height": ...
        }]
    """
    if not api_key:
        logger.warning("[Pexels] No API key — skipping search.")
        return []

    headers = {"Authorization": api_key, **HEADERS}
    params = {
        "query":       query,
        "per_page":    per_page,
        "orientation": orientation,
    }

    try:
        resp = requests.get(PEXELS_VIDEO_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error(f"[Pexels] Search failed: {exc}")
        return []

    results = []
    for video in data.get("videos", []):
        dur = video.get("duration", 0)
        if not (min_duration <= dur <= max_duration):
            continue

        # Pick best portrait file (HD preferred)
        files = sorted(
            video.get("video_files", []),
            key=lambda f: f.get("width", 0) * f.get("height", 0),
            reverse=True,
        )
        # Prefer 1080 or less to avoid huge files
        chosen = None
        for f in files:
            if f.get("width", 9999) <= 1920:
                chosen = f
                break
        if not chosen and files:
            chosen = files[-1]

        if chosen:
            results.append({
                "id":       video["id"],
                "duration": dur,
                "url":      chosen["link"],
                "width":    chosen.get("width", 0),
                "height":   chosen.get("height", 0),
            })

    logger.info(f"[Pexels] Found {len(results)} videos for '{query}'")
    return results


def download_video(url: str, output_path: str, timeout: int = 60) -> str:
    """
    Stream-download a Pexels video to output_path.
    Returns output_path on success.
    """
    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    try:
        with requests.get(url, stream=True, timeout=timeout, headers=HEADERS) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)
        size_mb = Path(output_path).stat().st_size / 1_048_576
        logger.info(f"[Pexels] Downloaded: {Path(output_path).name} ({size_mb:.1f} MB)")
        return output_path
    except Exception as exc:
        logger.error(f"[Pexels] Download failed: {exc}")
        raise


def search_and_download_clips(
    query:      str,
    api_key:    str,
    output_dir: str,
    n_clips:    int = 5,
    min_dur:    int = 3,
    max_dur:    int = 15,
) -> list[str]:
    """
    One-shot helper: search + download N portrait clips for a keyword.

    Returns list of local file paths.
    """
    videos = search_cc_videos(
        query=query, api_key=api_key,
        per_page=n_clips * 2,
        min_duration=min_dur,
        max_duration=max_dur,
    )[:n_clips]

    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, v in enumerate(videos):
        dest = str(Path(output_dir) / f"pexels_{v['id']}_{i:02d}.mp4")
        if Path(dest).exists():
            logger.info(f"[Pexels] Cache hit: {Path(dest).name}")
            paths.append(dest)
            continue
        try:
            download_video(v["url"], dest)
            paths.append(dest)
            time.sleep(0.3)   # polite delay
        except Exception:
            continue

    logger.info(f"[Pexels] {len(paths)} clips ready in {output_dir}")
    return paths
