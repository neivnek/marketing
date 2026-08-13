"""
====================================================================
  Pipeline v3.0
  File: core/tiktok_scraper.py — TikTok Video Scraper (Không cần API)
====================================================================

Cào video TikTok theo từ khóa hoặc hashtag hoàn toàn miễn phí
bằng yt-dlp (đã có trong requirements.txt).

Không cần API key, không cần đăng nhập, không tốn tiền.

Cách hoạt động:
  1. Tìm URL tìm kiếm TikTok theo từ khóa sản phẩm
  2. Dùng yt-dlp để tải danh sách video
  3. Tải về máy, xóa watermark bằng FFmpeg crop
  4. Trả về list đường dẫn file mp4

Usage:
  from core.tiktok_scraper import scrape_tiktok_clips
  clips = scrape_tiktok_clips("kem chống nắng", n=5, output_dir="temp/tiktok")
====================================================================
"""

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────

# Kích thước crop để xóa watermark TikTok (ở góc dưới bên phải)
# Format: crop=w:h:x:y (giữ lại w×h pixel bắt đầu từ tọa độ x,y)
# Watermark TikTok thường ở 40px dưới cùng và 40px phải
TIKTOK_WATERMARK_CROP = "crop=in_w:in_h-90:0:0"  # Cắt bỏ 90px dưới cùng


def _build_search_urls(keyword: str) -> list[str]:
    """Tạo danh sách URL TikTok để yt-dlp có thể cào."""
    encoded = keyword.replace(" ", "%20")
    encoded_tag = keyword.replace(" ", "")
    return [
        f"https://www.tiktok.com/search?q={encoded}",
        f"https://www.tiktok.com/tag/{encoded_tag}",
    ]


def _ytdlp_list_urls(search_url: str, n: int = 15, timeout: int = 30) -> list[str]:
    """
    Dùng yt-dlp để lấy danh sách URL video (không tải về).
    Trả về list link video TikTok.
    """
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "url",
        "--no-warnings",
        "--playlist-items", f"1-{n}",
        "--no-check-certificates",
        search_url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        urls = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().startswith("http") and "tiktok" in line
        ]
        logger.info(f"[TikTok] Tìm thấy {len(urls)} link từ: {search_url[:60]}...")
        return urls
    except subprocess.TimeoutExpired:
        logger.warning("[TikTok] yt-dlp timeout khi lấy danh sách URL")
        return []
    except Exception as e:
        logger.warning(f"[TikTok] Lỗi lấy danh sách URL: {e}")
        return []


def _download_single(video_url: str, output_dir: str, index: int) -> Optional[str]:
    """
    Tải một video TikTok về máy. Trả về đường dẫn file hoặc None.
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, f"tiktok_{index:03d}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--format", "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--output", out_template,
        "--quiet",
        "--no-warnings",
        "--no-check-certificates",
        "--merge-output-format", "mp4",
        video_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.debug(f"[TikTok] yt-dlp lỗi: {result.stderr[:100]}")
            return None

        # Tìm file vừa tải
        for f in os.listdir(output_dir):
            if f.startswith(f"tiktok_{index:03d}.") and f.endswith(".mp4"):
                path = os.path.join(output_dir, f)
                if os.path.getsize(path) > 10_000:  # Bỏ qua file < 10KB
                    return path
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"[TikTok] Timeout khi tải video {index}")
        return None
    except Exception as e:
        logger.warning(f"[TikTok] Lỗi tải video {index}: {e}")
        return None


def _remove_watermark(input_path: str, output_path: str) -> str:
    """
    Xóa watermark TikTok (phần dưới cùng và chữ @username) bằng FFmpeg crop.
    Đồng thời rescale về định dạng 9:16 chuẩn 1080x1920.
    """
    # Scale về 1080x1920, crop bỏ 90px dưới (watermark TikTok)
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "crop=1080:1830:0:0"  # Cắt 90px dưới (watermark)
        ",pad=1080:1920:0:0:black"  # Pad lại về 1920
    )
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.warning(f"[TikTok] Xóa watermark thất bại: {e}")
    return input_path  # Trả về file gốc nếu lỗi


def scrape_tiktok_clips(
    keyword: str,
    n: int = 5,
    output_dir: str = "temp/tiktok",
    remove_watermark: bool = True,
    max_duration_sec: int = 90,
) -> list[str]:
    """
    Cào video TikTok theo từ khóa sản phẩm.

    Parameters
    ----------
    keyword          : Từ khóa sản phẩm VD: "kem chống nắng", "túi da"
    n                : Số clip cần lấy (mặc định 5)
    output_dir       : Thư mục lưu video
    remove_watermark : Có xóa watermark TikTok không
    max_duration_sec : Bỏ qua video quá dài

    Returns
    -------
    list[str] — Đường dẫn các file mp4 đã tải về
    """
    logger.info(f"[TikTok] Bắt đầu cào: '{keyword}' | Cần {n} clips")
    os.makedirs(output_dir, exist_ok=True)
    raw_dir = os.path.join(output_dir, "raw")
    clean_dir = os.path.join(output_dir, "clean")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(clean_dir, exist_ok=True)

    # 1. Lấy danh sách URL từ nhiều nguồn
    all_urls: list[str] = []
    for search_url in _build_search_urls(keyword):
        urls = _ytdlp_list_urls(search_url, n=n * 3)
        all_urls.extend(urls)
        if len(all_urls) >= n * 3:
            break
        time.sleep(1)  # Tránh bị chặn

    # Loại bỏ trùng lặp
    seen: set = set()
    unique_urls = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    if not unique_urls:
        logger.warning(f"[TikTok] Không tìm thấy video nào cho '{keyword}'")
        return []

    logger.info(f"[TikTok] Tìm được {len(unique_urls)} URL duy nhất. Đang tải...")

    # 2. Tải video
    results: list[str] = []
    for i, url in enumerate(unique_urls):
        if len(results) >= n:
            break

        raw_path = _download_single(url, raw_dir, i)
        if not raw_path:
            continue

        # 3. Xóa watermark và rescale
        if remove_watermark:
            clean_path = os.path.join(clean_dir, f"tiktok_clean_{i:03d}.mp4")
            final_path = _remove_watermark(raw_path, clean_path)
        else:
            final_path = raw_path

        if os.path.exists(final_path) and os.path.getsize(final_path) > 10_000:
            results.append(final_path)
            logger.info(f"[TikTok] ✓ Clip {len(results)}/{n}: {Path(final_path).name}")

        time.sleep(0.5)  # Polite delay

    logger.info(f"[TikTok] Hoàn tất: {len(results)}/{n} clips từ '{keyword}'")
    return results


def scrape_from_direct_urls(
    urls: list[str],
    output_dir: str = "temp/tiktok",
    remove_watermark: bool = True,
) -> list[str]:
    """
    Tải trực tiếp từ list URL TikTok cho sẵn.
    Dùng khi bạn muốn tải đúng video cụ thể bạn đã thấy.
    """
    os.makedirs(output_dir, exist_ok=True)
    raw_dir = os.path.join(output_dir, "raw")
    clean_dir = os.path.join(output_dir, "clean")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(clean_dir, exist_ok=True)

    results = []
    for i, url in enumerate(urls):
        raw_path = _download_single(url, raw_dir, i)
        if not raw_path:
            continue
        if remove_watermark:
            clean_path = os.path.join(clean_dir, f"direct_clean_{i:03d}.mp4")
            final_path = _remove_watermark(raw_path, clean_path)
        else:
            final_path = raw_path
        if os.path.exists(final_path):
            results.append(final_path)

    return results
