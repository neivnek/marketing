import os
import json
import logging
import subprocess
import traceback
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

LANG_VOICE_MAP = {
    "Tiếng Việt": "vi-VN-HoaiMyNeural",
    "Tiếng Anh": "en-US-JennyNeural",
    "Tiếng Khmer": "km-KH-SreymomNeural",
    "Tiếng Thái": "th-TH-PremwadeeNeural",
    "Tiếng Indo": "id-ID-GadisNeural",
}

def _get_voice(language: str) -> str:
    return LANG_VOICE_MAP.get(language, "vi-VN-HoaiMyNeural")


def generate_scene_machine_storyboard(
    product_image_path: str,
    product_name: str,
    target_audience: str = "Khách hàng Việt Nam",
    brand_tone: str = "Thuyết phục, Hiện đại, Chân thực",
    num_scenes: int = 4,
    language: str = "Tiếng Việt",
    target_duration_sec: int = 30,
    style_profile: Optional[Dict] = None,
) -> List[Dict]:
    style_injection_block = ""
    if style_profile:
        try:
            from core.style_profile import build_style_injection_prompt
            style_injection_block = build_style_injection_prompt(style_profile)
            logger.info(f"[SceneMachine] Injected style profile '{style_profile.get('profile_name', 'unknown')}'")
        except Exception as e:
            logger.warning(f"[SceneMachine] Style profile injection failed: {e}")

    prompt = f"""Bạn là chuyên gia thiết kế Video Quảng Cáo (Storyboard) tài năng của Google.
Hãy phân tích sản phẩm "{product_name}" (đối tượng: {target_audience}, phong cách: {brand_tone}).
Nhiệm vụ của bạn là viết một kịch bản video quảng cáo CHUYÊN NGHIỆP, HẤP DẪN, có CỐT TRUYỆN RÕ RÀNG (Hook thu hút -> Thân bài nêu vấn đề/giải pháp -> Kêu gọi hành động CTA).
Tuyệt đối KHÔNG viết một kịch bản nhàm chán chỉ có hình ảnh tĩnh và giọng đọc đều đều. Hãy tưởng tượng ra các cảnh quay (B-roll) sống động, người mẫu, hoặc bối cảnh liên quan tới sản phẩm để ghép vào video.
Tạo ra đúng {num_scenes} CẢNH cho video quảng cáo dọc 9:16 (tổng thời lượng khoảng {target_duration_sec} giây).
Mỗi cảnh có duration trung bình khoảng {max(3, target_duration_sec // num_scenes)} giây, có thể dài hơn nếu cần thiết để đọc hết câu.
QUAN TRỌNG: Viết voiceover_text bằng {language}. Lời thoại phải tự nhiên, cuốn hút.
TUYỆT ĐỐI KHÔNG DÙNG DẤU NGOẶC KÉP (") BÊN TRONG CÁC ĐOẠN CHỮ. HÃY DÙNG NGOẶC ĐƠN (') NẾU CẦN ĐỂ TRÁNH LỖI JSON.

{style_injection_block}

Trả về JSON ARRAY (không bọc markdown):
[
  {{
    "scene_number": 1,
    "scene_type": "HOOK",
    "visual_prompt": "English B-roll search query (5 words max)",
    "voiceover_text": "Lời thoại bằng {language} (khoảng {max(3, target_duration_sec // num_scenes)} giây)",
    "duration_sec": {max(3, target_duration_sec // num_scenes)},
    "overlay_text": "Chữ nổi trên màn hình (dưới 5 từ bằng {language})"
  }}
]"""

    contents = [prompt]
    if product_image_path and os.path.isfile(product_image_path):
        try:
            from PIL import Image as PILImage
            img = PILImage.open(product_image_path)
            contents = [img, prompt]
        except Exception:
            pass

    response = None
    try:
        from google.genai import types
        from core.gemini_pool import generate_content_with_pool
        response = generate_content_with_pool(
            prompt_contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8192,
            )
        )
    except Exception as e:
        raise e

    if not response or not response.text:
        return []

    raw = response.text.strip()
    # Tìm mảng JSON đầu tiên trong chuỗi trả về
    import re
    match = re.search(r'\[\s*\{.*\}\s*\]', raw, re.DOTALL)
    if match:
        raw = match.group(0)
    else:
        # Xóa markdown nếu có
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

    try:
        return json.loads(raw.strip())
    except Exception as e:
        raise ValueError(f"AI trả về cấu trúc kịch bản không hợp lệ (Lỗi: {e}). \nNội dung AI trả về: {raw[:300]}...")

def render_scene_machine_video(
    storyboard: List[Dict],
    product_image_path: str,
    output_path: str = "output/scene_machine_ad.mp4",
    temp_dir: str = "temp/scene_machine",
    language: str = "Tiếng Việt",
    voice_name: str = "",
    tts_rate: str = "+0%",
) -> Optional[str]:
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

    from core.broll_aggregator import fetch_broll_clips
    from core.tts_engine import generate_tts
    from core.concat_helper import concatenate_clips

    scene_video_files = []
    
    selected_voice = _get_voice(language) if (not voice_name or voice_name == "Auto") else voice_name

    for i, scene in enumerate(storyboard):
        scene_num = scene.get("scene_number", i + 1)
        logger.info(f"[SceneMachine] Scene #{scene_num}: {scene.get('scene_type', 'UNK')}")
        
        duration = float(scene.get("duration_sec", 4.0))
        voiceover = scene.get("voiceover_text", "")
        visual_prompt = scene.get("visual_prompt", "")
        overlay = scene.get("overlay_text", "")

        # 1. TTS
        tts_audio = os.path.join(temp_dir, f"scene_{scene_num}_audio.mp3")
        tts_ok = False
        if voiceover:
            try:
                generate_tts(voiceover, tts_audio, voice=selected_voice, rate=tts_rate)
                tts_ok = os.path.isfile(tts_audio)
                if tts_ok:
                    try:
                        from mutagen.mp3 import MP3
                        audio = MP3(tts_audio)
                        tts_dur = audio.info.length
                        if tts_dur > duration:
                            duration = tts_dur + 0.5
                            logger.info(f"[SceneMachine] Scene {scene_num} adjusted duration to {duration:.2f}s based on TTS")
                    except Exception as e:
                        logger.warning(f"[SceneMachine] Lỗi đọc độ dài audio: {e}")
            except Exception as e:
                logger.warning(f"[SceneMachine] Lỗi tạo TTS scene {scene_num}: {e}")

        # 2. B-roll
        keywords = [k for k in visual_prompt.split() if len(k) > 2][:4]
        try:
            pexels_key = os.getenv("PEXELS_API_KEY", "")
            pixabay_key = os.getenv("PIXABAY_API_KEY", "")
            clips = fetch_broll_clips(
                query_keywords=keywords or ["product", "lifestyle"],
                product_category="generic",
                duration_sec=duration + 1.0,
                pexels_api_key=pexels_key,
                pixabay_api_key=pixabay_key,
                local_broll_dir="assets/local_broll/generic",
                n_clips=1,
                reference_image=product_image_path,
            )
            broll_clip = clips[0] if clips else ""
        except Exception as e:
            logger.warning(f"[SceneMachine] Lỗi tìm B-roll scene {scene_num}: {e}")
            broll_clip = ""

        # 3. FFmpeg Render
        scene_output = os.path.join(temp_dir, f"scene_{scene_num}_final.mp4")
        vf_parts = [
            "scale=1080:1920:force_original_aspect_ratio=decrease",
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "setsar=1",
        ]
        
        ass_path = None
        if overlay:
            ass_path = os.path.join(temp_dir, f"scene_{scene_num}_overlay.ass")
            from core.subtitle_gen import generate_ass_file
            try:
                generate_ass_file(
                    script_text=overlay,
                    timestamps=[duration],
                    output_path=ass_path,
                    preset_name="classic_box",
                    alignment=2,
                    margin_v=240,
                )
                ass_abs = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")
                fonts_abs = os.path.abspath("assets/fonts").replace("\\", "/").replace(":", "\\:")
                vf_parts.append(f"subtitles='{ass_abs}':fontsdir='{fonts_abs}'")
            except Exception as e:
                logger.warning(f"[SceneMachine] Lỗi tạo ASS overlay: {e}")

        vf_filter = ",".join(vf_parts)
        is_video = broll_clip and broll_clip.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))

        cmd = ["ffmpeg", "-y"]
        if is_video:
            cmd += ["-i", broll_clip]
        else:
            cmd += ["-loop", "1", "-i", broll_clip or product_image_path]

        if tts_ok:
            cmd += ["-i", tts_audio]

        if is_video:
            cmd += ["-vf", vf_filter, "-t", str(duration)]
        else:
            n = int(duration * 30)
            cmd += [
                "-vf",
                f"zoompan=z='min(zoom+0.001,1.1)':d={n}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,{vf_filter}",
                "-t", str(duration),
            ]

        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p"]
        if tts_ok:
            cmd += ["-c:a", "aac", "-shortest"]
        else:
            cmd += ["-an"]
        cmd.append(scene_output)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.isfile(scene_output):
                scene_video_files.append(scene_output)
            else:
                logger.warning(f"[SceneMachine] Scene {scene_num} render lỗi: {result.stderr[-400:]}")
        except Exception as e:
            logger.error(f"[SceneMachine] Scene {scene_num} exception: {e}")
        finally:
            if ass_path and os.path.isfile(ass_path):
                try: os.remove(ass_path)
                except: pass

    if not scene_video_files:
        logger.error("[SceneMachine] Không có scene nào render được!")
        return None

    try:
        final_video = concatenate_clips(scene_video_files, output_path, fps=30)
        if final_video and os.path.isfile(final_video):
            logger.info(f"[SceneMachine] Xuất video thành công: {final_video}")
            return final_video
    except Exception as e:
        logger.error(f"[SceneMachine] Lỗi ghép video: {e}")
    
    return None
