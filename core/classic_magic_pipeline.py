import os
import shutil
import logging
from typing import Generator, Tuple, Optional
from core.classic_scene_machine import generate_classic_storyboard, render_classic_video
from core.logo_remover import remove_video_logo

logger = logging.getLogger(__name__)

def run_classic_pipeline(
    image_path: str,
    language: str = "Tiếng Việt",
    voice_name: str = "",
    tts_rate: str = "+0%",
) -> Generator[Tuple[str, Optional[str]], None, None]:
    """
    Bản gốc:
    1. Đọc ảnh (lấy tên sp).
    2. Tải 8 B-roll theo tên.
    3. Tạo storyboard (8 cảnh, prompt cơ bản).
    4. Render video (dùng 8 B-roll vừa tải, không có API keys, không gọi AI broll).
    """
    yield "🌟 BƯỚC 1/3: Phân tích ảnh sản phẩm...", None

    from core.product_intelligence import run_product_intelligence
    api_key = os.getenv("GEMINI_API_KEY", "")
    product_name = "Sản phẩm"
    try:
        identity, _, _ = run_product_intelligence(
            image_path=image_path,
            api_key=api_key,
            product_name="",
            force_refresh=True,
        )
        product_name = (identity.name_guess or "Sản phẩm").strip()
        yield f"✅ Nhận diện: {product_name}", None
    except Exception as e:
        yield f"⚠️ Lỗi phân tích ({e}), dùng tên mặc định.", None

    yield f"📦 BƯỚC 2/3: Cào 8 video B-roll cho '{product_name}'...", None
    generic_broll_dir = "assets/local_broll/generic"
    os.makedirs(generic_broll_dir, exist_ok=True)
    raw_brolls = []
    try:
        from core.stockpile_broll_curator import curate_and_download_broll
        raw_brolls = curate_and_download_broll(keyword=product_name, max_clips=8)
        yield f"✅ Đã cào {len(raw_brolls)} video B-roll.", None
    except Exception as e:
        yield f"⚠️ Không cào được video ({e}).", None

    cleaned_count = 0
    try:
        for i, raw_vid in enumerate(raw_brolls):
            if not os.path.isfile(raw_vid): continue
            out_clean = f"temp/classic_clean_{i}.mp4"
            clean_vid = remove_video_logo(raw_vid, out_clean, mode="auto_tiktok")
            dest = os.path.join(generic_broll_dir, f"magic_broll_{i}.mp4")
            src = clean_vid if (clean_vid and os.path.isfile(clean_vid)) else raw_vid
            if os.path.isfile(src):
                shutil.copy(src, dest)
                cleaned_count += 1
    except Exception as e:
        pass

    yield f"📝 Đang viết kịch bản 8 phân cảnh...", None
    try:
        storyboard = generate_classic_storyboard(
            product_image_path=image_path,
            product_name=product_name,
            target_audience="Khách hàng Việt Nam",
            brand_tone="Thuyết phục, Hiện đại, Chân thực",
            num_scenes=8,
            language=language,
        )
    except Exception as e:
        yield f"❌ Lỗi kịch bản:\n{e}", None
        return

    if not storyboard:
        yield "❌ Không tạo được kịch bản.", None
        return
    
    yield "🎬 BƯỚC 3/3: Đang ghép nối video (Vui lòng đợi)...", None
    try:
        final_video = render_classic_video(
            storyboard=storyboard,
            product_image_path=image_path,
            output_path="output/classic_ad.mp4",
            language=language,
            voice_name=voice_name,
            tts_rate=tts_rate
        )
        if final_video:
            yield f"🎉 HOÀN TẤT! Video đã xuất: {final_video}", final_video
        else:
            yield "❌ Render thất bại.", None
    except Exception as e:
        yield f"❌ Lỗi render:\n{traceback.format_exc()}", None
