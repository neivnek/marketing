import os
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Cache các key đã bị lỗi 429 trong session hiện tại để không thử lại vô ích
_EXHAUSTED_KEYS = set()

DEFAULT_MODELS: List[str] = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]


def get_all_api_keys(preferred_key: Optional[str] = None) -> List[str]:
    keys = []

    # Key do caller truyền vào (nếu có) luôn được thử trước
    if preferred_key and preferred_key.strip():
        keys.append(preferred_key.strip())

    # Key chính
    primary = os.getenv("GEMINI_API_KEY")
    if primary and primary.strip() and primary.strip() not in keys:
        keys.append(primary.strip())

    # Các key phụ (GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...)
    for i in range(1, 20):
        val = os.getenv(f"GEMINI_API_KEY_{i}")
        if val and val.strip() and val.strip() not in keys:
            keys.append(val.strip())

    return keys


# ──────────────────────────────────────────────
# Đọc thuộc tính config (GenerateContentConfig hoặc dict)
# ──────────────────────────────────────────────

def _cfg_get(config: Any, name: str, default=None):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def _is_quota_error(exc: Exception) -> bool:
    """
    Nhận diện lỗi hết quota. Kiểm tra theo nội dung lỗi chứ không theo class,
    vì SDK có thể bọc 429 trong nhiều loại exception khác nhau.
    """
    msg = str(exc)
    return any(k in msg for k in ("429", "Quota", "quota", "RESOURCE_EXHAUSTED", "rate limit"))


def _is_text_part(part: Any) -> bool:
    """Phần prompt có phải text thuần không (Groq chỉ nhận được text)."""
    if isinstance(part, str):
        return True
    if isinstance(part, dict):
        return set(part.keys()) <= {"text"} and isinstance(part.get("text"), str)
    return False


def generate_content_with_pool(
    prompt_contents: list,
    config=None,
    fallback_models: Optional[List[str]] = None,
    preferred_key: Optional[str] = None,
):
    """
    Hàm gọi Gemini thông minh: Tự động lặp qua các API Key và lặp qua các Model.
    Nếu dính lỗi 429 Quota Exceeded, tự động chuyển sang API Key tiếp theo trong hồ,
    và cuối cùng là chuyển sang Groq (miễn phí) nếu mọi key Gemini đều cạn quota.
    """
    from google import genai
    from google.genai.errors import APIError, ClientError

    keys = get_all_api_keys(preferred_key)
    if not keys:
        raise ValueError("❌ Chưa cấu hình GEMINI_API_KEY nào trong file .env!")

    models_to_try = fallback_models or DEFAULT_MODELS

    # Nếu tất cả các Key đều đã bị đánh dấu là hết quota trong session này,
    # ta sẽ xóa cache đi để thử lại, vì có thể quota (phút/ngày) đã được Google reset.
    if all(k in _EXHAUSTED_KEYS for k in keys):
        logger.warning("[API Pool] Tất cả Key đều từng bị 429. Xóa bộ nhớ tạm để thử lại...")
        _EXHAUSTED_KEYS.clear()

    last_exception = None
    saw_quota_error = False   # bất kỳ key nào dính 429 -> vẫn cho phép fallback Groq

    for key in keys:
        if key in _EXHAUSTED_KEYS:
            saw_quota_error = True
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
                logger.warning(f"[API Pool] Model {m} trả về phản hồi rỗng, thử model tiếp theo.")
            except (APIError, ClientError) as e:
                if _is_quota_error(e):
                    logger.warning(f"[API Pool] Key {key_masked} bị cạn Quota (429). Chuyển sang Key tiếp theo!")
                    _EXHAUSTED_KEYS.add(key)
                    last_exception = e
                    saw_quota_error = True
                    break # Break vòng lặp model, nhảy sang Key tiếp theo
                logger.warning(f"[API Pool] Model {m} failed with error: {e}")
                if first_model_exception is None:
                    first_model_exception = e
                continue
            except Exception as e:
                # 429 có thể tới dưới dạng exception khác (httpx, ServerError...) — vẫn phải nhận ra
                if _is_quota_error(e):
                    logger.warning(f"[API Pool] Key {key_masked} bị cạn Quota (429). Chuyển sang Key tiếp theo!")
                    _EXHAUSTED_KEYS.add(key)
                    last_exception = e
                    saw_quota_error = True
                    break
                logger.warning(f"[API Pool] Model {m} unexpected error: {e}")
                if first_model_exception is None:
                    first_model_exception = e
                continue

        # Nếu đã thử hết các model mà vẫn lỗi (nhưng không phải 429), ta ưu tiên ném lỗi của model đầu tiên
        if first_model_exception:
            last_exception = first_model_exception

    # Hết quota ở bất kỳ key nào -> thử Groq, kể cả khi lỗi cuối cùng không phải 429
    if saw_quota_error:
        logger.warning("[API Pool] Gemini hết quota → Thử chuyển sang Groq AI (miễn phí)...")
        groq_result = _try_groq_fallback(prompt_contents, config)
        if groq_result:
            return groq_result
        if last_exception:
            raise RuntimeError(
                "❌ Gemini hết quota VÀ Groq không dùng được. "
                "Thêm GEMINI_API_KEY_2 hoặc GROQ_API_KEY vào file .env! "
                f"(lỗi cuối: {last_exception})"
            )

    if last_exception:
        raise last_exception

    raise RuntimeError("❌ Không có phản hồi từ bất kỳ API Key nào!")


def _try_groq_fallback(prompt_contents: list, config=None) -> object:
    """
    Thử dùng Groq AI thay thế khi Gemini hết quota.

    Groq chỉ nhận text: nếu prompt có ảnh/video/file (multimodal) thì BỎ QUA fallback
    thay vì gửi lên chuỗi repr vô nghĩa của object.
    Nếu caller yêu cầu JSON (response_mime_type="application/json") thì bật JSON mode
    của Groq để `response.text` vẫn parse được bằng json.loads().
    """
    try:
        from core.groq_client import generate_content_with_groq, is_groq_available
        if not is_groq_available():
            logger.info("[API Pool] Groq không khả dụng (chưa cài thư viện hoặc chưa có key).")
            return None

        parts = prompt_contents if isinstance(prompt_contents, list) else [prompt_contents]

        # Groq không xử lý được ảnh/video — không fallback để tránh sinh nội dung bịa
        non_text = [p for p in parts if not _is_text_part(p)]
        if non_text:
            kinds = ", ".join(sorted({type(p).__name__ for p in non_text}))
            logger.warning(
                f"[API Pool] Bỏ qua Groq fallback: prompt có {len(non_text)} phần "
                f"không phải text ({kinds}). Groq chỉ nhận text."
            )
            return None

        combined = " ".join(p if isinstance(p, str) else p.get("text", "") for p in parts)
        if not combined.strip():
            return None

        # Chuyển các tham số tương ứng từ GenerateContentConfig sang Groq
        want_json = _cfg_get(config, "response_mime_type") == "application/json"

        system_prompt = "You are a professional advertising copywriter and video script writer."
        sys_instruction = _cfg_get(config, "system_instruction")
        if sys_instruction:
            if isinstance(sys_instruction, (list, tuple)):
                sys_instruction = " ".join(str(s) for s in sys_instruction)
            system_prompt = str(sys_instruction)

        kwargs = {}
        temperature = _cfg_get(config, "temperature")
        if temperature is not None:
            kwargs["temperature"] = float(temperature)
        max_tokens = _cfg_get(config, "max_output_tokens")
        if max_tokens:
            kwargs["max_tokens"] = int(max_tokens)

        text = generate_content_with_groq(
            prompt=combined,
            system_prompt=system_prompt,
            json_mode=want_json,
            **kwargs,
        )
        if not text:
            return None

        # Trả về object giả lập response của Gemini để code cũ dùng được
        class _FakeResponse:
            def __init__(self, t: str):
                self.text = t
        logger.info(f"[API Pool] ✓ Groq fallback thành công!{' (JSON mode)' if want_json else ''}")
        return _FakeResponse(text)

    except Exception as e:
        logger.warning(f"[API Pool] Groq fallback thất bại: {e}")
        return None


# ──────────────────────────────────────────────
# Drop-in thay cho genai.Client
# ──────────────────────────────────────────────

class PooledClient:
    """
    Thay thế `genai.Client` để mọi lời gọi đều đi qua pool:
    xoay vòng nhiều GEMINI_API_KEY -> fallback nhiều model -> fallback Groq.

    Dùng y hệt client gốc:
        client = get_pooled_client(api_key)
        resp   = client.models.generate_content(model="...", contents=[...], config=cfg)
    """

    class _Models:
        def __init__(self, api_key: Optional[str]):
            self._api_key = api_key

        def generate_content(self, model: Optional[str] = None, contents=None, config=None, **_ignored):
            models = None
            if model:
                # Model caller yêu cầu được ưu tiên, phần còn lại làm dự phòng
                models = [model] + [m for m in DEFAULT_MODELS if m != model]
            return generate_content_with_pool(
                prompt_contents=contents,
                config=config,
                fallback_models=models,
                preferred_key=self._api_key,
            )

    def __init__(self, api_key: Optional[str] = None):
        self.models = PooledClient._Models(api_key)


def get_pooled_client(api_key: Optional[str] = None) -> PooledClient:
    """Tạo client dùng chung pool key/model + Groq fallback."""
    return PooledClient(api_key)
