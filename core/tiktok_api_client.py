import os
import logging
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class TikTokAdClient:
    """
    Client kết nối TikTok Commercial Content / Display API.
    Yêu cầu: ACCESS_TOKEN từ TikTok for Developers.
    Lưu ý: Môi trường Sandbox sẽ bị hạn chế kết quả so với Production.
    """
    def __init__(self, access_token: str = None):
        self.access_token = access_token or os.getenv("TIKTOK_AD_ACCESS_TOKEN", "")
        # Dùng endpoint Research API (Ad Library)
        self.base_url = "https://open.tiktokapis.com/v2/research/adlib/ad/query/"
        
    def search_ads(self, 
                   keyword: str, 
                   country: str = "VN",
                   limit: int = 10) -> List[Dict]:
        """
        Truy vấn quảng cáo trên TikTok theo từ khóa.
        """
        if not self.access_token:
            logger.error("[TikTokAds] Thiếu TIKTOK_AD_ACCESS_TOKEN. Vui lòng thêm vào file .env")
            return []
            
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Payload tham khảo cho TikTok Ad Library API
        payload = {
            "filters": {
                "ad_published_date_range": {
                    "min": "2024-01-01",
                    "max": "2026-12-31"
                },
                "country_code": country,
                "keyword": keyword
            },
            "search_term": keyword,
            "max_count": limit
        }
        
        try:
            logger.info(f"[TikTokAds] Đang tìm quảng cáo TikTok với từ khóa: '{keyword}'...")
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                # Tùy thuộc vào việc App đang ở Sandbox hay Prod, dữ liệu trả về sẽ khác nhau.
                ads = data.get("data", {}).get("ads", [])
                if not ads:
                    logger.warning("[TikTokAds] Không tìm thấy quảng cáo hoặc App của bạn đang ở Sandbox (bị giới hạn dữ liệu).")
                return ads
            else:
                logger.error(f"[TikTokAds] HTTP {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"[TikTokAds] Lỗi kết nối TikTok API: {e}")
            return []

    def extract_ad_content(self, raw_ad: Dict) -> Dict:
        """Trích xuất dữ liệu từ raw_ad của TikTok."""
        return {
            "ad_id": raw_ad.get("id", ""),
            "brand_name": raw_ad.get("advertiser_name", ""),
            "primary_text": raw_ad.get("ad_text", ""), # Lời thoại / Caption
            "video_url": raw_ad.get("video_url", ""),  # TikTok đôi khi trả về video URL trực tiếp
            "thumbnail_url": raw_ad.get("image_url", ""),
            "landing_page": raw_ad.get("landing_page_url", "")
        }

    def download_media(self, video_url: str, output_path: str) -> bool:
        """
        TikTok API thỉnh thoảng cấp quyền tải video trực tiếp qua `video_url` nếu được Audit.
        """
        if not video_url:
            return False
            
        try:
            logger.info(f"[TikTokAds] Đang tải video từ TikTok...")
            response = requests.get(video_url, stream=True, timeout=30)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        f.write(chunk)
                logger.info(f"[TikTokAds] Đã tải video thành công: {output_path}")
                return True
            else:
                logger.error(f"[TikTokAds] Lỗi tải video: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[TikTokAds] Lỗi khi tải video TikTok: {e}")
            return False
