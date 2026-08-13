"""
====================================================================
  Khmer FB Shorts Ads Generator
  File: app.py — Gradio Web UI (v3.0 — Premium Dark Theme)
  Run: python app.py   ->   http://localhost:7860
====================================================================
"""

import logging
import os
import queue
import sys
import threading
from pathlib import Path

import gradio as gr

# ── Pipeline imports ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from core.config import WorkflowMode, load_config
from core.router import PipelineInputs, AutoInputs, ManualInputs, run_pipeline

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Live log capture handler
# ──────────────────────────────────────────────────────────────────

class QueueHandler(logging.Handler):
    """Push log records into a thread-safe queue for streaming to UI."""
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self._q = log_queue

    def emit(self, record):
        self._q.put(self.format(record))


# ──────────────────────────────────────────────────────────────────
# Pipeline runner (streaming generator for Gradio)
# ──────────────────────────────────────────────────────────────────

def run_pipeline_streaming(
    workflow_mode:    str,
    product_image:    str | None,
    category_keyword: str,
    manual_ref_video: str | None,
    manual_script:    str,
    manual_prompt:    str,
    tts_voice:        str,
    output_dir:       str,
):
    """
    Generator that yields (video_path_or_None, log_text) tuples
    so Gradio can stream live log lines while the pipeline runs.
    """
    log_q: queue.Queue = queue.Queue()
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S")
    handler = QueueHandler(log_q)
    handler.setFormatter(fmt)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    result_container: dict = {}
    log_buffer: list[str] = []

    def _run():
        try:
            cfg = load_config()
            cfg.constraints.tts_voice = tts_voice
            cfg.output_dir = output_dir.strip() or "output"

            if not product_image:
                result_container["error"] = "[ERR]  กรุณาอัปโหลดภาพสินค้า / Please upload a product image."
                return

            category_keyword_str = (category_keyword or "").strip()
            manual_script_str = (manual_script or "").strip()
            manual_prompt_str = (manual_prompt or "").strip()

            mode = (
                WorkflowMode.AUTO_AUTONOMOUS
                if "Auto" in workflow_mode
                else WorkflowMode.MANUAL_OVERRIDE
            )

            if mode == WorkflowMode.AUTO_AUTONOMOUS:
                if not category_keyword_str:
                    result_container["error"] = "[ERR]  Category Keyword is required for Auto mode."
                    return
                inputs = PipelineInputs(
                    mode=mode,
                    product_image=product_image,
                    auto=AutoInputs(category_keyword=category_keyword_str),
                    output_dir=cfg.output_dir,
                )
            else:
                missing = []
                if not manual_ref_video: missing.append("Reference Audio/Video")
                if not manual_script_str: missing.append("Khmer Script")
                if not manual_prompt_str: missing.append("Motion Style Prompt")
                if missing:
                    result_container["error"] = f"[ERR]  Manual mode còn thiếu: {', '.join(missing)}"
                    return

                inputs = PipelineInputs(
                    mode=mode,
                    product_image=product_image,
                    manual=ManualInputs(
                        ref_video_path=manual_ref_video,
                        script=manual_script.strip(),
                        prompt=manual_prompt.strip(),
                    ),
                    output_dir=cfg.output_dir,
                )

            output_path = run_pipeline(inputs, cfg)
            result_container["output"] = output_path

        except Exception as exc:
            logger.error(f"Pipeline failed: {exc}", exc_info=True)
            result_container["error"] = f"[ERR]  {exc}"
        finally:
            result_container["done"] = True

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # Stream log lines while pipeline runs
    while thread.is_alive() or not log_q.empty():
        try:
            line = log_q.get(timeout=0.15)
            log_buffer.append(line)
            yield None, "\n".join(log_buffer)
        except queue.Empty:
            yield None, "\n".join(log_buffer)

    root_logger.removeHandler(handler)

    if "error" in result_container:
        log_buffer.append("\n" + result_container["error"])
        yield None, "\n".join(log_buffer)
    elif "output" in result_container:
        log_buffer.append(f"\n[OK]  DONE -> {result_container['output']}")
        yield result_container["output"], "\n".join(log_buffer)
    else:
        log_buffer.append("\n[WARN]  Pipeline ended with no output.")
        yield None, "\n".join(log_buffer)


# ──────────────────────────────────────────────────────────────────
# CSS — Premium Dark Theme
# ──────────────────────────────────────────────────────────────────

CSS = """
/* ── Google Fonts ─────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Root palette ─────────────────────────────────────────────── */
:root {
    --bg:        #0d0d14;
    --surface:   #13131f;
    --card:      #1a1a2e;
    --border:    #2a2a45;
    --primary:   #7c3aed;
    --primary-g: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%);
    --accent:    #a78bfa;
    --green:     #34d399;
    --red:       #f87171;
    --amber:     #fbbf24;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --radius:    12px;
}

/* ── Global reset ─────────────────────────────────────────────── */
* { font-family: 'Inter', sans-serif !important; box-sizing: border-box; }
body, .gradio-container { background: var(--bg) !important; color: var(--text) !important; }
.gradio-container { max-width: 1200px !important; margin: 0 auto !important; padding: 0 1rem !important; }
footer { display: none !important; }

/* ── Banner / hero ────────────────────────────────────────────── */
#hero {
    background: linear-gradient(135deg, #0d0d1a 0%, #1a0a2e 50%, #0d0d1a 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
#hero::before {
    content: '';
    position: absolute; top: -60px; right: -60px;
    width: 220px; height: 220px;
    background: radial-gradient(circle, rgba(124,58,237,0.25) 0%, transparent 70%);
    border-radius: 50%;
}
#hero::after {
    content: '';
    position: absolute; bottom: -40px; left: 40px;
    width: 140px; height: 140px;
    background: radial-gradient(circle, rgba(79,70,229,0.2) 0%, transparent 70%);
    border-radius: 50%;
}
#hero h1 {
    font-size: 1.9rem !important; font-weight: 700 !important;
    background: linear-gradient(135deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin: 0 0 0.4rem !important;
}
#hero p { color: var(--muted) !important; font-size: 0.875rem !important; margin: 0 !important; }
.badge {
    display: inline-block; padding: 2px 10px;
    background: rgba(124,58,237,0.2); border: 1px solid rgba(124,58,237,0.4);
    border-radius: 999px; font-size: 0.72rem; color: var(--accent);
    margin-right: 6px; margin-top: 0.75rem;
}

/* ── Cards ────────────────────────────────────────────────────── */
.card {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.25rem !important;
}
.section-label {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--muted);
    margin-bottom: 0.75rem; padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
}

/* ── Inputs ───────────────────────────────────────────────────── */
label > span, .label-wrap span {
    font-size: 0.8rem !important; font-weight: 500 !important;
    color: var(--accent) !important;
}
input[type=text], textarea, select, .gr-input, .gr-textbox textarea {
    background: #0f0f1c !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text) !important;
    font-size: 0.875rem !important;
}
input[type=text]:focus, textarea:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.2) !important;
    outline: none !important;
}

/* ── Dropdown ─────────────────────────────────────────────────── */
.gr-dropdown, .wrap .secondary-wrap {
    background: #0f0f1c !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* ── File/Image upload ────────────────────────────────────────── */
.upload-container, .gr-file, .gr-image {
    background: #0f0f1c !important;
    border: 2px dashed var(--border) !important;
    border-radius: 10px !important;
    transition: border-color 0.2s;
}
.upload-container:hover { border-color: var(--primary) !important; }

/* ── Tabs ─────────────────────────────────────────────────────── */
.tab-nav { border-bottom: 1px solid var(--border) !important; background: transparent !important; }
.tab-nav button {
    color: var(--muted) !important; font-weight: 500 !important;
    font-size: 0.875rem !important; padding: 0.6rem 1.2rem !important;
    border-radius: 8px 8px 0 0 !important; transition: all 0.2s;
}
.tab-nav button.selected {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--primary) !important;
    background: rgba(124,58,237,0.08) !important;
}

/* ── Run button ───────────────────────────────────────────────── */
#run-btn {
    background: var(--primary-g) !important;
    border: none !important; border-radius: 10px !important;
    font-size: 1rem !important; font-weight: 600 !important;
    padding: 0.85rem 2.5rem !important;
    letter-spacing: 0.02em !important;
    box-shadow: 0 4px 20px rgba(124,58,237,0.4) !important;
    transition: all 0.25s ease !important;
    color: #fff !important;
}
#run-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(124,58,237,0.55) !important;
}
#run-btn:active { transform: translateY(0) !important; }

/* ── Log box ──────────────────────────────────────────────────── */
#log-box textarea {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
    background: #080810 !important;
    color: #94a3b8 !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    line-height: 1.6 !important;
}

/* ── Output video ─────────────────────────────────────────────── */
#output-video { border-radius: 10px !important; overflow: hidden !important; }

/* ── Radio buttons ────────────────────────────────────────────── */
.gr-radio label { color: var(--text) !important; font-size: 0.875rem !important; }
.gr-radio input[type=radio]:checked + span { color: var(--accent) !important; }

/* ── Accordion ────────────────────────────────────────────────── */
.gr-accordion {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}
.gr-accordion .label-wrap { color: var(--accent) !important; font-size: 0.875rem !important; }

/* ── Status chips ─────────────────────────────────────────────── */
.status-ok  { color: var(--green)  !important; }
.status-err { color: var(--red)    !important; }
.status-wrn { color: var(--amber)  !important; }

/* ── Markdown ─────────────────────────────────────────────────── */
.md-content p, .prose p { color: var(--text) !important; font-size: 0.875rem !important; }
.md-content h3, .prose h3 { color: var(--accent) !important; font-size: 1rem !important; font-weight: 600 !important; }
.md-content table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.md-content th { background: rgba(124,58,237,0.15); color: var(--accent); padding: 6px 10px; }
.md-content td { padding: 5px 10px; border-bottom: 1px solid var(--border); color: var(--text); }
.md-content code {
    background: rgba(124,58,237,0.15); color: var(--accent);
    padding: 1px 6px; border-radius: 4px; font-family: 'JetBrains Mono', monospace;
    font-size: 0.82em;
}

/* ── Scrollbars ───────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--primary); }
"""


# ──────────────────────────────────────────────────────────────────
# UI Builder
# ──────────────────────────────────────────────────────────────────

VOICE_CHOICES = [
    ("🎙️ Sreymom — Nữ (Female)", "km-KH-SreymomNeural"),
    ("🎙️ Piseth — Nam (Male)",   "km-KH-PisethNeural"),
]

MODE_CHOICES = [
    "✨ Mode 1: Auto-Autonomous  (cần GEMINI_API_KEY)",
    "🖊️ Mode 2: Manual Override  (không cần API key)",
]

PROMPT_HINT = (
    "**Zoom speed:** `slow` · `fast` · `dramatic` · `gentle`  \n"
    "**Pan:** `left` · `right` · `up` · `down` · `center` · `zoom in`  \n"
    "**Color:** `warm` · `golden` · `cinematic` · `cool` · `vibrant` · `punchy` · `soft` · `dark` · `moody` · `neutral`"
)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="[VIDEO] Khmer Ads Generator") as demo:

        # ── Hero banner ──────────────────────────────────────────
        gr.HTML("""
        <div id="hero">
            <h1>[VIDEO] Khmer FB Shorts Ads Generator</h1>
            <p>Tạo video quảng cáo 9:16 (1080x1920) · Tiếng Khmer · MP4 · 30–90 giây</p>
            <div style="margin-top:0.75rem">
                <span class="badge">edge-tts Free</span>
                <span class="badge">FFmpeg Ken Burns</span>
                <span class="badge">Khmer Hardsub</span>
                <span class="badge">Zero Cost</span>
                <span class="badge">No GPU needed</span>
            </div>
        </div>
        """)

        # ── Main two-column layout ───────────────────────────────
        with gr.Row(equal_height=False):

            # ── LEFT COLUMN: Inputs ──────────────────────────────
            with gr.Column(scale=5, min_width=340):

                # ── Global inputs card ───────────────────────────
                gr.HTML('<div class="section-label">⚙️ Cấu hình chung (Global)</div>')

                workflow_mode = gr.Dropdown(
                    label="Workflow Mode",
                    choices=MODE_CHOICES,
                    value=MODE_CHOICES[1],
                    elem_id="workflow_mode",
                )

                product_image = gr.Image(
                    label="📷  Ảnh sản phẩm (JPG / PNG · tối đa 5 ảnh)",
                    type="filepath",
                    elem_id="product_image",
                    height=200,
                )

                with gr.Row():
                    tts_voice = gr.Radio(
                        label="[TTS] Giọng đọc Khmer",
                        choices=[c[0] for c in VOICE_CHOICES],
                        value=VOICE_CHOICES[0][0],
                    )

                output_dir = gr.Textbox(
                    label="📁 Thư mục xuất video",
                    value="output",
                    placeholder="output",
                    info="Thư mục sẽ được tạo tự động nếu chưa có",
                )

                gr.HTML('<div class="section-label" style="margin-top:1.25rem">🎛️ Tham số theo Mode</div>')

                # ── Mode tabs ────────────────────────────────────
                with gr.Tabs():

                    # Mode 2 — Manual (default)
                    with gr.Tab("🖊️ Mode 2: Manual Override"):
                        gr.Markdown(
                            "**Không cần API key.** Cung cấp kịch bản Khmer và file tham chiếu nhịp cắt.",
                            elem_classes=["md-content"],
                        )

                        manual_ref_video = gr.File(
                            label="[VIDEO] File tham chiếu nhịp cắt (MP4 / MP3 / WAV)",
                            file_types=[".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".m4a"],
                            elem_id="manual_ref_video",
                        )

                        manual_script = gr.Textbox(
                            label="[SUB] Kịch bản tiếng Khmer",
                            placeholder="ហ្សែលក្ដៅ! ធ្វើឱ្យសក់របស់អ្នករឹងប៉ូវ និងស្អាត។ ទទួលដឹកជញ្ជូនឥតគិតថ្លៃ!",
                            lines=5,
                            max_lines=10,
                            elem_id="manual_script",
                        )

                        manual_prompt = gr.Textbox(
                            label="✨ Motion Style Prompt",
                            placeholder="warm cinematic slow zoom",
                            info="Kết hợp màu sắc + tốc độ + hướng (xem bảng tham chiếu bên phải)",
                            elem_id="manual_prompt",
                        )

                        gr.Markdown(PROMPT_HINT, elem_classes=["md-content"])

                    # Mode 1 — Auto
                    with gr.Tab("[AI] Mode 1: Auto-Autonomous"):
                        gr.Markdown(
                            "[WARN] **Yêu cầu** `GEMINI_API_KEY` trong file `.env`.  \n"
                            "Pipeline sẽ tự tìm video Creative Commons và viết kịch bản Khmer.",
                            elem_classes=["md-content"],
                        )

                        category_keyword = gr.Textbox(
                            label="🔑 Category Keyword",
                            placeholder="e.g., hair gel cambodia",
                            elem_id="category_keyword",
                            info="Từ khóa tìm kiếm video tham chiếu",
                        )

                # ── Run button ───────────────────────────────────
                run_btn = gr.Button(
                    "🚀  Tạo Video Quảng Cáo",
                    variant="primary",
                    elem_id="run-btn",
                )

            # ── RIGHT COLUMN: Outputs ────────────────────────────
            with gr.Column(scale=7, min_width=400):

                gr.HTML('<div class="section-label">[VIDEO] Kết quả xuất ra</div>')

                output_video = gr.Video(
                    label="Video đầu ra (9:16 · MP4)",
                    elem_id="output-video",
                    height=480,
                )

                gr.HTML('<div class="section-label" style="margin-top:1.25rem">📋 Pipeline Log (Live)</div>')

                log_box = gr.Textbox(
                    label="",
                    lines=18,
                    max_lines=30,
                    interactive=False,
                    placeholder="Log sẽ hiển thị ở đây theo thời gian thực khi nhấn Tạo Video...",
                    elem_id="log-box",
                )

        # ── Reference guide accordion ────────────────────────────
        with gr.Accordion("📖  Hướng dẫn nhanh & Bảng tham chiếu Prompt", open=False):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("""
### 🖊️ Mode 2: Manual Override — Các bước

1. **Workflow Mode** -> chọn `Mode 2: Manual Override`
2. **Ảnh sản phẩm** -> upload ảnh JPG/PNG
3. **File tham chiếu** -> upload MP4 (video) hoặc MP3 (nhạc)  
   *(dùng để phân tích nhịp cắt cảnh — pipeline đã xử lý được cả audio-only)*
4. **Kịch bản Khmer** -> dán text tiếng Khmer vào
5. **Motion Style** -> ví dụ: `warm cinematic slow zoom`
6. Nhấn **Tạo Video** -> chờ khoảng 1–3 phút

---

### [AI] Mode 1: Auto-Autonomous — Các bước

1. Thêm `GEMINI_API_KEY=...` vào file `.env`
2. Chọn **Mode 1** 
3. Upload ảnh sản phẩm
4. Nhập keyword (ví dụ: `hair gel cambodia`)
5. Nhấn **Tạo Video**
""", elem_classes=["md-content"])

                with gr.Column():
                    gr.Markdown("""
### ✨ Bảng tham chiếu Motion Style Prompt

| Nhóm | Từ khóa | Hiệu ứng |
|------|---------|---------|
| **Tốc độ zoom** | `slow` · `gentle` | Nhẹ nhàng (zoom_end 1.04) |
| | `fast` · `quick` | Nhanh (zoom_end 1.15) |
| | `dramatic` | Rất mạnh (zoom_end 1.20) |
| **Hướng pan** | `left` `right` `up` `down` | Di chuyển theo hướng |
| | `center` · `zoom in` | Giữ giữa / zoom vào |
| **Màu sắc** | `warm` · `golden` | Ấm, hoàng hôn |
| | `cinematic` · `cool` | Điện ảnh, xanh nhẹ |
| | `vibrant` · `punchy` | Sắc nét, bão hòa cao |
| | `soft` · `pastel` | Mềm mại |
| | `dark` · `moody` | Tối, kịch tính |
| | `neutral` · `clean` | Không lọc màu |

**Ví dụ kết hợp:**  
`warm cinematic slow zoom` · `vibrant fast right` · `golden dramatic center`
""", elem_classes=["md-content"])

        # ── Wiring ───────────────────────────────────────────────
        def _resolve_voice(label: str) -> str:
            for lbl, val in VOICE_CHOICES:
                if lbl == label:
                    return val
            return "km-KH-SreymomNeural"

        def _resolve_ref(file_obj):
            """Gradio File component returns a file object or None."""
            if file_obj is None:
                return None
            if isinstance(file_obj, str):
                return file_obj
            # Gradio returns a dict with 'name' key for temp path
            if isinstance(file_obj, dict):
                return file_obj.get("name") or file_obj.get("path")
            # Newer Gradio returns object with .name
            return getattr(file_obj, "name", str(file_obj))

        def pipeline_wrapper(
            workflow_mode, product_image, category_keyword,
            manual_ref_video, manual_script, manual_prompt,
            tts_voice_label, output_dir,
        ):
            voice = _resolve_voice(tts_voice_label)
            ref   = _resolve_ref(manual_ref_video)
            yield from run_pipeline_streaming(
                workflow_mode, product_image, category_keyword,
                ref, manual_script, manual_prompt,
                voice, output_dir,
            )

        run_btn.click(
            fn=pipeline_wrapper,
            inputs=[
                workflow_mode, product_image, category_keyword,
                manual_ref_video, manual_script, manual_prompt,
                tts_voice, output_dir,
            ],
            outputs=[output_video, log_box],
            show_progress="minimal",
        )

    return demo


# ──────────────────────────────────────────────────────────────────
# Launch
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  [VIDEO]  Khmer Ads Generator — Web UI")
    print("  URL: http://localhost:7860")
    print("═" * 60 + "\n")

    ui = build_ui()
    ui.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=True,
        css=CSS,
        theme=gr.themes.Base(),
    )
