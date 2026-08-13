"""
====================================================================
  Video Assembly Engine
  File: core/video_assembly_engine.py
====================================================================
Handles stitching together a single existing video clip (e.g. from Auto-Discovery) 
with generated TTS, subtitles, music, and optionally removing logos.
"""

import os
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

def assemble_existing_video(
    video_path: str,
    product_name: str,
    benefits: list,
    output_path: str,
    temp_dir: str = "temp/assembly"
) -> Optional[str]:
    """
    1. Viết kịch bản nhanh dựa trên product_name và benefits.
    2. Gọi tts_engine tạo giọng đọc.
    3. Xóa logo/watermark trên video_path bằng logo_remover.
    4. Trộn (Mute audio gốc) -> Thêm nhạc nền -> Phụ đề.
    """
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Imports
    from core.logo_remover import remove_video_logo
    from core.tts_engine import generate_tts
    from core.subtitle_gen import generate_subtitles
    from core.music_library import mix_background_music
    from core.ffmpeg_utils import get_video_duration
    
    # 0. Check video
    if not os.path.exists(video_path):
        logger.error(f"[Assembly] Không tìm thấy video gốc: {video_path}")
        return None
        
    duration = get_video_duration(video_path)
    if duration <= 0:
        duration = 15.0 # fallback
        
    # 1. Viết kịch bản ngắn (15-20 từ) phù hợp với video (Gemini)
    api_key = os.getenv("GEMINI_API_KEY", "")
    script = f"Sản phẩm {product_name} cực kỳ tiện lợi. "
    if benefits:
        script += f"{benefits[0]}. "
    script += "Mua ngay hôm nay để nhận ưu đãi!"
    
    if api_key:
        from google import genai
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"Viết 1 đoạn kịch bản lồng tiếng siêu ngắn (dưới 30 từ, đọc khoảng {int(duration)} giây) cho quảng cáo TikTok về sản phẩm: {product_name}. Lợi ích: {', '.join(benefits[:2])}. Chỉ trả về nội dung lời thoại."
            resp = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
            if resp and resp.text:
                script = resp.text.strip().replace('"', '')
        except Exception as e:
            logger.warning(f"[Assembly] Lỗi sinh kịch bản Gemini, dùng mặc định. {e}")
            
    # 2. Sinh giọng đọc TTS
    tts_audio = os.path.join(temp_dir, "assembly_tts.mp3")
    generate_tts(text=script, output_path=tts_audio, voice="vi-VN-HoaiMyNeural")
    
    # 3. Làm sạch Video (Xóa logo)
    clean_video = os.path.join(temp_dir, "assembly_clean.mp4")
    # Sử dụng mode blur để làm mờ các góc an toàn
    cleaned = remove_video_logo(video_path, clean_video, mode="auto_tiktok")
    if not cleaned or not os.path.exists(clean_video):
        clean_video = video_path # Fallback to original
        
    # 4. Mute âm thanh gốc, scale/crop về 9:16 và lồng TTS
    # Filter: crop to 9:16 if needed, or pad to 9:16
    muted_tts_video = os.path.join(temp_dir, "assembly_muted_tts.mp4")
    
    vf_filter = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    
    cmd_mute = [
        "ffmpeg", "-y",
        "-i", clean_video,
        "-i", tts_audio,
        "-map", "0:v:0",   # Take video from 1st input
        "-map", "1:a:0",   # Take audio from 2nd input (TTS)
        "-vf", vf_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac",
        "-shortest",       # Cut to shortest (usually TTS or Video)
        "-pix_fmt", "yuv420p",
        muted_tts_video
    ]
    subprocess.run(cmd_mute, capture_output=True)
    
    if not os.path.exists(muted_tts_video):
        logger.error("[Assembly] Lỗi ghép TTS và Mute âm thanh.")
        return None
        
    # 5. Phụ đề (Subtitle)
    subbed_video = os.path.join(temp_dir, "assembly_subbed.mp4")
    generate_subtitles(muted_tts_video, tts_audio, subbed_video, style="classic_box")
    if not os.path.exists(subbed_video):
        subbed_video = muted_tts_video
        
    # 6. Nhạc nền (Music)
    dur = get_video_duration(subbed_video)
    try:
        mix_background_music(subbed_video, output_path, energy="high", duration_sec=dur, temp_dir=temp_dir)
    except Exception as e:
        logger.warning(f"[Assembly] Nhạc nền lỗi: {e}. Copy video không nhạc.")
        import shutil
        shutil.copy(subbed_video, output_path)
    
    if os.path.exists(output_path):
        logger.info(f"[Assembly] Đã xuất video hoàn chỉnh: {output_path}")
        return output_path
    
    return None
