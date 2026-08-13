import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Cache các key đã bị lỗi 429 trong session hiện tại để không thử lại vô ích
_EXHAUSTED_KEYS = set()

def get_all_api_keys() -> List[str]:
    keys = []
    # Key chính
    primary = os.getenv("GEMINI_API_KEY")
    if primary and primary.strip(): 
        keys.append(primary.strip())
    
    # Các key phụ (GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...)
    for i in range(1, 20):
        val = os.getenv(f"GEMINI_API_KEY_{i}")
        if val and val.strip() and val.strip() not in keys:
            keys.append(val.strip())
    
    return keys

def generate_content_with_pool(
    prompt_contents: list, 
    config=None, 
    fallback_models: Optional[List[str]] = None
):
    """
    Hàm gọi Gemini thông minh: Tự động lặp qua các API Key và lặp qua các Model.
    Nếu dính lỗi 429 Quota Exceeded, tự động chuyển sang API Key tiếp theo trong hồ.
    """
    from google import genai
    from google.genai.errors import APIError, ClientError
    
    keys = get_all_api_keys()
    if not keys:
        raise ValueError("❌ Chưa cấu hình GEMINI_API_KEY nào trong file .env!")
        
    models_to_try = fallback_models or [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-flash-latest"
    ]
    
    # Nếu tất cả các Key đều đã bị đánh dấu là hết quota trong session này,
    # ta sẽ xóa cache đi để thử lại, vì có thể quota (phút/ngày) đã được Google reset.
    if all(k in _EXHAUSTED_KEYS for k in keys):
        logger.warning("[API Pool] Tất cả Key đều từng bị 429. Xóa bộ nhớ tạm để thử lại...")
        _EXHAUSTED_KEYS.clear()

    last_exception = None
    
    for key in keys:
        if key in _EXHAUSTED_KEYS:
            continue
            
        client = genai.Client(api_key=key)
        key_masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "UNK"
        
        first_model_exception = None
        for m in models_to_try:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt_contents,
                    config=config
                )
                if response and response.text:
                    return response
            except (APIError, ClientError) as e:
                err_msg = str(e)
                if "429" in err_msg or "Quota" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    logger.warning(f"[API Pool] Key {key_masked} bị cạn Quota (429). Chuyển sang Key tiếp theo!")
                    _EXHAUSTED_KEYS.add(key)
                    last_exception = e
                    break # Break vòng lặp model, nhảy sang Key tiếp theo
                else:
                    logger.warning(f"[API Pool] Model {m} failed with error: {err_msg}")
                    if first_model_exception is None:
                        first_model_exception = e
                    continue
            except Exception as e:
                logger.warning(f"[API Pool] Model {m} unexpected error: {e}")
                if first_model_exception is None:
                    first_model_exception = e
                continue
                
        # Nếu đã thử hết các model mà vẫn lỗi (nhưng không phải 429), ta ưu tiên ném lỗi của model đầu tiên
        if first_model_exception:
            last_exception = first_model_exception
                
    if last_exception:
        err_str = str(last_exception)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            # Tự động chuyển sang Groq khi Gemini hết quota
            logger.warning("[API Pool] Gemini hết quota → Thử chuyển sang Groq AI (miễn phí)...")
            groq_result = _try_groq_fallback(prompt_contents)
            if groq_result:
                return groq_result
            raise RuntimeError(
                "❌ Gemini hết quota VÀ Groq cũng thất bại. "
                "Thêm GEMINI_API_KEY_2 hoặc GROQ_API_KEY vào file .env!"
            )
        raise last_exception

    raise RuntimeError("❌ Không có phản hồi từ bất kỳ API Key nào!")


def _try_groq_fallback(prompt_contents: list) -> object:
    """
    Thử dùng Groq AI thay thế khi Gemini hết quota.
    Tự động chuyển đổi định dạng prompt từ Gemini sang Groq.
    """
    try:
        from core.groq_client import generate_content_with_groq, is_groq_available
        if not is_groq_available():
            logger.info("[API Pool] Groq không khả dụng (chưa cài thư viện hoặc chưa có key).")
            return None

        # Trích xuất text từ prompt_contents của Gemini
        if isinstance(prompt_contents, list):
            combined = " ".join(
                p if isinstance(p, str) else (p.get("text", "") if isinstance(p, dict) else str(p))
                for p in prompt_contents
            )
        else:
            combined = str(prompt_contents)

        text = generate_content_with_groq(
            prompt=combined,
            system_prompt="You are a professional advertising copywriter and video script writer.",
        )
        if not text:
            return None

        # Trả về object giả lập response của Gemini để code cũ dùng được
        class _FakeResponse:
            def __init__(self, t: str):
                self.text = t
        logger.info("[API Pool] ✓ Groq fallback thành công!")
        return _FakeResponse(text)

    except Exception as e:
        logger.warning(f"[API Pool] Groq fallback thất bại: {e}")
        return None
