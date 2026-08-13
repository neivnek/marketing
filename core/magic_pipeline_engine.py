import os
import shutil
import logging
import traceback
from typing import Generator, Tuple, Optional, List, Dict, Any

logger = logging.getLogger(__name__)

def _yield_err(msg: str):
    logger.error(msg)
    return msg, None

def generate_magic_storyboard(
    image_path: str,
    target_audience: str,
    brand_tone: str,
    language: str = "Tiếng Việt",
    duration_mode: str = "Vừa (~30s)",
    style_profile: Optional[Dict] = None,
) -> Generator[Tuple[str, Optional[List[Dict]]], None, None]:
    """
    BƯỚC 1: Phân tích ảnh -> Cào B-roll -> Tạo Storyboard
    Yields (log_message, storyboard_or_None)
    """
    # Xử lý độ dài
    if "15s" in duration_mode:
        num_scenes = 3
        max_clips = 3
        target_dur = 15
    elif "60s" in duration_mode:
        num_scenes = 12
        max_clips = 12
        target_dur = 60
    else:
        num_scenes = 6
        max_clips = 6
        target_dur = 30

    yield "🌟 BƯỚC 1/2: Gemini Vision đang đọc ảnh sản phẩm...", None

    from core.product_intelligence import run_product_intelligence
    api_key = os.getenv("GEMINI_API_KEY", "")
    product_name = "Sản phẩm"
    try:
        identity, research, _ = run_product_intelligence(
            image_path=image_path,
            api_key=api_key,
            product_name="",
            force_refresh=True,
        )
        product_name = (identity.name_guess or "Sản phẩm").strip()
        yield f"✅ Nhận diện: {product_name}", None
    except Exception as e:
        yield f"⚠️ Gemini Vision lỗi ({e}), dùng tên mặc định.", None

    yield f"📦 Đang cào tối đa {max_clips} video B-roll cho '{product_name}'...", None
    generic_broll_dir = "assets/local_broll/generic"
    os.makedirs(generic_broll_dir, exist_ok=True)
    raw_brolls = []
    try:
        from core.stockpile_broll_curator import curate_and_download_broll
        raw_brolls = curate_and_download_broll(keyword=product_name, max_clips=max_clips)
        yield f"✅ Đã cào {len(raw_brolls)} video B-roll.", None
    except Exception as e:
        yield f"⚠️ Không cào được video ({e}).", None

    yield "🧹 Đang xóa logo/watermark TikTok...", None
    cleaned_count = 0
    try:
        from core.logo_remover import remove_video_logo
        for i, raw_vid in enumerate(raw_brolls):
            if not os.path.isfile(raw_vid): continue
            out_clean = f"temp/magic_clean_{i}.mp4"
            clean_vid = remove_video_logo(raw_vid, out_clean, mode="auto_tiktok")
            dest = os.path.join(generic_broll_dir, f"magic_broll_{i}.mp4")
            src = clean_vid if (clean_vid and os.path.isfile(clean_vid)) else raw_vid
            if os.path.isfile(src):
                shutil.copy(src, dest)
                cleaned_count += 1
    except Exception as e:
        yield f"⚠️ Logo remover lỗi ({e}).", None

    yield f"✅ Đã làm sạch {cleaned_count} video.", None

    yield f"📝 Gemini đang viết kịch bản {num_scenes} phân cảnh (tổng ~{target_dur}s)...", None
    storyboard = []
    try:
        from core.scene_machine_engine import generate_scene_machine_storyboard
        storyboard = generate_scene_machine_storyboard(
            product_image_path=image_path,
            product_name=product_name,
            target_audience=target_audience,
            brand_tone=brand_tone,
            num_scenes=num_scenes,
            language=language,
            target_duration_sec=target_dur,
            style_profile=style_profile,
        )
        if not storyboard:
            yield "❌ Không tạo được Storyboard.", None
            return
        yield f"✅ Đã tạo kịch bản xong! Vui lòng chỉnh sửa ở bảng bên dưới.", storyboard
    except Exception as e:
        yield f"❌ Lỗi Storyboard:\n{traceback.format_exc()}", None

def render_magic_video(
    storyboard: List[Dict],
    image_path: str,
    language: str = "Tiếng Việt",
    voice_name: str = "",
    tts_rate: str = "+0%",
) -> Generator[Tuple[str, Optional[str]], None, None]:
    """
    BƯỚC 2: Từ Storyboard (đã chỉnh sửa) -> Render ra video
    Yields (log_message, video_path_or_None)
    """
    yield "🚀 BƯỚC 2/2: Đang render video (TTS + hiệu ứng + ghép cảnh)...", None

    try:
        from core.scene_machine_engine import render_scene_machine_video
        product_name = "scene_machine"
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in product_name)[:30]
        out_path = f"output/magic_{safe_name}.mp4"
        os.makedirs("output", exist_ok=True)

        res = render_scene_machine_video(
            storyboard=storyboard,
            product_image_path=image_path,
            output_path=out_path,
            temp_dir="temp/magic_scenes",
            language=language,
            voice_name=voice_name,
            tts_rate=tts_rate,
        )

        if res and os.path.isfile(res):
            yield f"🎉 HOÀN TẤT! Video đã xuất: {res}", res
        else:
            yield "❌ Render thất bại. Không có file output nào.", None
    except Exception as e:
        yield f"❌ Lỗi render:\n{traceback.format_exc()}", None

# Giữ nguyên bản gốc cho tương thích ngược
def run_magic_pipeline(
    image_path: str,
    target_audience: str,
    brand_tone: str,
    language: str = "Tiếng Việt",
    voice_name: str = "",
    tts_rate: str = "+0%",
    duration_mode: str = "Vừa (~30s)",
    style_profile: Optional[Dict] = None,
) -> Generator[Tuple[str, Optional[str]], None, None]:
    gen1 = generate_magic_storyboard(image_path, target_audience, brand_tone, language, duration_mode, style_profile)
    storyboard = None
    for log, obj in gen1:
        if isinstance(obj, list):
            storyboard = obj
            yield log, None
        else:
            yield log, None
    if storyboard:
        gen2 = render_magic_video(storyboard, image_path, language, voice_name, tts_rate)
        for log, vid in gen2:
            yield log, vid
