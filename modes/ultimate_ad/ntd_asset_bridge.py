"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: modes/ultimate_ad/ntd_asset_bridge.py — NTD-Labs Asset Bridge
====================================================================

Resolves visual assets for each shot from two sources, in priority order:

  1. NTD-Labs export folder (AI-generated images/videos, upscaled to 4K)
     Naming convention (REQUIRED):
       {segment_id:03d}_{visual_hint_slug}.{ext}
       e.g.:  003_product_close_up.mp4
              005_happy_customer_face.jpg
     Match is strict regex-only — no fuzzy matching.
     Miss → immediate Pexels fallback.

  2. Pexels / Pixabay stock footage (via core/broll_aggregator.py)
     Used when NTD-Labs asset is absent or NTD dir is not specified.

Logs the naming convention reminder every run so the user knows
what filename format is expected for NTD-Labs exports.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Naming convention regex ─────────────────────────────────────────
# Matches: 003_product_close_up.mp4  or  005_happy_face.jpg  etc.
_NTD_FILENAME_RE = re.compile(
    r"^(\d{3})_([a-z0-9_]+)\.(mp4|mov|jpg|jpeg|png|webm)$",
    re.IGNORECASE,
)

_SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".webm"}
_SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


# ──────────────────────────────────────────────
# NTD-Labs Directory Scanner
# ──────────────────────────────────────────────

def _scan_ntd_dir(ntd_dir: str) -> dict[int, str]:
    """
    Scan the NTD-Labs export directory and build a mapping:
      {segment_id (int): absolute_file_path}

    Only files matching the naming convention are indexed.
    Logs a warning for non-conforming files.

    Returns
    -------
    dict[int, str] — segment_id → file path.
    """
    if not ntd_dir or not os.path.isdir(ntd_dir):
        return {}

    index: dict[int, str] = {}
    skipped = []

    for fname in os.listdir(ntd_dir):
        m = _NTD_FILENAME_RE.match(fname)
        if m:
            seg_id = int(m.group(1))
            full_path = os.path.join(ntd_dir, fname)
            # If multiple files for same segment_id, prefer video over image
            if seg_id in index:
                existing_ext = Path(index[seg_id]).suffix.lower()
                new_ext      = Path(full_path).suffix.lower()
                if existing_ext in _SUPPORTED_VIDEO_EXTS and new_ext in _SUPPORTED_IMAGE_EXTS:
                    continue  # keep existing video
            index[seg_id] = full_path
        else:
            skipped.append(fname)

    if skipped:
        logger.debug(
            f"[NTD-Bridge] {len(skipped)} file(s) skipped (non-conforming names): "
            f"{skipped[:5]}{'...' if len(skipped) > 5 else ''}"
        )

    logger.info(
        f"[NTD-Bridge] Scanned {ntd_dir}: {len(index)} asset(s) matched "
        f"out of {len(os.listdir(ntd_dir))} files."
    )
    return index


def _log_convention_reminder(ntd_dir: str) -> None:
    """Log the naming convention so the user knows the expected format."""
    logger.info(
        "[NTD-Bridge] ══════════════════════════════════════════════════════\n"
        "[NTD-Bridge] NTD-Labs Asset Naming Convention (REQUIRED):\n"
        "[NTD-Bridge]   {segment_id:03d}_{visual_hint_slug}.{ext}\n"
        "[NTD-Bridge]   Examples:\n"
        "[NTD-Bridge]     001_product_hero_shot.mp4\n"
        "[NTD-Bridge]     003_happy_customer_face.jpg\n"
        "[NTD-Bridge]     005_before_after_comparison.mp4\n"
        "[NTD-Bridge]   ⚠ Files not matching this pattern are IGNORED.\n"
        f"[NTD-Bridge]   Target folder: {ntd_dir or '(not set)'}\n"
        "[NTD-Bridge] ══════════════════════════════════════════════════════"
    )


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def resolve_shot_assets(
    segment_id:         int,
    visual_hint:        str,
    duration_sec:       float,
    ntd_dir:            str,
    ntd_index:          Optional[dict] = None,   # pre-scanned index (pass for performance)
    pexels_api_key:     str = "",
    pixabay_api_key:    str = "",
    temp_dir:           str = "temp",
    n_clips:            int = 1,
) -> list[str]:
    """
    Resolve the best visual asset(s) for a shot, with NTD-Labs as priority source.

    Priority:
      1. NTD-Labs indexed file for this segment_id (exact ID match)
      2. Pexels/Pixabay stock fetch using visual_hint as English search query

    Parameters
    ----------
    segment_id      : Shot segment ID (integer, 1-based or 0-based — matches filename prefix).
    visual_hint     : English description for stock footage fallback search.
    duration_sec    : Desired clip duration (for stock fetch).
    ntd_dir         : Path to NTD-Labs exports folder.
    ntd_index       : Pre-built NTD index from build_ntd_index() — pass to avoid re-scan.
    pexels_api_key  : Pexels API key for fallback.
    pixabay_api_key : Pixabay API key for fallback.
    temp_dir        : Temp directory for downloaded clips.
    n_clips         : Max number of clips to return.

    Returns
    -------
    list[str] — List of local file paths (may be empty if both sources fail).
    """
    from core.broll_aggregator import fetch_broll_clips

    # Build index if not pre-provided
    if ntd_index is None and ntd_dir:
        ntd_index = _scan_ntd_dir(ntd_dir)
    elif ntd_index is None:
        ntd_index = {}

    # ── Priority 1: NTD-Labs ──────────────────────────────────────
    ntd_asset = ntd_index.get(segment_id)
    if ntd_asset and os.path.isfile(ntd_asset):
        logger.info(f"[NTD-Bridge] Seg {segment_id:03d} → NTD-Labs asset: {Path(ntd_asset).name}")
        return [ntd_asset]

    # ── Priority 2: Pexels / Pixabay fallback ────────────────────
    logger.info(
        f"[NTD-Bridge] Seg {segment_id:03d} → No NTD asset match; "
        f"fetching stock via Pexels (query='{visual_hint[:40]}')"
    )
    try:
        clips = fetch_broll_clips(
            query_keywords=visual_hint,
            product_category="ultimate_ad",
            duration_sec=duration_sec,
            pexels_api_key=pexels_api_key,
            pixabay_api_key=pixabay_api_key,
            temp_dir=temp_dir,
            n_clips=n_clips,
        )
        return [c.local_path for c in clips if c.local_path and os.path.isfile(c.local_path)]
    except Exception as exc:
        logger.warning(f"[NTD-Bridge] Pexels fallback failed for seg {segment_id}: {exc}")
        return []


def build_ntd_index(ntd_dir: str) -> dict[int, str]:
    """
    Pre-build the NTD-Labs asset index for a render session.
    Call once at pipeline start and pass the result to resolve_shot_assets().

    Also logs the naming convention reminder.
    """
    _log_convention_reminder(ntd_dir)
    return _scan_ntd_dir(ntd_dir)
