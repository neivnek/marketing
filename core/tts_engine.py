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


def _alt_voice(voice: str) -> str:
    """
    Tìm giọng thay thế cùng ngôn ngữ (nữ <-> nam).

    Dịch vụ edge-tts thỉnh thoảng trả về 0 byte cho một tổ hợp text+giọng cụ thể
    (tái hiện được 100%), nhưng đổi sang giọng còn lại của cùng ngôn ngữ thì chạy.
    """
    try:
        from core.language_resolver import LANGUAGE_VOICE_MAP
    except Exception:
        return ""
    for female, male in LANGUAGE_VOICE_MAP.values():
        if voice == female:
            return male
        if voice == male:
            return female
    return ""


def _tts_attempts(script_text: str, voice: str) -> list[tuple[str, str]]:
    """
    Thang thử lại cho TTS, xếp từ ít can thiệp tới nhiều:
      1. nguyên văn + giọng yêu cầu
      2. bỏ dấu câu ở cuối + giọng yêu cầu   (đã kiểm chứng: chữa được lỗi rỗng)
      3-4. hai biến thể trên với giọng thay thế cùng ngôn ngữ
    """
    base = script_text.strip()
    texts = [base]
    trimmed = base.rstrip(" .!?…。！？").strip()
    if trimmed and trimmed != base:
        texts.append(trimmed)

    attempts = [(t, voice) for t in texts]
    alt = _alt_voice(voice)
    if alt and alt != voice:
        attempts += [(t, alt) for t in texts]
    return attempts


def _audio_is_usable(path: str) -> bool:
    """File TTS chỉ được coi là hợp lệ khi tồn tại, khác rỗng VÀ đọc được thời lượng."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return False
    return get_audio_duration(path) > 0


def _discard(path: str) -> None:
    """Xoá file audio hỏng và metadata kèm theo để không ai dùng nhầm."""
    for p in (path, str(Path(path).with_suffix(".words.json"))):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


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

    attempts = _tts_attempts(script_text, voice)
    last_error = None

    for i, (text, use_voice) in enumerate(attempts, 1):
        if i > 1:
            logger.warning(
                f"[TTS] Thử lại lần {i}/{len(attempts)} — giọng={use_voice}, "
                f"{'đã bỏ dấu câu cuối' if text != script_text.strip() else 'nguyên văn'}"
            )
        try:
            # edge-tts is async — use asyncio.run() (Python 3.10+)
            # Falls back to nest_asyncio for Gradio / Jupyter environments
            try:
                asyncio.run(_synthesize_async(text, use_voice, rate, output_path))
            except RuntimeError:
                # Already inside a running event loop (Gradio/Jupyter)
                import nest_asyncio  # type: ignore
                nest_asyncio.apply()
                loop = asyncio.get_event_loop()
                loop.run_until_complete(_synthesize_async(text, use_voice, rate, output_path))
        except Exception as exc:
            # _synthesize_async mở file TRƯỚC khi stream, nên lỗi giữa chừng
            # luôn để lại file 0 byte — phải dọn, nếu không nó trôi xuống ffmpeg.
            last_error = exc
            logger.warning(f"[TTS] Lần thử {i} lỗi: {type(exc).__name__}: {str(exc)[:120]}")
            _discard(output_path)
            continue

        # edge-tts có thể "thành công" mà không trả về byte audio nào
        if _audio_is_usable(output_path):
            if i > 1:
                logger.info(f"[TTS] ✓ Thành công ở lần thử {i} (giọng={use_voice})")
            break
        logger.warning(f"[TTS] Lần thử {i} trả về audio rỗng — bỏ và thử phương án khác.")
        _discard(output_path)
    else:
        raise RuntimeError(
            f"TTS thất bại sau {len(attempts)} lần thử cho đoạn text "
            f"{script_text.strip()[:60]!r} (giọng gốc: {voice})."
            + (f" Lỗi cuối: {type(last_error).__name__}: {last_error}" if last_error else
               " Dịch vụ trả về audio rỗng ở mọi phương án.")
        )

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

def create_silent_mp3(output_path: str, duration: float = 0.5) -> str:
    """
    Tạo MP3 im lặng dài `duration` giây.

    Dùng khi một đoạn lời đọc thất bại nhưng vẫn cần giữ đúng nhịp thời gian của
    dòng thời gian hình ảnh — thay vì bỏ hẳn đoạn audio làm tiếng lệch khỏi hình.
    """
    _create_silent_mp3(output_path, duration)
    return output_path


def _create_silent_mp3(output_path: str, duration: float = 0.5) -> None:
    """
    Tạo một file MP3 im lặng khi text bị rỗng để tránh lỗi FFmpeg.

    Nếu không tạo được thì RAISE — tuyệt đối không ghi file 0 byte, vì file rỗng
    sẽ đi tiếp xuống pipeline và chết ở một bước ffmpeg xa hơn với lỗi khó hiểu.
    """
    import subprocess
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(duration), "-q:a", "9", "-acodec", "libmp3lame", output_path
        ], capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        raise RuntimeError(f"[TTS] Không tạo được file MP3 im lặng: {stderr[-500:]}") from e
    except FileNotFoundError as e:
        raise RuntimeError("[TTS] Không tìm thấy ffmpeg trong PATH khi tạo MP3 im lặng.") from e

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"[TTS] File MP3 im lặng rỗng hoặc không tồn tại: {output_path}")

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
