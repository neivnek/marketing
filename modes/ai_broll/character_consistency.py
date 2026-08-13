import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

def build_consistent_scene_set(
    product_image_path: str,
    script_segments: List[Dict],
    style_suffix: str = "cinematic product shot, 4k resolution, photorealistic, beautiful lighting"
) -> List[Dict]:
    """
    Sinh các lệnh prompt nhất quán về mặt hình ảnh (character/product consistency).
    Dành cho Mode 11 (AI Broll).
    
    script_segments mẫu:
    [
        {"id": 1, "visual_hint": "hand holding the product"},
        {"id": 2, "visual_hint": "product glowing in dark"}
    ]
    """
    tasks_data = []
    
    for seg in script_segments:
        base_hint = seg.get("visual_hint", "product in focus")
        
        # Cú pháp @product (tùy thuộc vào model Flow/Whisk quy định)
        # Thường là: "@reference <hành động/bối cảnh>"
        prompt = f"@product {base_hint}, {style_suffix}"
        
        tasks_data.append({
            "prompt": prompt,
            "reference_image": product_image_path,
            "segment_id": seg.get("id", 0)
        })
        
    return tasks_data
