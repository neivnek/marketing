from typing import List, Dict, Optional
import logging

from .character_consistency import build_consistent_scene_set
from .generation_queue import generate_batch_async

logger = logging.getLogger(__name__)

def generate_ai_broll_set(
    product_image_path: str,
    script_segments: List[Dict],
    style_suffix: str = "cinematic product shot"
) -> List[Optional[str]]:
    """
    Điểm vào (Entry point) chính cho Mode 11.
    Tạo ra một danh sách đường dẫn tới video B-roll sinh bằng AI.
    
    script_segments: list các dict chứa 'id' và 'visual_hint'.
    Trả về: List các đường dẫn file .mp4, vị trí nào sinh lỗi sẽ là None.
    """
    logger.info(f"[AIBroll] Bắt đầu sinh {len(script_segments)} clips cho sản phẩm: {product_image_path}")
    
    # 1. Tạo batch data
    tasks_data = build_consistent_scene_set(product_image_path, script_segments, style_suffix)
    
    # 2. Đẩy qua hàng đợi async Playwright automation
    # Sẽ tự động chia việc ra cho các account trong pool rảnh rỗi.
    results = generate_batch_async(tasks_data)
    
    success_count = sum(1 for r in results if r is not None)
    logger.info(f"[AIBroll] Hoàn thành. Thành công {success_count}/{len(tasks_data)} clips.")
    
    return results
