"""
====================================================================
  Auto-Discovery Engine
  File: core/auto_discovery_engine.py
====================================================================
Orchestration layer to gather product information and videos from:
- Gemini (product_intelligence.py)
- YouTube/Shorts (stockpile_broll_curator.py)
- TikTok Ads (tiktok_api_client.py)
"""

import os
import json
import logging
from typing import Dict, List, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class DiscoveryReport:
    product_name: str
    category: str
    benefits: List[str]
    pain_points: List[str]
    target_audience: str
    youtube_videos: List[Dict[str, str]]  # list of {"url": "", "title": ""}
    tiktok_ads: List[Dict[str, str]]      # list of {"url": "", "title": "", "text": ""}
    local_brolls: List[str]               # list of local downloaded paths

def run_full_discovery(image_path: str, keyword: str) -> DiscoveryReport:
    """
    Quét và tổng hợp thông tin, video từ tất cả các nguồn khả dụng.
    """
    logger.info(f"[AutoDiscovery] Bắt đầu quét thông tin cho: {keyword}")
    api_key = os.getenv("GEMINI_API_KEY", "")
    
    # 1. Product Intelligence (Gemini + Web Grounding)
    from core.product_intelligence import run_product_intelligence
    
    benefits = []
    pain_points = []
    product_name = keyword
    category = "general"
    
    try:
        identity, research, yt_vids = run_product_intelligence(
            image_path=image_path if os.path.exists(image_path) else "",
            api_key=api_key,
            product_name=keyword,
            force_refresh=True
        )
        # Use Gemini's guess if keyword was empty
        product_name = identity.name_guess or keyword or "sản phẩm"
        category = identity.category or "general"
        benefits = research.benefits if research else []
        pain_points = research.suggested_pain_points if research else []
        
        # Format YT videos
        youtube_videos = []
        for v in yt_vids:
            youtube_videos.append({"url": v.url, "title": v.title})
            
    except Exception as e:
        logger.warning(f"[AutoDiscovery] Lỗi khi chạy Product Intelligence: {e}")
        youtube_videos = []

    # 2. Stockpile B-Roll Curator (yt-dlp)
    from core.stockpile_broll_curator import curate_and_download_broll
    local_brolls = []
    try:
        # Sử dụng product_name (tên đoán được từ ảnh) để tìm video
        search_term = product_name
        local_brolls = curate_and_download_broll(keyword=search_term, max_clips=2)
    except Exception as e:
        logger.warning(f"[AutoDiscovery] Lỗi khi cào B-roll Stockpile: {e}")

    # 3. TikTok Ads API
    from core.tiktok_api_client import TikTokAdClient
    tiktok_ads = []
    try:
        tk_client = TikTokAdClient()
        search_term = product_name
        ads = tk_client.search_ads(keyword=search_term, limit=3)
        for ad in ads:
            ad_data = tk_client.extract_ad_content(ad)
            if ad_data.get("video_url"):
                tiktok_ads.append({
                    "url": ad_data["video_url"],
                    "title": ad_data["brand_name"],
                    "text": ad_data["primary_text"]
                })
    except Exception as e:
        logger.warning(f"[AutoDiscovery] Lỗi khi cào TikTok Ads: {e}")
        
    report = DiscoveryReport(
        product_name=product_name,
        category=category,
        benefits=benefits,
        pain_points=pain_points,
        target_audience="Khách hàng Việt Nam (chưa xác định rõ)", # Defaults
        youtube_videos=youtube_videos,
        tiktok_ads=tiktok_ads,
        local_brolls=local_brolls
    )
    
    logger.info("[AutoDiscovery] Hoàn tất quá trình càn quét.")
    return report

def format_report_html(report: DiscoveryReport) -> str:
    """Format the report into beautiful HTML for Gradio."""
    html = f"<h3>🛍️ Thông tin: {report.product_name} ({report.category})</h3>"
    
    html += "<h4>✨ Lợi ích chính (Benefits):</h4><ul>"
    for b in report.benefits:
        html += f"<li>{b}</li>"
    if not report.benefits: html += "<li>(Không tìm thấy)</li>"
    html += "</ul>"
    
    html += "<h4>🎯 Vấn đề giải quyết (Pain points):</h4><ul>"
    for p in report.pain_points:
        html += f"<li>{p}</li>"
    if not report.pain_points: html += "<li>(Không tìm thấy)</li>"
    html += "</ul>"
    
    html += "<h4>📺 Video YouTube tìm thấy:</h4><ul>"
    for y in report.youtube_videos:
        html += f"<li><a href='{y['url']}' target='_blank'>{y['title']}</a></li>"
    if not report.youtube_videos: html += "<li>(Không tìm thấy)</li>"
    html += "</ul>"
    
    html += "<h4>🎵 TikTok Ads (API):</h4><ul>"
    for t in report.tiktok_ads:
        html += f"<li><a href='{t['url']}' target='_blank'>{t['title']}</a> - {t['text'][:50]}...</li>"
    if not report.tiktok_ads: html += "<li>(Không tìm thấy)</li>"
    html += "</ul>"
    
    return html
