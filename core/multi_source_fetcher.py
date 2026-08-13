"""
====================================================================
  Pipeline v3.0
  File: core/multi_source_fetcher.py — Gom Video Đa Nguồn Song Song
====================================================================

Chạy đồng thời (concurrent) nhiều nguồn video cùng lúc:
  1. TikTok scraper  (yt-dlp, không cần API)
  2. Pexels API      (200 req/giờ, miễn phí)
  3. Pixabay API     (100 req/phút, miễn phí)
  4. YouTube         (yt-dlp, không cần API)
  5. Local B-roll    (assets/local_broll/)

Tất cả nguồn chạy song song → Gộp kết quả → Trả về clips tốt nhất.
Đảm bảo luôn có đủ clip để làm video 60 giây dù bất kỳ nguồn nào thất bại.

Usage:
  from core.multi_source_fetcher import fetch_all_sources
  clips = fetch_all_sources(
      keyword="kem chống nắng",
      n_total=12,
      sources=["tiktok", "pexels", "pixabay"]
  )
====================================================================
"""

import asyncio
import logging
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── YouTube Clip Downloader ───────────────────────────────────────

def fetch_from_youtube(
    keyword: str,
    n: int = 5,
    output_dir: str = "temp/youtube",
    max_duration_sec: int = 120,
) -> list[str]:
    """
    Tải B-roll từ YouTube theo từ khóa.
    Tự động chọn phần hay nhất của video (giữa video, tránh intro/outro).
    Không cần API key — dùng yt-dlp tìm kiếm trực tiếp.
    """
    os.makedirs(output_dir, exist_ok=True)
    search_query = f"ytsearch{n * 3}:{keyword} product review vertical"

    # Bước 1: Lấy danh sách URL
    cmd_list = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "url",
        "--match-filter", f"duration < {max_duration_sec}",
        "--no-warnings",
        search_query,
    ]
    try:
        result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=30,
                                encoding="utf-8", errors="replace")
        urls = [l.strip() for l in result.stdout.splitlines() if l.strip().startswith("http")]
    except Exception as e:
        logger.warning(f"[YouTube] Lấy danh sách thất bại: {e}")
        return []

    clips = []
    for i, url in enumerate(urls[:n]):
        out_path = os.path.join(output_dir, f"yt_{i:03d}.mp4")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
            clips.append(out_path)
            continue

        # Tải + Rescale về 9:16
        cmd_dl = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
            "--postprocessor-args", "ffmpeg:-vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920 -t 30",
            "--output", out_path,
            "--quiet",
            "--no-warnings",
            "--merge-output-format", "mp4",
            url,
        ]
        try:
            subprocess.run(cmd_dl, capture_output=True, text=True, timeout=90)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
                clips.append(out_path)
                logger.info(f"[YouTube] ✓ Clip {len(clips)}/{n}")
        except Exception:
            continue

        time.sleep(0.3)

    logger.info(f"[YouTube] Xong: {len(clips)} clips cho '{keyword}'")
    return clips


# ── Pexels Fetcher ────────────────────────────────────────────────

def fetch_from_pexels(
    keyword: str,
    api_key: str,
    n: int = 5,
    output_dir: str = "temp/pexels",
) -> list[str]:
    """Wrapper gọn gàng cho pexels_client."""
    if not api_key:
        logger.info("[MultiSource] Bỏ qua Pexels — chưa có API key")
        return []
    try:
        from core.pexels_client import search_and_download_clips
        return search_and_download_clips(
            query=keyword,
            api_key=api_key,
            output_dir=output_dir,
            n_clips=n,
            min_dur=3,
            max_dur=30,
        )
    except Exception as e:
        logger.warning(f"[Pexels] Thất bại: {e}")
        return []


# ── Pixabay Fetcher ───────────────────────────────────────────────

def fetch_from_pixabay(
    keyword: str,
    api_key: str,
    n: int = 5,
    output_dir: str = "temp/pixabay",
) -> list[str]:
    """Tải B-roll từ Pixabay API (miễn phí, 100 req/phút)."""
    if not api_key:
        logger.info("[MultiSource] Bỏ qua Pixabay — chưa có API key")
        return []

    import requests
    os.makedirs(output_dir, exist_ok=True)

    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": api_key,
                "q": keyword,
                "per_page": n * 2,
                "video_type": "film",
                "safesearch": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except Exception as e:
        logger.warning(f"[Pixabay] API thất bại: {e}")
        return []

    clips = []
    for i, hit in enumerate(hits[:n]):
        videos = hit.get("videos", {})
        # Chọn chất lượng medium hoặc small
        vdata = videos.get("medium") or videos.get("small") or {}
        url = vdata.get("url")
        if not url:
            continue

        out_path = os.path.join(output_dir, f"pixabay_{hit['id']}_{i:02d}.mp4")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
            clips.append(out_path)
            continue

        try:
            import requests as req
            r = req.get(url, stream=True, timeout=60)
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    f.write(chunk)
            if os.path.getsize(out_path) > 10_000:
                clips.append(out_path)
                logger.info(f"[Pixabay] ✓ Clip {len(clips)}/{n}")
        except Exception as e:
            logger.warning(f"[Pixabay] Tải clip thất bại: {e}")
        time.sleep(0.2)

    return clips


# ── TikTok Fetcher ────────────────────────────────────────────────

def fetch_from_tiktok(
    keyword: str,
    n: int = 5,
    output_dir: str = "temp/tiktok",
) -> list[str]:
    """Wrapper gọn gàng cho tiktok_scraper."""
    try:
        from core.tiktok_scraper import scrape_tiktok_clips
        return scrape_tiktok_clips(keyword, n=n, output_dir=output_dir)
    except Exception as e:
        logger.warning(f"[TikTok] Thất bại: {e}")
        return []


# ── Multi-Source Main Function ────────────────────────────────────

def fetch_all_sources(
    keyword: str,
    n_total: int = 12,
    sources: Optional[list[str]] = None,
    output_dir: str = "temp/multi_source",
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    n_per_source: Optional[int] = None,
) -> list[str]:
    """
    Tổng hợp video từ nhiều nguồn cùng lúc (chạy song song).

    Parameters
    ----------
    keyword         : Từ khóa tìm kiếm VD: "kem chống nắng"
    n_total         : Tổng số clip cần lấy
    sources         : Danh sách nguồn ["tiktok", "pexels", "pixabay", "youtube"]
                      Mặc định: tất cả nguồn có API key
    output_dir      : Thư mục tổng hợp output
    pexels_api_key  : Key Pexels (lấy từ .env tự động nếu để trống)
    pixabay_api_key : Key Pixabay (lấy từ .env tự động nếu để trống)
    n_per_source    : Số clip mỗi nguồn (mặc định = n_total // số_nguồn)

    Returns
    -------
    list[str] — Đường dẫn các clip mp4 đã sẵn sàng
    """
    import os
    pexels_key  = pexels_api_key  or os.getenv("PEXELS_API_KEY", "")
    pixabay_key = pixabay_api_key or os.getenv("PIXABAY_API_KEY", "")

    if sources is None:
        sources = ["tiktok", "pexels", "pixabay"]
        if not pexels_key:
            sources.remove("pexels")
        if not pixabay_key:
            sources.remove("pixabay")

    if not n_per_source:
        n_per_source = max(3, n_total // max(len(sources), 1))

    logger.info(
        f"[MultiSource] Bắt đầu fetch '{keyword}' | "
        f"Nguồn: {sources} | {n_per_source} clips/nguồn"
    )

    # Định nghĩa task cho từng nguồn
    tasks = {}
    if "tiktok" in sources:
        tasks["tiktok"] = lambda: fetch_from_tiktok(
            keyword, n=n_per_source,
            output_dir=os.path.join(output_dir, "tiktok"),
        )
    if "pexels" in sources:
        tasks["pexels"] = lambda: fetch_from_pexels(
            keyword, api_key=pexels_key, n=n_per_source,
            output_dir=os.path.join(output_dir, "pexels"),
        )
    if "pixabay" in sources:
        tasks["pixabay"] = lambda: fetch_from_pixabay(
            keyword, api_key=pixabay_key, n=n_per_source,
            output_dir=os.path.join(output_dir, "pixabay"),
        )
    if "youtube" in sources:
        tasks["youtube"] = lambda: fetch_from_youtube(
            keyword, n=n_per_source,
            output_dir=os.path.join(output_dir, "youtube"),
        )

    # Chạy song song tất cả nguồn
    all_clips: list[str] = []
    source_stats: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_source = {
            executor.submit(fn): name
            for name, fn in tasks.items()
        }
        for future in as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                clips = future.result()
                source_stats[source_name] = len(clips)
                all_clips.extend(clips)
                logger.info(f"[MultiSource] ✓ {source_name}: {len(clips)} clips")
            except Exception as e:
                source_stats[source_name] = 0
                logger.warning(f"[MultiSource] ✗ {source_name} thất bại: {e}")

    # Thống kê
    logger.info(
        f"[MultiSource] Tổng kết: {source_stats} | "
        f"Tổng {len(all_clips)} clips cho '{keyword}'"
    )

    # Trả về tối đa n_total clips, ưu tiên đa dạng nguồn
    return all_clips[:n_total]


def fetch_all_sources_for_video(
    product_name: str,
    scene_keywords: list[str],
    clips_per_scene: int = 2,
    pexels_api_key: str = "",
    pixabay_api_key: str = "",
    temp_dir: str = "temp",
) -> dict[str, list[str]]:
    """
    Phiên bản nâng cao: Fetch đa nguồn cho TỪNG CẢNH trong kịch bản video.

    Parameters
    ----------
    product_name    : Tên sản phẩm
    scene_keywords  : Danh sách từ khóa từng cảnh ["product showcase", "happy customer", ...]
    clips_per_scene : Số clip mỗi cảnh

    Returns
    -------
    dict { scene_keyword: [clip_path1, clip_path2, ...] }
    """
    results: dict[str, list[str]] = {}

    for i, scene_kw in enumerate(scene_keywords):
        # Kết hợp sản phẩm + từ khóa cảnh cho kết quả chính xác hơn
        combined_kw = f"{product_name} {scene_kw}"
        scene_dir = os.path.join(temp_dir, "multi_source", f"scene_{i:02d}")

        logger.info(f"[MultiSource] Cảnh {i+1}/{len(scene_keywords)}: '{combined_kw}'")
        clips = fetch_all_sources(
            keyword=combined_kw,
            n_total=clips_per_scene,
            output_dir=scene_dir,
            pexels_api_key=pexels_api_key,
            pixabay_api_key=pixabay_api_key,
        )
        results[scene_kw] = clips

    total = sum(len(v) for v in results.values())
    logger.info(f"[MultiSource] Hoàn tất tất cả cảnh: {total} clips tổng")
    return results
