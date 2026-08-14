"""
====================================================================
  FB Shorts Ads Generator v3.0
  File: app2.py — Web UI (Light Theme, Vietnamese)
  Run: python app2.py  ->  http://localhost:7861
====================================================================
"""

import logging
import os
import queue
import sys
import tempfile
import threading
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

from modes.fb_shorts.fb_shorts_pipeline import FBShortsInputs, run_fb_shorts_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _run_temp_dir(prefix: str) -> str:
    """
    Thư mục tạm riêng cho mỗi lần chạy.

    Trước đây các bước trung gian ghi vào đường dẫn cố định (temp/mv_clean_0.mp4,
    temp/clean_video_<tên>.mp4...), nên hai người dùng chạy song song sẽ ghi đè
    file của nhau — dễ xảy ra vì UI có thể bật share link công khai.
    """
    os.makedirs("temp", exist_ok=True)
    return tempfile.mkdtemp(prefix=f"{prefix}_", dir="temp")


# ──────────────────────────────────────────────────────────────────
# Live log capture
# ──────────────────────────────────────────────────────────────────

class QueueHandler(logging.Handler):
    def __init__(self, q):
        super().__init__()
        self._q = q
    def emit(self, record):
        try:
            self._q.put(self.format(record))
        except Exception:
            pass


def _stream(fn, *args, **kwargs):
    """Run fn(*args) in a thread, stream log lines as (video, log) tuples."""
    log_q: queue.Queue = queue.Queue()
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S")
    handler = QueueHandler(log_q)
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.addHandler(handler)

    result: dict = {}
    buf: list[str] = []

    def _run():
        try:
            out = fn(*args, **kwargs)
            result["output"] = out
        except Exception as exc:
            logger.error(f"Pipeline failed: {exc}", exc_info=True)
            result["error"] = str(exc)
        finally:
            result["done"] = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    while t.is_alive() or not log_q.empty():
        try:
            line = log_q.get(timeout=0.2)
            buf.append(line)
            yield None, "\n".join(buf)
        except queue.Empty:
            yield None, "\n".join(buf)

    root.removeHandler(handler)

    if "error" in result:
        buf.append(f"\n[LOI] {result['error']}")
        yield None, "\n".join(buf)
    elif "output" in result:
        buf.append(f"\n[OK] Hoan thanh: {result['output']}")
        yield result["output"], "\n".join(buf)
    else:
        yield None, "\n".join(buf)


# ──────────────────────────────────────────────────────────────────
# CSS — Light professional theme
# ──────────────────────────────────────────────────────────────────

CSS = """
:root {
    --primary: #4f46e5;
    --primary-g: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
}
.gradio-container { max-width: 1400px !important; margin: 0 auto !important; }
#hero {
    background: var(--primary-g);
    border-radius: 12px;
    padding: 2rem;
    margin-bottom: 1.5rem;
    color: white;
    box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.4);
}
#hero h1 {
    font-size: 2rem !important; font-weight: 800 !important;
    color: white !important;
    margin: 0 0 0.5rem !important;
}
#hero p { color: rgba(255,255,255,0.9) !important; font-size: 0.95rem !important; margin: 0 !important; }
.badge {
    display: inline-block; padding: 4px 12px;
    background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.3);
    border-radius: 999px; font-size: 0.75rem; color: white;
    margin-right: 8px; margin-top: 0.8rem; font-weight: 500;
}
.section-label {
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em;
    text-transform: uppercase; color: #6366f1;
    margin-bottom: 0.8rem; padding-bottom: 0.4rem;
    border-bottom: 2px solid #e0e7ff;
}
.info-box {
    background: #e0e7ff; border-left: 4px solid #4f46e5;
    border-radius: 6px; padding: 12px 16px;
    font-size: 0.85rem; color: #3730a3; margin-bottom: 1rem;
}
.warn-box {
    background: #fef3c7; border-left: 4px solid #d97706;
    border-radius: 6px; padding: 12px 16px;
    font-size: 0.85rem; color: #92400e; margin-bottom: 1rem;
}
/* Fix for buttons */
button.primary {
    background: var(--primary-g) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.3) !important;
    transition: all 0.2s !important;
}
button.primary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(79, 70, 229, 0.4) !important;
}
#log-box textarea {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.8rem !important;
    background: #1e1e1e !important;
    color: #4ade80 !important;
}
/* Tabs Fix */
.main-tabs { overflow: visible !important; }
.main-tabs > div:first-child { 
    overflow: visible !important; 
    z-index: 999 !important;
}
.main-tabs button { border-radius: 8px !important; margin-bottom: 4px; padding: 8px 16px !important; }
"""


# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────

VOICE_CHOICES = [
    ("Sreymom — Nu (Female)",    "km-KH-SreymomNeural"),
    ("Piseth — Nam (Male)",      "km-KH-PisethNeural"),
]

UGC_LEVELS = ["subtle", "medium", "strong"]
PRICE_COLORS = ["red", "black", "orange", "white"]

_ENV_GEMINI   = os.getenv("GEMINI_API_KEY", "")
_ENV_PEXELS   = os.getenv("PEXELS_API_KEY", "")
_ENV_REPLICATE = os.getenv("REPLICATE_API_TOKEN", "")


def _voice_val(label: str) -> str:
    for lbl, val in VOICE_CHOICES:
        if lbl == label:
            return val
    return "km-KH-SreymomNeural"


def _resolve_file(f) -> str | None:
    if f is None: return None
    if isinstance(f, str): return f
    if isinstance(f, dict): return f.get("path") or f.get("name")
    return getattr(f, "path", None) or getattr(f, "name", None) or str(f)


def _resolve_images(img_list) -> list[str]:
    if img_list is None: return []
    if isinstance(img_list, str): return [img_list]
    paths = []
    for item in (img_list if isinstance(img_list, list) else [img_list]):
        p = _resolve_file(item)
        if p: paths.append(p)
    return paths


# ──────────────────────────────────────────────────────────────────
# UI Builder
# ──────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    with gr.Blocks(title="FB Shorts Ads Generator") as demo:

        # Hero
        gr.HTML("""
        <div id="hero">
            <h1>FB Shorts Ads Generator</h1>
            <p>Tao video quang cao 9:16 (1080x1920) tu dong — Giong doc Khmer — Co phu de — 15-30 giay</p>
            <div>
                <span class="badge">edge-tts Mien phi</span>
                <span class="badge">Pexels CC Videos</span>
                <span class="badge">UGC Authenticity</span>
                <span class="badge">Khmer Subtitle</span>
                <span class="badge">Gia tien Overlay</span>
            </div>
        </div>
        """)

        with gr.Tabs(elem_classes="main-tabs"):
            with gr.Tab("🌟 Magic One-Click (Làm Tất Cả)"):
                gr.HTML('<div class="info-box">Chế độ Siêu Tự Động mới: Bước 1: Quét ảnh & Tạo kịch bản. Bước 2: Chỉnh sửa và Render Video.</div>')
                with gr.Row():
                    with gr.Column(scale=5):
                        magic_img = gr.File(label="Upload ảnh sản phẩm chính (JPG/PNG)", file_types=[".jpg", ".jpeg", ".png", ".webp"])
                        magic_audience = gr.Textbox(label="Đối tượng khách hàng", value="Khách hàng Việt Nam")
                        magic_tone = gr.Textbox(label="Phong cách / Tone giọng", value="Thuyết phục, Hiện đại, Chân thực")
                        magic_lang = gr.Dropdown(
                            choices=["Tiếng Việt", "Tiếng Khmer", "Tiếng Anh", "Tiếng Thái", "Tiếng Indo"],
                            value="Tiếng Việt",
                            label="🌐 Ngôn ngữ kịch bản"
                        )
                        magic_duration = gr.Dropdown(
                            choices=[
                                "Ngắn (~15s) - Chờ siêu nhanh",
                                "Vừa (~30s) - Chờ bình thường",
                                "Dài (~60s) - Chờ lâu"
                            ],
                            value="Vừa (~30s) - Chờ bình thường",
                            label="⏳ Độ dài Video mong muốn"
                        )
                        with gr.Row():
                            magic_voice = gr.Dropdown(
                                choices=["Auto", "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural", "km-KH-SreymomNeural", "km-KH-PisethNeural", "en-US-JennyNeural"],
                                value="Auto",
                                label="Giọng đọc (Auto = Chọn theo ngôn ngữ)"
                            )
                            magic_rate = gr.Dropdown(
                                choices=["-10%", "+0%", "+10%", "+25%"],
                                value="+0%",
                                label="Tốc độ đọc"
                            )
                        btn_gen_script = gr.Button("📝 BƯỚC 1: QUÉT ẢNH & TẠO KỊCH BẢN", variant="primary", size="lg")
                        btn_render = gr.Button("🎬 BƯỚC 2: RENDER VIDEO TỪ KỊCH BẢN NÀY", variant="secondary", size="lg")
                        gr.Markdown("---")
                        btn_auto_all = gr.Button("🚀 CHẠY TỰ ĐỘNG TỪ A-Z (BỎ QUA CHỈNH SỬA)", variant="stop", size="lg")
                    
                    with gr.Column(scale=7):
                        magic_log = gr.Textbox(label="Tiến trình làm việc của AI", lines=8, interactive=False)
                        gr.Markdown("### 📝 Bảng Kịch Bản (Click đúp vào ô để sửa chữ, sửa thời lượng, v.v.)")
                        magic_df = gr.Dataframe(
                            headers=["Scene", "Type", "B-roll Keyword", "Voiceover (Lời đọc)", "Thời lượng (s)", "Chữ nổi (Overlay)"],
                            datatype=["number", "str", "str", "str", "number", "str"],
                            col_count=(6, "fixed"),
                            interactive=True,
                            type="array",
                            wrap=True
                        )
                        magic_out_video = gr.Video(label="Video Thành Phẩm")
                        
                        with gr.Accordion("⚙️ Chỉnh tốc độ video sau khi xong", open=False):
                            with gr.Row():
                                magic_speed_slider = gr.Slider(minimum=0.5, maximum=2.0, step=0.1, value=1.0, label="Tốc độ (1.0 = Bình thường, >1 = Nhanh, <1 = Chậm)")
                                btn_apply_speed = gr.Button("⚡ Áp dụng tốc độ mới", variant="primary")
                            magic_speed_out_video = gr.Video(label="Video đã chỉnh tốc độ")

                # Helpers
                def sb_to_df(storyboard):
                    df_data = []
                    for s in storyboard:
                        df_data.append([
                            s.get("scene_number", 1),
                            s.get("scene_type", "HOOK"),
                            s.get("visual_prompt", ""),
                            s.get("voiceover_text", ""),
                            float(s.get("duration_sec", 4.0)),
                            s.get("overlay_text", "")
                        ])
                    return df_data

                def df_to_sb(df_data):
                    storyboard = []
                    if not df_data: return storyboard
                    for i, row in enumerate(df_data):
                        # Bỏ qua hàng trống
                        if not any(row): continue
                        storyboard.append({
                            "scene_number": int(row[0]) if row[0] else (i+1),
                            "scene_type": str(row[1]) if row[1] else "BODY",
                            "visual_prompt": str(row[2]) if row[2] else "",
                            "voiceover_text": str(row[3]) if row[3] else "",
                            "duration_sec": float(row[4]) if row[4] else 4.0,
                            "overlay_text": str(row[5]) if row[5] else ""
                        })
                    return storyboard

                def _gen_script(img_file, audience, tone, lang, duration):
                    img_path = _resolve_file(img_file)
                    if not img_path:
                        yield "❌ Lỗi: Vui lòng upload ảnh sản phẩm!", []
                        return
                    try:
                        from core.magic_pipeline_engine import generate_magic_storyboard
                        df_data = []
                        for log_msg, sb in generate_magic_storyboard(img_path, audience, tone, lang, duration):
                            if sb is not None:
                                df_data = sb_to_df(sb)
                            yield log_msg, df_data
                    except Exception as exc:
                        import traceback
                        yield f"❌ Lỗi:\n{traceback.format_exc()}", []

                def _render_video(df_data, img_file, lang, voice, rate):
                    img_path = _resolve_file(img_file)
                    storyboard = df_to_sb(df_data)
                    if not storyboard:
                        yield "❌ Lỗi: Bảng kịch bản trống!", None
                        return
                    if not img_path:
                        # Vẫn có thể render nếu storyboard dùng ảnh cũ (B-roll)
                        img_path = "luoc.jpg"
                    
                    try:
                        from core.magic_pipeline_engine import render_magic_video
                        for log_msg, vid_path in render_magic_video(storyboard, img_path, lang, voice, rate):
                            yield log_msg, vid_path
                    except Exception as exc:
                        import traceback
                        yield f"❌ Lỗi:\n{traceback.format_exc()}", None

                def _auto_all(img_file, audience, tone, lang, voice, rate, duration):
                    img_path = _resolve_file(img_file)
                    if not img_path:
                        yield "❌ Lỗi: Vui lòng upload ảnh sản phẩm!", None
                        return
                    try:
                        from core.magic_pipeline_engine import run_magic_pipeline
                        for log_msg, vid_path in run_magic_pipeline(
                            image_path=img_path, 
                            target_audience=audience, 
                            brand_tone=tone, 
                            language=lang,
                            voice_name=voice,
                            tts_rate=rate,
                            duration_mode=duration
                        ):
                            yield log_msg, vid_path
                    except Exception as exc:
                        import traceback
                        yield f"❌ Lỗi:\n{traceback.format_exc()}", None

                btn_gen_script.click(
                    fn=_gen_script,
                    inputs=[magic_img, magic_audience, magic_tone, magic_lang, magic_duration],
                    outputs=[magic_log, magic_df]
                )
                
                btn_render.click(
                    fn=_render_video,
                    inputs=[magic_df, magic_img, magic_lang, magic_voice, magic_rate],
                    outputs=[magic_log, magic_out_video]
                )

                btn_auto_all.click(
                    fn=_auto_all,
                    inputs=[magic_img, magic_audience, magic_tone, magic_lang, magic_voice, magic_rate, magic_duration],
                    outputs=[magic_log, magic_out_video]
                )

                def _change_speed(video_path, speed):
                    if not video_path:
                        yield "❌ Lỗi: Chưa có video thành phẩm để chỉnh tốc độ!", None
                        return
                    import subprocess
                    import os
                    yield f"⏳ Đang xử lý thay đổi tốc độ video thành {speed}x...", None
                    out_path = video_path.replace(".mp4", f"_speed_{speed}x.mp4")
                    v_pts = 1.0 / float(speed)
                    a_tempo = float(speed)
                    
                    cmd = [
                        "ffmpeg", "-y", "-i", video_path,
                        "-filter_complex", f"[0:v]setpts={v_pts}*PTS[v];[0:a]atempo={a_tempo}[a]",
                        "-map", "[v]", "-map", "[a]",
                        out_path
                    ]
                    try:
                        subprocess.run(cmd, check=True, capture_output=True)
                        yield "✅ Đã thay đổi tốc độ thành công!", out_path
                    except Exception as e:
                        yield f"❌ Lỗi ffmpeg: {str(e)}", None

                btn_apply_speed.click(
                    fn=_change_speed,
                    inputs=[magic_out_video, magic_speed_slider],
                    outputs=[magic_log, magic_speed_out_video]
                )

            with gr.Tab("🌟 Magic One-Click (Bản Classic)"):
                gr.HTML('<div class="info-box">Chế độ nguyên thuỷ: Cố định 8 cảnh, tự lấy chung 8 B-roll theo tên sản phẩm, 1 chạm là xong không rườm rà.</div>')
                with gr.Row():
                    with gr.Column(scale=3):
                        classic_img = gr.Image(type="filepath", label="📄 Upload ảnh sản phẩm", height=200)
                        classic_lang = gr.Dropdown(
                            choices=["Tiếng Việt", "Tiếng Khmer", "Tiếng Anh", "Tiếng Thái", "Tiếng Indo"],
                            value="Tiếng Việt",
                            label="🌐 Ngôn ngữ"
                        )
                        btn_classic_run = gr.Button("🚀 CHẠY CLASSIC (1-CLICK TỪ A-Z)", variant="primary", size="lg")
                    with gr.Column(scale=7):
                        classic_log = gr.Textbox(label="Tiến trình làm việc", lines=8, interactive=False)
                        classic_out_video = gr.Video(label="Video Thành Phẩm")

                def _run_classic_mode(img_file, lang):
                    img_path = _resolve_file(img_file)
                    if not img_path:
                        yield "❌ Lỗi: Vui lòng upload ảnh sản phẩm!", None
                        return
                    try:
                        from core.classic_magic_pipeline import run_classic_pipeline
                        for log_msg, vid_path in run_classic_pipeline(
                            image_path=img_path,
                            language=lang,
                        ):
                            yield log_msg, vid_path
                    except Exception as exc:
                        import traceback
                        yield f"❌ Lỗi:\n{traceback.format_exc()}", None

                btn_classic_run.click(
                    fn=_run_classic_mode,
                    inputs=[classic_img, classic_lang],
                    outputs=[classic_log, classic_out_video]
                )

            with gr.Tab("🌐 URL → Multi-Variant Ads"):
                gr.HTML('<div class="info-box">Dán URL sản phẩm (Shopee, Lazada, Amazon...) → AI tự cào thông tin → Cào video UGC → Tự tạo 3 biến thể video (Awareness 15s / Consideration 30s / Action 10s) kèm caption & hashtag sẵn sàng đăng.</div>')
                with gr.Row():
                    with gr.Column(scale=5):
                        mv_url = gr.Textbox(label="🔗 URL Sản Phẩm", placeholder="https://shopee.vn/... hoặc https://lazada.vn/... hoặc bất kỳ URL nào")
                        mv_audience = gr.Textbox(label="Đối tượng khách hàng", value="Khách hàng Việt Nam")
                        mv_lang = gr.Dropdown(
                            choices=["Tiếng Việt", "Tiếng Khmer", "Tiếng Anh"],
                            value="Tiếng Việt",
                            label="Ngôn ngữ lồng tiếng"
                        )
                        btn_mv_run = gr.Button("🚀 Cào URL & Tạo 3 Biến Thể Video", variant="primary", size="lg")

                    with gr.Column(scale=7):
                        mv_product_html = gr.HTML(value="<p style='color:#888'>Thông tin sản phẩm sẽ hiển thị ở đây sau khi cào...</p>")
                        mv_log = gr.Textbox(label="Tiến trình", lines=8, interactive=False)

                gr.HTML('<hr/><div class="section-label">🎬 3 Biến Thể Video Output (Awareness / Consideration / Action)</div>')
                with gr.Row():
                    mv_vid_awareness = gr.Video(label="⚡ Awareness (15s) — Nhận biết")
                    mv_vid_consideration = gr.Video(label="🧠 Consideration (30s) — Thuyết phục")
                    mv_vid_action = gr.Video(label="💰 Action (10s) — Chốt đơn")

                mv_text_assets = gr.Textbox(label="📋 Text Assets (Caption + Hashtags cho cả 3 biến thể)", lines=10, interactive=False)

                def _run_mv_tab(url, audience, lang):
                    import os as _os
                    _ERR_EMPTY = "<p style='color:red'>❌ Lỗi không xác định. Xem logs.</p>"

                    try:
                        if not url or not url.strip().startswith("http"):
                            yield "<p style='color:red'>❌ Vui lòng nhập URL hợp lệ bắt đầu bằng http!</p>", "Lỗi URL.", None, None, None, ""
                            return

                        yield "<p>⏳ Đang cào URL...</p>", "[1/5] 🌐 Đang cào thông tin sản phẩm từ URL...", None, None, None, ""

                        from core.product_url_scraper import scrape_product_from_url
                        product_info = scrape_product_from_url(url.strip())

                        if not product_info or "error" in product_info:
                            err_msg = product_info.get("error", "Không cào được trang") if product_info else "Không cào được trang"
                            # Không dừng ở đây — thử tiếp với tên sản phẩm lấy từ URL
                            from urllib.parse import urlparse, unquote
                            path_parts = [p for p in urlparse(url).path.split("/") if p]
                            guessed_name = unquote(path_parts[-1]).replace("-", " ").replace("_", " ") if path_parts else "sản phẩm"
                            product_info = {
                                "product_name": guessed_name[:60],
                                "price": "",
                                "short_description": "",
                                "key_features": [],
                                "target_audience": audience,
                                "pain_points": [],
                                "image_path": None,
                            }
                            warn_html = f"<div style='padding:10px;background:#fff3cd;border-radius:8px;'>⚠️ {err_msg}<br/>Tự đoán tên từ URL: <b>{product_info['product_name']}</b></div>"
                            yield warn_html, f"[1/5] ⚠️ {err_msg}. Tiếp tục với tên đoán: {product_info['product_name']}", None, None, None, ""
                            info_html = warn_html
                        else:
                            name = product_info.get("product_name", "Không rõ")
                            price = product_info.get("price", "Chưa rõ")
                            desc = product_info.get("short_description", "")
                            features = product_info.get("key_features", [])
                            feat_html = "".join(f"<li>{f}</li>" for f in features)
                            info_html = f"""<div style='padding:12px;background:#f0f4ff;border-radius:8px;'>
                                <h3>🛍️ {name}</h3>
                                <b>Giá:</b> {price}<br/>
                                <b>Mô tả:</b> {desc}<br/>
                                <b>Tính năng:</b><ul>{feat_html}</ul>
                            </div>"""
                            yield info_html, f"[2/5] ✅ Đã cào: {name}. Đang cào video B-roll...", None, None, None, ""

                        product_info["target_audience"] = audience
                        name = product_info.get("product_name", "sản phẩm")

                        # Cào B-roll
                        try:
                            from core.stockpile_broll_curator import curate_and_download_broll
                            raw_brolls = curate_and_download_broll(keyword=name, max_clips=3)
                        except Exception as e_broll:
                            raw_brolls = []
                            yield info_html, f"[2/5] ⚠️ Không cào được B-roll: {e_broll}. Tiếp tục với ảnh tĩnh.", None, None, None, ""

                        # Xóa logo
                        from core.logo_remover import remove_video_logo
                        clean_brolls = []
                        _mv_tmp = _run_temp_dir("mv_clean")
                        for i, vid in enumerate(raw_brolls):
                            try:
                                out = os.path.join(_mv_tmp, f"clean_{i}.mp4")
                                cleaned = remove_video_logo(vid, out, mode="auto_tiktok")
                                clean_brolls.append(cleaned if cleaned else vid)
                            except Exception:
                                clean_brolls.append(vid)

                        yield info_html, f"[3/5] ✅ Đã xử lý {len(clean_brolls)} video. Đang sinh script 3 biến thể...", None, None, None, ""

                        from core.multi_variant_engine import generate_multi_variants
                        variants = generate_multi_variants(
                            product_info=product_info,
                            broll_clips=clean_brolls,
                            output_dir="output",
                            temp_dir="temp/multi_variant",
                        )

                        yield info_html, f"[4/5] ✅ Đã render {len(variants)} biến thể. Đang tổng hợp...", None, None, None, ""

                        vid_a = vid_b = vid_c = None
                        text_out = ""
                        for v in variants:
                            text_out += f"[{v['variant'].upper()} — {v['duration_sec']}s]\n"
                            text_out += f"Caption: {v.get('caption', '')}\n"
                            text_out += f"Hashtags: {v.get('hashtags', '')}\n"
                            text_out += f"Voiceover: {v.get('voiceover', '')}\n\n"
                            vp = v.get("video_path")
                            if v["variant"] == "awareness" and vp and _os.path.isfile(vp):
                                vid_a = vp
                            elif v["variant"] == "consideration" and vp and _os.path.isfile(vp):
                                vid_b = vp
                            elif v["variant"] == "action" and vp and _os.path.isfile(vp):
                                vid_c = vp

                        yield info_html, "[5/5] 🎉 HOÀN TẤT! 3 video quảng cáo đã sẵn sàng!", vid_a, vid_b, vid_c, text_out

                    except Exception as exc:
                        import traceback
                        err_detail = traceback.format_exc()
                        yield _ERR_EMPTY, f"❌ Lỗi không xử lý được:\n{err_detail}", None, None, None, ""

                btn_mv_run.click(
                    fn=_run_mv_tab,
                    inputs=[mv_url, mv_audience, mv_lang],
                    outputs=[mv_product_html, mv_log, mv_vid_awareness, mv_vid_consideration, mv_vid_action, mv_text_assets]
                )

            with gr.Tab("🏪 Quảng Cáo Tiệm (Local Store)"):
                gr.HTML('<div class="info-box">Chế độ chuyên biệt cho Cửa hàng vật lý (Quán ăn, Tiệm tóc, Shop, Spa...). Nhập thông tin quán và AI sẽ tự lo kịch bản thu hút khách địa phương!</div>')
                with gr.Row():
                    with gr.Column(scale=4):
                        local_name = gr.Textbox(label="Tên Tiệm / Quán", placeholder="VD: Tiệm Bánh Nhà Bông")
                        local_address = gr.Textbox(label="Địa chỉ (Sẽ in to lên Video)", placeholder="VD: 123 Đường ABC, Quận 1")
                        local_promo = gr.Textbox(label="Khuyến mãi / Đặc điểm nổi bật", placeholder="VD: Giảm 20% cho học sinh sinh viên")
                        local_images = gr.File(label="Upload hình ảnh quán/món ăn (chọn nhiều ảnh)", file_count="multiple", type="filepath")
                        local_lang = gr.Dropdown(choices=["Tiếng Việt", "Tiếng Khmer", "Tiếng Anh"], value="Tiếng Việt", label="Ngôn ngữ")
                        local_dur = gr.Dropdown(choices=["15s (Nhanh gọn)", "30s (Chi tiết)"], value="15s (Nhanh gọn)", label="Độ dài")
                        
                        btn_local_run = gr.Button("🚀 TẠO VIDEO QUẢNG CÁO TIỆM", variant="primary", size="lg")
                        
                    with gr.Column(scale=6):
                        local_log = gr.Textbox(label="Tiến trình làm việc", lines=6, interactive=False)
                        local_out_vid = gr.Video(label="Video Thành Phẩm")
                        
                        with gr.Accordion("⚙️ Chỉnh tốc độ video sau khi xong", open=False):
                            with gr.Row():
                                local_speed_slider = gr.Slider(minimum=0.5, maximum=2.0, step=0.1, value=1.0, label="Tốc độ (1.0 = Bình thường)")
                                btn_local_speed = gr.Button("⚡ Áp dụng tốc độ mới", variant="primary")
                            local_speed_out = gr.Video(label="Video đã chỉnh tốc độ")

                def _run_local_mode(name, addr, promo, files, lang, dur):
                    from core.local_business_engine import run_local_business_pipeline
                    if not name or not addr:
                        yield "❌ Lỗi: Vui lòng nhập Tên Tiệm và Địa Chỉ!", None
                        return
                        
                    img_paths = [f if isinstance(f, str) else f.name for f in (files or [])]
                    
                    try:
                        for log_msg, vid in run_local_business_pipeline(name, addr, promo, img_paths, lang, "Auto", "+0%", dur):
                            yield log_msg, vid
                    except Exception as e:
                        import traceback
                        yield f"❌ Lỗi: {traceback.format_exc()}", None
                        
                btn_local_run.click(
                    fn=_run_local_mode,
                    inputs=[local_name, local_address, local_promo, local_images, local_lang, local_dur],
                    outputs=[local_log, local_out_vid]
                )
                
                # Tái sử dụng hàm _change_speed
                btn_local_speed.click(
                    fn=_change_speed,
                    inputs=[local_out_vid, local_speed_slider],
                    outputs=[local_log, local_speed_out]
                )


            with gr.Tab("🎬 Tạo Video Mới (Generative)"):
                with gr.Tabs():
                    # ── TAB 3: FB Shorts — Generative AI ─────────────────
                    with gr.Tab("FB Shorts — AI Tao Video Moi"):
                        gr.HTML('<div class="info-box">Bien anh san pham thanh video dong (AI) + them giong Khmer + gia + phu de.</div>')
                        gr.HTML('<div class="warn-box">Can GEMINI_API_KEY. Replicate key tuy chon (fallback sang Ken Burns neu khong co).</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">Anh san pham (1-5 anh)</div>')
                                gen_images = gr.File(
                                    label="Upload anh san pham (JPG/PNG)",
                                    file_types=[".jpg", ".jpeg", ".png", ".webp"],
                                    file_count="multiple",
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">Thong tin</div>')
                                gen_price = gr.Textbox(label="Gia san pham", placeholder="35,000 KHR  hoac  $5")
                                gen_url   = gr.Textbox(label="URL bai quang cao (Gemini se doc va viet script Khmer)", placeholder="https://...")
                                gen_dur   = gr.Slider(label="Do dai video muc tieu (giay)", minimum=15, maximum=30, value=20, step=1)

                                gr.HTML('<div class="section-label" style="margin-top:1rem">Cai dat</div>')
                                with gr.Row():
                                    gen_voice = gr.Dropdown(
                                        label="Giong Khmer", choices=[c[0] for c in VOICE_CHOICES],
                                        value=VOICE_CHOICES[0][0],
                                    )
                                    gen_rate = gr.Dropdown(
                                        label="Tốc độ đọc (Tua)",
                                        choices=["+0%", "+10%", "+25%", "+50%"],
                                        value="+0%",
                                    )
                                    gen_transition_speed = gr.Dropdown(
                                        label="Tốc độ chuyển cảnh",
                                        choices=["Chậm (4.0s)", "Bình thường (3.0s)", "Nhanh (2.0s)", "Rất nhanh (1.5s)"],
                                        value="Bình thường (3.0s)",
                                    )
                                    gen_ugc = gr.Dropdown(
                                        label="UGC Intensity", choices=UGC_LEVELS, value="medium",
                                    )
                                with gr.Row():
                                    gen_color = gr.Dropdown(
                                        label="Mau nen gia", choices=PRICE_COLORS, value="red",
                                    )
                                    gen_gemini_key = gr.Textbox(
                                        label="Gemini API Key",
                                        type="password", value=_ENV_GEMINI,
                                        placeholder="AIzaSy... (lay mien phi tai aistudio.google.com)",
                                    )
                                gen_replicate_key = gr.Textbox(
                                    label="Replicate Token (tuy chon — de trong = dung Ken Burns)",
                                    type="password", value=_ENV_REPLICATE,
                                    placeholder="r8_... (lay tai replicate.com)",
                                )

                                gen_out = gr.Textbox(label="Thu muc xuat", value="output")
                                run_gen = gr.Button("Tao Video AI", elem_id="run-gen", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Ket qua</div>')
                                gen_out_video = gr.Video(label="FB Shorts AI")
                                gen_log = gr.Textbox(label="", lines=14, interactive=False,
                                                     placeholder="Log hien o day...", elem_id="log-box")

                        def _run_gen(imgs, price, url, duration, voice_lbl, ugc, color,
                                     gemini_key, replicate_key, out_dir):
                            images = _resolve_images(imgs)
                            if not images:
                                yield None, "[LOI] Chua upload anh san pham."
                                return
                            if not price.strip():
                                yield None, "[LOI] Chua nhap gia san pham."
                                return
                            if not url.strip():
                                yield None, "[LOI] Chua nhap URL bai quang cao."
                                return
                            gkey = gemini_key.strip() or _ENV_GEMINI

                            inputs = FBShortsInputs(
                                sub_mode="generative",
                                product_images=images,
                                price_text=price.strip(),
                                ad_text_url=url.strip(),
                                gemini_api_key=gkey,
                                replicate_token=replicate_key.strip() or _ENV_REPLICATE,
                                tts_voice=_voice_val(voice_lbl),
                                ugc_intensity=ugc,
                                price_color=color,
                                target_duration=float(duration),
                            )
                            yield from _stream(run_fb_shorts_pipeline, inputs, out_dir)

                        run_gen.click(
                            fn=_run_gen,
                            inputs=[gen_images, gen_price, gen_url, gen_dur, gen_voice,
                                    gen_ugc, gen_color, gen_gemini_key, gen_replicate_key, gen_out],
                            outputs=[gen_out_video, gen_log],
                        )

                    # ── TAB 4: News Auto — Video Tin Tức ────────────────
                    with gr.Tab("News Auto — Video Tin Tức (JSON)"):
                        gr.HTML('<div class="info-box">Dán JSON kịch bản (sinh từ Gemini/ChatGPT) để render tự động thành Video Tin Tức 9:16.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">1. Copy Prompt Mẫu Gemini</div>')
                                from modes.news_auto.prompt_template import get_news_prompt_template
                                prompt_tmpl_box = gr.Textbox(
                                    label="System Prompt Mẫu (Copy và dán cho Gemini/ChatGPT)",
                                    value=get_news_prompt_template(),
                                    lines=4,
                                    interactive=False,
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">2. Đầu Vào Kịch Bản JSON</div>')
                                news_json_input = gr.Textbox(
                                    label="Dán JSON kịch bản vào đây",
                                    placeholder='{\n  "title": "Tin Tức Mới",\n  "script_segments": [...]\n}',
                                    lines=8,
                                )
                                news_product_price = gr.Textbox(
                                    label="Giá sản phẩm (tùy chọn)",
                                    placeholder="Ví dụ: 15,000 KHR",
                                )
                                with gr.Row():
                                    news_quality = gr.Dropdown(
                                        label="Chất lượng xuất",
                                        choices=["720p", "1080p", "4k"],
                                        value="1080p",
                                    )
                                    news_voice = gr.Radio(
                                        label="Giọng đọc Khmer",
                                        choices=[c[0] for c in VOICE_CHOICES],
                                        value=VOICE_CHOICES[0][0],
                                    )

                                news_out_dir = gr.Textbox(label="Thư mục xuất", value="output")
                                run_news = gr.Button("Tạo Video Tin Tức", elem_id="run-news", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả</div>')
                                news_out_video = gr.Video(label="Video Tin Tức Thành Phẩm")
                                news_log = gr.Textbox(label="", lines=14, interactive=False,
                                                     placeholder="Log hiển thị ở đây...", elem_id="log-box")

                        def _run_news_auto(json_str, product_price, quality, voice_lbl, out_dir):
                            if not (json_str or "").strip():
                                yield None, "[LỖI] Chưa dán JSON kịch bản."
                                return
                            from core.router import PipelineInputs, NewsAutoInputs, WorkflowMode, run_pipeline
                            inputs = PipelineInputs(
                                mode=WorkflowMode.NEWS_AUTO,
                                product_image="",
                                news_auto=NewsAutoInputs(
                                    json_payload=json_str.strip(),
                                    product_price=product_price.strip(),
                                    output_quality=quality,
                                    tts_voice=_voice_val(voice_lbl),
                                ),
                                output_dir=out_dir,
                            )
                            yield from _stream(run_pipeline, inputs)

                        run_news.click(
                            fn=_run_news_auto,
                            inputs=[news_json_input, news_product_price, news_quality, news_voice, news_out_dir],
                            outputs=[news_out_video, news_log],
                        )

            with gr.Tab("🔄 Xử Lý & Chế Biến Lại"):
                with gr.Tabs():
                    # ── TAB 1: Dub Only ──────────────────────────────────
                    with gr.Tab("Loc tieng — Dub Only"):
                        gr.HTML('<div class="info-box">Nhan video goc + kich ban Khmer → xuat video da loc tieng Khmer + phu de tu dong.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">Dau vao</div>')

                                dub_video = gr.File(
                                    label="Video goc (MP4 / MOV / AVI)",
                                    file_types=[".mp4", ".mov", ".avi", ".mkv"],
                                    elem_id="dub_video",
                                )
                                dub_script = gr.Textbox(
                                    label="Kich ban tieng Khmer",
                                    placeholder="ហ្សែលក្ដៅ! ធ្វើឱ្យសក់រឹងប៉ូវ...",
                                    lines=6,
                                )

                                with gr.Row():
                                    dub_voice = gr.Radio(
                                        label="Giong doc Khmer",
                                        choices=[c[0] for c in VOICE_CHOICES],
                                        value=VOICE_CHOICES[0][0],
                                    )
                                    dub_rate = gr.Dropdown(
                                        label="Tốc độ đọc (Tua)",
                                        choices=["+0%", "+10%", "+25%", "+50%"],
                                        value="+0%",
                                    )
                                    dub_mix = gr.Radio(
                                        label="Che do am thanh",
                                        choices=["replace (thay the)", "mix (hoa tron)"],
                                        value="replace (thay the)",
                                    )

                                dub_output_dir = gr.Textbox(label="Thu muc xuat", value="output")
                                run_dub = gr.Button("Tao Video Loc Tieng", elem_id="run-dub", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Ket qua</div>')
                                dub_out_video = gr.Video(label="Video da loc tieng")
                                dub_log = gr.Textbox(label="", lines=14, interactive=False,
                                                     placeholder="Log hien o day...", elem_id="log-box")

                        def _run_dub(video_file, script, voice_lbl, rate_val, mix_mode, out_dir):
                            vp = _resolve_file(video_file)
                            if not vp:
                                yield None, "[LOI] Chua chon video."
                                return
                            if not (script or "").strip():
                                yield None, "[LOI] Chua nhap kich ban."
                                return
                            from core.router import PipelineInputs, WorkflowMode, run_pipeline
                            from core.config import DubOnlyInputs
                    
                            inputs = PipelineInputs(
                                mode=WorkflowMode.DUB_ONLY,
                                product_image="",
                                dub_only=DubOnlyInputs(
                                    source_video_path=vp,
                                    script_text=script.strip(),
                                    voice=_voice_val(voice_lbl),
                                    tts_rate=rate_val,
                                    burn_subtitle=False
                                ),
                                output_dir=out_dir,
                            )
                            yield from _stream(run_pipeline, inputs)

                        run_dub.click(
                            fn=_run_dub,
                            inputs=[dub_video, dub_script, dub_voice, dub_rate, dub_mix, dub_output_dir],
                            outputs=[dub_out_video, dub_log],
                        )

                    # ── TAB 2: FB Shorts — Remix ─────────────────────────
                    with gr.Tab("FB Shorts — Remix (Tim video CC)"):
                        gr.HTML('<div class="info-box">Tim video Creative Commons tu Pexels, cat ghep theo nhip va them giong Khmer.</div>')
                        gr.HTML('<div class="warn-box">Can PEXELS_API_KEY trong file .env (mien phi tai pexels.com/api)</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">Anh san pham (1-5 anh)</div>')
                                remix_images = gr.File(
                                    label="Upload anh san pham (JPG/PNG)",
                                    file_types=[".jpg", ".jpeg", ".png", ".webp"],
                                    file_count="multiple",
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">Thong tin quang cao</div>')
                                remix_price = gr.Textbox(label="Gia san pham", placeholder="35,000 KHR  hoac  $5")
                                remix_url   = gr.Textbox(label="URL bai quang cao cu (de trich xuat noi dung)", placeholder="https://...")
                                remix_kw    = gr.Textbox(label="Tu khoa tim video Pexels (de trong = tu dong)", placeholder="body massage gel")
                                remix_ref   = gr.File(label="Video tham chieu nhip cat (MP4/MP3, tuy chon)", file_types=[".mp4", ".mp3", ".wav"])

                                gr.HTML('<div class="section-label" style="margin-top:1rem">Cai dat</div>')
                                with gr.Row():
                                    remix_voice = gr.Dropdown(
                                        label="Giong Khmer", choices=[c[0] for c in VOICE_CHOICES],
                                        value=VOICE_CHOICES[0][0],
                                    )
                                    remix_rate = gr.Dropdown(
                                        label="Tốc độ đọc (Tua)",
                                        choices=["+0%", "+10%", "+25%", "+50%"],
                                        value="+0%",
                                    )
                                    remix_ugc = gr.Dropdown(
                                        label="UGC Intensity", choices=UGC_LEVELS, value="medium",
                                    )
                                with gr.Row():
                                    remix_color = gr.Dropdown(
                                        label="Mau nen gia", choices=PRICE_COLORS, value="red",
                                    )
                                    remix_pexels_key = gr.Textbox(
                                        label="Pexels API Key (neu chua co trong .env)",
                                        placeholder="Paste key vao day neu chua them vao .env",
                                        type="password",
                                        value=_ENV_PEXELS,
                                    )

                                remix_out = gr.Textbox(label="Thu muc xuat", value="output")
                                run_remix = gr.Button("Tao Video Remix", elem_id="run-remix", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Ket qua</div>')
                                remix_out_video = gr.Video(label="FB Shorts Remix")
                                remix_log = gr.Textbox(label="", lines=14, interactive=False,
                                                       placeholder="Log hien o day...", elem_id="log-box")

                        def _run_remix(imgs, price, url, kw, ref_file, voice_lbl, rate_val, ugc, color, pexels_key, out_dir):
                            images = _resolve_images(imgs)
                            if not images:
                                yield None, "[LOI] Chua upload anh san pham."
                                return
                            if not price.strip():
                                yield None, "[LOI] Chua nhap gia san pham."
                                return
                            if not url.strip():
                                yield None, "[LOI] Chua nhap URL bai quang cao."
                                return
                            key = pexels_key.strip() or _ENV_PEXELS
                            if not key:
                                yield None, "[LOI] Chua co Pexels API Key. Lay mien phi tai pexels.com/api"
                                return

                            inputs = FBShortsInputs(
                                sub_mode="remix",
                                product_images=images,
                                price_text=price.strip(),
                                ad_text_url=url.strip(),
                                ref_video_url=_resolve_file(ref_file),
                                pexels_api_key=key,
                                gemini_api_key=_ENV_GEMINI,
                                tts_voice=_voice_val(voice_lbl),
                                tts_rate=rate_val,
                                ugc_intensity=ugc,
                                search_keyword=kw.strip(),
                                price_color=color,
                            )
                            yield from _stream(run_fb_shorts_pipeline, inputs, out_dir)

                        run_remix.click(
                            fn=_run_remix,
                            inputs=[remix_images, remix_price, remix_url, remix_kw, remix_ref, 
                                    remix_voice, remix_rate, remix_ugc, remix_color, remix_pexels_key, remix_out],
                            outputs=[remix_out_video, remix_log],
                        )

                    # ── TAB 5: Full Remix — Lồng Tiếng & Dựng Lại Video ────
                    with gr.Tab("Full Remix — Lồng Tiếng & Dựng Lại Video Gốc"):
                        gr.HTML('<div class="info-box">Từ 1 video nguồn gốc: AI lồng tiếng ngôn ngữ tuỳ chọn → tạo <b>1 video chính + N bản remix</b> có B-roll từ Pexels.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">1. Video Gốc Chính Chủ</div>')
                                dub_remix_file = gr.File(
                                    label="Upload Video gốc (MP4 / MOV)",
                                    file_types=[".mp4", ".mov", ".avi", ".mkv"],
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">2. Ngôn Ngữ & Âm Thanh</div>')
                                from core.language_resolver import LANGUAGE_DISPLAY_NAMES
                                dub_remix_lang = gr.Dropdown(
                                    label="🌐 Ngôn ngữ lồng tiếng",
                                    choices=list(LANGUAGE_DISPLAY_NAMES.values()),
                                    value=list(LANGUAGE_DISPLAY_NAMES.values())[0],  # Khmer
                                )
                                dub_remix_mode = gr.Radio(
                                    label="Chế độ âm thanh",
                                    choices=["A. AI tự dịch giọng sang ngôn ngữ đã chọn", "B. Nhập lời thoại tùy ý"],
                                    value="A. AI tự dịch giọng sang ngôn ngữ đã chọn",
                                )
                                dub_remix_script = gr.Textbox(
                                    label="Lời thoại tùy ý (nếu chọn B)",
                                    placeholder="Nhập script voiceover...",
                                    lines=3,
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">3. Remix & B-Roll</div>')
                                dub_remix_num = gr.Slider(
                                    label="Số bản Remix muốn tạo (0 = chỉ tạo video chính)",
                                    minimum=0, maximum=3, step=1, value=2,
                                )
                                dub_remix_broll = gr.Textbox(
                                    label="Từ khoá B-roll (tiếng Anh) — để trống = AI tự phân tích",
                                    placeholder="VD: skincare morning routine",
                                )
                                dub_remix_music = gr.Dropdown(
                                    label="Nhạc nền",
                                    choices=["upbeat", "calm", "urgent"],
                                    value="upbeat",
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">4. Che Chữ Cũ (Tùy chọn)</div>')
                                dub_remix_on_screen_text = gr.Textbox(
                                    label="Chữ phụ đề muốn viết lên video (để trống nếu không muốn)",
                                    placeholder="VD: Giảm Giá 50% Hôm Nay!",
                                    lines=2,
                                )
                                with gr.Row():
                                    dub_remix_mask_style = gr.Dropdown(
                                        label="Kiểu che chữ cũ",
                                        choices=["box (Khung viền)", "blur (Làm mờ)", "none (Không che)"],
                                        value="box (Khung viền)",
                                    )
                                    dub_remix_mask_color = gr.Dropdown(
                                        label="Màu khung viền",
                                        choices=["black", "white", "darkblue"],
                                        value="black",
                                    )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">5. Cài Đặt Nâng Cao</div>')
                                with gr.Row():
                                    dub_remix_rate = gr.Dropdown(
                                        label="Tốc độ đọc",
                                        choices=["-10%", "+0%", "+10%", "+25%"],
                                        value="+0%",
                                    )
                                    dub_remix_ugc = gr.Dropdown(
                                        label="UGC Intensity", choices=["subtle", "medium", "strong"], value="medium",
                                    )

                                # Style Profile selector — dynamically populated
                                def _get_profile_choices():
                                    from core.style_profile import list_style_profiles
                                    profiles = list_style_profiles()
                                    choices = ["— Không dùng Style Profile —"]
                                    choices += [f"{p['profile_id']} | {p['profile_name']}" for p in profiles]
                                    return choices

                                dub_remix_style = gr.Dropdown(
                                    label="🎨 Style Profile (tuỳ chọn)",
                                    choices=_get_profile_choices(),
                                    value="— Không dùng Style Profile —",
                                )

                                dub_remix_out_dir = gr.Textbox(label="Thư mục xuất", value="output")
                                run_dub_remix = gr.Button("🎬 XỬ LÝ FULL REMIX", elem_id="run-dub-remix", variant="primary", size="lg")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả</div>')
                                gr.HTML('<div class="info-box" style="font-size:0.82rem">'
                                        '📂 Các file video được lưu vào thư mục output:<br/>'
                                        '&nbsp;• <b>[tên]_main.mp4</b> — Video chính đã lồng tiếng<br/>'
                                        '&nbsp;• <b>[tên]_remix_1.mp4</b> — Remix 1 (B-roll xen đoạn 0+2)<br/>'
                                        '&nbsp;• <b>[tên]_remix_2.mp4</b> — Remix 2 (B-roll xen đoạn 1+3)'
                                        '</div>')
                                dub_remix_out_video = gr.Video(label="Video Chính (Main) Thành Phẩm")
                                dub_remix_log = gr.Textbox(label="", lines=18, interactive=False,
                                                           placeholder="Log hiển thị ở đây...", elem_id="log-box")

                        def _run_dub_remix_ui(
                            video_file, lang_display, audio_opt, script_text,
                            num_remixes, broll_query, music_energy,
                            on_screen_text, mask_style_str, mask_color_str,
                            rate_val, ugc_val, style_choice, out_dir
                        ):
                            vp = _resolve_file(video_file)
                            if not vp:
                                yield None, "[LỖI] Chưa upload video gốc."
                                return
                            audio_mode = "translate" if "AI tự dịch" in audio_opt else "custom"
                            if audio_mode == "custom" and not (script_text or "").strip():
                                yield None, "[LỖI] Chọn chế độ B nhưng chưa nhập lời thoại."
                                return

                            # Resolve language key
                            from core.language_resolver import display_name_to_key
                            lang_key = display_name_to_key(lang_display)

                            # Resolve style profile id
                            style_profile_id = ""
                            if style_choice and style_choice != "— Không dùng Style Profile —":
                                style_profile_id = style_choice.split(" | ")[0].strip()

                            mask_style = "blur" if "blur" in mask_style_str else ("none" if "none" in mask_style_str else "box")

                            from core.router import PipelineInputs, WorkflowMode, FullRemixInputs, run_pipeline
                            inputs = PipelineInputs(
                                mode=WorkflowMode.FULL_REMIX,
                                product_image="",
                                full_remix=FullRemixInputs(
                                    source_video=vp,
                                    audio_mode=audio_mode,
                                    target_language=lang_key,
                                    tts_voice="",          # auto-resolved from language
                                    script=script_text.strip() if script_text else "",
                                    on_screen_text=on_screen_text.strip() if on_screen_text else "",
                                    mask_style=mask_style,
                                    mask_color=mask_color_str,
                                    create_remix=int(num_remixes) > 0,
                                    num_remixes=int(num_remixes),
                                    broll_query=broll_query.strip() if broll_query else "",
                                    music_energy=music_energy,
                                    ugc_intensity=ugc_val,
                                    tts_rate=rate_val,
                                    style_profile_id=style_profile_id,
                                ),
                                output_dir=out_dir,
                            )
                            yield from _stream(run_pipeline, inputs)

                        run_dub_remix.click(
                            fn=_run_dub_remix_ui,
                            inputs=[
                                dub_remix_file, dub_remix_lang, dub_remix_mode, dub_remix_script,
                                dub_remix_num, dub_remix_broll, dub_remix_music,
                                dub_remix_on_screen_text, dub_remix_mask_style, dub_remix_mask_color,
                                dub_remix_rate, dub_remix_ugc, dub_remix_style, dub_remix_out_dir
                            ],
                            outputs=[dub_remix_out_video, dub_remix_log],
                        )

            with gr.Tab("🛒 Quảng Cáo & Thương Mại"):
                with gr.Tabs():
                    # ── TAB 10: Ultimate Ad (Mode 10) ────────────────
                    with gr.Tab("Ultimate Ad (Mode 10) 🌟"):
                        gr.HTML('<div class="info-box">Tạo quảng cáo chuyên nghiệp chuẩn Agency. Áp dụng drift cuts 0.18s, Mixkit SFX, B-roll tự động. (Khuyên dùng)</div>')
                        gr.HTML('<div class="warn-box">Cần GEMINI_API_KEY. Render cực nhanh và 100% miễn phí.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">1. Hình Ảnh & Thông Tin Cơ Bản</div>')
                                ult_image = gr.File(
                                    label="Upload ảnh sản phẩm chính (JPG/PNG - Tùy chọn)",
                                    file_types=[".jpg", ".jpeg", ".png", ".webp"],
                                )
                                ult_name = gr.Textbox(label="Tên sản phẩm", placeholder="Ví dụ: Gôm Vuốt Tóc Kềm")
                                ult_price = gr.Textbox(label="Giá (tùy chọn)", placeholder="Ví dụ: 15,000 KHR")
                                ult_lang = gr.Dropdown(
                                    label="Ngôn ngữ",
                                    choices=["vietnamese", "khmer", "english"],
                                    value="vietnamese",
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">2. Dữ Liệu Marketing</div>')
                                ult_benefits = gr.Textbox(label="Ưu điểm (cách nhau dấu phẩy)", placeholder="Giữ nếp 24h, Thơm mát")
                                ult_pain = gr.Textbox(label="Vấn đề khách hàng", placeholder="Tóc xẹp, Tóc rối")
                                ult_script = gr.Textbox(label="Kịch bản tự viết (Để trống để AI tự sinh)", placeholder="Tùy chọn: Nhập script...", lines=3)

                                gr.HTML('<div class="section-label" style="margin-top:1rem">3. Cài Đặt Khác</div>')
                                ult_template = gr.Dropdown(
                                    label="Template Quảng Cáo",
                                    choices=[
                                        "motion-graphics-spot",
                                        "talking-head-founder-ad",
                                        "split-screen",
                                        "imessage-conversation",
                                        "listicle-top5",
                                        "revid-story",
                                        "whiteboard"
                                    ],
                                    value="motion-graphics-spot",
                                )
                                ult_hooks = gr.Slider(label="Số lượng Hook (A/B Test)", minimum=1, maximum=5, value=3, step=1)
                                ult_ntd_dir = gr.Textbox(label="Thư mục NTD-Labs Assets (Tùy chọn)", placeholder="C:/NTD_Exports/")
                                ult_out_dir = gr.Textbox(label="Thư mục xuất", value="output")
                                run_ult = gr.Button("Tạo Video Ultimate Ad", elem_id="run-ult", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả</div>')
                                ult_out_video = gr.Video(label="Video (Hiển thị 1 bản mẫu)")
                                ult_log = gr.Textbox(label="", lines=14, interactive=False, placeholder="Log hiển thị ở đây...", elem_id="log-box")

                        def _run_ultimate_ad(img, name, price, lang, benefits, pain, script_text, template, hooks, ntd_dir, out_dir):
                            if not name.strip() and not (script_text or "").strip():
                                yield None, "[LỖI] Cần ít nhất tên sản phẩm hoặc kịch bản tự viết."
                                return

                            vp = _resolve_file(img)
                            b_list = [b.strip() for b in (benefits or "").split(",") if b.strip()]
                            p_list = [p.strip() for p in (pain or "").split(",") if p.strip()]

                            from core.router import PipelineInputs, WorkflowMode, run_pipeline
                            from core.config import UltimateAdInputs
                            
                            inp = UltimateAdInputs(
                                product_name=name.strip(),
                                target_language=lang,
                                product_image=vp or "",
                                price=price.strip(),
                                key_benefits=b_list,
                                pain_points=p_list,
                                ad_template=template,
                                num_hook_variants=int(hooks),
                                script_text=(script_text or "").strip(),
                                ntd_assets_dir=(ntd_dir or "").strip()
                            )
                            
                            inputs = PipelineInputs(
                                mode=WorkflowMode.ULTIMATE_AD,
                                product_image=vp or "",
                                ultimate_ad=inp,
                                output_dir=out_dir,
                            )
                            yield from _stream(run_pipeline, inputs)

                        run_ult.click(
                            fn=_run_ultimate_ad,
                            inputs=[ult_image, ult_name, ult_price, ult_lang, ult_benefits, ult_pain, ult_script, ult_template, ult_hooks, ult_ntd_dir, ult_out_dir],
                            outputs=[ult_out_video, ult_log],
                        )

                    # ── TAB 11: Visual Search Engine ────────────────
                    with gr.Tab("Visual Search Engine 🔍"):
                        gr.HTML('<div class="info-box">Tìm kiếm sản phẩm hoặc ảnh b-roll có nét tương đồng cao nhất (dùng AI ResNet50).</div>')
                        
                        with gr.Row():
                            with gr.Column(scale=4):
                                vs_image = gr.Image(label="Upload ảnh cần tìm (Query Image)", type="pil")
                                vs_threshold = gr.Slider(label="Độ chính xác (Threshold)", minimum=0.1, maximum=1.0, value=0.7, step=0.05)
                                vs_top_n = gr.Slider(label="Số kết quả (Top N)", minimum=1, maximum=12, value=5, step=1)
                                run_vs = gr.Button("🔍 Tìm Kiếm Ảnh", elem_id="run-vs", variant="primary")
                                
                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả tìm kiếm</div>')
                                vs_gallery = gr.Gallery(label="Ảnh tương đồng tìm thấy")
                                vs_log = gr.Textbox(label="Log / Trạng thái", lines=2)

                        def _run_visual_search(query_img, thresh, top_n):
                            if query_img is None:
                                yield [], "Vui lòng upload ảnh!"
                                return
                            try:
                                yield [], "Đang nạp Model ResNet50 và quét Database (Vui lòng đợi vài giây)..."
                                from core.product_vision_index import search_engine
                                results = search_engine.find_similar_images(query_img, threshold=thresh, top_n=top_n)
                                if not results:
                                    yield [], "Không tìm thấy ảnh nào tương đồng trên mức threshold!"
                                    return
                                
                                import os
                                gallery_imgs = []
                                logs = []
                                for item in results:
                                    path = item["path"]
                                    score = item["score"]
                                    name = item.get("product_name", "Unknown")
                                    price = item.get("price", "")
                                    claims = item.get("key_claims", "")
                                    
                                    # Tạo caption hiển thị trong Gallery
                                    caption = f"[{score:.2f}] {name}"
                                    if price:
                                        caption += f" | Giá: {price}"
                                        
                                    gallery_imgs.append((path, caption))
                                    
                                    # Log chi tiết
                                    logs.append(f"• {name} (Độ khớp: {score:.2f})")
                                    if price: logs.append(f"  Giá: {price}")
                                    if claims: logs.append(f"  Claims: {claims}")
                                    logs.append("")
                                    
                                yield gallery_imgs, "Đã tìm thấy các sản phẩm sau:\n" + "\n".join(logs)
                            except Exception as exc:
                                yield [], f"Lỗi: {exc}"
                                
                        run_vs.click(
                            fn=_run_visual_search,
                            inputs=[vs_image, vs_threshold, vs_top_n],
                            outputs=[vs_gallery, vs_log],
                        )

                    # ── TAB 12: Ad Spy Engine ────────────────
                    with gr.Tab("Ad Spy (Meta & TikTok) 🕵️"):
                        gr.HTML('<div class="info-box">Tìm kiếm và sao chép nội dung quảng cáo (Copywriting) đang chạy từ Meta Ad Library và TikTok API.</div>')
                        
                        with gr.Row():
                            with gr.Column(scale=4):
                                spy_platform = gr.Radio(["Meta (Facebook)", "TikTok"], label="Nền tảng", value="Meta (Facebook)")
                                spy_keyword = gr.Textbox(label="Từ khóa tìm kiếm (Ví dụ: kem chống nắng)", placeholder="Nhập từ khóa...")
                                spy_limit = gr.Slider(label="Số kết quả", minimum=1, maximum=20, value=5, step=1)
                                run_spy = gr.Button("🕵️ Spy Ads", elem_id="run-spy", variant="primary")
                                
                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Nội dung Ads (Copywriting / Script)</div>')
                                spy_results = gr.Textbox(label="Kết quả tìm kiếm", lines=15, interactive=False, placeholder="Nội dung kịch bản quảng cáo sẽ hiển thị ở đây...")

                        def _run_ad_spy(platform, keyword, limit):
                            if not keyword or not keyword.strip():
                                yield "Vui lòng nhập từ khóa tìm kiếm (Ví dụ: dao, kem chống nắng, mỹ phẩm...)"
                                return
                                
                            keyword = keyword.strip()
                            yield f"🕵️ Đang quét kịch bản quảng cáo đối thủ cho từ khóa '{keyword}' trên {platform}..."

                            results_text = []
                            ads = []
                            
                            try:
                                import os
                                if "Meta" in platform:
                                    from core.ad_library_client import MetaAdLibraryClient
                                    client = MetaAdLibraryClient()
                                    ads = client.search_ads(keyword, limit=limit)
                                    if ads:
                                        for i, ad in enumerate(ads):
                                            content = client.extract_ad_content(ad)
                                            results_text.append(f"--- AD #{i+1} (Meta API) ---")
                                            results_text.append(f"Tiêu đề: {content.get('headline')}")
                                            results_text.append(f"Nội dung chính:\n{content.get('primary_text')}")
                                            results_text.append(f"Nền tảng: {content.get('platforms')}")
                                            results_text.append(f"Xem chi tiết: {content.get('snapshot_url')}\n")
                                            
                                elif "TikTok" in platform:
                                    from core.tiktok_api_client import TikTokAdClient
                                    client = TikTokAdClient()
                                    ads = client.search_ads(keyword, limit=limit)
                                    if ads:
                                        for i, ad in enumerate(ads):
                                            content = client.extract_ad_content(ad)
                                            results_text.append(f"--- AD #{i+1} (TikTok API) ---")
                                            results_text.append(f"Brand: {content.get('brand_name')}")
                                            results_text.append(f"Nội dung:\n{content.get('primary_text')}")
                                            results_text.append(f"Video URL: {content.get('video_url')}\n")
                                            
                                # Fallback: Sử dụng AI Intelligence khi App ở Sandbox hoặc API chưa cấp quyền Ads Archive
                                if not ads:
                                    api_key = os.getenv("GEMINI_API_KEY", "")
                                    if api_key:
                                        from google import genai
                                        from core.gemini_pool import get_pooled_client
                                        client_ai = get_pooled_client(api_key=api_key)
                                        prompt = f"""Bạn là một chuyên gia Spy Ads và Copywriting hàng đầu trên {platform}.
Hãy phân tích và viết ra {limit} kịch bản quảng cáo video ngắn (TikTok/Reels/Shorts) triệu view đang có tỷ lệ chuyển đổi cao nhất cho sản phẩm/từ khóa: "{keyword}".

Với mỗi mẫu quảng cáo (Ví dụ: Mẫu #1, Mẫu #2...), hãy trình bày rõ ràng:
- **Tên Góc Nhìn / Concept**: 
- **Hook 3 giây đầu tiên (Cực hút)**: 
- **Kịch bản Lời thoại / Caption chi tiết**: 
- **Góc quay Video gợi ý (B-Roll)**: 
- **Lời kêu gọi hành động (CTA)**: 

Hãy viết chuẩn tiếng Việt bán hàng hấp dẫn, giữ nguyên phong cách người thật quay (UGC) đỉnh cao."""
                                        
                                        candidate_models = ['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash', 'gemini-pro-latest']
                                        ai_text = None
                                        for m in candidate_models:
                                            try:
                                                resp = client_ai.models.generate_content(
                                                    model=m,
                                                    contents=prompt
                                                )
                                                if resp and resp.text:
                                                    ai_text = resp.text
                                                    break
                                            except Exception:
                                                continue

                                        if ai_text:
                                            results_text.append(f"⚡ KỊCH BẢN QUẢNG CÁO PHÂN TÍCH CHO TỪ KHÓA: '{keyword}' ({platform})\n")
                                            results_text.append(ai_text)

                                            
                                if results_text:
                                    yield "\n".join(results_text)
                                else:
                                    yield f"Không tìm thấy Ads hoặc Lỗi Token. Vui lòng kiểm tra lại thiết lập."
                            except Exception as exc:
                                yield f"Lỗi: {exc}"
                                
                    # ── TAB: Google Scene Machine ────────────────────────
                    with gr.Tab("🎬 Google Scene Machine"):
                        gr.HTML('<div class="info-box">Tích hợp Google Marketing Solutions Scene Machine: Tạo video quảng cáo từ Storyboard 4-cảnh tự động (Gemini 3.6 + Scene Pipeline).</div>')

                        with gr.Row():
                            with gr.Column(scale=5):
                                sm_image = gr.File(label="Upload ảnh sản phẩm chính (JPG/PNG)", file_types=[".jpg", ".jpeg", ".png", ".webp"])
                                sm_name = gr.Textbox(label="Tên Sản Phẩm", placeholder="Ví dụ: Kem dưỡng da trị mụn...")
                                sm_audience = gr.Textbox(label="Đối tượng khách hàng", value="Khách hàng Việt Nam")
                                sm_tone = gr.Textbox(label="Phong cách / Tone giọng", value="Thuyết phục, Hiện đại, Chân thực")
                                sm_scenes_cnt = gr.Slider(minimum=3, maximum=6, step=1, value=4, label="Số lượng Cảnh (Scenes)")

                                btn_gen_storyboard = gr.Button("1. 📝 Tạo Storyboard (Scene Machine)", variant="secondary")
                                btn_render_sm_video = gr.Button("2. 🚀 Render Video Quảng Cáo (Scene Machine)", variant="primary")

                            with gr.Column(scale=7):
                                sm_storyboard_json = gr.JSON(label="Kịch Bản Storyboard Theo Cảnh (Scenes)")
                                sm_output_video = gr.Video(label="Video Thành Phẩm (Scene Machine)")
                                sm_log = gr.Textbox(label="Trạng thái & Tiến trình", lines=8, interactive=False)

                        def _run_sm_storyboard(image_file, name, audience, tone, num_scenes):
                            img_path = _resolve_file(image_file)
                            if not name:
                                yield "[LỖI] Vui lòng nhập tên sản phẩm.", None
                                return
                            yield "Đang gọi Gemini 3.6 Flash sinh Storyboard chuẩn Google Scene Machine...", None
                            from core.scene_machine_engine import generate_scene_machine_storyboard
                            sb = generate_scene_machine_storyboard(
                                product_image_path=img_path or "",
                                product_name=name,
                                target_audience=audience,
                                brand_tone=tone,
                                num_scenes=int(num_scenes)
                            )
                            if sb:
                                yield f"✅ Đã tạo thành công Storyboard {len(sb)} Cảnh!", sb
                            else:
                                yield "[LỖI] Không thể tạo Storyboard. Kiểm tra GEMINI_API_KEY.", None

                        def _run_sm_render(image_file, name, audience, tone, num_scenes, current_sb):
                            img_path = _resolve_file(image_file)
                            if not current_sb:
                                yield None, "[LỖI] Chưa có Storyboard. Vui lòng bấm 'Tạo Storyboard' trước."
                                return
                            yield None, "🚀 Đang tiến hành dựng video từng Cảnh (Scene Machine Pipeline)..."
                            from core.scene_machine_engine import render_scene_machine_video
                            out_path = "output/google_scene_machine_ad.mp4"
                            res = render_scene_machine_video(
                                storyboard=current_sb,
                                product_image_path=img_path or "",
                                output_path=out_path
                            )
                            if res and os.path.exists(res):
                                yield res, "🎉 Đã xuất thành công Video Quảng Cáo từ Google Scene Machine!"
                            else:
                                yield None, "[LỖI] Dựng video thất bại. Kiểm tra logs."

                        btn_gen_storyboard.click(
                            fn=_run_sm_storyboard,
                            inputs=[sm_image, sm_name, sm_audience, sm_tone, sm_scenes_cnt],
                            outputs=[sm_log, sm_storyboard_json]
                        )
                        btn_render_sm_video.click(
                            fn=_run_sm_render,
                            inputs=[sm_image, sm_name, sm_audience, sm_tone, sm_scenes_cnt, sm_storyboard_json],
                            outputs=[sm_output_video, sm_log]
                        )
                    # ── TAB: Stockpile AI B-Roll Curator ──────────────────
                    with gr.Tab("📦 Stockpile AI B-Roll Curator"):
                        gr.HTML('<div class="info-box">Tích hợp sasoder/stockpile: AI tự động tìm kiếm, cào & tuyển chọn B-Roll video HD từ từ khóa/sản phẩm lưu vào thư viện local.</div>')

                        with gr.Row():
                            with gr.Column(scale=5):
                                st_keyword = gr.Textbox(label="Từ khóa / Sản phẩm cào B-Roll", placeholder="Ví dụ: dao bếp, lược chải tóc, mỹ phẩm...")
                                st_clips_cnt = gr.Slider(minimum=1, maximum=8, step=1, value=3, label="Số lượng video B-Roll cào về")
                                btn_run_stockpile = gr.Button("📦 Cào & Tuyển Chọn B-Roll (Stockpile AI)", variant="primary")

                            with gr.Column(scale=7):
                                st_results_files = gr.Files(label="Danh sách Video B-Roll đã cào về thư viện local")
                                st_log = gr.Textbox(label="Trạng thái & Tiến trình", lines=8, interactive=False)

                        def _run_stockpile_curator(kw, max_c):
                            if not kw or not kw.strip():
                                yield "[LỖI] Vui lòng nhập từ khóa sản phẩm.", None
                                return
                            kw = kw.strip()
                            yield f"📦 AI Stockpile đang mở rộng từ khóa và cào B-roll cho '{kw}'...", None
                            from core.stockpile_broll_curator import curate_and_download_broll
                            files = curate_and_download_broll(keyword=kw, max_clips=int(max_c))
                            if files:
                                yield f"🎉 Đã cào & tuyển chọn thành công {len(files)} clip B-Roll lưu vào thư viện assets/local_broll!", files
                            else:
                                yield "⚠️ Không cào được clip nào hoặc mạng bị gián đoạn. Thử lại sau.", None

                        btn_run_stockpile.click(
                            fn=_run_stockpile_curator,
                            inputs=[st_keyword, st_clips_cnt],
                            outputs=[st_log, st_results_files]
                        )

                    # ── TAB: Logo & Watermark Remover ─────────────────────
                    with gr.Tab("🧹 Xóa Logo Video (Logo Remover)"):
                        gr.HTML('<div class="info-box">Tích hợp shijincai/remove-logo-from-video: Tự động xóa logo, watermark, chữ rác hoặc ID TikTok/Douyin khỏi video clip B-roll.</div>')

                        with gr.Row():
                            with gr.Column(scale=5):
                                rm_video = gr.File(label="Upload Video cần xóa Logo (.mp4)", file_types=[".mp4", ".mov", ".avi", ".mkv"])
                                rm_mode = gr.Radio(
                                    choices=["Tự động xóa TikTok Watermark", "Xóa theo Tọa độ tùy chỉnh", "Làm mờ vùng Logo (Blur)"],
                                    value="Tự động xóa TikTok Watermark",
                                    label="Chế độ xóa Logo"
                                )
                                with gr.Row():
                                    rm_x = gr.Number(value=50, label="Tọa độ X")
                                    rm_y = gr.Number(value=50, label="Tọa độ Y")
                                    rm_w = gr.Number(value=200, label="Rộng (Width)")
                                    rm_h = gr.Number(value=100, label="Cao (Height)")

                                btn_run_remove_logo = gr.Button("🧹 Xóa Logo & Watermark Ngay", variant="primary")

                            with gr.Column(scale=7):
                                rm_out_video = gr.Video(label="Video Đã Xóa Logo Sạch Sẽ")
                                rm_log = gr.Textbox(label="Trạng thái & Tiến trình", lines=8, interactive=False)

                        def _run_logo_remover(video_file, mode_choice, x, y, w, h):
                            vp = _resolve_file(video_file)
                            if not vp:
                                yield None, "[LỖI] Chưa upload file video."
                                return

                            yield None, "🧹 Đang tiến hành xóa logo và watermark khỏi video..."
                            from core.logo_remover import remove_video_logo
                            out_p = os.path.join(_run_temp_dir("logo_remover"), os.path.basename(vp))

                            mode_key = "auto_tiktok"
                            if "Tọa độ" in mode_choice:
                                mode_key = "custom_box"
                            elif "Làm mờ" in mode_choice:
                                mode_key = "blur"

                            res = remove_video_logo(
                                input_video_path=vp,
                                output_video_path=out_p,
                                x=int(x or 50), y=int(y or 50),
                                w=int(w or 200), h=int(h or 100),
                                mode=mode_key
                            )

                            if res and os.path.exists(res):
                                yield res, "🎉 Đã xóa logo thành công! File video sạch sẵn sàng sử dụng."
                            else:
                                yield None, "[LỖI] Xóa logo thất bại. Kiểm tra file video."

                        btn_run_remove_logo.click(
                            fn=_run_logo_remover,
                            inputs=[rm_video, rm_mode, rm_x, rm_y, rm_w, rm_h],
                            outputs=[rm_out_video, rm_log]
                        )
                    # ── TAB: Auto-Discovery & Assembly ─────────────────────
                    with gr.Tab("🔍 Auto-Discovery & Assembly"):
                        gr.HTML('<div class="info-box">Tính năng 2-in-1: Tự động quét thông tin sản phẩm và video liên quan, sau đó cho phép tự tạo mới hoặc lắp ráp lên video có sẵn.</div>')
                        
                        # Store temporary report state
                        state_report = gr.State(None)

                        with gr.Row():
                            with gr.Column(scale=5):
                                gr.HTML('<div class="section-label">Bước 1: Khám Phá & Quét Dữ Liệu</div>')
                                ad_image = gr.File(label="Upload ảnh sản phẩm", file_types=[".jpg", ".png", ".webp"])
                                ad_keyword = gr.Textbox(label="Từ khóa / Tên sản phẩm", placeholder="Ví dụ: sữa rửa mặt")
                                btn_discovery = gr.Button("🔍 1. Quét & Khám Phá Sản Phẩm", variant="secondary")

                            with gr.Column(scale=7):
                                ad_html_report = gr.HTML("<p>Chưa có dữ liệu.</p>")
                                
                        gr.HTML('<hr/>')
                                
                        with gr.Row():
                            with gr.Column(scale=5):
                                gr.HTML('<div class="section-label">Bước 2: Chọn Hướng Xử Lý</div>')
                                gr.HTML('<p><b>Hướng A:</b> Sang tab <i>Ultimate Ad</i> hoặc <i>Scene Machine</i> để tạo video từ B-roll mới.</p>')
                                gr.HTML('<p><b>Hướng B: Lắp Ráp Video Có Sẵn</b> (Xóa logo, tắt tiếng cũ, lồng tiếng AI mới)</p>')
                                
                                ad_video_file = gr.File(label="Upload video gốc để lắp ráp", file_types=[".mp4"])
                                btn_assembly = gr.Button("🎬 2. Lắp Ráp & Lồng Tiếng Video Này", variant="primary")
                                
                            with gr.Column(scale=7):
                                ad_final_video = gr.Video(label="Video Thành Phẩm")
                                ad_log = gr.Textbox(label="Tiến trình", lines=4, interactive=False)
                                
                        def _run_step1(img, kw):
                            img_path = _resolve_file(img) or ""
                            if not kw and not img_path:
                                return "<p style='color:red;'>Vui lòng tải lên 1 ảnh hoặc nhập từ khóa!</p>", None
                            from core.auto_discovery_engine import run_full_discovery, format_report_html
                            report = run_full_discovery(img_path, kw)
                            html = format_report_html(report)
                            import dataclasses
                            return html, dataclasses.asdict(report)
                            
                        def _run_step2(vid_file, report_dict):
                            if not vid_file:
                                yield None, "[LỖI] Vui lòng upload file video cần lắp ráp."
                                return
                            if not report_dict:
                                yield None, "[LỖI] Vui lòng chạy Bước 1 trước."
                                return
                                
                            yield None, "🎬 Đang tiến hành lắp ráp video (Xóa logo, Lồng tiếng, Thêm nhạc)..."
                            
                            vp = _resolve_file(vid_file)
                            from core.video_assembly_engine import assemble_existing_video
                            out_p = os.path.join(_run_temp_dir("assembly"), os.path.basename(vp))
                            
                            res = assemble_existing_video(
                                video_path=vp,
                                product_name=report_dict.get("product_name", "Sản phẩm"),
                                benefits=report_dict.get("benefits", []),
                                output_path=out_p
                            )
                            if res and os.path.exists(res):
                                yield res, "🎉 Lắp ráp thành công! Video chuẩn 9:16 sẵn sàng chạy Ads."
                            else:
                                yield None, "[LỖI] Quá trình lắp ráp thất bại."

                        btn_discovery.click(
                            fn=_run_step1,
                            inputs=[ad_image, ad_keyword],
                            outputs=[ad_html_report, state_report]
                        )
                        btn_assembly.click(
                            fn=_run_step2,
                            inputs=[ad_video_file, state_report],
                            outputs=[ad_final_video, ad_log]
                        )


                    # ── TAB 6: Pro Editor (A/B Test Hooks) ────────────────
                    with gr.Tab("Pro Editor (Mode 7)"):



                        gr.HTML('<div class="info-box">Tạo quảng cáo chuyên nghiệp với cấu trúc Hook-PAS-Proof-CTA, tự động tìm B-roll và ghép nhạc nền.</div>')
                        gr.HTML('<div class="warn-box">Cần GEMINI_API_KEY. Tùy chọn: PEXELS_API_KEY và PIXABAY_API_KEY trong .env.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">1. Hình Ảnh & Thông Tin Cơ Bản</div>')
                                pro_image = gr.File(
                                    label="Upload ảnh sản phẩm chính (JPG/PNG)",
                                    file_types=[".jpg", ".jpeg", ".png", ".webp"],
                                )
                                pro_name = gr.Textbox(label="Tên sản phẩm", placeholder="Ví dụ: Gôm Vuốt Tóc Kềm")
                                pro_price = gr.Textbox(label="Giá (tùy chọn)", placeholder="Ví dụ: 15,000 KHR")

                                gr.HTML('<div class="section-label" style="margin-top:1rem">2. Dữ Liệu Marketing</div>')
                                pro_benefits = gr.Textbox(label="Ưu điểm (cách nhau dấu phẩy)", placeholder="Giữ nếp 24h, Thơm mát, Không bết dính")
                                pro_pain = gr.Textbox(label="Vấn đề khách hàng (cách nhau dấu phẩy)", placeholder="Tóc xẹp, Tóc rối")

                                gr.HTML('<div class="section-label" style="margin-top:1rem">3. Cài Đặt Khác</div>')
                                with gr.Row():
                                    pro_hooks = gr.Slider(label="Số lượng Video Hook (A/B Test)", minimum=2, maximum=5, value=3, step=1)
                                    pro_voice = gr.Dropdown(
                                        label="Giọng đọc Khmer", choices=[c[0] for c in VOICE_CHOICES],
                                        value=VOICE_CHOICES[0][0],
                                    )
                                    pro_rate = gr.Dropdown(
                                        label="Tốc độ đọc (Tua)",
                                        choices=["+0%", "+10%", "+25%", "+50%"],
                                        value="+0%",
                                    )
                        
                                gr.HTML('<div class="section-label" style="margin-top:1rem">4. Kiểu Phụ Đề (Caption Style)</div>')
                                # Gallery of 4 presets
                                import os
                                gallery_items = []
                                for preset, display in [
                                    ("classic_box", "Classic Box"),
                                    ("outline_bold", "Outline Bold"),
                                    ("karaoke_highlight", "Karaoke Highlight"),
                                    ("minimal_clean", "Minimal Clean"),
                                ]:
                                    path = f"assets/caption_style_previews/{preset}.png"
                                    if os.path.exists(path):
                                        gallery_items.append((path, display))
                                
                                pro_caption_gallery = gr.Gallery(
                                    label="Chọn kiểu phụ đề (Bấm vào ảnh)",
                                    show_label=True,
                                    elem_id="caption-gallery",
                                    columns=4,
                                    rows=1,
                                    height=220,
                                    allow_preview=False,
                                    interactive=True,
                                    value=gallery_items,
                                )
                                pro_caption_style = gr.Textbox(value="classic_box", visible=False)
                        
                                # Map gallery index to preset name
                                preset_keys = ["classic_box", "outline_bold", "karaoke_highlight", "minimal_clean"]
                                pro_caption_gallery.select(
                                    fn=lambda evt: preset_keys[evt.index] if evt.index < len(preset_keys) else "classic_box",
                                    inputs=[],
                                    outputs=[pro_caption_style]
                                )
                        
                                pro_out_dir = gr.Textbox(label="Thư mục xuất", value="output")
                                run_pro = gr.Button("Tạo Video Pro Editor", elem_id="run-pro", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả</div>')
                                pro_out_video = gr.Video(label="Video (Hiển thị 1 bản mẫu)")
                                pro_log = gr.Textbox(label="", lines=14, interactive=False,
                                                     placeholder="Log hiển thị ở đây...", elem_id="log-box")

                        def _run_pro_editor(img, name, price, benefits, pain, hooks, voice_lbl, rate_val, cap_style, out_dir):
                            vp = _resolve_file(img)
                            if not vp:
                                yield None, "[LỖI] Chưa upload ảnh sản phẩm."
                                return
                            if not name.strip():
                                yield None, "[LỖI] Chưa nhập tên sản phẩm."
                                return

                            from core.router import PipelineInputs, WorkflowMode, run_pipeline
                            from core.config import ProEditorInputs
                    
                            b_list = [b.strip() for b in benefits.split(",") if b.strip()]
                            p_list = [p.strip() for p in pain.split(",") if p.strip()]

                            inputs = PipelineInputs(
                                mode=WorkflowMode.PRO_EDITOR,
                                product_image=vp,
                                pro_editor=ProEditorInputs(
                                    product_image=vp,
                                    product_name=name.strip(),
                                    price=price.strip(),
                                    key_benefits=b_list,
                                    pain_points=p_list,
                                    num_hook_variants=int(hooks),
                                    tts_voice=_voice_val(voice_lbl),
                                    tts_rate=rate_val,
                                    caption_style=cap_style,
                                ),
                                output_dir=out_dir,
                            )
                            # Chạy pipeline stream log
                            yield from _stream(run_pipeline, inputs)

                        run_pro.click(
                            fn=_run_pro_editor,
                            inputs=[pro_image, pro_name, pro_price, pro_benefits, pro_pain, pro_hooks, pro_voice, pro_rate, pro_caption_style, pro_out_dir],
                            outputs=[pro_out_video, pro_log],
                        )


                    # ── TAB 7: News Ads — Quảng Cáo Tin Tức (Mode 8) ────────────────
                    with gr.Tab("News Ads (Mode 8)"):
                        gr.HTML('<div class="info-box">Kết hợp News Auto & Pro Editor: quảng cáo dạng bản tin thời sự giúp né "banner blindness".</div>')
                        gr.HTML('<div class="warn-box">Cần GEMINI_API_KEY.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">1. Cài đặt Format & Nguồn</div>')
                                news_ads_format = gr.Dropdown(
                                    label="Format Style",
                                    choices=["news_style_ad", "pure_news", "direct_ad"],
                                    value="news_style_ad",
                                )
                                news_ads_source_type = gr.Radio(
                                    label="Loại Nguồn",
                                    choices=["product", "topic", "article"],
                                    value="product",
                                )
                                news_ads_source_content = gr.Textbox(
                                    label="Nội dung nguồn (Topic, Text Bài báo, v.v.)",
                                    placeholder="Nhập nội dung nếu chọn topic/article...",
                                    lines=3,
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">2. Thông tin Sản phẩm (Nếu có)</div>')
                                news_ads_product_image = gr.File(
                                    label="Upload ảnh sản phẩm (JPG/PNG)",
                                    file_types=[".jpg", ".jpeg", ".png", ".webp"],
                                )
                                news_ads_product_name = gr.Textbox(label="Tên sản phẩm", placeholder="Gôm vuốt tóc")
                                news_ads_price = gr.Textbox(label="Giá", placeholder="15,000 KHR")
                                news_ads_benefits = gr.Textbox(label="Ưu điểm", placeholder="Thơm mát, Giữ nếp")
                                news_ads_pain = gr.Textbox(label="Vấn đề", placeholder="Tóc rối")

                                gr.HTML('<div class="section-label" style="margin-top:1rem">3. Cài Đặt Chung</div>')
                                with gr.Row():
                                    news_ads_channel = gr.Textbox(label="Tên Kênh (Watermark)", value="KHMER NEWS DAILY")
                                    news_ads_hooks = gr.Slider(label="Số lượng Hook", minimum=2, maximum=5, value=3, step=1)
                                with gr.Row():
                                    news_ads_voice = gr.Radio(
                                        label="Giọng đọc",
                                        choices=[c[0] for c in VOICE_CHOICES],
                                        value=VOICE_CHOICES[0][0],
                                    )
                                    news_ads_rate = gr.Dropdown(
                                        label="Tốc độ đọc (Tua)",
                                        choices=["+0%", "+10%", "+25%", "+50%"],
                                        value="+0%",
                                    )
                                    news_ads_quality = gr.Dropdown(
                                        label="Chất lượng",
                                        choices=["720p", "1080p", "4k"],
                                        value="1080p",
                                    )

                                news_ads_out_dir = gr.Textbox(label="Thư mục xuất", value="output")
                                run_news_ads = gr.Button("Tạo Video News Ads", elem_id="run-news", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả</div>')
                                news_ads_out_video = gr.Video(label="Video (Hiển thị 1 bản mẫu)")
                                news_ads_log = gr.Textbox(label="", lines=14, interactive=False,
                                                     placeholder="Log hiển thị ở đây...", elem_id="log-box")

                        def _run_news_ads(fmt, stype, scontent, p_img, p_name, price, benefits, pain, channel, hooks, voice_lbl, rate_val, qual, out_dir):
                            vp = _resolve_file(p_img)
                            if stype == "product" and not vp and not p_name.strip():
                                yield None, "[LỖI] Cần nhập ảnh hoặc tên sản phẩm khi chọn source_type='product'."
                                return

                            from core.router import PipelineInputs, WorkflowMode, run_pipeline
                            from core.config import NewsAdsInputs
                    
                            b_list = [b.strip() for b in benefits.split(",") if b.strip()]
                            p_list = [p.strip() for p in pain.split(",") if p.strip()]

                            inputs = PipelineInputs(
                                mode=WorkflowMode.NEWS_ADS,
                                product_image=vp or "",
                                news_ads=NewsAdsInputs(
                                    source_type=stype,
                                    source_content=scontent.strip(),
                                    product_name=p_name.strip(),
                                    product_image=vp or "",
                                    price=price.strip(),
                                    key_benefits=b_list,
                                    pain_points=p_list,
                                    format_style=fmt,
                                    channel_name=channel.strip(),
                                    target_duration_sec=90,
                                    target_language="khmer",
                                    num_hook_variants=int(hooks),
                                    output_quality=qual,
                                    tts_voice=_voice_val(voice_lbl),
                                    tts_rate=rate_val,
                                ),
                                output_dir=out_dir,
                            )
                            yield from _stream(run_pipeline, inputs)

                        run_news_ads.click(
                            fn=_run_news_ads,
                            inputs=[news_ads_format, news_ads_source_type, news_ads_source_content, news_ads_product_image, news_ads_product_name, news_ads_price, news_ads_benefits, news_ads_pain, news_ads_channel, news_ads_hooks, news_ads_voice, news_ads_rate, news_ads_quality, news_ads_out_dir],
                            outputs=[news_ads_out_video, news_ads_log],
                        )


                    # ── TAB 8: News Pro — Quảng Cáo Bán Tự Động (Mode 9) ────────────────
                    with gr.Tab("News Pro (Mode 9)"):
                        gr.HTML('<div class="info-box">Phân tích ảnh tự động & tạo Prompt mẫu để bạn copy/paste sang Gemini Web, lách giới hạn API.</div>')
                        gr.HTML('<div class="warn-box">Cần GEMINI_API_KEY để phân tích ảnh.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">1. Upload Ảnh & Tự Động Điền Form</div>')
                                news_pro_image = gr.File(
                                    label="Upload ảnh sản phẩm (JPG/PNG)",
                                    file_types=[".jpg", ".jpeg", ".png", ".webp"],
                                    file_count="multiple",
                                )
                                btn_analyze_image = gr.Button("Phân tích ảnh & tự động điền", variant="secondary")

                                gr.HTML('<div class="section-label" style="margin-top:1rem">2. Chỉnh Sửa Thông Tin (Checkpoint)</div>')
                                news_pro_product_name = gr.Textbox(label="Tên sản phẩm", placeholder="Tên sản phẩm sẽ được điền tự động...")
                                news_pro_price = gr.Textbox(label="Giá (tùy chọn)", placeholder="VD: 15,000 KHR")
                                news_pro_benefits = gr.Textbox(label="Ưu điểm (cách nhau dấu phẩy)", lines=2, placeholder="Công dụng 1, công dụng 2...")
                                news_pro_pain_points = gr.Textbox(label="Vấn đề khách hàng (cách nhau dấu phẩy)", lines=2, placeholder="Vấn đề 1, vấn đề 2...")

                                gr.HTML('<div class="section-label" style="margin-top:1rem">3. System Prompt Mẫu (Tự động cập nhật)</div>')
                                news_pro_prompt_out = gr.Textbox(
                                    label="System Prompt Mẫu (Copy và dán cho Gemini/ChatGPT)",
                                    lines=8,
                                    interactive=False,
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">4. Đầu Vào Kịch Bản JSON</div>')
                                news_pro_json_input = gr.Textbox(
                                    label="Dán JSON kịch bản vào đây (sau khi lấy từ Gemini)",
                                    placeholder='{\n  "title": "Tin Tức Mới",\n  "script_segments": [...]\n}',
                                    lines=8,
                                )

                                gr.HTML('<div class="section-label" style="margin-top:1rem">5. Cài Đặt Chung & Xuất Video</div>')
                                with gr.Row():
                                    news_pro_channel = gr.Textbox(label="Tên Kênh (Watermark)", value="KHMER NEWS DAILY")
                                    news_pro_voice = gr.Radio(
                                        label="Giọng đọc",
                                        choices=[c[0] for c in VOICE_CHOICES],
                                        value=VOICE_CHOICES[0][0],
                                    )
                                    news_pro_rate = gr.Dropdown(
                                        label="Tốc độ đọc (Tua)",
                                        choices=["+0%", "+10%", "+25%", "+50%"],
                                        value="+0%",
                                    )
                        
                                with gr.Row():
                                    news_pro_transition_speed = gr.Dropdown(
                                        label="Tốc độ chuyển cảnh",
                                        choices=["Chậm (4.0s)", "Bình thường (3.0s)", "Nhanh (2.0s)", "Rất nhanh (1.5s)"],
                                        value="Bình thường (3.0s)",
                                    )
                                    news_pro_title_style = gr.Dropdown(
                                        label="Phong cách Tiêu đề (CapCut Style)",
                                        choices=["Khung Xanh (Mặc định)", "Khung Đỏ", "Khung Đen Chữ Vàng", "Chữ Xanh Viền Trắng", "Chữ Trắng Viền Đen"],
                                        value="Khung Xanh (Mặc định)"
                                    )
                                    news_pro_subtitles = gr.Checkbox(label="Tạo phụ đề trên video", value=False)
                                    news_pro_out_dir = gr.Textbox(label="Thư mục xuất", value="output")
                                run_news_pro = gr.Button("Tạo Video News Pro", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả</div>')
                                news_pro_out_video = gr.Video(label="Video Thành Phẩm")
                                news_pro_log = gr.Textbox(label="", lines=14, interactive=False,
                                                     placeholder="Log hiển thị ở đây...", elem_id="log-box")

                        def _analyze_image(imgs, hint_name):
                            images = _resolve_images(imgs)
                            vp = images[0] if images else None
                            if not vp:
                                yield "", "", "", "", "", "[LỖI] Chưa upload ảnh sản phẩm."
                                return
                    
                            from core.router import PipelineInputs, WorkflowMode, run_pipeline
                            from core.config import NewsProInputs
                            import tempfile
                            import json
                    
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tf:
                                out_json_path = tf.name

                            inputs = PipelineInputs(
                                mode=WorkflowMode.NEWS_PRO,
                                product_image=vp,
                                news_pro=NewsProInputs(
                                    step="analyze-image",
                                    product_images=images,
                                    product_name=hint_name,
                                    output_prompt=out_json_path
                                ),
                                output_dir="output",
                            )
                    
                            try:
                                run_pipeline(inputs)
                                if os.path.exists(out_json_path):
                                    with open(out_json_path, "r", encoding="utf-8") as f:
                                        res = json.load(f)
                                    os.remove(out_json_path)
                            
                                    p_name = res.get("product_name", "")
                                    price = res.get("price", "")
                                    ben = res.get("benefits_csv", "")
                                    pain = res.get("pain_points_csv", "")
                            
                                    from modes.news_pro.news_prompt_template_pro import build_prefilled_prompt
                                    prompt = build_prefilled_prompt(p_name, price, ben, pain, "khmer", 90, 3)
                            
                                    yield p_name, price, ben, pain, prompt, ""
                                else:
                                    yield "", "", "", "", "", "[LỖI] Không tạo được kết quả phân tích."
                            except Exception as e:
                                yield "", "", "", "", "", f"[LỖI] {e}"

                        btn_analyze_image.click(
                            fn=_analyze_image,
                            inputs=[news_pro_image, news_pro_product_name],
                            outputs=[news_pro_product_name, news_pro_price, news_pro_benefits, news_pro_pain_points, news_pro_prompt_out, news_pro_log],
                        )

                        def _live_bind_prompt(p_name, price, benefits, pain):
                            from modes.news_pro.news_prompt_template_pro import build_prefilled_prompt
                            return build_prefilled_prompt(p_name, price, benefits, pain, "khmer", 90, 3)

                        for _tb in [news_pro_product_name, news_pro_price, news_pro_benefits, news_pro_pain_points]:
                            _tb.change(
                                fn=_live_bind_prompt,
                                inputs=[news_pro_product_name, news_pro_price, news_pro_benefits, news_pro_pain_points],
                                outputs=[news_pro_prompt_out]
                            )

                        def _run_news_pro(imgs, json_str, channel, voice_lbl, rate_val, transition_speed, subs, t_style, out_dir):
                            images = _resolve_images(imgs)
                            if not (json_str or "").strip():
                                yield None, "[LỖI] Chưa dán JSON kịch bản."
                                return
                    
                            from core.router import PipelineInputs, WorkflowMode, run_pipeline
                            from core.config import NewsProInputs
                    
                            inputs = PipelineInputs(
                                mode=WorkflowMode.NEWS_PRO,
                                product_image=images[0] if images else "",
                                news_pro=NewsProInputs(
                                    step="render-from-script",
                                    product_images=images,
                                    script_json=json_str.strip(),
                                    channel_name=channel.strip(),
                                    tts_voice=_voice_val(voice_lbl),
                                    tts_rate=rate_val,
                                    transition_speed=transition_speed,
                                    enable_subtitles=bool(subs),
                                    title_style=t_style,
                                ),
                                output_dir=out_dir,
                            )
                            yield from _stream(run_pipeline, inputs)

                        run_news_pro.click(
                            fn=_run_news_pro,
                            inputs=[news_pro_image, news_pro_json_input, news_pro_channel, news_pro_voice, news_pro_rate, news_pro_transition_speed, news_pro_subtitles, news_pro_title_style, news_pro_out_dir],
                            outputs=[news_pro_out_video, news_pro_log],
                        )


                    # ── TAB 10: Polish — Đánh Bóng Video ────────────────────────────────
                    with gr.Tab("Polish — Đánh Bóng Video"):
                        gr.HTML('<div class="info-box">Thêm hiệu ứng, Watermark, Giá, Đánh giá, và các biến thể Hook vào video đã có.</div>')

                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.HTML('<div class="section-label">1. Video Đầu Vào</div>')
                                polish_video = gr.File(
                                    label="Upload Video đã hoàn thiện",
                                    file_types=[".mp4", ".mov"],
                                )
                        
                                gr.HTML('<div class="section-label" style="margin-top:1rem">2. Đóng Dấu & Khung Giá</div>')
                                polish_watermark = gr.Textbox(label="Watermark Text", placeholder="KHMER DAILY")
                                polish_add_price = gr.Checkbox(label="Thêm khung giá (Price Badge)", value=False)
                                polish_price = gr.Textbox(label="Giá sản phẩm", placeholder="15,000 KHR")
                        
                                gr.HTML('<div class="section-label" style="margin-top:1rem">3. Cài Đặt Social Proof & Hooks</div>')
                                polish_add_social = gr.Checkbox(label="Thêm Social Proof Overlay (Review, Đã bán)", value=False)
                                polish_hooks = gr.Slider(label="Số lượng Hook (Tạo N biến thể)", minimum=0, maximum=5, value=0, step=1)
                        
                                polish_out_dir = gr.Textbox(label="Thư mục xuất", value="output")
                                run_polish = gr.Button("Xử Lý Polish Video", variant="primary")

                            with gr.Column(scale=8):
                                gr.HTML('<div class="section-label">Kết quả</div>')
                                polish_out_video = gr.Video(label="Video Đã Đánh Bóng")
                                polish_log = gr.Textbox(label="", lines=14, interactive=False,
                                                     placeholder="Log hiển thị ở đây...", elem_id="log-box")

                        def _run_polish(video_file, watermark, add_price, price, add_social, hooks, out_dir):
                            vp = _resolve_file(video_file)
                            if not vp:
                                yield None, "[LỖI] Chưa upload video."
                                return

                            from core.router import PipelineInputs, WorkflowMode, run_pipeline
                            from core.config import PolishInputs
                    
                            inputs = PipelineInputs(
                                mode=WorkflowMode.POLISH,
                                product_image="",
                                polish=PolishInputs(
                                    source_video_path=vp,
                                    watermark_text=watermark.strip(),
                                    add_price_badge=bool(add_price),
                                    price=price.strip(),
                                    add_social_proof=bool(add_social),
                                    hook_variants=int(hooks)
                                ),
                                output_dir=out_dir,
                            )
                            yield from _stream(run_pipeline, inputs)

                        run_polish.click(
                            fn=_run_polish,
                            inputs=[polish_video, polish_watermark, polish_add_price, polish_price, polish_add_social, polish_hooks, polish_out_dir],
                            outputs=[polish_out_video, polish_log],
                        )


            with gr.Tab("📚 Hướng Dẫn"):
                with gr.Tabs():
                    # ── TAB 9: Huong dan ─────────────────────────────────
                    with gr.Tab("Huong dan"):
                        gr.Markdown("""
        ### Chay lan dau

        ```powershell
        cd d:\\ADS\\pipeline
        .venv\\Scripts\\Activate.ps1
        python app2.py
        # Mo trinh duyet: http://localhost:7861
        ```

        ### Lay API Keys (mien phi)

        | Key | Link | Dung cho |
        |-----|------|---------|
        | GEMINI_API_KEY | https://aistudio.google.com/app/apikey | Tab AI Tao Video |
        | PEXELS_API_KEY | https://www.pexels.com/api/ | Tab Remix |
        | REPLICATE_API_TOKEN | https://replicate.com | Tab AI (tuy chon) |

        Them vao file `.env`:
        ```
        GEMINI_API_KEY=AIzaSy...
        PEXELS_API_KEY=...
        REPLICATE_API_TOKEN=r8_...
        ```

        ### 3 che do hoat dong

        | Tab | Dau vao | Dau ra |
        |-----|--------|--------|
        | **Loc tieng** | Video goc + Script Khmer | Video + giong Khmer + phu de |
        | **Remix** | Anh SP + Gia + URL + Pexels key | Video 15-30s tu CC clips |
        | **AI Tao Video** | Anh SP + Gia + URL + Gemini key | Video 15-30s tu AI |
        | **Pro Editor** | Anh SP + Ten SP + Uu Diem + Van De | N ban video chuyen nghiep voi cac hook khac nhau |

        ### UGC Intensity

        | Muc | Grain | Shake | Ghi chu |
        |-----|-------|-------|---------|
        | subtle | 8 | 6px | Rat nhe, gan nhu khong biet |
        | medium | 14 | 10px | Cam giac dien thoai thuc (khuyen dung) |
        | strong | 20 | 16px | Manh, ro rang la quay tay |

        ### Mau nen gia

        | Mau | Phu hop |
        |-----|--------|
        | red | San pham nhanh, flash sale |
        | black | San pham cao cap |
        | orange | Khuyen mai, mua he |
        | white | San pham thien nhien, organic |
        """)

            # ── NEW TAB: Style Profile ─────────────────────────────────────
            with gr.Tab("🎨 Style Profile — Phong Cách Video"):
                gr.HTML("""
                <div id="hero" style="background: linear-gradient(135deg, #7c3aed 0%, #db2777 100%);">
                    <h1>🎨 Phân Tích Phong Cách Video</h1>
                    <p>Upload 1–5 video mẫu của bạn → AI phân tích phong cách → Lưu thành Style Profile → Áp dụng cho mọi chế độ tạo video</p>
                    <div>
                        <span class="badge">Gemini Vision</span>
                        <span class="badge">Lưu cục bộ (JSON)</span>
                        <span class="badge">Dùng cho mọi Mode</span>
                    </div>
                </div>
                """)

                with gr.Row():
                    # ── Left: Upload & Create ──────────────────────────────
                    with gr.Column(scale=5):
                        gr.HTML('<div class="section-label">📤 1. Tạo Profile Mới</div>')
                        gr.HTML('<div class="info-box">Upload 1–5 video mẫu thể hiện phong cách làm video của bạn. AI sẽ phân tích nhịp cắt, hook style, cảm xúc, màu sắc, v.v.</div>')

                        sp_videos = gr.File(
                            label="Upload video mẫu (tối đa 5 video, MP4/MOV)",
                            file_types=[".mp4", ".mov", ".avi", ".mkv"],
                            file_count="multiple",
                        )
                        sp_name = gr.Textbox(
                            label="Tên phong cách",
                            placeholder="VD: Phong Cách TikTok Nhanh / Style Zalo Nhẹ Nhàng",
                        )
                        sp_gemini_key = gr.Textbox(
                            label="Gemini API Key (hoặc để trống nếu đã có trong .env)",
                            type="password",
                            value=_ENV_GEMINI,
                            placeholder="AIzaSy...",
                        )
                        btn_analyze = gr.Button("🔍 PHÂN TÍCH PHONG CÁCH", variant="primary", size="lg")

                        gr.HTML('<div class="section-label" style="margin-top:1.5rem">🗂 2. Quản Lý Profile Đã Lưu</div>')
                        btn_refresh = gr.Button("🔄 Làm mới danh sách", variant="secondary")
                        sp_profiles_html = gr.HTML(value="<p style='color:#888'>Nhấn '🔄 Làm mới' để xem các profile đã lưu...</p>")

                        sp_delete_id = gr.Textbox(
                            label="ID profile muốn xoá (copy từ danh sách bên trên)",
                            placeholder="VD: style_20260813_120000",
                        )
                        btn_delete = gr.Button("🗑 Xoá Profile", variant="stop")

                    # ── Right: Results ─────────────────────────────────────
                    with gr.Column(scale=7):
                        gr.HTML('<div class="section-label">📊 Kết Quả Phân Tích</div>')
                        sp_log = gr.Textbox(
                            label="Tiến trình AI",
                            lines=5, interactive=False,
                            placeholder="Log sẽ hiện ở đây...",
                        )
                        sp_result_html = gr.HTML(value="<p style='color:#888'>Kết quả Style DNA sẽ hiển thị ở đây sau khi phân tích...</p>")

                        gr.HTML('<div class="section-label" style="margin-top:1rem">📝 Ghi Chú Phong Cách (dùng để inject vào Gemini)</div>')
                        sp_notes_box = gr.Textbox(
                            label="Style Notes (tự động tạo — có thể chỉnh sửa)",
                            lines=5, interactive=True,
                            placeholder="AI sẽ điền vào đây sau khi phân tích...",
                        )
                        sp_current_profile_id = gr.Textbox(visible=False)

                # ── Bottom: Generate Video with Style ──────────────────────
                gr.HTML('<hr style="margin:2rem 0; border-color:#e0e7ff"/>')
                gr.HTML('<div class="section-label" style="font-size:1.1rem; color:#db2777">🎬 3. Tạo Video Với Phong Cách Này</div>')
                gr.HTML('<div class="info-box" style="border-left-color:#db2777; color:#9d174d; background:#fce7f3">Sau khi phân tích xong (hoặc tự nhập Ghi Chú Phong Cách ở trên), bạn có thể tải ảnh sản phẩm lên để AI tự động viết kịch bản và tạo video quảng cáo bám sát phong cách này!</div>')
                
                with gr.Row():
                    with gr.Column(scale=4):
                        sp_gen_mode = gr.Radio(
                            choices=[
                                "1. Tạo video mới từ Ảnh (Sử dụng phong cách đã phân tích)", 
                                "2. Đạo nhái video mẫu (Giữ video gốc, lồng tiếng lại & chèn thêm phân cảnh mới)"
                            ],
                            value="2. Đạo nhái video mẫu (Giữ video gốc, lồng tiếng lại & chèn thêm phân cảnh mới)",
                            label="Chế độ tạo video"
                        )
                        sp_gen_image = gr.File(label="Upload ảnh sản phẩm chính (Dùng cho Chế độ A)", file_types=[".jpg", ".png", ".jpeg", ".webp"])
                        sp_gen_audience = gr.Textbox(label="Đối tượng khách hàng (Dùng cho Chế độ A)", value="Khách hàng Việt Nam")
                        sp_gen_tone = gr.Textbox(label="Giọng điệu thương hiệu (Dùng cho Chế độ A)", value="Thuyết phục, chuyên nghiệp")
                        with gr.Row():
                            sp_gen_lang = gr.Dropdown(
                                choices=["Tiếng Việt", "Tiếng Khmer", "Tiếng Anh", "Tiếng Thái", "Tiếng Indo"],
                                value="Tiếng Việt",
                                label="Ngôn ngữ"
                            )
                            sp_gen_duration = gr.Dropdown(
                                choices=["Ngắn (~15s) - Nhanh", "Vừa (~30s) - Bình thường"],
                                value="Vừa (~30s) - Bình thường",
                                label="Độ dài"
                            )
                        sp_gen_scrape_kw = gr.Textbox(
                            label="Từ khoá cào B-roll từ mạng (Tuỳ chọn - cho Chế độ B)", 
                            placeholder="VD: shampoo review, mỹ phẩm..."
                        )
                        btn_sp_generate = gr.Button("🚀 TẠO VIDEO BẰNG PHONG CÁCH NÀY", variant="primary", size="lg")
                    
                    with gr.Column(scale=8):
                        sp_gen_log = gr.Textbox(label="Tiến trình làm việc", lines=6, interactive=False)
                        sp_gen_video = gr.Video(label="Video Thành Phẩm (Style Profile)")

                # ── Handlers ──────────────────────────────────────────────
                def _analyze_style(video_files, profile_name, api_key):
                    api_key = (api_key or "").strip() or _ENV_GEMINI
                    if not api_key:
                        yield "❌ Cần Gemini API Key!", "<p style='color:red'>❌ Vui lòng nhập Gemini API Key.</p>", "", ""
                        return

                    vpaths = []
                    if video_files:
                        for vf in (video_files if isinstance(video_files, list) else [video_files]):
                            p = _resolve_file(vf)
                            if p: vpaths.append(p)

                    if not vpaths:
                        yield "❌ Chưa upload video mẫu nào!", "<p style='color:red'>❌ Vui lòng upload ít nhất 1 video mẫu.</p>", "", ""
                        return

                    yield f"⏳ Đang phân tích {len(vpaths)} video...", "<p>⏳ AI đang xem video của bạn...</p>", "", ""

                    try:
                        from core.style_profile import analyze_style_from_videos
                        import traceback

                        profile = analyze_style_from_videos(
                            video_paths=vpaths,
                            api_key=api_key,
                            profile_name=profile_name.strip() or "My Style",
                        )

                        dna = profile.get("style_dna", {})
                        notes = profile.get("gemini_style_notes", "")

                        dna_rows = "".join(
                            f"<tr><td style='padding:6px 12px;font-weight:600;color:#4f46e5'>{k}</td>"
                            f"<td style='padding:6px 12px'>{v}</td></tr>"
                            for k, v in dna.items()
                        )
                        result_html = f"""
                        <div style='background:#f0f4ff;border-radius:12px;padding:16px;'>
                            <h3 style='color:#3730a3;margin-top:0'>✅ Profile ID: <code>{profile['profile_id']}</code></h3>
                            <p style='color:#6366f1'><b>📝 Tóm tắt:</b> {dna.get('style_summary', '')}</p>
                            <table style='width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden'>
                                <thead><tr style='background:#e0e7ff'>
                                    <th style='padding:8px 12px;text-align:left'>Chỉ số</th>
                                    <th style='padding:8px 12px;text-align:left'>Giá trị</th>
                                </tr></thead>
                                <tbody>{dna_rows}</tbody>
                            </table>
                        </div>
                        """
                        yield (
                            f"✅ Phân tích xong! Profile '{profile['profile_id']}' đã lưu.",
                            result_html,
                            notes,
                            profile['profile_id'],
                        )

                    except Exception as exc:
                        yield f"❌ Lỗi: {exc}", f"<p style='color:red'>❌ {exc}</p>", "", ""

                def _refresh_profiles():
                    from core.style_profile import list_style_profiles
                    profiles = list_style_profiles()
                    if not profiles:
                        return "<p style='color:#888;padding:12px'>Chưa có profile nào được lưu. Hãy tạo profile đầu tiên của bạn!</p>"
                    rows = ""
                    for p in profiles:
                        rows += f"""
                        <tr style='border-bottom:1px solid #e0e7ff'>
                            <td style='padding:8px 12px'><code style='background:#e0e7ff;padding:2px 6px;border-radius:4px'>{p['profile_id']}</code></td>
                            <td style='padding:8px 12px;font-weight:600'>{p['profile_name']}</td>
                            <td style='padding:8px 12px;color:#6b7280;font-size:0.85rem'>{p.get('created_at', '')[:16]}</td>
                            <td style='padding:8px 12px;color:#374151;font-size:0.85rem'>{p.get('style_summary', '')[:80]}...</td>
                        </tr>
                        """
                    return f"""
                    <table style='width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1)'>
                        <thead><tr style='background:#e0e7ff'>
                            <th style='padding:10px 12px;text-align:left'>ID</th>
                            <th style='padding:10px 12px;text-align:left'>Tên</th>
                            <th style='padding:10px 12px;text-align:left'>Ngày tạo</th>
                            <th style='padding:10px 12px;text-align:left'>Tóm tắt</th>
                        </tr></thead>
                        <tbody>{rows}</tbody>
                    </table>
                    """

                def _delete_profile(profile_id):
                    if not (profile_id or "").strip():
                        return "❌ Chưa nhập ID profile", ""
                    from core.style_profile import delete_style_profile
                    deleted = delete_style_profile(profile_id.strip())
                    if deleted:
                        return f"✅ Đã xoá profile '{profile_id}'", ""
                    else:
                        return f"❌ Không tìm thấy profile '{profile_id}'", ""

                btn_analyze.click(
                    fn=_analyze_style,
                    inputs=[sp_videos, sp_name, sp_gemini_key],
                    outputs=[sp_log, sp_result_html, sp_notes_box, sp_current_profile_id],
                )
                btn_refresh.click(
                    fn=_refresh_profiles,
                    inputs=[],
                    outputs=[sp_profiles_html],
                )
                btn_delete.click(
                    fn=_delete_profile,
                    inputs=[sp_delete_id],
                    outputs=[sp_log, sp_delete_id],
                )

                def _generate_video_with_style(gen_mode, video_files, profile_id, image_file, audience, tone, lang, duration, scrape_kw, notes_text):
                    if "Đạo nhái" in gen_mode or "Clone" in gen_mode:
                        vpaths = []
                        if video_files:
                            for vf in (video_files if isinstance(video_files, list) else [video_files]):
                                p = _resolve_file(vf)
                                if p: vpaths.append(p)
                        if not vpaths:
                            yield "❌ Lỗi: Chưa có video mẫu nào được tải lên ở phần 1!", None
                            return
                        
                        source_video = vpaths[0]
                        from core.language_resolver import display_name_to_key
                        lang_key = display_name_to_key(lang)
                        
                        from core.router import PipelineInputs, WorkflowMode, FullRemixInputs, run_pipeline
                        inputs = PipelineInputs(
                            mode=WorkflowMode.FULL_REMIX,
                            product_image="",
                            full_remix=FullRemixInputs(
                                source_video=source_video,
                                audio_mode="translate",
                                target_language=lang_key,
                                tts_voice="",          # auto-resolved
                                script="",             # will be auto-translated
                                on_screen_text="",
                                mask_style="none",     # No mask by default for simple clone
                                mask_color="black",
                                create_remix=True,
                                num_remixes=2,
                                broll_query="",
                                scrape_broll_keyword=scrape_kw.strip() if scrape_kw else "",
                                music_energy="upbeat",
                                ugc_intensity="medium",
                                tts_rate="+0%",
                                style_profile_id=(profile_id or "").strip(),
                            ),
                            output_dir="output",
                        )
                        for vid_out, log_out in _stream(run_pipeline, inputs):
                            yield log_out, vid_out
                        return

                    # Chế độ A: Magic Mode
                    img_path = _resolve_file(image_file)
                    if not img_path:
                        yield "❌ Lỗi: Vui lòng upload ảnh sản phẩm (Chế độ A)!", None
                        return
                    
                    # Construct a dummy style_profile dict using just the notes text
                    style_profile_obj = None
                    if (notes_text or "").strip():
                        style_profile_obj = {
                            "profile_name": "Custom UI Style",
                            "gemini_style_notes": notes_text.strip()
                        }
                    else:
                        yield "⚠️ Cảnh báo: Ghi Chú Phong Cách trống, video sẽ được tạo với phong cách mặc định.", None
                    
                    try:
                        from core.magic_pipeline_engine import run_magic_pipeline
                        for log_msg, vid_path in run_magic_pipeline(
                            image_path=img_path, 
                            target_audience=audience, 
                            brand_tone=tone, 
                            language=lang,
                            voice_name="Auto",
                            tts_rate="+0%",
                            duration_mode=duration,
                            style_profile=style_profile_obj
                        ):
                            yield log_msg, vid_path
                    except Exception as exc:
                        import traceback
                        yield f"❌ Lỗi:\n{traceback.format_exc()}", None

                btn_sp_generate.click(
                    fn=_generate_video_with_style,
                    inputs=[sp_gen_mode, sp_videos, sp_current_profile_id, sp_gen_image, sp_gen_audience, sp_gen_tone, sp_gen_lang, sp_gen_duration, sp_gen_scrape_kw, sp_notes_box],
                    outputs=[sp_gen_log, sp_gen_video],
                )

        return demo


# ──────────────────────────────────────────────────────────────────
# Launch
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Cổng mặc định 7860 — khớp với Dockerfile (EXPOSE 7860) và app_port của
    # Hugging Face Spaces. Đổi cổng khi chạy local: PORT=7871 python app2.py
    SERVER_PORT = int(os.getenv("PORT") or os.getenv("GRADIO_SERVER_PORT") or 7860)
    # Tắt link chia sẻ công khai / tự mở trình duyệt khi chạy trong container:
    #   GRADIO_SHARE=0 GRADIO_INBROWSER=0
    _off = ("0", "false", "no")
    # Mặc định TẮT: share=True tạo public URL cho bất kỳ ai có link, chạy bằng
    # API key trong .env của bạn. Bật lại khi cần: GRADIO_SHARE=1 python app2.py
    SHARE     = os.getenv("GRADIO_SHARE", "0").strip().lower() not in _off
    INBROWSER = os.getenv("GRADIO_INBROWSER", "1").strip().lower() not in _off

    print("\n" + "=" * 60)
    print("  FB Shorts Ads Generator v3.5")
    print(f"  URL: http://localhost:{SERVER_PORT}")
    print("=" * 60 + "\n")

    from core.subtitle_gen import ensure_caption_style_previews
    try:
        print("[System] Generating caption style previews...")
        ensure_caption_style_previews()
    except Exception as exc:
        print(f"[System] Warning: Failed to generate caption previews - {exc}")

    ui = build_ui()
    ui.launch(
        server_name="0.0.0.0",
        server_port=SERVER_PORT,
        share=SHARE,
        inbrowser=INBROWSER,
        css=CSS,
        theme=gr.themes.Soft(primary_hue="indigo"),
    )
