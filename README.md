---
title: Hybrid Zero Cost Video Pipeline
emoji: 🎥
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Hybrid Zero-Cost Khmer Video Pipeline v3.0

This repository provides an automated video generation pipeline targeted for FB Shorts and News Ads with a primary focus on Khmer audiences. It utilizes zero-cost APIs (Gemini Flash free tier, edge-tts, Pexels free tier) to generate high-quality video content from images, scripts, or existing videos.

## Features

- **Dub Only**: Translate or dub existing videos with Khmer voiceover and auto-generated subtitles.
- **Full Remix**: Re-edit existing footage, apply branded overlays, dub, and mix background music.
- **Polish**: Apply post-processing effects like watermarks, price badges, social proof, and prepend Ken Burns-style hook variants for A/B testing.
- **News Ads**: Generate news-style advertisements to prevent banner blindness.
- **Pro Editor**: Full ad generation pipeline with AI product research, hook-pas-proof-cta structure, and b-roll fetching.

## Running Locally

To run the Gradio UI locally:

```bash
pip install -r requirements.txt
python app2.py
```

The web interface will be available at `http://localhost:7860`.

## Environment Variables

Make sure to create a `.env` file or export the following variables:
- `GEMINI_API_KEY`: Required for AI generation modes.
- `PEXELS_API_KEY`: Required for fetching b-roll clips.
- `REPLICATE_API_TOKEN`: Optional, used for AI video generation (falls back to Ken Burns if missing).

## Deployment

This app is ready to be deployed to Hugging Face Spaces using the provided `Dockerfile` and metadata block.
