---
title: Hybrid Zero Cost Video Pipeline
emoji: 🎥
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Hybrid Zero-Cost Video Pipeline v3.5

Automated 9:16 short-form ad video generation for Facebook Shorts, Reels and TikTok, targeting
Khmer and Vietnamese audiences. Feed it a product image (or a video, or a product URL) and it
returns finished MP4s — AI-written script, sourced B-roll, TTS voiceover, burned captions,
background music and overlays — typically 3–5 hook variants for A/B testing.

Everything runs on free tiers and local FFmpeg: Gemini Flash (with Groq fallback), edge-tts,
Pexels/Pixabay, yt-dlp, and an offline ResNet50 + SQLite visual search index.

## Documentation

| Document | Audience |
|---|---|
| [`START.md`](START.md) | Hướng dẫn sử dụng đầy đủ (tiếng Việt) — cài đặt, API key, Web UI, CLI, xử lý lỗi |
| [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | Full technical spec — modules, modes, APIs, implementation rules |

## Features

- **Ultimate Ad / Magic One-Click** — one product image to 3–5 A/B-testable ad variants.
- **Pro Editor** — Hook-PAS-Proof-CTA scripting with product research and B-roll fetching.
- **Dub Only / Full Remix** — revoice and re-edit existing footage, mask old on-screen text.
- **Polish** — watermark, price badge, social proof, and prepended hook variants.
- **News Ads / News Pro / News Auto** — news-styled ads to counter banner blindness.
- **Stockpile B-Roll Curator** — keyword-driven yt-dlp crawl into a local B-roll library.
- **Logo Remover** — FFmpeg delogo/blur cleanup of watermarks on sourced clips.
- **Visual Search & Ad Spy** — offline product lookup, plus Meta/TikTok competitor ad research.

## Running locally

```bash
pip install -r requirements.txt
python app2.py
```

The Gradio UI opens at `http://localhost:7860` (override with `PORT=7871`). `main.py` exposes a CLI covering nine of the
modes — see [`START.md`](START.md) §5.

Requires Python 3.10+ and FFmpeg in `PATH`.

## Environment variables

Copy `.env.example` to `.env`. Only `GEMINI_API_KEY` is required; the rest are optional and the
pipeline degrades gracefully without them.

- `GEMINI_API_KEY` — required, all AI script and vision generation.
- `GROQ_API_KEY` — free LLM fallback when the Gemini quota is exhausted.
- `PEXELS_API_KEY` / `PIXABAY_API_KEY` — stock B-roll.
- `YOUTUBE_API_KEY`, `META_AD_ACCESS_TOKEN`, `TIKTOK_AD_ACCESS_TOKEN` — research and Ad Spy.
- `REPLICATE_API_TOKEN`, `ELEVENLABS_API_KEY` — optional, fall back to Ken Burns / edge-tts.

## Deployment

Deploys to Hugging Face Spaces via the provided `Dockerfile` and the metadata block above.
The app binds **7860** by default, matching `EXPOSE 7860` and the `app_port` declared above.
In a container, disable the share tunnel and browser launch: `GRADIO_SHARE=0 GRADIO_INBROWSER=0`.
