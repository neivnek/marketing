"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/broll_aggregator.py — Multi-Source B-Roll Fetcher
====================================================================

Priority order:
  1. assets/local_broll/<category>/ — local clips (fastest, no API)
  2. Pexels Video API               — free, 200 req/hr, portrait-first
  3. Pixabay Video API              — optional, free 100 req/min,
                                     ToS: 24h JSON response cache (MANDATORY)
  4. assets/local_broll/generic/   — last-resort local (no keyword match needed)

Keyword fallback chain:
  full keywords → simplified (nouns only) → generic/ folder → None (Ken Burns)

All used clip IDs are logged in temp/broll_manifest.db (SQLite) keyed by
(product_category, clip_source) with a 30-day dedup window.

24h API cache: temp/broll_api_cache.db stores raw JSON responses per
(source, query_hash) to comply with Pixabay ToS and avoid quota waste.
"""

import glob
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────
PEXELS_VIDEO_URL  = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
_HEADERS          = {"User-Agent": "KhmerAdsGenerator/3.0"}
DEDUP_DAYS        = 30
API_CACHE_HOURS   = 24   # Pixabay ToS: MUST cache responses 24h


# ── SQLite Manifest (30-day dedup) ────────────────────────────────

def _get_manifest_db(temp_dir: str) -> sqlite3.Connection:
    """Open (or create) the broll manifest SQLite database."""
    os.makedirs(temp_dir, exist_ok=True)
    db_path = os.path.join(temp_dir, "broll_manifest.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS used_clips (
            clip_id          TEXT NOT NULL,
            clip_source      TEXT NOT NULL,
            product_category TEXT NOT NULL DEFAULT '',
            used_at          TEXT NOT NULL,
            PRIMARY KEY (clip_id, clip_source)
        )
    """)
    conn.commit()
    return conn


def _is_recently_used(
    conn: sqlite3.Connection,
    clip_id: str,
    clip_source: str,
    product_category: str,
) -> bool:
    """Return True if clip was used for this category within DEDUP_DAYS."""
    cutoff = (datetime.utcnow() - timedelta(days=DEDUP_DAYS)).isoformat()
    row = conn.execute(
        """SELECT 1 FROM used_clips
           WHERE clip_id=? AND clip_source=? AND product_category=?
             AND used_at > ?""",
        (str(clip_id), clip_source, product_category, cutoff),
    ).fetchone()
    return row is not None


def _mark_used(
    conn: sqlite3.Connection,
    clip_id: str,
    clip_source: str,
    product_category: str,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO used_clips
           (clip_id, clip_source, product_category, used_at)
           VALUES (?, ?, ?, ?)""",
        (str(clip_id), clip_source, product_category, datetime.utcnow().isoformat()),
    )
    conn.commit()


# ── 24h API Response Cache (Pixabay ToS compliance) ──────────────

def _get_api_cache_db(temp_dir: str) -> sqlite3.Connection:
    """Open (or create) the 24h API response cache database."""
    os.makedirs(temp_dir, exist_ok=True)
    db_path = os.path.join(temp_dir, "broll_api_cache.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_cache (
            cache_key  TEXT PRIMARY KEY,
            source     TEXT NOT NULL,
            query      TEXT NOT NULL,
            response   TEXT NOT NULL,
            cached_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _api_cache_key(source: str, query: str, extra: str = "") -> str:
    raw = f"{source}::{query.strip().lower()}::{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _read_api_cache(conn: sqlite3.Connection, key: str) -> Optional[list]:
    """Return cached JSON hits list if present and fresh (<24h)."""
    cutoff = (datetime.utcnow() - timedelta(hours=API_CACHE_HOURS)).isoformat()
    row = conn.execute(
        "SELECT response FROM api_cache WHERE cache_key=? AND cached_at > ?",
        (key, cutoff),
    ).fetchone()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return None
    return None


def _write_api_cache(conn: sqlite3.Connection, key: str, source: str, query: str, hits: list) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO api_cache (cache_key, source, query, response, cached_at)
           VALUES (?, ?, ?, ?, ?)""",
        (key, source, query, json.dumps(hits, ensure_ascii=False), datetime.utcnow().isoformat()),
    )
    conn.commit()


# ── Keyword Simplification ────────────────────────────────────────

# Common adjectives stripped during keyword simplification fallback
_STRIP_ADJECTIVES = {
    "beautiful", "happy", "sad", "amazing", "stunning", "gorgeous",
    "frustrated", "excited", "lifestyle", "authentic", "genuine",
    "vibrant", "dynamic", "modern", "stylish", "perfect", "great",
    "close", "closeup", "real", "organic", "natural", "fresh",
}


def _simplify_keywords(keywords: list[str]) -> list[str]:
    """
    Strip adjectives from keywords, keep nouns/verbs.
    Used as fallback when full-keyword search returns no results.
    E.g. ["frustrated person", "messy hair salon"] -> ["person", "hair salon"]
    """
    simplified = []
    for kw in keywords:
        words = kw.lower().split()
        kept  = [w for w in words if w not in _STRIP_ADJECTIVES]
        simplified.append(" ".join(kept) if kept else kw)
    # Deduplicate
    seen, out = set(), []
    for k in simplified:
        if k.strip() and k not in seen:
            seen.add(k)
            out.append(k.strip())
    return out or keywords


# ── Local B-Roll Search ───────────────────────────────────────────

def _search_local_broll(
    query_keywords: list[str],
    local_broll_dir: str,
    product_category: str,
    conn: sqlite3.Connection,
    n_clips: int = 3,
    use_generic: bool = False,
) -> list[str]:
    """
    Scan assets/local_broll/ for clips matching any keyword in the filename.
    If use_generic=True, scans the 'generic/' subfolder without keyword filtering.
    Returns up to n_clips paths not recently used for this category.
    """
    if not os.path.isdir(local_broll_dir):
        return []

    if use_generic:
        # Generic folder — last resort, no keyword matching needed
        search_dir = os.path.join(local_broll_dir, "generic")
        all_mp4 = glob.glob(os.path.join(search_dir, "*.mp4"))
        all_mp4 += glob.glob(os.path.join(search_dir, "**", "*.mp4"), recursive=True)
    else:
        all_mp4 = glob.glob(os.path.join(local_broll_dir, "**", "*.mp4"), recursive=True)

    matched = []
    for path in all_mp4:
        name_lower = Path(path).stem.lower()
        if use_generic or any(kw.lower() in name_lower for kw in query_keywords):
            clip_id = Path(path).stem
            if not _is_recently_used(conn, clip_id, "local", product_category):
                matched.append(path)

    random.shuffle(matched)
    chosen = matched[:n_clips]
    for path in chosen:
        _mark_used(conn, Path(path).stem, "local", product_category)

    if use_generic:
        logger.info(f"[BRoll] Generic local fallback: {len(chosen)} clips")
    else:
        logger.info(f"[BRoll] Local: {len(chosen)}/{n_clips} clips for {query_keywords}")
    return chosen


# ── Pexels Search ─────────────────────────────────────────────────

def _search_pexels(
    query: str,
    api_key: str,
    product_category: str,
    conn: sqlite3.Connection,
    api_conn: sqlite3.Connection,
    n_clips: int = 3,
    temp_dir: str = "temp",
) -> list[str]:
    """Search & download clips from Pexels. 24h cache applied."""
    if not api_key:
        logger.debug("[BRoll] No PEXELS_API_KEY — skipping Pexels.")
        return []

    cache_key = _api_cache_key("pexels", query, f"portrait:{n_clips * 3}")
    cached = _read_api_cache(api_conn, cache_key)
    if cached is not None:
        logger.debug(f"[BRoll] Pexels cache HIT for '{query}'")
        videos = cached
    else:
        headers = {"Authorization": api_key, **_HEADERS}
        # Per Pexels API docs: orientation=portrait, size=medium
        params = {
            "query":       query,
            "per_page":    min(n_clips * 3, 15),
            "orientation": "portrait",
            "size":        "medium",
        }
        try:
            resp = requests.get(PEXELS_VIDEO_URL, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            _write_api_cache(api_conn, cache_key, "pexels", query, videos)
        except Exception as exc:
            logger.warning(f"[BRoll] Pexels search failed: {exc}")
            return []

    clip_dir = os.path.join(temp_dir, "broll_pexels")
    os.makedirs(clip_dir, exist_ok=True)
    paths = []

    for v in videos:
        if len(paths) >= n_clips:
            break
        vid_id = str(v["id"])
        if _is_recently_used(conn, vid_id, "pexels", product_category):
            continue

        # Pick best portrait file ≤ 1920px wide
        files = sorted(
            v.get("video_files", []),
            key=lambda f: f.get("width", 0) * f.get("height", 0),
            reverse=True,
        )
        chosen_file = next((f for f in files if f.get("width", 9999) <= 1920), None)
        if not chosen_file and files:
            chosen_file = files[-1]
        if not chosen_file:
            continue

        dest = os.path.join(clip_dir, f"pexels_{vid_id}.mp4")
        if not Path(dest).exists():
            try:
                with requests.get(chosen_file["link"], stream=True, timeout=60, headers=_HEADERS) as r:
                    r.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(chunk_size=256 * 1024):
                            f.write(chunk)
                time.sleep(0.3)
            except Exception as exc:
                logger.warning(f"[BRoll] Pexels download failed ({vid_id}): {exc}")
                continue

        _mark_used(conn, vid_id, "pexels", product_category)
        paths.append(dest)

    logger.info(f"[BRoll] Pexels: {len(paths)} clips for '{query}'")
    return paths


# ── Pixabay Search ────────────────────────────────────────────────

def _search_pixabay(
    query: str,
    api_key: str,
    product_category: str,
    conn: sqlite3.Connection,
    api_conn: sqlite3.Connection,
    n_clips: int = 3,
    temp_dir: str = "temp",
) -> list[str]:
    """Search & download clips from Pixabay. MANDATORY 24h cache per ToS."""
    if not api_key:
        logger.debug("[BRoll] No PIXABAY_API_KEY — skipping Pixabay.")
        return []

    cache_key = _api_cache_key("pixabay", query, f"film:{n_clips * 3}")
    cached = _read_api_cache(api_conn, cache_key)
    if cached is not None:
        logger.debug(f"[BRoll] Pixabay cache HIT for '{query}'")
        hits = cached
    else:
        # Per Pixabay Video API docs: video_type, per_page, orientation
        params = {
            "key":         api_key,
            "q":           query,
            "video_type":  "film",
            "per_page":    min(n_clips * 3, 20),
            "orientation": "vertical",   # portrait-first
        }
        try:
            resp = requests.get(PIXABAY_VIDEO_URL, params=params, timeout=15, headers=_HEADERS)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            _write_api_cache(api_conn, cache_key, "pixabay", query, hits)   # ToS mandatory
        except Exception as exc:
            logger.warning(f"[BRoll] Pixabay search failed: {exc}")
            return []

    clip_dir = os.path.join(temp_dir, "broll_pixabay")
    os.makedirs(clip_dir, exist_ok=True)
    paths = []

    for hit in hits:
        if len(paths) >= n_clips:
            break
        vid_id = str(hit["id"])
        if _is_recently_used(conn, vid_id, "pixabay", product_category):
            continue

        # videos dict: quality labels "tiny"|"small"|"medium"|"large"
        vids = hit.get("videos", {})
        chosen_url = None
        for quality in ("medium", "small", "large", "tiny"):
            entry = vids.get(quality, {})
            if entry.get("url"):
                chosen_url = entry["url"]
                break
        if not chosen_url:
            continue

        dest = os.path.join(clip_dir, f"pixabay_{vid_id}.mp4")
        if not Path(dest).exists():
            try:
                with requests.get(chosen_url, stream=True, timeout=60, headers=_HEADERS) as r:
                    r.raise_for_status()
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(chunk_size=256 * 1024):
                            f.write(chunk)
                time.sleep(0.3)
            except Exception as exc:
                logger.warning(f"[BRoll] Pixabay download failed ({vid_id}): {exc}")
                continue

        _mark_used(conn, vid_id, "pixabay", product_category)
        paths.append(dest)

    logger.info(f"[BRoll] Pixabay: {len(paths)} clips for '{query}'")
    return paths


# ── Clip Trim / Rescale Utilities ────────────────────────────────

def trim_clip(input_path: str, output_path: str, duration: float) -> str:
    """Trim a video clip to exactly `duration` seconds using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"trim_clip failed: {result.stderr[-300:]}")
    return output_path


def rescale_clip(input_path: str, output_path: str, width: int = 1080, height: int = 1920) -> str:
    """
    Rescale & pad a clip to target portrait resolution (1080x1920).
    Uses scale-then-pad so aspect ratio is preserved and borders are black.
    """
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-an",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"rescale_clip failed: {result.stderr[-300:]}")
    return output_path


# ── Public API ────────────────────────────────────────────────────

def fetch_broll_clips(
    query_keywords:   list[str],
    product_category: str,
    duration_sec:     float,
    pexels_api_key:   str  = "",
    pixabay_api_key:  str  = "",
    local_broll_dir:  str  = "assets/local_broll",
    temp_dir:         str  = "temp",
    n_clips:          int  = 2,
    out_w:            int  = 1080,
    out_h:            int  = 1920,
    reference_image:  str  = "",
) -> list[str]:
    """
    Fetch B-roll clips for a given scene query with full graceful fallback chain.

    Fallback order (Rule 17: never raises, always has a path):
      1. Local keyword-matched   — no quota
      2. Pexels API (24h cached)
      3. Pixabay API (24h cached, ToS MANDATORY)
      4. Local simplified keywords — strip adjectives, keep nouns
      5. Local generic/           — no keyword filter needed
      6. [] — caller must use Ken Burns fallback

    Returns
    -------
    list[str] — Portrait MP4 clips, rescaled + trimmed.
                [] when all fallbacks exhausted.
    """
    conn     = _get_manifest_db(temp_dir)
    api_conn = _get_api_cache_db(temp_dir)
    query_str = " ".join(query_keywords)
    raw_clips: list[str] = []

    # 1. Local keyword-matched
    raw_clips.extend(
        _search_local_broll(query_keywords, local_broll_dir, product_category, conn, n_clips)
    )

    # 1.5 AI B-roll (Mode 11) - Nếu có reference image
    if len(raw_clips) < n_clips and reference_image and os.path.exists(reference_image):
        from modes.ai_broll.generation_queue import generate_batch_async
        needed = n_clips - len(raw_clips)
        # Bọc try-catch để fallback an toàn
        try:
            tasks_data = [{"prompt": f"@product {query_str}", "reference_image": reference_image} for _ in range(needed)]
            logger.info(f"[BRoll] Kích hoạt AI_BROLL (Mode 11) tạo {needed} clips cho '{query_str}'")
            ai_clips = generate_batch_async(tasks_data)
            valid_ai_clips = [c for c in ai_clips if c is not None]
            raw_clips.extend(valid_ai_clips)
            if len(valid_ai_clips) < needed:
                logger.warning("[BRoll] AI_BROLL không đủ kết quả, fallback sang Pexels...")
        except Exception as e:
            logger.error(f"[BRoll] AI_BROLL thất bại: {e}")

    # 2. Pexels
    if len(raw_clips) < n_clips:
        raw_clips.extend(_search_pexels(
            query_str, pexels_api_key, product_category, conn, api_conn,
            n_clips - len(raw_clips), temp_dir,
        ))

    # 3. Pixabay (24h cache mandatory)
    if len(raw_clips) < n_clips:
        raw_clips.extend(_search_pixabay(
            query_str, pixabay_api_key, product_category, conn, api_conn,
            n_clips - len(raw_clips), temp_dir,
        ))

    # 4. Simplified keywords (strip adjectives, keep nouns)
    if not raw_clips:
        simplified = _simplify_keywords(query_keywords)
        if simplified != query_keywords:
            logger.info(f"[BRoll] Simplified keyword fallback: {simplified}")
            raw_clips.extend(
                _search_local_broll(simplified, local_broll_dir, product_category, conn, n_clips)
            )
            if not raw_clips and pexels_api_key:
                raw_clips.extend(_search_pexels(
                    " ".join(simplified), pexels_api_key, product_category, conn, api_conn,
                    n_clips, temp_dir,
                ))
            if not raw_clips and pixabay_api_key:
                raw_clips.extend(_search_pixabay(
                    " ".join(simplified), pixabay_api_key, product_category, conn, api_conn,
                    n_clips, temp_dir,
                ))

    # 5. Generic/ folder (last-resort local — no keyword filter)
    if not raw_clips:
        logger.info("[BRoll] Trying generic/ local fallback folder...")
        raw_clips.extend(
            _search_local_broll(
                query_keywords, local_broll_dir, product_category, conn, n_clips,
                use_generic=True,
            )
        )

    conn.close()
    api_conn.close()

    # 6. Complete failure — caller uses Ken Burns
    if not raw_clips:
        logger.warning(f"[BRoll] All fallbacks exhausted for '{query_str}' — use Ken Burns.")
        return []

    # Rescale + trim each clip
    processed = []
    proc_dir  = os.path.join(temp_dir, "broll_processed")
    os.makedirs(proc_dir, exist_ok=True)

    for i, src in enumerate(raw_clips[:n_clips]):
        slug     = re.sub(r"[^a-z0-9]", "_", query_str[:20].lower())
        rescaled = os.path.join(proc_dir, f"broll_{slug}_{i:02d}_scaled.mp4")
        trimmed  = os.path.join(proc_dir, f"broll_{slug}_{i:02d}.mp4")
        try:
            rescale_clip(src, rescaled, out_w, out_h)
            trim_clip(rescaled, trimmed, duration_sec)
            processed.append(trimmed)
        except Exception as exc:
            logger.warning(f"[BRoll] Post-process failed for {src}: {exc}")

    logger.info(f"[BRoll] Ready: {len(processed)} clips for '{query_str}' ({duration_sec:.1f}s each)")
    return processed
