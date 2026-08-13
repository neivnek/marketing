import os
import time
import logging
import requests
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class MetaAdLibraryClient:
    """
    Client kết nối Meta Ad Library API.
    Yêu cầu: ACCESS_TOKEN lấy từ tài khoản Developer Meta đã xác minh danh tính.
    """
    def __init__(self, access_token: str = None):
        self.access_token = access_token or os.getenv("META_AD_ACCESS_TOKEN", "")
        self.base_url = "https://graph.facebook.com/v19.0/ads_archive"
        
    def search_ads(self, 
                   keyword: str, 
                   country: str = "VN", 
                   limit: int = 10,
                   active_status: str = "ACTIVE") -> List[Dict]:
        """
        Tìm kiếm quảng cáo theo từ khóa.
        """
        if not self.access_token:
            logger.error("[MetaAds] Thiếu META_AD_ACCESS_TOKEN. Vui lòng thêm vào file .env")
            return []
            
        params = {
            "access_token": self.access_token,
            "search_terms": keyword,
            "ad_reached_countries": f"['{country}']",
            "ad_active_status": active_status,
            "limit": limit,
            "fields": "id,page_name,ad_creation_time,ad_creative_bodies,ad_creative_link_captions,ad_creative_link_titles,ad_snapshot_url,publisher_platforms"
        }
        
        try:
            logger.info(f"[MetaAds] Đang tìm quảng cáo với từ khóa: '{keyword}'...")
            response = requests.get(self.base_url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            elif response.status_code == 400: # Lỗi Token hoặc Rate Limit
                err = response.json().get("error", {})
                logger.error(f"[MetaAds] API Error {err.get('code')}: {err.get('message')}")
                # Nếu là throttle (rate limit), Meta thường báo code 613 hoặc 17
                if err.get('code') in [613, 17, 32]:
                    logger.warning("[MetaAds] Đang bị Rate Limit. Vui lòng chờ vài phút rồi thử lại.")
                return []
            else:
                logger.error(f"[MetaAds] HTTP {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"[MetaAds] Lỗi kết nối: {e}")
            return []

    def extract_ad_content(self, raw_ad: Dict) -> Dict:
        """Trích xuất Text (Copywriting) từ raw_ad."""
        bodies = raw_ad.get("ad_creative_bodies", [])
        body_text = bodies[0] if bodies else ""
        
        titles = raw_ad.get("ad_creative_link_titles", [])
        title_text = titles[0] if titles else ""
        
        platforms = raw_ad.get("publisher_platforms", [])
        
        return {
            "ad_id": raw_ad.get("id"),
            "page_name": raw_ad.get("page_name"),
            "creation_time": raw_ad.get("ad_creation_time"),
            "primary_text": body_text,
            "headline": title_text,
            "platforms": ", ".join(platforms),
            "snapshot_url": raw_ad.get("ad_snapshot_url")
        }

    def download_media(self, snapshot_url: str, output_dir: str) -> Optional[str]:
        """
        Meta API chính thức KHÔNG cung cấp raw mp4/jpg link để tránh vi phạm bản quyền.
        Họ chỉ cấp `ad_snapshot_url` (Link dạng webpage).
        Để lấy video thực tế từ URL này, ta cần dùng trình duyệt ẩn danh (Playwright) 
        để cào (scrape) thẻ <video> hoặc dùng yt-dlp.
        Ở đây ta giả lập hàm tải (Trong thực tế cần cài yt-dlp hoặc Playwright).
        """
        logger.warning("[MetaAds] Tính năng tải Media trực tiếp từ Snapshot URL cần cấu hình Playwright/yt-dlp.")
        # Placeholder cho việc tải media
        return None
