"""
====================================================================
  Pipeline v3.0
  File: core/groq_client.py — Groq AI Free Fallback Client
====================================================================

Groq là dịch vụ AI miễn phí với tốc độ siêu nhanh (nhanh hơn Gemini 3-5 lần).
Gói miễn phí: 14.400 lượt/ngày (hơn đủ dùng).
Model mặc định: llama-3.3-70b-versatile (mạnh ngang GPT-4)

Cách lấy API Key MIỄN PHÍ (5 phút):
  1. Vào https://console.groq.com/keys
  2. Đăng nhập bằng Google Account
  3. Bấm "Create API Key"
  4. Copy key có dạng gsk_xxxxx
  5. Thêm vào .env: GROQ_API_KEY=gsk_xxxxx
====================================================================
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Các model Groq miễn phí, sắp xếp từ mạnh nhất đến nhẹ nhất
GROQ_MODELS = [
    "llama-3.3-70b-versatile",    # Mạnh nhất, ngang GPT-4
    "llama-3.1-8b-instant",       # Siêu nhanh, nhẹ hơn
    "mixtral-8x7b-32768",         # Context window lớn
]

_EXHAUSTED_KEYS: set = set()


def get_groq_keys() -> list[str]:
    """Lấy tất cả Groq API keys từ .env (hỗ trợ nhiều key: GROQ_API_KEY, GROQ_API_KEY_2...)"""
    keys = []
    primary = os.getenv("GROQ_API_KEY", "").strip()
    if primary:
        keys.append(primary)
    for i in range(1, 10):
        k = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def generate_content_with_groq(
    prompt: str,
    system_prompt: str = "You are a professional advertising copywriter.",
    max_tokens: int = 2048,
    temperature: float = 0.8,
) -> Optional[str]:
    """
    Gọi Groq API để tạo nội dung. Tự động fallback qua nhiều key và model.

    Parameters
    ----------
    prompt        : Nội dung yêu cầu
    system_prompt : Vai trò của AI
    max_tokens    : Giới hạn output
    temperature   : Độ sáng tạo (0.0-1.0)

    Returns
    -------
    str  — Text phản hồi, hoặc None nếu tất cả đều thất bại
    """
    try:
        from groq import Groq
    except ImportError:
        logger.warning("[Groq] Thư viện 'groq' chưa được cài. Chạy: pip install groq")
        return None

    keys = get_groq_keys()
    if not keys:
        logger.warning("[Groq] Không tìm thấy GROQ_API_KEY trong .env — bỏ qua Groq.")
        return None

    # Reset exhausted keys nếu tất cả đều bị đánh dấu
    active_keys = [k for k in keys if k not in _EXHAUSTED_KEYS]
    if not active_keys:
        logger.info("[Groq] Tất cả key đã hết quota tạm thời. Reset cache...")
        _EXHAUSTED_KEYS.clear()
        active_keys = keys

    for key in active_keys:
        key_masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
        client = Groq(api_key=key)

        for model in GROQ_MODELS:
            try:
                logger.info(f"[Groq] Dùng model: {model} | Key: {key_masked}")
                completion = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                text = completion.choices[0].message.content
                if text and text.strip():
                    logger.info(f"[Groq] ✓ Thành công với model {model}")
                    return text.strip()

            except Exception as e:
                err = str(e)
                if "429" in err or "rate_limit" in err.lower() or "quota" in err.lower():
                    logger.warning(f"[Groq] Key {key_masked} hết quota (429). Thử key tiếp theo...")
                    _EXHAUSTED_KEYS.add(key)
                    break  # Chuyển sang key khác
                elif "model" in err.lower() or "not found" in err.lower():
                    logger.warning(f"[Groq] Model {model} không khả dụng, thử model khác...")
                    continue
                else:
                    logger.warning(f"[Groq] Lỗi không xác định từ model {model}: {err[:200]}")
                    continue

    logger.error("[Groq] Tất cả key và model đều thất bại.")
    return None


def is_groq_available() -> bool:
    """Kiểm tra nhanh xem Groq có sẵn sàng dùng không."""
    try:
        from groq import Groq  # noqa: F401
        return bool(get_groq_keys())
    except ImportError:
        return False
