# 📐 System Architecture & Specification
## Hybrid Zero-Cost Video Pipeline v3.5

Authoritative technical spec of this codebase — architecture, workflow modes, core modules,
data schemas, CLI surface, and the rules to follow when modifying it.
This is the single reference document for developers and AI coding assistants.
End-user instructions (in Vietnamese) live in [`START.md`](START.md).

---

## 🎯 1. PURPOSE & ZERO-COST POLICY

- **What it does**: fully automated 9:16 portrait (1080×1920, 30fps) short-form ad video
  generation for Facebook Shorts / Reels / TikTok, targeting Khmer (Cambodia) and Vietnamese
  audiences, plus a news-style ad format.
- **Input**: a product image + name/keyword/price, or an existing video, or a product URL.
- **Output**: finished `.mp4` with AI-written script, B-roll, TTS voiceover, hardsubbed
  captions, background music, SFX and overlays — typically 3–5 hook variants for A/B testing.
- **Strict zero-cost policy (0 VNĐ / 0 USD)** — every dependency must have a usable free tier:
  | Layer | Service | Notes |
  |---|---|---|
  | Text & vision LLM | Google Gemini Flash free tier via `google-genai` | pool + fallback chain |
  | LLM fallback | Groq free tier (`groq`) | used when Gemini quota is exhausted |
  | TTS | Microsoft Edge TTS (`edge-tts`) | unlimited, neural voices |
  | Stock clips | Pexels (250 req/h), Pixabay | free API keys |
  | Scraped B-roll | `yt-dlp` (YouTube / TikTok) | local library |
  | Ad intelligence | Meta Ads Library (Playwright/Selenium), TikTok Commercial Content API | public data |
  | Vision search | ResNet50 (TensorFlow) + SQLite | 100% offline |
  | Render / FX | local FFmpeg subprocesses | 100% offline |

---

## 📁 2. PROJECT STRUCTURE

```text
<repo root>/
│
├── app2.py                     # PRIMARY ENTRY POINT — Gradio Web UI (all modes)
├── main.py                     # CLI entry point (subset of modes, see §5)
├── smoke_test.py               # Import & environment verification
├── requirements.txt            # Python deps (tested on 3.10+; 3.11 in Docker)
├── Dockerfile                  # Hugging Face Spaces / container deploy
├── CAI_DAT.bat / KHOI_DONG.bat # Windows one-click install / launch
├── .env.example                # Template for .env (API keys)
├── config/pipeline_config.json # Declarative defaults (resolution, fonts, Ken Burns, subtitle)
│
├── core/                       # Decoupled processing modules (shared by every mode)
│   │  ── AI / LLM ──
│   ├── gemini_pool.py          # Multi-key Gemini pool + model fallback chain
│   ├── groq_client.py          # Groq fallback when Gemini quota is exhausted
│   ├── config.py               # WorkflowMode enum + all config/input dataclasses
│   ├── router.py               # Input validation & mode dispatch
│   │  ── Audio / caption ──
│   ├── tts_engine.py           # Edge-TTS synthesis (Khmer + Vietnamese + others)
│   ├── language_resolver.py    # Language → voice/font resolution
│   ├── prosody_mapper.py       # Emotion → TTS rate/volume mapping
│   ├── subtitle_gen.py         # ASS generator, 4 caption presets, karaoke word timing
│   ├── music_library.py        # Local music by energy (calm/upbeat/urgent), -18dB mix
│   ├── sfx_fetcher.py          # Pop / whoosh SFX
│   │  ── Visual sourcing ──
│   ├── broll_aggregator.py     # B-roll chain: local → Pexels → Pixabay → TikTok → generic
│   ├── multi_source_fetcher.py # Multi-provider fetch orchestration
│   ├── pexels_client.py        # Pexels API client
│   ├── tiktok_scraper.py       # yt-dlp based TikTok clip scraper
│   ├── stockpile_broll_curator.py # Keyword → yt-dlp crawl → curated local B-roll library
│   ├── logo_remover.py         # FFmpeg delogo/boxblur watermark removal
│   ├── visual_search_engine.py # Image → product lookup
│   ├── product_vision_index.py # ResNet50 feature vectors + SQLite (products.sqlite)
│   │  ── Intelligence ──
│   ├── product_intelligence.py # Product research (web + LLM), 30-day cache
│   ├── product_url_scraper.py  # Product page → structured attributes
│   ├── ad_library_client.py    # Meta Ads Library client (Ad Spy)
│   ├── tiktok_api_client.py    # TikTok Commercial Content API (Ad Spy)
│   ├── auto_discovery_engine.py# Keyword → assets → assembly, end to end
│   ├── claim_validator.py      # Filters unsafe/unverifiable ad claims
│   │  ── Assembly / FX ──
│   ├── video_assembly_engine.py# Segment → final video assembly
│   ├── ffmpeg_utils.py         # Ken Burns, CFR normalize, hardsub, audio speed, probing
│   ├── concat_helper.py        # Concat demuxer with SAR/CFR normalization
│   ├── overlay_renderer.py     # Price tag & promo badge overlays
│   ├── social_proof_overlay.py # Star rating & sold-counter overlay
│   ├── ugc_filters.py          # Film grain, camera shake (subtle/medium/strong)
│   ├── pacing_enforcer.py      # Enforces target pacing/cut rhythm
│   ├── style_profile.py        # Saved visual style presets (assets/style_profiles/)
│   ├── reverse_template.py     # Reverse-engineer a template from a reference video
│   ├── variation_engine.py     # Script/visual variation generation
│   ├── multi_variant_engine.py # N-variant batch output
│   ├── scene_machine_engine.py # Google Scene Machine 4-scene storyboard
│   ├── classic_scene_machine.py# Classic (non-LLM-heavy) storyboard variant
│   ├── magic_pipeline_engine.py# "Magic One-Click" orchestration
│   ├── classic_magic_pipeline.py # Classic Magic One-Click variant
│   └── local_business_engine.py# Local store / shop ad generation
│
├── modes/                      # Workflow pipeline orchestrators (see §3)
│   ├── auto/ manual/ news_auto/ news_ads/ news_pro/
│   ├── dub/ dub_only/ full_remix/ polish/
│   ├── fb_shorts/ pro_editor/ ultimate_ad/ ai_broll/
│
├── assets/
│   ├── fonts/                  # NotoSans-Bold.ttf, NotoSansKhmer-Bold.ttf (auto re-downloaded)
│   ├── local_broll/            # Scraped B-roll library: <category>/ + generic/
│   ├── local_music/            # User-supplied music: calm/ upbeat/ urgent/
│   ├── caption_style_previews/ # Auto-generated caption preset thumbnails
│   ├── product_db/crops/       # Cropped product images for visual search
│   └── style_profiles/         # Saved style profile JSON
│
├── vendors/remove-logo-from-video/  # Upstream reference docs for the delogo technique
├── temp/                       # Intermediate build files + caches (gitignored)
└── output*/                    # Rendered MP4s (gitignored)
```

---

## ⚙️ 3. WORKFLOW MODES

`WorkflowMode` (`core/config.py`) declares 11 modes. `modes/` holds 13 pipeline packages —
`fb_shorts` and `ai_broll` are driven from the Web UI rather than the `--mode` enum.

| Mode | Package | What it does |
|---|---|---|
| `auto` | `modes/auto/` | Scrape a competitor ad from Meta Ads Library → Gemini analyzes video + product image → script + cut timestamps → Ken Burns render → TTS → hardsub |
| `manual` | `modes/manual/` | User supplies script + motion prompt; pacing extracted from a reference video via FFprobe; prompt parsed into zoom/pan/color params |
| `dub_only` | `modes/dub_only/` | Replace a video's audio with TTS voiceover (auto-generating the script if empty), tempo-match to duration, optional burned subtitles |
| `dub_remix` | `modes/dub/` | Dub + light re-edit variant (replace or mix over the original audio, optional subtitles) |
| `full_remix` | `modes/full_remix/` | Strip original audio → new voiceover → mask original on-screen text (box/blur/branded) → music mix → re-cut UGC remix. Outputs `_main.mp4` + `_remix.mp4` |
| `polish` | `modes/polish/` | Post-process a finished video: watermark, price badge, social proof, then prepend N hook variants → N MP4s |
| `pro_editor` | `modes/pro_editor/` | Full ad pipeline: product research → Hook-PAS-Proof-CTA `CreativeScript` JSON → shotlist → B-roll → prosody TTS → overlays → music → N hook variants |
| `ultimate_ad` | `modes/ultimate_ad/` | Most automated ad mode (UI Mode 10): one product image → 3–5 A/B variants, with NTD asset and FB Studio bridges |
| `news_auto` | `modes/news_auto/` | JSON-driven news video (720p/1080p/4K) with channel watermark; schema-validated payload |
| `news_ads` | `modes/news_ads/` | News-styled ad format to counter banner blindness |
| `news_pro` | `modes/news_pro/` | Advanced news generator with its own prompt templates |
| — | `modes/fb_shorts/` | UI-only: FB Shorts generative + remix sub-modes, URL extraction |
| — | `modes/ai_broll/` | UI-only: AI-generated B-roll via Google Labs client, account pool, generation queue, character consistency |

### `news_auto` JSON schema

```json
{
  "title": "Tiêu đề tin tức nổi bật",
  "script_segments": [
    {
      "id": 1,
      "voiceover_text": "Lời đọc voiceover",
      "on_screen_text": "Chữ hiển thị trên màn hình",
      "visual_hint": "breaking news studio",
      "duration_hint_sec": 4
    }
  ],
  "product_price": "15,000 KHR",
  "output_quality": "1080p"
}
```

Validated and sanitized by `modes/news_auto/json_schema_validator.py` before use.

---

## 🛠️ 4. CORE API REFERENCE

### `core/config.py`
- `WorkflowMode`: `AUTO_AUTONOMOUS`, `MANUAL_OVERRIDE`, `NEWS_AUTO`, `DUB_REMIX`, `PRO_EDITOR`,
  `NEWS_ADS`, `NEWS_PRO`, `DUB_ONLY`, `FULL_REMIX`, `POLISH`, `ULTIMATE_AD`.
- Dataclasses: `GlobalConstraints`, `APIConfig`, `KenBurnsConfig`, `SubtitleConfig`,
  `PipelineConfig`, plus per-mode `*Inputs` (`AutoInputs`, `ManualInputs`, `NewsAutoInputs`,
  `FullRemixInputs`, `DubOnlyInputs`, `PolishInputs`, `UltimateAdInputs`, `PipelineInputs`).
- Defaults: 1080×1920 @ 30fps, libx264/aac, CRF 23, 15–90s, `km-KH-SreymomNeural`,
  fonts `Noto Sans Khmer` / `Noto Sans`.

### `core/router.py`
- `run_pipeline(inputs: PipelineInputs, cfg: Optional[PipelineConfig] = None) -> str` — central dispatch.
- `validate_inputs(...)` — per-mode required-field validation.

### `core/gemini_pool.py` — the only sanctioned way to reach Gemini
- `get_pooled_client(api_key=None) -> PooledClient` — drop-in replacement for `genai.Client`.
  Same call shape (`client.models.generate_content(model=…, contents=…, config=…)`), but every
  call gains key rotation, model fallback and the Groq escape hatch. **Use this, never
  `genai.Client` directly** — all 18 previous direct-client sites were migrated to it.
- `generate_content_with_pool(contents, config=None, fallback_models=None, preferred_key=None)`
  — rotates `GEMINI_API_KEY`, `GEMINI_API_KEY_1..19` (plus `preferred_key` first when the caller
  passes one) and walks `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-flash-latest`.
- Quota handling: a 429 on any key marks that key exhausted and moves on; once every key is
  exhausted the cache self-clears so a later run can retry. Quota is detected by message content
  (`_is_quota_error`), not exception class, because the SDK wraps 429 in several types.
- Groq fallback fires whenever *any* key hit quota — not only when the last error was a 429.
  It refuses to run on multimodal prompts (image/video parts) instead of stringifying them, and
  it forwards `response_mime_type="application/json"`, `system_instruction`, `temperature` and
  `max_output_tokens` from the Gemini config.

### `core/groq_client.py`
- Free-tier fallback over `llama-3.3-70b-versatile` → `llama-3.1-8b-instant` → `mixtral-8x7b-32768`,
  rotating `GROQ_API_KEY`, `GROQ_API_KEY_2`, …
- `json_mode=True` sets Groq's `response_format={"type": "json_object"}` and injects the word
  "JSON" into the system prompt (Groq requires it), so `json.loads(response.text)` still works
  on the fallback path.

### `core/ffmpeg_utils.py` — audio contract
- `adjust_audio_speed(...)` always produces `output_audio`. When the source duration can't be read
  (or the target is 0) it copies the input instead of returning early, because the next ffmpeg step
  consumes that path and used to die with an empty `CalledProcessError`.

### `core/tts_engine.py`
- `synthesize_khmer(script_text, output_path, voice="km-KH-SreymomNeural") -> str`
- Vietnamese path defaults to `vi-VN-HoaiMyNeural` (male: `vi-VN-NamMinhNeural`).
- Voice table per language lives in `core/language_resolver.py` (Khmer, Vietnamese, English,
  Thai, Indonesian). **Empty scripts must be handled — `edge_tts` raises `NoAudioReceived`.**

### `core/subtitle_gen.py`
- `generate_ass_file(script_text, timestamps, output_path, preset_name="classic_box", word_timestamps=None, font_name="Noto Sans Khmer", alignment=2) -> str`
- `CAPTION_PRESETS`: `classic_box`, `outline_bold`, `karaoke_highlight`, `minimal_clean`.
- `ensure_caption_style_previews(...)` renders UI gallery thumbnails offline (called on app boot).

### `core/ffmpeg_utils.py`
- `apply_ken_burns(image_path, output_path, timestamps, total_duration, out_w, out_h, zoom_start, zoom_end, pan_directions, fps=30, temp_dir=None)` — includes the `scale=8000:-1` pre-pass before `zoompan` to kill jitter.
- `normalize_segment_cfr(input_path, output_path, fps=30)` — `-vsync cfr -r 30`, required before concat.
- `burn_hardsub(input_video, ass_path, fonts_dir, output_path, crf=23)`
- `adjust_audio_speed(input_audio, output_audio, target_duration)` — `atempo`, clamped 0.5×–2.0×.
- `get_video_duration(video_path) -> float`

### `core/concat_helper.py`
- `concatenate_clips(clip_paths, output_path, fps=30)` — every clip passes through
  `normalize_segment_cfr` first to guarantee A/V sync.

### Local databases (under `temp/`, except `products.sqlite`)
| File | Purpose | TTL |
|---|---|---|
| `products.sqlite` | Visual search: product metadata + ResNet50 vectors | persistent |
| `broll_manifest.db` | B-roll usage history (anti-repeat) | 30 days |
| `broll_api_cache.db` | Cached Pexels/Pixabay JSON (per their ToS) | 24 h |
| `product_research_cache.db` | Product research results | 30 days |

---

## 🖥️ 5. INTERFACES

### Web UI — `app2.py` (primary)
`python app2.py` → Gradio on **port 7860** (matching `Dockerfile` and the Spaces `app_port`).
Overridable per run: `PORT` or `GRADIO_SERVER_PORT` for the port, `GRADIO_SHARE=1` to opt into the
public share tunnel (off by default — it exposes the app, running on your keys, to anyone with the
link), `GRADIO_INBROWSER=0` to stop it opening a browser.
Per-run intermediates go to `tempfile.mkdtemp(dir="temp")` via `_run_temp_dir()`; never write to a
fixed `temp/<name>` path, or concurrent users overwrite each other.
Nine top-level tabs: Magic One-Click · Magic Classic · URL → Ads · Quảng Cáo Tiệm ·
Tạo Video Mới (FB Shorts, News Auto) · Chế Biến Lại (Dub Only, Remix, Full Remix) ·
Thương Mại (Ultimate Ad, Visual Search, Ad Spy, Scene Machine, Stockpile Curator, Logo Remover,
Auto-Discovery, Pro Editor, News Ads, News Pro, Polish) · Hướng Dẫn · Style Profile.

Gradio 6 notes — the UI targets Gradio 6 and **cannot run on 4.x** (`launch(css=…, theme=…)` only
exists from 5/6). Two constraints follow from its tab bar and table:
- Tab labels must stay short and `.main-tabs > .tab-wrapper` keeps a viewport-based `min-width`.
  Gradio 6 collapses overflowing tabs into a `…` menu based on the measured bar width, and that bar
  shrinks to the active tab's content — so without the pin, each tab showed a different tab count.
- `gr.Dataframe` must pass `column_count` (not the deprecated `col_count`); otherwise clicking a
  header opens column-rename mode and crams a `⋮` menu into the cell, clipping the label.
- `.select()` handlers must annotate `evt: gr.SelectData` — a bare lambda gets called with zero
  arguments and raises.

### CLI — `main.py`
`--mode` accepts: `auto`, `manual`, `news_auto`, `pro_editor`, `news_ads`, `news_pro`,
`dub_only`, `full_remix`, `polish`, `ultimate_ad`. *(`fb_shorts` and `ai_broll` are Web-UI only;
`dub_remix` dispatches through the router but has no CLI flag bundle yet.)*

```bash
# Auto-Autonomous
python main.py --mode auto --product-image gel.jpg --keyword "hair gel cambodia" --output output

# Manual Override
python main.py --mode manual --product-image gel.jpg --ref-video ref.mp4 \
    --script "ហ្សែលក្ដៅ!" --prompt "warm cinematic slow zoom" --output output

# Dub Only
python main.py --mode dub_only --dub-only-source video.mp4 \
    --dub-only-script "ស្វាគមន៍" --dub-only-burn-subtitle --output output

# Full Remix
python main.py --mode full_remix --full-remix-source video.mp4 --script "ស្វាគមន៍" \
    --full-remix-mask-style box --full-remix-create-remix --output output

# Polish
python main.py --mode polish --polish-source video.mp4 --polish-watermark "DAILY NEWS" \
    --polish-add-price --price "15000 KHR" --polish-add-social --polish-hooks 3 --output output

# Pro Editor (A/B hook variants)
python main.py --mode pro_editor --product-image gel.jpg --product-name "Gôm Vuốt Tóc" \
    --price "15000 KHR" --benefits "giữ nếp,thơm,rẻ" --pain-points "tóc rối,bết" \
    --hook-variants 3 --caption-style karaoke_highlight --output output
```

Pro Editor extras: `--skip-product-research`, `--force-refresh-research`,
`--allow-scraped-footage`, `--caption-style {classic_box,outline_bold,karaoke_highlight,minimal_clean}`,
`--hook-variants N` (default 3, max 5).

### Docker / Hugging Face Spaces
`Dockerfile` installs FFmpeg + fontconfig, copies `assets/fonts/` into `/usr/share/fonts/khmer/`,
runs `fc-cache`, installs the Playwright Chromium browser, exposes **7860** and runs `python app2.py`.
The `playwright install --with-deps chromium` step is required by the `auto` mode scraper and the
AI B-roll client — without it those two modes fail at runtime with "Executable doesn't exist".
It costs ~1.5 GB of image size (≈4.3 GB → ≈5.8 GB).

---

## 🔑 6. ENVIRONMENT VARIABLES

Read from `.env` (see `.env.example`). Only `GEMINI_API_KEY` is truly required.

| Variable | Required | Used for |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | All AI script/vision generation |
| `GEMINI_MODEL` | — | Override the default model of the fallback chain |
| `GROQ_API_KEY` (+ `_2`, …) | — | LLM fallback when Gemini quota runs out |
| `PEXELS_API_KEY` | — | Stock B-roll |
| `PIXABAY_API_KEY` | — | Alternate stock B-roll |
| `YOUTUBE_API_KEY` | — | Product research video search |
| `META_AD_ACCESS_TOKEN` | — | Ad Spy (Facebook) |
| `TIKTOK_AD_ACCESS_TOKEN` | — | Ad Spy (TikTok) |
| `REPLICATE_API_TOKEN` | — | Optional AI video gen (falls back to Ken Burns) |
| `ELEVENLABS_API_KEY` | — | Optional premium TTS (edge-tts is the free default) |

Without the optional keys the system degrades gracefully — it falls back to Ken Burns motion on
the product image and local B-roll.

---

## 🔒 7. IMPLEMENTATION RULES

1. **Zero-cost compliance** — never introduce a paid-only SDK or a required paid token.
   Default to FFmpeg, Edge TTS, and free-tier AI Studio / Groq.
2. **Gemini access goes through `core/gemini_pool.py`** — call `get_pooled_client(api_key)`,
   never `genai.Client(...)`. A bare client silently opts that call site out of key rotation and
   the Groq fallback, so it dies on quota exhaustion while the rest of the app survives. Keep the
   model fallback chain intact, set `response_mime_type="application/json"` for structured output,
   and do not reintroduce retired models (e.g. `gemini-2.5-flash`).
3. **Font handling** — always pass `fonts_dir="assets/fonts"` to `burn_hardsub(...)`, and keep
   font references on the two shipped families (see §8).
4. **FFmpeg path sanitizing on Windows** — normalize with `.replace("\\", "/")` and escape colons
   `.replace(":", "\\:")` inside `subtitles='{file}':fontsdir='{dir}'` filter strings.
5. **Word-level TTS timing** — use `edge_tts.SubMaker` + `Communicate.stream()` (not `.save()`)
   to capture `WordBoundary` events into `.words.json` for karaoke captions; fall back to classic
   captions when boundaries are missing, so subtitles never drift.
6. **Guard empty scripts** before calling TTS — `edge_tts` raises `NoAudioReceived`.
7. **CFR before concat** — always route clips through `normalize_segment_cfr` to avoid A/V desync.
8. **Batch scripts (`.bat`)** — keep `chcp 65001`, save without a UTF-8 BOM, so Vietnamese text
   renders correctly in Windows CMD.

---

## 🔤 8. FONTS

Only two families are shipped, and every subtitle/drawtext call must stay on them:

| Family (ASS `font_name`, fontconfig) | File |
|---|---|
| `Noto Sans Khmer` | `assets/fonts/NotoSansKhmer-Bold.ttf` |
| `Noto Sans` | `assets/fonts/NotoSans-Bold.ttf` |

- ASS styles get the **family name**; FFmpeg `drawtext` gets the **file path**. Do not mix them.
- `core/overlay_renderer.py::_ensure_fonts()` re-downloads both files from the Noto repo if missing.
- `core/language_resolver.py::LANGUAGE_FONT_MAP` resolves language → family (Khmer → `Noto Sans
  Khmer`, everything else → `Noto Sans`). Add a font file before adding a family here — referencing
  an unavailable family makes FFmpeg silently substitute, and referencing a missing *file* makes
  `drawtext` fail outright.
- `config/pipeline_config.json` is **reference-only documentation** — nothing reads it.
  `load_config()` returns `PipelineConfig()` dataclass defaults from `core/config.py`.
