import json
import logging
from PIL import Image
from typing import Dict, Optional

# Giả sử trong core.gemini_vision đã có hàm gọi Gemini (như ultimate_ad_pipeline.py hay dùng)
# Ở đây ta sẽ mock hoặc viết hàm gọi chuẩn.
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

from .visual_search_engine import VisualSearchEngine

logger = logging.getLogger(__name__)

# Khởi tạo instance toàn cục cho Visual Search
search_engine = VisualSearchEngine()

def extract_product_metadata_via_gemini(poster_image_path: str, api_key: str) -> Optional[Dict]:
    """
    Gọi Gemini Vision để lấy thông tin sản phẩm và Tọa độ Bounding Box (Bbox).
    """
    if not genai:
        logger.error("[VisionIndex] Thiếu thư viện google-genai.")
        return None

    try:
        client = genai.Client(api_key=api_key)
        
        prompt = """
        Ảnh này là 1 poster quảng cáo sản phẩm. Hãy phân tích và trả về CHUẨN JSON với cấu trúc sau:
        {
          "product_name": "Tên sản phẩm chính",
          "product_bbox": [x1, y1, x2, y2], 
          "detected_text_khmer": "Tất cả text Khmer trên poster",
          "detected_text_other": "Text tiếng khác",
          "key_claims": ["claim 1", "claim 2"],
          "category": "ngành hàng"
        }
        LƯU Ý QUAN TRỌNG: 
        - product_bbox là tọa độ KHUNG CHỮ NHẬT chứa RIÊNG sản phẩm (không tính chữ, nền rác, hay người mẫu).
        - Trả về tọa độ dưới dạng mảng [x_min, y_min, x_max, y_max] theo chuẩn pixel của ảnh.
        - Trả về ĐÚNG ĐỊNH DẠNG JSON, không bọc trong markdown (```json).
        """
        
        # Mở ảnh bằng Pillow
        img = Image.open(poster_image_path)
        
        response = None
        for m in ['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash', 'gemini-pro-latest']:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=[img, prompt],
                )
                if response and response.text:
                    break
            except Exception:
                continue

        if not response or not response.text:
            return None
            
        raw_text = response.text.strip()

        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3]
            
        return json.loads(raw_text)
        
    except Exception as e:
        logger.error(f"[VisionIndex] Lỗi khi gọi Gemini: {e}")
        return None

def validate_and_crop_bbox(image: Image.Image, bbox: list) -> Image.Image:
    """
    Xử lý fallback: Kiểm tra xem Bbox do Gemini trả về có hợp lệ không.
    Nếu sai, fallback về Center Crop (cắt 50% ở giữa ảnh).
    """
    width, height = image.size
    
    # 1. Check định dạng mảng
    if not isinstance(bbox, list) or len(bbox) != 4:
        logger.warning("[VisionIndex] Bbox không đúng 4 tham số. Dùng Fallback (Center crop).")
        return _fallback_center_crop(image)
        
    x1, y1, x2, y2 = bbox
    
    # 2. Check tính logic
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        logger.warning(f"[VisionIndex] Bbox {bbox} vượt quá kích thước ảnh {width}x{height}. Dùng Fallback.")
        return _fallback_center_crop(image)
        
    # 3. Check kích thước tối thiểu (phải > 5% diện tích)
    area = (x2 - x1) * (y2 - y1)
    total_area = width * height
    if area < 0.05 * total_area:
        logger.warning("[VisionIndex] Bbox quá nhỏ (< 5% ảnh). Khả năng crop nhầm. Dùng Fallback.")
        return _fallback_center_crop(image)
        
    # An toàn, tiến hành crop
    logger.info(f"[VisionIndex] Đã crop ảnh theo tọa độ: {bbox}")
    return image.crop((x1, y1, x2, y2))

def _fallback_center_crop(image: Image.Image) -> Image.Image:
    """Fallback: Cắt 50% diện tích ở chính giữa ảnh."""
    width, height = image.size
    x1 = int(width * 0.25)
    y1 = int(height * 0.25)
    x2 = int(width * 0.75)
    y2 = int(height * 0.75)
    return image.crop((x1, y1, x2, y2))

def process_uploaded_poster(poster_image_path: str, api_key: str) -> Dict:
    """
    Luồng hoàn chỉnh (2-Tier Pipeline):
    1. Trích xuất metadata và bbox qua Gemini
    2. Crop vùng sản phẩm
    3. Đưa crop vào Visual Search (ResNet50) để đối chiếu
    """
    # 1. Gọi Gemini
    metadata = extract_product_metadata_via_gemini(poster_image_path, api_key)
    if not metadata:
        return {"error": "Không thể phân tích ảnh qua Gemini."}
        
    bbox = metadata.get("product_bbox", [])
    
    try:
        # 2. Mở ảnh gốc và Crop
        img = Image.open(poster_image_path)
        cropped_product = validate_and_crop_bbox(img, bbox)
        
        # 3. Lưu crop và lưu Metadata vào SQLite
        product_name_safe = metadata.get("product_name", "Unknown").replace(" ", "_").replace("/", "")
        save_path = f"assets/product_db/crops/{product_name_safe}.jpg"
        cropped_product.save(save_path)
        logger.info(f"[VisionIndex] Đã lưu crop sạch vào: {save_path}")
        
        # Gọi engine để lưu metadata
        search_engine.save_metadata(
            name=metadata.get("product_name", "Unknown"),
            price=metadata.get("price", ""),  # Có thể Gemini không trả về price, ta mặc định rỗng
            claims=metadata.get("key_claims", []),
            image_path=save_path
        )
        
        # 4. Tìm kiếm ảnh tương tự (Ví dụ: tìm xem đã có B-roll nào giống cái này chưa)
        # Force refresh index do vừa add thêm ảnh
        search_engine.refresh_db_index()
        similar_images = search_engine.find_similar_images(cropped_product, threshold=0.85)
        metadata["similar_images_found"] = similar_images
        
        return metadata
        
    except Exception as e:
        logger.error(f"[VisionIndex] Lỗi quá trình xử lý Crop/Search: {e}")
        return {"error": str(e), "metadata_partial": metadata}
