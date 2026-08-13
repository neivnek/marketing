# 📐 COMPREHENSIVE SYSTEM ARCHITECTURE & SPECIFICATION
## Hybrid Zero-Cost Khmer Video Pipeline v3.0

This document contains the complete, authoritative specification of the entire **Hybrid Zero-Cost Video Pipeline v3.0** codebase. Any AI coding assistant reading this document will have 100% full context of the architecture, workflow modes, core modules, data schemas, CLI commands, and design rules.

---

## 🎯 1. EXECUTIVE SUMMARY & ZERO-COST POLICY

- **Purpose**: Fully automated 9:16 portrait (1080x1920, 30fps) short-form video generation system designed for Cambodian (Khmer language) Facebook Shorts, Reels, and TikTok e-commerce & news advertising.
- **Strict Zero-Cost Policy (0 VNĐ / 0 USD)**:
  - **AI Text & Vision**: Google Gemini Flash Free Tier via `google-genai` SDK (`gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-flash-latest`, `gemini-2.0-flash`).
  - **Text-To-Speech (TTS)**: Microsoft Edge TTS (`edge-tts`) using Khmer neural voices (`km-KH-SreymomNeural` female or `km-KH-PisethNeural` male).
  - **Visual Motion & FX**: Local FFmpeg subprocesses executing Ken Burns pan/zoom, UGC camera shake/grain, ASS hardsub burning, and price badge overlays.
  - **Stock Video Clips**: Pexels Free API (250 requests/hour free tier).
  - **Data Scraping**: Playwright / Selenium for Meta Ads Library.

---

## 📁 2. PROJECT DIRECTORY STRUCTURE

```
d:\ADS\pipeline\
│
├── main.py                     # Primary CLI Entry Point & Router Dispatcher
├── app2.py                     # Light-themed Gradio Web UI (Port 7860)
├── smoke_test.py               # Comprehensive Import & Environment Verification Script
├── requirements.txt            # Python Dependencies (google-genai, edge-tts, gradio, ffmpeg-python, etc.)
├── .env                        # Environment Configuration (GEMINI_API_KEY, PEXELS_API_KEY)
├── .env.example                # Template for Environment Configuration
├── START.md                    # Quick-start documentation & operation instructions
│
├── core/                       # Core Decoupled Processing Modules
│   ├── config.py               # Centralized configuration dataclasses & WorkflowMode enum
│   ├── router.py               # Central input validation & mode routing engine
│   ├── tts_engine.py           # Edge-TTS Khmer voiceover synthesis wrapper
│   ├── subtitle_gen.py        # Advanced ASS subtitle generator with Khmer font styling
│   ├── ffmpeg_utils.py         # FFmpeg wrapper: Ken Burns motion, color grading, hardsub burning, duration probing
│   ├── pexels_client.py        # Pexels API client for downloading Creative Commons stock video clips
│   ├── overlay_renderer.py     # Price tag & promotional badge graphic overlay renderer
│   ├── ugc_filters.py          # UGC authenticity filters (film grain, subtle/medium/strong camera shake)
│   ├── concat_helper.py        # FFmpeg video clip concatenation engine with SAR normalization
│   ├── broll_aggregator.py     # Local & API B-roll fetcher with SQLite deduplication
│   ├── prosody_mapper.py       # Edge-TTS rate/volume prosody mapping for emotional contrast
│   ├── social_proof_overlay.py # Social proof & star rating FFmpeg drawtext overlay
│   └── music_library.py        # Local background music manager (calm/upbeat/urgent)
│
├── modes/                      # Workflow Pipeline Orchestrators
│   ├── auto/                   # Mode 1: Auto-Autonomous Pipeline
│   │   ├── __init__.py
│   │   ├── auto_pipeline.py    # Main Auto Mode orchestrator
│   │   ├── scraper.py          # Meta Ads Library scraper (Playwright/Selenium)
│   │   └── ai_analyzer.py      # Gemini 3.6 Flash multimodal video timestamp & Khmer script generator
│   │
│   ├── manual/                 # Mode 2: Manual Override Pipeline
│   │   ├── __init__.py
│   │   ├── manual_pipeline.py  # Main Manual Mode orchestrator
│   │   ├── pacing_analyzer.py  # Reference video cut point & pacing extractor via FFprobe
│   │   └── prompt_interpreter.py # Natural language prompt parser to Ken Burns motion/color settings
│   │
│   ├── dub_only/               # Mode 3: Dub Only Pipeline
│   │   ├── __init__.py
│   │   └── dub_only_pipeline.py # Replaces original audio with Khmer TTS & ASS hardsubs
│   │
│   ├── full_remix/             # Mode 4: Full Remix Pipeline
│   │   ├── __init__.py
│   │   ├── full_remix_pipeline.py # Main Full Remix orchestrator
│   │   ├── audio_replace.py    # Audio stripping & Khmer translation / custom TTS replacement
│   │   ├── text_mask_overlay.py # Text region masking (Box / Blur / Branded overlay)
│   │   └── remix_cut_generator.py # Re-cut segment re-ordering, UGC camera shake & AI Dubbed badge
│   │
│   ├── news_auto/              # Mode 5: Auto News Video (JSON-driven)
│   │   ├── __init__.py
│   │   ├── news_auto_pipeline.py # Main News Auto orchestrator (720p/1080p/4K support)
│   │   ├── json_schema_validator.py # Safe JSON schema validator & sanitizer
│   │   ├── prompt_template.py  # Gemini system prompt template for news script generation
│   │   └── watermark_injector.py # Channel name watermark overlay
│   │
│   ├── polish/                 # Mode: Polish
│   │   ├── __init__.py
│   │   └── polish_pipeline.py  # Applies watermark, price badge, social proof, and prepends hooks
│
│   └── pro_editor/             # Mode 7: Professional Ads Editor Pipeline
│       ├── __init__.py
│       ├── pro_editor_pipeline.py # Main Pro Editor orchestrator
│       ├── creative_director.py # Gemini CreativeScript JSON generator (Hook-PAS-Proof-CTA)
│       ├── shotlist_planner.py  # Shotlist builder & English B-roll keyword normalizer
│       └── hook_variant_generator.py # A/B test hook clip generator (Ken Burns + text)
│
├── assets/                     # Static Assets
│   └── fonts/                  # Khmer Unicode Fonts (Hanuman.ttf, Battambang.ttf, Moul.ttf)
│
├── temp/                       # Temporary build workspace (automatically cleaned after runs)
└── output/                     # Final output directory for rendered MP4 videos
```

---

## ⚙️ 3. WORKFLOW MODES & TECHNICAL SPECIFICATIONS

### Mode 1: `auto` (Auto-Autonomous Pipeline)
- **Input**: Product Image (`.jpg`/`.png`), Category Keyword (e.g. `"hair gel cambodia"`).
- **Process**:
  1. `modes/auto/scraper.py`: Scrapes Meta Ads Library for competitor videos and downloads reference MP4.
  2. `modes/auto/ai_analyzer.py`: Sends video + product image to `gemini-3.6-flash` (with fallback to `gemini-3.5-flash`, `gemini-flash-latest`, `gemini-2.0-flash`). Uses `response_mime_type="application/json"` to extract scene cut timestamps and write a natural Khmer advertising voiceover script.
  3. `core/tts_engine.py`: Synthesizes Khmer voiceover MP3 using `edge-tts`.
  4. `core/ffmpeg_utils.py`: Renders Ken Burns pan/zoom motion on the product image matching scene cut timestamps, muxes audio, generates `.ASS` Khmer subtitles, and hardsubs video.

### Mode 2: `manual` (Manual Override Pipeline)
- **Input**: Product Image, Reference Video Path, Custom Khmer Script, Motion Prompt (e.g. `"warm cinematic slow zoom"`).
- **Process**:
  1. `modes/manual/pacing_analyzer.py`: Extracts cut points from reference video via FFprobe.
  2. `modes/manual/prompt_interpreter.py`: Parses prompt into motion parameters (`zoom_speed`, `pan_directions`, `color_preset`).
  3. `core/tts_engine.py`: Synthesizes custom Khmer script to audio.
  4. `core/ffmpeg_utils.py`: Renders Ken Burns motion + color filter + audio merge + hardsubbed ASS subtitles.

### Mode 3: `dub_only` (Dub Only Pipeline)
- **Input**: Source Video Path (`.mp4`), Custom Khmer Script.
- **Process**:
  1. `modes/dub_only/dub_only_pipeline.py`: Uses AI to generate script if empty, synthesizes Khmer voiceover script.
  2. `core/ffmpeg_utils.py`: Adjusts audio speed to match video duration.
  3. Muxes video with new voiceover.
  4. Generates and hardsubs ASS subtitles formatted with Khmer Hanuman font (if enabled).

### Mode 4: `full_remix` (Full Remix Pipeline)
- **Scope**: Re-cut user-owned footage with dubbing and music.
- **Input**: Source Video Path, Custom Khmer Script, Custom On-Screen Text (Optional), Mask Style (`"box"`, `"blur"`, `"branded_title_frame"`, `"none"`), Mask Color, Create Remix Flag.
- **Process**:
  1. `modes/full_remix/audio_replace.py`: Strips original audio track (`ffmpeg -an`) and merges new Khmer voiceover.
  2. `modes/full_remix/text_mask_overlay.py`: Applies FFmpeg mask over original text region. If `on_screen_text` is provided, hardsubs it onto the video.
  3. `core/music_library.py`: Mixes upbeat background music at -18dB.
  4. `modes/full_remix/remix_cut_generator.py`: Generates a 2nd re-cut remix version by re-ordering CFR-normalized video segments and applying UGC camera shake/grain.
  5. Outputs 2 separate MP4 files: `[video]_main.mp4` and `[video]_remix.mp4`.

### Mode 5: `news_auto` (Auto News Video Generator)
- **Input**: JSON payload (string or file path), Channel Name (watermark), Output Quality (`720p`, `1080p`, `4k`).
- **JSON Schema**:
  ```json
  {
    "title": "Tiêu đề tin tức nổi bật",
    "script_segments": [
      {
        "id": 1,
        "voiceover_text": "Lời đọc voiceover 100% tiếng Khmer",
        "on_screen_text": "Chữ nổi bật hiển thị trên màn hình",
        "visual_hint": "breaking news studio",
        "duration_hint_sec": 4
      }
    ],
    "product_price": "Giá sản phẩm (ví dụ: 15,000 KHR)",
    "output_quality": "1080p"
  }
  ```
- **Process**:
  1. `modes/news_auto/json_schema_validator.py`: Validates and sanitizes JSON payload.
  2. `core/tts_engine.py`: Synthesizes segment voiceovers and concatenates master audio track.
  3. `core/pexels_client.py` / `core/ffmpeg_utils.py`: Fetches Pexels CC stock clips matching `visual_hint` per segment, or generates Ken Burns text/visual tiles as fallback.
  4. `core/subtitle_gen.py` & `core/overlay_renderer.py`: Generates news-style ASS captions, hardsubs subtitles, injects product price overlay, and scales output to 720p/1080p/4K.

### Mode 6: `polish` (Post-Processing Polish Pipeline)
- **Scope**: Polishing an already completed video.
- **Input**: Source Video Path, Add Price Badge, Price, Add Social Proof, Hook Variants, Watermark Text.
- **Process**:
  1. `core/overlay_renderer.py`: Adds watermark and price badge overlay.
  2. `core/social_proof_overlay.py`: Applies star rating and sold counter to the video.
  3. `modes/pro_editor/hook_variant_generator.py`: Prepend N A/B hook variants to the polished video.
  4. Outputs N separate MP4 files, each with a distinct hook.

### Mode 7: `pro_editor` (Professional Ads Editor Pipeline)
- **Input**: Product Name, Product Image, Price, Key Benefits, Pain Points, Number of Hooks (A/B Test Variants).
- **Process**:
  1. `modes/pro_editor/creative_director.py`: Sends product context to Gemini to generate a structured `CreativeScript` JSON following the Hook-PAS-Proof-CTA framework. Outputs `script_segments` with explicit `overlay_type`, `emotion`, and `visual_hint`.
  2. `modes/pro_editor/hook_variant_generator.py`: Generates N distinct short intro hook clips using Ken Burns motion + bold text overlays based on `hook_type` (question, shock_fact, relatable_scenario).
  3. `modes/pro_editor/shotlist_planner.py`: Parses the script into a validated shotlist, handling the English batch-translation of `visual_hint`.
  4. `core/broll_aggregator.py`: Fetches B-roll from local `assets/local_broll/`, then Pexels/Pixabay APIs, ensuring no duplicates via SQLite manifest.
  5. `core/tts_engine.py` + `core/prosody_mapper.py`: Synthesizes Khmer voiceovers with dynamic rate/volume prosody adjustments mapping directly to the segment's `emotion` (concerned, urgent, confident, upbeat, energetic).
  6. `core/ffmpeg_utils.py` & `core/overlay_renderer.py`: Render per-segment visuals. Directly applies `price_tag` or `social_proof` overlays onto specific segments based on the `overlay_type` value.
  7. `core/music_library.py`: Mixes mood-appropriate background music (calm/upbeat/urgent) at -18dB based on the dominant emotion.
  8. `core/subtitle_gen.py`: Applies ASS hardsubs. Outputs N complete MP4 files, each prepended with a different hook variant.

---

## 🛠️ 4. CORE UTILITY API REFERENCE

### `core/config.py`
- `WorkflowMode`: Enum(`AUTO_AUTONOMOUS`, `MANUAL_OVERRIDE`, `NEWS_AUTO`, `PRO_EDITOR`, `NEWS_ADS`, `NEWS_PRO`, `DUB_ONLY`, `FULL_REMIX`, `POLISH`).
- Dataclasses: `GlobalConstraints`, `APIConfig`, `KenBurnsConfig`, `SubtitleConfig`, `PipelineConfig`, `AutoInputs`, `ManualInputs`, `NewsAutoInputs`, `FullRemixInputs`, `DubOnlyInputs`, `PolishInputs`, `PipelineInputs`.

### `core/router.py`
- `run_pipeline(inputs: PipelineInputs, cfg: Optional[PipelineConfig] = None) -> str`: Central dispatch router.

### `core/tts_engine.py`
- `synthesize_khmer(script_text: str, output_path: str, voice: str = "km-KH-SreymomNeural") -> str`: Uses `edge-tts` to generate Khmer voiceover MP3.

### `core/subtitle_gen.py`
- `generate_ass_file(script_text: str, timestamps: list[float], output_path: str, preset_name: str = "classic_box", word_timestamps: Optional[list[dict]] = None, font_name: str = "Hanuman", alignment: int = 2) -> str`: Builds formatted ASS subtitle file using defined `CAPTION_PRESETS` (`classic_box`, `outline_bold`, `karaoke_highlight`, `minimal_clean`).
- `ensure_caption_style_previews(...)`: Offline renders FFmpeg preview thumbnails for the UI Gallery.

### `core/ffmpeg_utils.py`
- `apply_ken_burns(image_path, output_path, timestamps, total_duration, out_w, out_h, zoom_start, zoom_end, pan_directions, fps=30, temp_dir=None)`: Renders segmented Ken Burns motion. **Includes high-res `scale=8000:-1` fix before `zoompan` to prevent jitter.**
- `normalize_segment_cfr(input_path: str, output_path: str, fps: int = 30) -> str`: Enforces Constant Frame Rate (CFR) using `-vsync cfr -r 30` to prevent desync during concatenation.
- `burn_hardsub(input_video, ass_path, fonts_dir, output_path, crf=23)`: Hardsubs ASS subtitles with Khmer Unicode fonts.
- `adjust_audio_speed(input_audio: str, output_audio: str, target_duration: float)`: Adjusts audio tempo using `atempo` filter to precisely match video duration (clamped between 0.5x and 2.0x).
- `get_video_duration(video_path: str) -> float`: Returns duration in seconds via `ffprobe`.

### `core/concat_helper.py`
- `concatenate_clips(clip_paths: list[str], output_path: str, fps: int = 30)`: Securely merges video segments via FFmpeg `concat` demuxer, passing every clip through `normalize_segment_cfr` first to ensure perfect audio/video sync.

---

## 🖥️ 5. INTERFACES & COMMAND LINE USAGE

### CLI Usage (`main.py`)

```powershell
# Mode 1: Auto-Autonomous
python main.py --mode auto --product-image "d:/ADS/gel.jpg" --keyword "hair gel cambodia" --output "d:/ADS/output"

# Mode 2: Manual Override
python main.py --mode manual --product-image "d:/ADS/gel.jpg" --ref-video "d:/ADS/ref.mp4" --script "ហ្សែលក្ដៅ!" --prompt "warm cinematic slow zoom" --output "d:/ADS/output"

# Mode 3: Dub Only
python main.py --mode dub_only --dub-only-source "d:/ADS/video.mp4" --dub-only-script "ស្វាគមន៍" --output "d:/ADS/output"

# Mode 4: Full Remix
python main.py --mode full_remix --full-remix-source "d:/ADS/video.mp4" --script "ស្វាគមន៍" --full-remix-mask-style box --full-remix-create-remix --output "d:/ADS/output"

# Mode 6: Polish
python main.py --mode polish --polish-source "d:/ADS/video.mp4" --polish-watermark "DAILY NEWS" --polish-add-price --price "15000 KHR" --polish-add-social --polish-hooks 3 --output "d:/ADS/output"

# Mode 7: Pro Editor (A/B Test Hooks)
python main.py --mode pro_editor --product-image "d:/ADS/gel.jpg" --product-name "Gôm Vuốt Tóc Kềm" --price "15000 KHR" --benefits "giữ nếp,thơm,rẻ" --pain-points "tóc rối,bết" --hook-variants 3 --output "d:/ADS/output"
```

### Web UI (`app2.py`)
### Web UI (`app2.py`)
- Executed via `python app2.py` (opens browser at `http://localhost:7860`).
- Contains 10 light-themed Gradio tabs, main ones being:
  1. **Auto / Manual**: Generative pipeline.
  2. **Dub Only**: Quick voice replacement & subtitle burning.
  3. **Full Remix**: Pexels CC clip search & video remixing + Dubbing.
  4. **Polish**: Post-processing effects (Watermark, Social Proof, Price, Hook variants).
  5. **Pro Editor**: Full professional A/B test hook generation.

---

## 🔒 6. CRITICAL IMPLEMENTATION RULES FOR AI ASSISTANTS

1. **Maintain Zero-Cost Compliance**: Never introduce paid API SDKs or required paid tokens (e.g. Replicate, OpenAI Paid API). Always default to free local processing (FFmpeg, Edge TTS, Google AI Studio Free Tier for vision/text).
2. **Robust Gemini Model Resolution**: When invoking Gemini API, always use `_generate_content_with_fallback(...)` with candidate list `['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash']` and set `response_mime_type="application/json"` for structured JSON extraction.
3. **Khmer Font Path Handling**: Always ensure `fonts_dir="assets/fonts"` is passed to `burn_hardsub(...)` so FFmpeg can load `Hanuman.ttf`, `Battambang.ttf`, or `Moul.ttf`.
4. **Sanitize Paths & Input**: Never pass unescaped backslashes in FFmpeg drawtext / filter strings on Windows. Normalize Windows paths using `.replace("\\", "/")` and escape colons `.replace(":", "\\:")` when using FFmpeg `subtitles='{file}':fontsdir='{dir}'` syntax.
5. **Word-Level TTS Boundaries**: Use `edge_tts.SubMaker` and `Communicate.stream()` instead of `.save()` to extract `WordBoundary` events and save as `.words.json`. This is required for Karaoke word-highlighting. If word boundaries are missing, seamlessly fallback to classic caption generation to prevent drifting.
