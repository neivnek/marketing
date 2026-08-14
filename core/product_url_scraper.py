"""
====================================================================
  Product URL Scraper
  File: core/product_url_scraper.py
====================================================================
Lấy ý tưởng từ theadtya/ai-video-ad-generator.
Cào thông tin sản phẩm từ bất kỳ URL nào (Shopee, Lazada, Amazon,
website cửa hàng...) bằng Python requests + Gemini để parse HTML.
Hoàn toàn miễn phí, không cần Node.js, không cần OpenAI.
"""

import os
import re
import logging
import requests
import tempfile
from typing import Optional
from urllib.parse import urlparse
from core.gemini_pool import get_pooled_client

logger = logging.getLogger(__name__)

# Headers giả lập trình duyệt để không bị block
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """Tải HTML từ URL với nhiều user-agent fallback, trả về None nếu thất bại."""
    parsed = urlparse(url)
    domain = parsed.netloc

    headers_list = [
        # Chrome giả lập
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": f"https://www.google.com/search?q={domain}",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
        # Firefox giả lập
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.8,en-US;q=0.5,en;q=0.3",
        },
    ]
    session = requests.Session()
    for headers in headers_list:
        try:
            resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code in (403, 503, 429):
                logger.warning(f"[URLScraper] Trang bị chặn ({resp.status_code}): {domain}")
                continue
            else:
                logger.warning(f"[URLScraper] HTTP {resp.status_code}: {url}")
                return resp.text  # Trả về dù có lỗi để Gemini thử parse
        except requests.exceptions.Timeout:
            logger.warning(f"[URLScraper] Timeout khi tải {url}")
        except Exception as e:
            logger.warning(f"[URLScraper] Không tải được {url}: {e}")

    return None


def _extract_text_from_html(html: str) -> str:
    """Loại bỏ toàn bộ HTML tags, chỉ giữ lại văn bản thuần."""
    # Xóa scripts và style
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Xóa tất cả các HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Gộp khoảng trắng thừa
    text = re.sub(r"\s+", " ", text).strip()
    # Giới hạn độ dài để không vượt ngưỡng token của Gemini
    return text[:8000]


def _find_first_image_url(html: str, base_url: str) -> Optional[str]:
    """Tìm URL ảnh sản phẩm đầu tiên trong HTML."""
    # Tìm tất cả các thẻ img có src
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    for img in imgs:
        # Loại bỏ icon nhỏ và placeholder
        if any(skip in img.lower() for skip in ["icon", "logo", "pixel", "1x1", "blank", "data:image"]):
            continue
        # Ưu tiên ảnh có kích thước lớn
        if any(size in img for size in ["800", "1000", "1200", "large", "original", "full"]):
            if img.startswith("http"):
                return img
    # Nếu không tìm được ảnh lớn, lấy ảnh đầu tiên hợp lệ
    for img in imgs:
        if img.startswith("http") and not any(skip in img.lower() for skip in ["icon", "logo", "pixel", "1x1"]):
            return img
    return None


def _download_image(img_url: str, save_dir: str = "temp") -> Optional[str]:
    """Tải ảnh về máy và trả về đường dẫn file local."""
    os.makedirs(save_dir, exist_ok=True)
    try:
        resp = requests.get(img_url, headers=BROWSER_HEADERS, timeout=10, stream=True)
        resp.raise_for_status()
        # Xác định extension
        ext = ".jpg"
        content_type = resp.headers.get("Content-Type", "")
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        # Lưu file
        tmp = tempfile.NamedTemporaryFile(dir=save_dir, suffix=ext, delete=False)
        for chunk in resp.iter_content(8192):
            tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.warning(f"[URLScraper] Không tải được ảnh {img_url}: {e}")
        return None


def _parse_with_gemini(page_text: str, url: str) -> dict:
    """
    Dùng Gemini Flash để đọc văn bản trang HTML và trích xuất
    thông tin sản phẩm có cấu trúc (tên, giá, mô tả, tính năng).
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("[URLScraper] Thiếu GEMINI_API_KEY")
        return {}

    try:
        from google import genai
        from google.genai import types

        client = get_pooled_client(api_key=api_key)
        prompt = f"""Bạn là trợ lý phân tích trang web thương mại điện tử.
Dưới đây là nội dung văn bản cào được từ trang: {url}

---
{page_text}
---

Hãy trích xuất thông tin sản phẩm chính từ văn bản trên và trả về JSON thuần (không markdown):
{{
  "product_name": "Tên sản phẩm đầy đủ",
  "price": "Giá hiển thị (kèm đơn vị tiền tệ)",
  "short_description": "Mô tả ngắn sản phẩm trong 1-2 câu",
  "key_features": ["Tính năng 1", "Tính năng 2", "Tính năng 3"],
  "target_audience": "Đối tượng khách hàng phù hợp",
  "pain_points": ["Vấn đề sản phẩm giải quyết 1", "Vấn đề 2"]
}}

Nếu không tìm thấy thông tin nào, điền chuỗi rỗng hoặc mảng rỗng."""

        response = None
        for model in ["gemini-3.6-flash", "gemini-flash-latest", "gemini-2.0-flash"]:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=2048,
                        response_mime_type="application/json",
                    ),
                )
                if response and response.text:
                    break
            except Exception:
                continue

        if not response or not response.text:
            return {}

        raw = response.text.strip()
        # Loại bỏ markdown nếu có
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        import json
        return json.loads(raw.strip())

    except Exception as e:
        logger.error(f"[URLScraper] Lỗi Gemini parse: {e}")
        return {}


def scrape_product_from_url(url: str) -> dict:
    """
    Hàm chính: Cào thông tin sản phẩm từ URL bất kỳ.

    Trả về dict:
    {
        "product_name": str,
        "price": str,
        "short_description": str,
        "key_features": list[str],
        "target_audience": str,
        "pain_points": list[str],
        "image_path": str | None,   # Đường dẫn ảnh local đã tải về
        "source_url": str
    }
    """
    logger.info(f"[URLScraper] Bắt đầu cào: {url}")

    # 1. Tải HTML
    html = _fetch_html(url)
    if not html:
        return {"error": f"Không thể tải trang: {url}", "source_url": url}

    # 2. Tìm ảnh sản phẩm và tải về
    img_url = _find_first_image_url(html, url)
    image_path = None
    if img_url:
        logger.info(f"[URLScraper] Tìm thấy ảnh: {img_url[:80]}...")
        image_path = _download_image(img_url)

    # 3. Trích xuất văn bản thuần
    page_text = _extract_text_from_html(html)

    # 4. Dùng Gemini phân tích
    logger.info("[URLScraper] Đang dùng Gemini phân tích nội dung trang...")
    product_info = _parse_with_gemini(page_text, url)

    # 5. Gộp kết quả
    result = {
        "product_name": product_info.get("product_name", ""),
        "price": product_info.get("price", ""),
        "short_description": product_info.get("short_description", ""),
        "key_features": product_info.get("key_features", []),
        "target_audience": product_info.get("target_audience", "Khách hàng phổ thông"),
        "pain_points": product_info.get("pain_points", []),
        "image_path": image_path,
        "source_url": url,
    }

    logger.info(f"[URLScraper] Đã cào xong: {result.get('product_name', 'Không rõ tên')}")
    return result
