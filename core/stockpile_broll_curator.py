"""
====================================================================
  Stockpile AI B-Roll Curator Engine (Tích hợp từ sasoder/stockpile)
  File: core/stockpile_broll_curator.py
====================================================================
Tích hợp quy trình cào & tuyển chọn B-Roll bằng AI từ dự án Stockpile:
1. AI Query Expansion: Dùng Gemini 3.6 Flash phân tích từ khóa sản phẩm -> Tạo từ khóa tìm kiếm B-roll tối ưu.
2. yt-dlp Video Search & Fetch: Tự động tìm kiếm & tải video Shorts / B-roll chất lượng cao.
3. Curation & Trimming: Cắt thành các clip B-roll ngắn (3-5s), phân loại vào `assets/local_broll/<category>/`.
"""

import os
import re
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)

def generate_broll_search_queries(keyword: str, num_queries: int = 3) -> List[str]:
    """
    Sử dụng Gemini 3.6 Flash để mở rộng từ khóa tìm kiếm B-Roll chất lượng cao.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return [f"{keyword} review", f"{keyword} b-roll", f"{keyword} shorts"]

    try:
        from google import genai
        client = get_pooled_client(api_key=api_key)
        prompt = f"""Bạn là AI Curator B-Roll của Stockpile Engine.
Với từ khóa/sản phẩm: "{keyword}".
Hãy tạo ra {num_queries} cụm từ khóa tiếng Anh/tiếng Việt tối ưu nhất để tìm kiếm video B-roll minh họa (Shorts/Reels/Stock video).
Trả về dạng JSON Array đơn giản: ["từ khóa 1", "từ khóa 2", "từ khóa 3"]"""

        candidate_models = ['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash']
        for m in candidate_models:
            try:
                resp = client.models.generate_content(model=m, contents=prompt)
                if resp and resp.text:
                    txt = resp.text.strip()
                    if txt.startswith("```json"):
                        txt = txt[7:-3].strip()
                    elif txt.startswith("```"):
                        txt = txt[3:-3].strip()
                    return json.loads(txt)
            except Exception:
                continue
    except Exception as e:
        logger.error(f"[Stockpile] Lỗi sinh query: {e}")

    return [f"{keyword} review", f"{keyword} broll", f"{keyword} shorts"]

def curate_and_download_broll(
    keyword: str,
    max_clips: int = 3,
    output_dir: str = "assets/local_broll"
) -> List[str]:
    """
    Quy trình Stockpile Curator:
    1. Sinh query qua Gemini.
    2. Dùng yt-dlp cào video B-roll về `assets/local_broll/<slug>/`.
    3. Cắt tỉa thành các clip B-roll ngắn sẵn sàng cho pipeline dựng video.
    """
    _PARTIAL_SUFFIXES = (".part", ".ytdl", ".temp", ".part-Frag")

    def _cleanup_partials(folder: str) -> None:
        """Xóa mảnh tải dở của yt-dlp (timeout/kill giữa chừng)."""
        removed = 0
        for f in os.listdir(folder):
            if any(s in f for s in _PARTIAL_SUFFIXES):
                try:
                    os.remove(os.path.join(folder, f))
                    removed += 1
                except OSError as exc:
                    logger.debug(f"[Stockpile] Không xóa được mảnh tải dở {f}: {exc}")
        if removed:
            logger.info(f"[Stockpile] Đã dọn {removed} mảnh tải dở (.part/.ytdl).")

    clean_slug = re.sub(r"[^a-zA-Z0-9_]", "_", keyword.lower()).strip("_") or "generic"
    target_folder = os.path.join(output_dir, clean_slug)
    os.makedirs(target_folder, exist_ok=True)

    queries = generate_broll_search_queries(keyword, num_queries=2)
    logger.info(f"[Stockpile] Tìm kiếm B-roll với queries: {queries}")

    downloaded_files = []
    clip_count = 0

    # Ảnh chụp trước khi cào: chỉ những file MỚI mới được tính là kết quả lần này,
    # tránh đếm nhầm clip của các lần chạy trước rồi báo "cào thành công N clips".
    def _existing_mp4() -> set:
        return {f for f in os.listdir(target_folder) if f.endswith(".mp4")}

    before = _existing_mp4()

    for q in queries:
        if clip_count >= max_clips:
            break

        temp_out = os.path.join(target_folder, "stockpile_raw_%(id)s.%(ext)s")
        # Sử dụng yt-dlp để tìm và tải 1-2 video Shorts/b-roll
        yt_cmd = [
            "yt-dlp",
            f"ytsearch{max_clips}:#shorts {q}",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--max-filesize", "50M",
            "-o", temp_out,
            "--no-playlist",
            "--quiet",
            "--no-warnings"
        ]

        try:
            logger.info(f"[Stockpile] Đang cào B-roll cho query: '{q}'...")
            res = subprocess.run(yt_cmd, timeout=45, capture_output=True, text=True)
            if res.returncode != 0:
                logger.warning(
                    f"[Stockpile] yt-dlp trả về mã {res.returncode} cho query '{q}': "
                    f"{(res.stderr or '').strip()[-300:]}"
                )
        except subprocess.TimeoutExpired:
            logger.warning(f"[Stockpile] yt-dlp quá 45s cho query '{q}' — bỏ qua query này.")
        except Exception as err:
            logger.warning(f"[Stockpile] Lỗi yt-dlp cho query '{q}': {err}")
        finally:
            # yt-dlp bị timeout/kill sẽ để lại mảnh .part, .ytdl, .temp nằm mãi
            # trong kho B-roll (từng tích tụ tới 52MB). Dọn ngay sau mỗi query.
            _cleanup_partials(target_folder)

        clip_count = len(_existing_mp4() - before)

    # Chỉ lấy các file MP4 MỚI cào về trong lần chạy này
    for file in sorted(_existing_mp4() - before):
        if len(downloaded_files) >= max_clips:
            break
        downloaded_files.append(os.path.join(target_folder, file))

    logger.info(f"[Stockpile] Đã nạp thành công {len(downloaded_files)} clips B-roll vào kho '{clean_slug}'.")
    return downloaded_files
