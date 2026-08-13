"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/tts_engine.py — edge-tts Khmer TTS Wrapper

  NOTE: We exclusively use `edge-tts` for production voiceovers.
  Gemini TTS models (`gemini-*-tts`) are strictly NOT used here because
  the free tier of Google AI Studio TTS does not provide a commercial
  license, making it unsuitable for advertising publishing.
  
  WARNING / LEGAL DISCLAIMER: `edge-tts` is a community-developed reverse
  engineered tool that accesses Microsoft Edge's Read Aloud service. It is NOT
  an officially licensed commercial API. While it provides a zero-cost option,
  operators must be aware that using this for commercial advertising carries a
  non-zero legal risk and operates in a grey area. Proceed with caution.
====================================================================
"""

import asyncio
import logging
import os
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3

logger = logging.getLogger(__name__)

# Default Khmer voices (Microsoft Edge TTS, free, no API key)
VOICE_FEMALE = "km-KH-SreymomNeural"
VOICE_MALE   = "km-KH-PisethNeural"


async def _synthesize_async(text: str, voice: str, rate: str, output_path: str) -> None:
    """Internal async synthesis call via edge-tts."""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    sub = edge_tts.SubMaker()
    word_events = []

    with open(output_path, "wb") as f_audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f_audio.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                try:
                    sub.feed(chunk)
                except ValueError:
                    pass
                word_events.append({
                    "type": chunk["type"],
                    "text": chunk.get("text", ""),
                    "start": chunk.get("offset", 0) / 10000000.0,
                    "duration": chunk.get("duration", 0) / 10000000.0,
                    "end": (chunk.get("offset", 0) + chunk.get("duration", 0)) / 10000000.0,
                })

    # Save timestamp metadata
    words_json_path = str(Path(output_path).with_suffix(".words.json"))
    try:
        import json
        with open(words_json_path, "w", encoding="utf-8") as f_json:
            json.dump(word_events, f_json, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.debug(f"[TTS] Could not save words json: {exc}")


def synthesize_khmer(
    script_text: str,
    output_path: str,
    voice: str = VOICE_FEMALE,
    rate: str = "+0%"
) -> str:
    """
    Synthesize Khmer text to speech using edge-tts.
    
    Parameters
    ----------
    script_text : str
        Khmer-language script to synthesize.
    output_path : str
        Destination path for the output .mp3 file.
    voice : str
        Edge TTS voice name. Defaults to km-KH-SreymomNeural (female).
    rate : str
        Speech rate adjustment (e.g. "+25%", "-10%"). Defaults to "+0%".
        
    Returns
    -------
    str
        Absolute path to the synthesized .mp3 file.
    """
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not script_text or not script_text.strip():
        logger.warning("[TTS] Bỏ qua tạo TTS do đoạn text rỗng hoặc chỉ có khoảng trắng.")
        # Create an empty silent MP3 file or just a minimal valid MP3 so FFmpeg doesn't crash
        # For simplicity, if we have no text, we just raise an error that it's empty, or create a dummy file.
        # But usually it's better to just skip. We will create a 0.1s silence.
        _create_silent_mp3(output_path)
        return output_path

    logger.info(f"[TTS]  TTS synthesis -> voice={voice}, rate={rate}")
    logger.info(f"    Script length: {len(script_text)} chars")

    # edge-tts is async — use asyncio.run() (Python 3.10+)
    # Falls back to nest_asyncio for Gradio / Jupyter environments
    try:
        asyncio.run(_synthesize_async(script_text, voice, rate, output_path))
    except RuntimeError:
        # Already inside a running event loop (Gradio/Jupyter)
        import nest_asyncio  # type: ignore
        nest_asyncio.apply()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_synthesize_async(script_text, voice, rate, output_path))

    if not os.path.isfile(output_path):
        raise RuntimeError(f"TTS synthesis failed — output not found: {output_path}")

    duration = get_audio_duration(output_path)
    logger.info(f"    ✓ Voiceover saved: {output_path}  ({duration:.1f}s)")
    return output_path


def get_audio_duration(mp3_path: str) -> float:
    """
    Return the duration of an MP3 file in seconds.

    Parameters
    ----------
    mp3_path : str
        Path to the MP3 file.

    Returns
    -------
    float
        Duration in seconds.
    """
    try:
        audio = MP3(mp3_path)
        return audio.info.length
    except Exception as e:
        logger.warning(f"[TTS] Không thể đọc thời lượng audio {mp3_path}: {e}")
        return 0.0

def _create_silent_mp3(output_path: str, duration: float = 0.5) -> None:
    """Tạo một file MP3 im lặng khi text bị rỗng để tránh lỗi FFmpeg."""
    try:
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration), "-q:a", "9", "-acodec", "libmp3lame", output_path
        ], capture_output=True, check=True)
    except Exception as e:
        logger.error(f"[TTS] Lỗi tạo silent MP3: {e}")
        # Create a completely empty file as absolute fallback
        open(output_path, 'wb').close()

async def list_khmer_voices() -> list[dict]:
    """
    Query all available Khmer voices from edge-tts.

    Returns
    -------
    list[dict]
        List of voice descriptor dicts for locale 'km-KH'.
    """
    voices = await edge_tts.list_voices()
    return [v for v in voices if v.get("Locale", "").startswith("km")]


def generate_tts(
    text: str,
    output_path: str,
    voice: str = "vi-VN-HoaiMyNeural",
    rate: str = "+0%",
) -> str:
    """
    Alias đa ngôn ngữ cho synthesize_khmer — hỗ trợ giọng Việt, Khmer,
    và bất kỳ voice edge-tts nào khác.

    Parameters
    ----------
    text : str
        Văn bản cần đọc.
    output_path : str
        Đường dẫn file MP3 đầu ra.
    voice : str
        Tên giọng edge-tts. Mặc định: vi-VN-HoaiMyNeural (Tiếng Việt nữ).
        Các giọng phổ biến:
          - Tiếng Việt nữ : vi-VN-HoaiMyNeural
          - Tiếng Việt nam : vi-VN-NamMinhNeural
          - Khmer nữ       : km-KH-SreymomNeural
          - Khmer nam      : km-KH-PisethNeural
    rate : str
        Tốc độ đọc (+25%, -10% ...). Mặc định "+0%".

    Returns
    -------
    str
        Đường dẫn file MP3 đã tạo.
    """
    return synthesize_khmer(script_text=text, output_path=output_path, voice=voice, rate=rate)
