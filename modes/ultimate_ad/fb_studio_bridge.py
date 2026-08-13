"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/ultimate_ad/fb_studio_bridge.py
====================================================================

Bridge to fb-ad-video-studio scripts:
  - ElevenLabs TTS (Chris voice, ad-tuned settings)
  - Whisper word-level timestamps → .words.json
  - Silence cutting (BIT cut, for talking-head footage)

Includes ElevenLabsQuotaTracker:
  - Tracks character usage locally in .elevenlabs_quota.json
  - Fallback to edge-tts BEFORE hitting the free tier limit
  - Logs which TTS provider was used per video (for A/B analysis)

ElevenLabs free tier: ~10,000 chars/month.
Safety threshold: 9,500 chars (500 char buffer before limit).
One video script: ~200-400 chars on average.
"""

import asyncio
import json
import logging
import os
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# ElevenLabs Constants
# ──────────────────────────────────────────────

_EL_VOICE_CHRIS = "iP95p4xoKVk53GoZ742B"
_EL_MODEL       = "eleven_turbo_v2_5"
_EL_SETTINGS    = {
    "stability":        0.45,
    "similarity_boost": 0.78,
    "style":            0.55,
    "use_speaker_boost": True,
}
_EL_API_BASE = "https://api.elevenlabs.io/v1"

FREE_TIER_LIMIT     = 10_000   # ElevenLabs free tier
SAFETY_THRESHOLD    = 9_500    # fallback BEFORE hitting limit


# ──────────────────────────────────────────────
# ElevenLabs Quota Tracker
# ──────────────────────────────────────────────

class ElevenLabsQuotaTracker:
    """
    Tracks ElevenLabs character usage locally in a JSON file.
    Resets automatically at the start of a new calendar month.

    Usage:
        tracker = ElevenLabsQuotaTracker()
        if tracker.can_use(text):
            # call ElevenLabs
            tracker.record_usage(len(text))
        else:
            # fallback to edge-tts
    """

    QUOTA_FILE = ".elevenlabs_quota.json"

    def __init__(self, quota_file: Optional[str] = None):
        self._file = quota_file or self.QUOTA_FILE
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.isfile(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Reset if new month
                stored_month = data.get("month", "")
                current_month = datetime.now(timezone.utc).strftime("%Y-%m")
                if stored_month != current_month:
                    logger.info(
                        f"[ELQuota] New month ({current_month}). "
                        f"Resetting usage from {data.get('used', 0)} chars."
                    )
                    return {"month": current_month, "used": 0, "history": []}
                return data
            except Exception:
                pass
        return {"month": datetime.now(timezone.utc).strftime("%Y-%m"), "used": 0, "history": []}

    def _save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as exc:
            logger.debug(f"[ELQuota] Could not save quota file: {exc}")

    def can_use(self, text: str) -> bool:
        """Return True if sending this text stays under the safety threshold."""
        projected = self._data.get("used", 0) + len(text)
        if projected > SAFETY_THRESHOLD:
            logger.warning(
                f"[ELQuota] ElevenLabs quota ~exhausted: "
                f"{self._data.get('used', 0)}/{SAFETY_THRESHOLD} chars used. "
                f"Requested +{len(text)} chars would exceed threshold. "
                "Falling back to edge-tts."
            )
            return False
        return True

    def record_usage(self, chars: int, script_snippet: str = "") -> None:
        """Record usage after a successful ElevenLabs call."""
        self._data["used"] = self._data.get("used", 0) + chars
        self._data["history"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chars":     chars,
            "snippet":   script_snippet[:40],
        })
        self._save()
        logger.info(
            f"[ELQuota] Recorded {chars} chars. "
            f"Total this month: {self._data['used']}/{SAFETY_THRESHOLD}."
        )

    def get_report(self) -> dict:
        """Return a summary dict for embedding in render_report.json."""
        return {
            "provider":  "elevenlabs",
            "used_chars": self._data.get("used", 0),
            "threshold":  SAFETY_THRESHOLD,
            "remaining":  max(0, SAFETY_THRESHOLD - self._data.get("used", 0)),
            "month":      self._data.get("month", ""),
        }


# ──────────────────────────────────────────────
# ElevenLabs TTS
# ──────────────────────────────────────────────

def _call_elevenlabs(
    text:       str,
    output_path: str,
    api_key:    str,
    voice_id:   str = _EL_VOICE_CHRIS,
) -> None:
    """Make the ElevenLabs API call and save MP3 to output_path."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    payload = json.dumps({
        "text":          text,
        "model_id":      _EL_MODEL,
        "voice_settings": _EL_SETTINGS,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{_EL_API_BASE}/text-to-speech/{voice_id}",
        data=payload,
        headers={
            "xi-api-key":   api_key,
            "Content-Type": "application/json",
            "Accept":       "audio/mpeg",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        audio_bytes = resp.read()

    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    logger.info(f"[ElevenLabs] VO saved: {output_path} ({len(audio_bytes):,} bytes)")


def _call_edge_tts(
    text:        str,
    output_path: str,
    voice:       str,
    rate:        str = "+0%",
) -> None:
    """Synthesize with edge-tts (zero-cost fallback)."""
    import edge_tts

    async def _synth():
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
        word_events = []
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f_audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f_audio.write(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    word_events.append({
                        "type":  chunk["type"],
                        "text":  chunk.get("text", ""),
                        "start": chunk.get("offset", 0) / 10_000_000.0,
                        "end":   (chunk.get("offset", 0) + chunk.get("duration", 0)) / 10_000_000.0,
                        "duration": chunk.get("duration", 0) / 10_000_000.0,
                    })
        # Save word timestamps
        words_path = str(Path(output_path).with_suffix(".words.json"))
        with open(words_path, "w", encoding="utf-8") as f_json:
            json.dump(word_events, f_json, ensure_ascii=False, indent=2)
        logger.info(f"[EdgeTTS] VO saved: {output_path} ({len(word_events)} word events)")

    try:
        asyncio.run(_synth())
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(_synth())


# ──────────────────────────────────────────────
# Public TTS Entry Point
# ──────────────────────────────────────────────

def run_tts(
    text:         str,
    output_path:  str,
    voice_id_el:  str = _EL_VOICE_CHRIS,
    voice_edge:   str = "km-KH-SreymomNeural",
    tts_rate:     str = "+0%",
    tracker:      Optional[ElevenLabsQuotaTracker] = None,
) -> tuple[str, str]:
    """
    Synthesize voiceover using ElevenLabs (if quota allows) or edge-tts fallback.

    Parameters
    ----------
    text         : Script text to synthesize.
    output_path  : Destination MP3 path.
    voice_id_el  : ElevenLabs voice ID.
    voice_edge   : edge-tts voice name for fallback.
    tts_rate     : Speech rate for edge-tts (e.g., "+10%").
    tracker      : ElevenLabsQuotaTracker instance (created internally if None).

    Returns
    -------
    (output_path: str, provider_used: str)
        provider_used is "elevenlabs" or "edge-tts" — for render_report.
    """
    el_key = os.getenv("ELEVENLABS_API_KEY", "")

    if tracker is None:
        tracker = ElevenLabsQuotaTracker()

    # ── Try ElevenLabs ────────────────────────────────────────────
    if el_key and tracker.can_use(text):
        try:
            _call_elevenlabs(text=text, output_path=output_path, api_key=el_key, voice_id=voice_id_el)
            tracker.record_usage(len(text), script_snippet=text)
            # ElevenLabs doesn't auto-produce words.json — run Whisper
            run_whisper_sync(output_path)
            return output_path, "elevenlabs"
        except urllib.error.HTTPError as e:
            logger.warning(f"[FbBridge] ElevenLabs HTTP {e.code}: {e.reason}. Falling back to edge-tts.")
        except Exception as exc:
            logger.warning(f"[FbBridge] ElevenLabs failed: {exc}. Falling back to edge-tts.")

    # ── Fallback: edge-tts ────────────────────────────────────────
    if not el_key:
        logger.info("[FbBridge] No ELEVENLABS_API_KEY — using edge-tts.")
    _call_edge_tts(text=text, output_path=output_path, voice=voice_edge, rate=tts_rate)
    return output_path, "edge-tts"


# ──────────────────────────────────────────────
# Whisper Word Timestamps
# ──────────────────────────────────────────────

def run_whisper_sync(audio_path: str) -> str:
    """
    Run faster-whisper on an audio file to produce word-level timestamps.

    Output: <audio_stem>.words.json in same directory as audio_path.

    Returns
    -------
    str — Path to the .words.json file (may not exist if faster-whisper not installed).
    """
    words_path = str(Path(audio_path).with_suffix(".words.json"))

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small.en", compute_type="int8")
        segments, _ = model.transcribe(
            audio_path,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            word_timestamps=True,
        )
        words = [
            {"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for seg in segments
            for w in (seg.words or [])
        ]
        with open(words_path, "w", encoding="utf-8") as f:
            json.dump(words, f, indent=2)
        logger.info(f"[Whisper] {len(words)} word timestamps → {words_path}")
        return words_path

    except ImportError:
        logger.warning(
            "[Whisper] faster-whisper not installed. Word-level subtitle sync unavailable. "
            "Install: pip install faster-whisper"
        )
        return words_path
    except Exception as exc:
        logger.warning(f"[Whisper] Transcription failed: {exc}")
        return words_path


# ──────────────────────────────────────────────
# Silence Cutter (BIT cut for talking-head)
# ──────────────────────────────────────────────

def run_silence_cut(
    input_path:  str,
    output_path: str,
    gap:         float = 0.18,
    min_sil:     float = 0.40,
) -> str:
    """
    Trim dead air from presenter footage using faster-whisper VAD.
    Keeps 0.18s of room tone between phrases (BIT cut standard).

    Equivalent to fb-ad-video-studio/scripts/cut-silences.py.

    Parameters
    ----------
    input_path  : Raw presenter recording.
    output_path : Cut output path.
    gap         : Room tone buffer to keep between segments (seconds).
    min_sil     : Minimum silence duration to treat as a cut candidate (seconds).

    Returns
    -------
    str — output_path on success, input_path on failure (fallback to original).
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small.en", compute_type="int8")
        segs, _ = model.transcribe(
            input_path,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": int(min_sil * 1000)},
            word_timestamps=True,
        )
        spans = [(round(s.start, 3), round(s.end + gap, 3)) for s in segs]

        # Merge overlapping spans
        keep: list[tuple[float, float]] = []
        for a, b in spans:
            if keep and a <= keep[-1][1]:
                keep[-1] = (keep[-1][0], max(keep[-1][1], b))
            else:
                keep.append((a, b))

        if not keep:
            logger.warning("[SilenceCut] No speech segments detected. Returning original.")
            return input_path

        # Build FFmpeg filtergraph
        fc_parts = []
        for i, (a, b) in enumerate(keep):
            fc_parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
            fc_parts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
        cat = "".join(f"[v{i}][a{i}]" for i in range(len(keep)))
        fc_parts.append(f"{cat}concat=n={len(keep)}:v=1:a=1[outv][outa]")

        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-filter_complex", ";".join(fc_parts),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-r", "30", "-g", "30", "-keyint_min", "30",
            "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-300:])

        logger.info(f"[SilenceCut] {len(keep)} segments kept → {Path(output_path).name}")
        return output_path

    except ImportError:
        logger.warning("[SilenceCut] faster-whisper not installed. Skipping silence cut.")
        return input_path
    except Exception as exc:
        logger.warning(f"[SilenceCut] Failed: {exc}. Returning original footage.")
        return input_path
