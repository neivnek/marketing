"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/prosody_mapper.py — TTS Prosody per Act
====================================================================

Maps a script segment's `act` label to edge-tts Communicate rate
and volume parameters.

NOTE: edge-tts `pitch` parameter is NOT stable in versions >= 6.0.3
      and is intentionally excluded. Emotional contrast is achieved
      via rate + volume variation and male/female voice switching.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prosody Table ─────────────────────────────────────────────────
# Values are percentage strings accepted by edge-tts Communicate:
#   rate   : "+X%" / "-X%"  relative to default rate
#   volume : "+X%" / "-X%"  relative to default volume

_PROSODY_TABLE: dict[str, dict[str, str]] = {
    "concerned":  {"rate": "-8%",  "volume": "+0%"},
    "urgent":     {"rate": "+15%", "volume": "+10%"},
    "confident":  {"rate": "+0%",  "volume": "+5%"},
    "upbeat":     {"rate": "+10%", "volume": "+10%"},
    "energetic":  {"rate": "+20%", "volume": "+15%"},
    # Micro-Story Ad Emotions
    "curious":    {"rate": "-5%",  "volume": "+0%"},
    "frustrated": {"rate": "+10%", "volume": "+10%"},
    "worried":    {"rate": "-10%", "volume": "-5%"},
    "relieved":   {"rate": "+0%",  "volume": "-5%"},
    "excited":    {"rate": "+15%", "volume": "+15%"},
    # Fallback for unknown act labels
    "default":    {"rate": "+0%",  "volume": "+0%"},
}

# Maps emotion → preferred voice gender (for contrast)
_EMOTION_VOICE_GENDER: dict[str, str] = {
    "concerned":  "female",
    "urgent":     "female",
    "confident":  "female",
    "upbeat":     "female",
    "energetic":  "female",
    "curious":    "female",
    "frustrated": "female",
    "worried":    "female",
    "relieved":   "female",
    "excited":    "female",
}

VOICE_FEMALE = "km-KH-SreymomNeural"
VOICE_MALE   = "km-KH-PisethNeural"


# ── Public API ────────────────────────────────────────────────────

def get_prosody(emotion: str, voiceover_text: str = "", is_hook_line: bool = False) -> dict[str, str]:
    """
    Return edge-tts Communicate kwargs for the given emotion label.

    Short-line rule: if voiceover_text has fewer than 5 words (typical hook),
    volume is forced to +10% regardless of emotion — ensures opening line cuts through.

    Parameters
    ----------
    emotion        : One of: "concerned", "urgent", "confident", "upbeat", "energetic".
    voiceover_text : The actual text to be spoken (used to detect short hook lines).
    is_hook_line   : Force short-line treatment even if text >= 5 words.

    Returns
    -------
    dict with keys "rate" and "volume" (string percentage values).
    """
    key    = emotion.lower().strip()
    prosody = dict(_PROSODY_TABLE.get(key, _PROSODY_TABLE["default"]))

    # Short-line boost (hook rule): fewer than 5 words -> volume +10%
    word_count = len(voiceover_text.strip().split()) if voiceover_text.strip() else 0
    if is_hook_line or (word_count > 0 and word_count < 5):
        prosody["volume"] = "+10%"
        logger.debug(
            f"[Prosody] Short-line boost applied (words={word_count}) "
            f"emotion={emotion!r} -> volume={prosody['volume']}"
        )

    logger.debug(f"[Prosody] emotion={emotion!r} words={word_count} -> rate={prosody['rate']}, volume={prosody['volume']}")
    return prosody


def map_prosody(emotion: str, is_hook_line: bool = False) -> dict:
    """
    Alias for get_prosody() matching the spec API:
      map_prosody(emotion, is_hook_line) -> ProsodyParams-like dict

    Returns dict with "rate", "volume", "voice_variant" keys.
    """
    params = get_prosody(emotion, is_hook_line=is_hook_line)
    gender = _EMOTION_VOICE_GENDER.get(emotion.lower(), "female")
    params["voice_variant"] = VOICE_FEMALE if gender == "female" else VOICE_MALE
    return params


def synthesize_with_prosody(
    script_text:  str,
    output_path:  str,
    emotion:      str,
    voice:        Optional[str] = None,
    base_rate:    str = "+0%",
) -> str:
    """
    Synthesize Khmer TTS with prosody tuned for the given emotion.

    Uses `edge_tts.Communicate` directly with rate + volume parameters
    derived from the prosody table.

    Parameters
    ----------
    script_text : str
        Khmer voiceover text for this segment.
    output_path : str
        Destination .mp3 path.
    emotion : str
        Emotion label: concerned | urgent | confident | upbeat | energetic.
    voice : str, optional
        Override voice; defaults to VOICE_FEMALE.

    Returns
    -------
    str — Path to the synthesized .mp3 file.
    """
    import asyncio
    import os
    import edge_tts
    from pathlib import Path

    prosody     = get_prosody(emotion, voiceover_text=script_text)
    voice       = voice or VOICE_FEMALE
    
    # Combine base_rate (e.g., "+25%") with prosody rate (e.g., "+15%")
    try:
        b_val = int(base_rate.replace("%", "").replace("+", ""))
        p_val = int(prosody["rate"].replace("%", "").replace("+", ""))
        combined_rate = b_val + p_val
        rate_val = f"+{combined_rate}%" if combined_rate >= 0 else f"{combined_rate}%"
    except Exception:
        rate_val = prosody["rate"]

    volume_val  = prosody["volume"]

    os.makedirs(str(Path(output_path).parent), exist_ok=True)
    logger.info(
        f"[Prosody-TTS] emotion={emotion!r}  rate={rate_val}  vol={volume_val}  "
        f"voice={voice}  -> {Path(output_path).name}"
    )

    async def _run():
        communicate = edge_tts.Communicate(
            text=script_text,
            voice=voice,
            rate=rate_val,
            volume=volume_val,
        )
        
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

        words_json_path = str(Path(output_path).with_suffix(".words.json"))
        try:
            import json
            with open(words_json_path, "w", encoding="utf-8") as f_json:
                json.dump(word_events, f_json, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.debug(f"[Prosody-TTS] Could not save words json: {exc}")

    try:
        asyncio.run(_run())
    except RuntimeError:
        import nest_asyncio  # type: ignore
        nest_asyncio.apply()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_run())

    if not os.path.isfile(output_path):
        raise RuntimeError(f"Prosody TTS synthesis failed — output not found: {output_path}")

    return output_path


def dominant_energy(emotions: list[str]) -> str:
    """
    Return the dominant energy level for a list of emotions.
    Used by music_library.py to pick the right background track folder.

    Mapping:
        concerned         → "calm"    (builds tension with quiet music)
        confident, upbeat → "upbeat"  (positive energy)
        urgent, energetic → "urgent"  (drives action)

    Returns "upbeat" if list is empty or unrecognised.
    """
    energy_map = {
        "concerned": "calm",
        "urgent":    "urgent",
        "confident": "upbeat",
        "upbeat":    "upbeat",
        "energetic": "urgent",
    }
    counts: dict[str, int] = {}
    for e in emotions:
        energy = energy_map.get(e.lower().strip(), "upbeat")
        counts[energy] = counts.get(energy, 0) + 1

    if not counts:
        return "upbeat"
    return max(counts, key=lambda k: counts[k])
