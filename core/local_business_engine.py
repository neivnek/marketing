import os
import re
import json
import logging
import traceback
import subprocess
from typing import Generator, Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)

LOCAL_AD_PROMPT = """Bạn là chuyên gia marketing địa phương (Local Marketing).
Tôi đang cần viết kịch bản video quảng cáo {target_duration_sec} giây cho một cửa hàng/tiệm vật lý.

Thông tin tiệm:
- Tên tiệm: {store_name}
- Địa chỉ: {address}
- Khuyến mãi/Đặc điểm: {promotions}
- Ngôn ngữ: {language}

Yêu cầu Kịch bản:
- Chia làm {num_scenes} phân cảnh (scenes). Tổng thời lượng ~{target_duration_sec}s.
- Cấu trúc: 
  + Cảnh đầu (Hook): Thu hút khách hàng địa phương (VD: "Góc quán xịn sò ở Quận 1...").
  + Giữa: Khoe điểm nổi bật/Khuyến mãi.
  + Cuối: Đọc rõ ĐỊA CHỈ và kêu gọi đến ngay.
- Chữ nổi (overlay_text): Rất ngắn gọn, cảnh cuối BẮT BUỘC phải hiện To & Rõ Địa Chỉ.

Trả về JSON thuần tuý (không markdown, không bọc trong ```json):
[
  {
    "scene_number": 1,
    "broll_keyword": "Không gian quán, mặt tiền tiệm",
    "voiceover_text": "Lên kịch bản tiếng {language}...",
    "duration_sec": 4.0,
    "overlay_text": "Chữ nổi bật"
  }
]
"""

def generate_local_storyboard(
    store_name: str,
    address: str,
    promotions: str,
    language: str,
    duration_sec: int,
) -> List[Dict]:
    from core.gemini_pool import generate_content_with_pool
    
    num_scenes = max(3, int(duration_sec / 5)) # Trung bình 5s 1 cảnh
    
    prompt = LOCAL_AD_PROMPT.format(
        store_name=store_name,
        address=address,
        promotions=promotions,
        language=language,
        target_duration_sec=duration_sec,
        num_scenes=num_scenes
    )
    
    try:
        response = generate_content_with_pool([prompt])
        if not response or not response.text:
            return []
            
        raw = response.text.strip()
        if raw.startswith("```json"): raw = raw[7:]
        if raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        
        data = json.loads(raw.strip())
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"[LocalEngine] Lỗi sinh kịch bản: {e}")
        return []

def render_local_video(
    storyboard: List[Dict],
    images: List[str],
    language: str,
    voice_name: str,
    tts_rate: str,
) -> Optional[str]:
    # Khá giống render_classic_video nhưng xử lý nhiều ảnh
    from core.tts_engine import generate_tts
    import subprocess
    
    temp_dir = "temp/local_ad"
    os.makedirs(temp_dir, exist_ok=True)
    out_video = "output/local_business_ad.mp4"
    
    concat_file = os.path.join(temp_dir, "concat.txt")
    scene_vids = []
    
    img_count = len(images) if images else 0
    
    for i, scene in enumerate(storyboard):
        dur = float(scene.get("duration_sec", 4.0))
        vo_text = scene.get("voiceover_text", "")
        overlay = scene.get("overlay_text", "")
        
        # 1. TTS
        tts_path = os.path.join(temp_dir, f"tts_{i}.mp3")
        tts_dur = dur
        if vo_text:
            tts_ok = generate_tts(vo_text, tts_path, voice_name, tts_rate)
            if tts_ok:
                try:
                    # Lấy độ dài TTS thực tế để chỉnh video
                    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", tts_path], capture_output=True, text=True)
                    actual_dur = float(res.stdout.strip())
                    if actual_dur > 0:
                        tts_dur = actual_dur + 0.5
                except:
                    pass
        else:
            tts_path = None

        # 2. Xử lý hình ảnh (Ken Burns)
        scene_img = images[i % img_count] if img_count > 0 else None
        out_scene = os.path.join(temp_dir, f"scene_{i}.mp4")
        
        vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        if overlay:
            safe_ov = overlay.replace("'", "\\'").replace(":", "\\:")
            # Giữ overlay ở giữa màn hình
            vf += f",drawtext=text='{safe_ov}':fontfile=assets/fonts/NotoSansKhmer-Bold.ttf:fontcolor=white:fontsize=64:x=(w-text_w)/2:y=h/2-100:box=1:boxcolor=black@0.7:boxborderw=20"

        if scene_img and os.path.isfile(scene_img):
            frames = int(tts_dur * 30)
            # Zoom nhẹ
            zoom_vf = f"zoompan=z='min(zoom+0.0015,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,{vf}"
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", scene_img]
            if tts_path:
                cmd += ["-i", tts_path]
            cmd += ["-vf", zoom_vf, "-t", str(tts_dur)]
            if tts_path:
                cmd += ["-c:a", "aac", "-shortest"]
            else:
                cmd += ["-an"]
            cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", out_scene]
        else:
            # Fallback màn đen
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s=1080x1920:r=30:d={tts_dur}"]
            if tts_path:
                cmd += ["-i", tts_path, "-c:a", "aac", "-shortest"]
            cmd += ["-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", out_scene]
            
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            scene_vids.append(out_scene)
        except Exception as e:
            logger.error(f"Lỗi render scene {i}: {e}")

    # Ghép các cảnh
    if not scene_vids:
        return None
        
    with open(concat_file, "w", encoding="utf-8") as f:
        for sv in scene_vids:
            # Escape backslashes for ffmpeg concat
            path_str = sv.replace('\\', '/')
            f.write(f"file '{path_str}'\n")
            
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", out_video], check=True, capture_output=True)
        return out_video
    except Exception as e:
        logger.error(f"Lỗi ghép video: {e}")
        return None

def run_local_business_pipeline(
    store_name: str,
    address: str,
    promotions: str,
    images: List[str],
    language: str = "Tiếng Việt",
    voice_name: str = "Auto",
    tts_rate: str = "+0%",
    duration_mode: str = "Vừa (~30s)"
) -> Generator[Tuple[str, Optional[str]], None, None]:
    
    yield "🌟 BƯỚC 1: Đang nhờ AI viết kịch bản cho Cửa hàng...", None
    
    dur_sec = 15 if "15s" in duration_mode else 60 if "60s" in duration_mode else 30
    
    storyboard = generate_local_storyboard(
        store_name=store_name,
        address=address,
        promotions=promotions,
        language=language,
        duration_sec=dur_sec
    )
    
    if not storyboard:
        yield "❌ Lỗi: AI không thể tạo kịch bản. Hãy thử lại.", None
        return
        
    yield f"✅ Đã lên kịch bản với {len(storyboard)} phân cảnh. Bắt đầu thu âm & ghép video...", None
    
    if voice_name == "Auto":
        voice_name = "vi-VN-HoaiMyNeural" if "Việt" in language else "km-KH-SreymomNeural"
        
    final_video = render_local_video(
        storyboard=storyboard,
        images=images,
        language=language,
        voice_name=voice_name,
        tts_rate=tts_rate
    )
    
    if final_video and os.path.isfile(final_video):
        yield "🎉 HOÀN TẤT! Video quảng cáo Tiệm đã sẵn sàng!", final_video
    else:
        yield "❌ Lỗi: Render video thất bại trong FFmpeg.", None
