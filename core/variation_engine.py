"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/variation_engine.py — Per-Shot Visual Variation Engine
====================================================================

Tránh "creative fatigue" khi xuất nhiều biến thể quảng cáo:
mỗi hook variant nhận một visual treatment khác nhau (zoom, LUT,
grain) nhưng reproducible qua seed = hook_id.

Profiles:
  subtle   — minimal treatment, gần với footage gốc
  ugc      — warm tone + handheld grain (giả phone camera)
  clean    — cool blue-white, sharp (brand clean aesthetic)
  dynamic  — high-contrast + heavy grain (aggressive energy)

Integration point: Bước 3 trong ultimate_ad_pipeline.py,
  sau resolve_shot_assets(), trước mux audio.
"""

import logging
import os
import random
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Variation Profiles
# ──────────────────────────────────────────────

VARIATION_PROFILES: dict[str, dict] = {
    "subtle": {
        "zoom_delta": 0.03,
        "grain":      6,
        "saturation": 0.96,
        "contrast":   1.02,
        "brightness": -0.005,
        "eq_extra":   "",               # no LUT-style eq
        "shake":      0,
    },
    "ugc": {
        "zoom_delta": 0.05,
        "grain":      12,
        "saturation": 0.88,
        "contrast":   1.04,
        "brightness": -0.015,
        "eq_extra":   "curves=red='0/0 0.5/0.55 1/1':green='0/0 0.5/0.50 1/1'",  # warm
        "shake":      8,
    },
    "clean": {
        "zoom_delta": 0.02,
        "grain":      3,
        "saturation": 1.05,
        "contrast":   1.06,
        "brightness": 0.01,
        "eq_extra":   "curves=blue='0/0 0.5/0.55 1/1'",  # cool
        "shake":      0,
    },
    "dynamic": {
        "zoom_delta": 0.07,
        "grain":      16,
        "saturation": 0.82,
        "contrast":   1.12,
        "brightness": -0.02,
        "eq_extra":   "curves=all='0/0 0.3/0.25 0.7/0.8 1/1'",  # S-curve contrast
        "shake":      12,
    },
}

# Deterministic mapping: hook_id (int) → profile
# hook 0 → ugc, hook 1 → clean, hook 2 → dynamic, hook 3+ → cycle
_PROFILE_CYCLE = ["ugc", "clean", "dynamic", "subtle"]


def profile_for_hook(hook_index: int) -> str:
    """Return the variation profile name for a given hook index (0-based)."""
    return _PROFILE_CYCLE[hook_index % len(_PROFILE_CYCLE)]


# ──────────────────────────────────────────────
# Filter Builder
# ──────────────────────────────────────────────

def _build_variation_filter(
    profile_name: str,
    out_w: int = 1080,
    out_h: int = 1920,
    seed: int = 0,
) -> str:
    """
    Build FFmpeg -vf filter string for a given variation profile.

    Parameters
    ----------
    profile_name : Key in VARIATION_PROFILES.
    out_w / out_h: Output resolution.
    seed         : Random seed for reproducible shake offsets.

    Returns
    -------
    str — FFmpeg filter chain string.
    """
    p = VARIATION_PROFILES.get(profile_name, VARIATION_PROFILES["ugc"])

    rng = random.Random(seed)

    parts = []

    # Step 1: Ensure correct resolution
    parts.append(f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h}")

    # Step 2: Handheld shake (only if shake > 0)
    shake = p["shake"]
    if shake > 0:
        margin = shake * 2
        crop_w = out_w - margin
        crop_h = out_h - margin
        freq_x = round(rng.uniform(0.4, 0.9), 3)
        freq_y = round(rng.uniform(0.3, 0.7), 3)
        phase_x = round(rng.uniform(0, 3.14), 3)
        phase_y = round(rng.uniform(0, 3.14), 3)
        amp = shake // 2
        x_expr = f"(iw-{crop_w})/2+{amp}*sin({freq_x}*t+{phase_x})"
        y_expr = f"(ih-{crop_h})/2+{amp}*sin({freq_y}*t+{phase_y})"
        parts.append(f"crop={crop_w}:{crop_h}:'{x_expr}':'{y_expr}'")
        parts.append(f"scale={out_w}:{out_h}:flags=lanczos")

    # Step 3: Color grade (eq)
    eq_str = (
        f"eq=saturation={p['saturation']}"
        f":contrast={p['contrast']}"
        f":brightness={p['brightness']}"
    )
    parts.append(eq_str)

    # Step 4: LUT-style curves (if any)
    if p.get("eq_extra"):
        parts.append(p["eq_extra"])

    # Step 5: Film grain
    grain = p["grain"]
    if grain > 0:
        parts.append(f"noise=alls={grain}:allf=t+u")

    # Step 6: Vignette (subtle always)
    parts.append("vignette=PI*0.10")

    # Step 7: SAR
    parts.append("setsar=1")

    return ",".join(parts)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def apply_shot_variation(
    clip_path:    str,
    output_path:  str,
    profile:      str = "ugc",
    seed:         int = 0,
    out_w:        int = 1080,
    out_h:        int = 1920,
    crf:          int = 23,
) -> str:
    """
    Apply a variation profile to a video clip.

    Uses a seed derived from hook_id so the same hook always gets the
    same visual treatment — making A/B analysis meaningful (differences
    come from hooks, not random visual noise).

    Parameters
    ----------
    clip_path   : Input video path.
    output_path : Output video path.
    profile     : Profile key from VARIATION_PROFILES.
    seed        : Integer seed for reproducible randomness (use hook_id).
    out_w/out_h : Output resolution.
    crf         : H.264 quality factor.

    Returns
    -------
    str — output_path on success.
    """
    if profile not in VARIATION_PROFILES:
        logger.warning(f"[VariationEngine] Unknown profile '{profile}', falling back to 'ugc'.")
        profile = "ugc"

    os.makedirs(str(Path(output_path).parent), exist_ok=True)

    vf = _build_variation_filter(profile, out_w=out_w, out_h=out_h, seed=seed)

    cmd = [
        "ffmpeg", "-y",
        "-i", clip_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", str(crf),
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"[VariationEngine] FFmpeg failed (profile={profile}, seed={seed}):\n"
            f"{result.stderr[-500:]}"
        )

    logger.info(f"[VariationEngine] profile={profile} seed={seed} → {Path(output_path).name}")
    return output_path


def apply_variation_batch(
    clip_path:    str,
    num_variants: int,
    output_dir:   str,
    stem:         str = "var",
    out_w:        int = 1080,
    out_h:        int = 1920,
) -> list[str]:
    """
    Apply one variation per hook index to the same clip, returning a list of
    output paths ordered by hook index.

    Useful when the body video is the same but each hook gets a unique look.

    Parameters
    ----------
    clip_path    : Input video path.
    num_variants : Number of variants to create.
    output_dir   : Directory for output files.
    stem         : Base name prefix (e.g. "product_slug").

    Returns
    -------
    list[str] — Paths to variant clips, ordered by hook index.
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for idx in range(num_variants):
        profile = profile_for_hook(idx)
        out_path = os.path.join(output_dir, f"{stem}_var{idx:02d}_{profile}.mp4")
        try:
            apply_shot_variation(
                clip_path=clip_path,
                output_path=out_path,
                profile=profile,
                seed=idx,
                out_w=out_w,
                out_h=out_h,
            )
            results.append(out_path)
        except Exception as exc:
            logger.warning(f"[VariationEngine] Variant {idx} failed: {exc}. Using original.")
            results.append(clip_path)  # fallback to unmodified

    return results
