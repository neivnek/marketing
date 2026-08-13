"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/router.py — Central Routing Engine
====================================================================
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from core.config import WorkflowMode, PipelineConfig, load_config, ProEditorInputs, NewsAdsInputs, NewsProInputs, DubOnlyInputs, PolishInputs, UltimateAdInputs

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Input Bundle Dataclasses
# ──────────────────────────────────────────────

@dataclass
class AutoInputs:
    """Inputs exclusive to Mode 1: Auto-Autonomous."""
    category_keyword: str


@dataclass
class ManualInputs:
    """Inputs exclusive to Mode 2: Manual Override."""
    ref_video_path: str
    script:         str
    prompt:         str


@dataclass
class NewsAutoInputs:
    """Inputs exclusive to Mode 5: Auto News Video."""
    json_payload: str                     # JSON string or path to JSON file
    product_price: str = ""               # Optional price tag for overlay
    output_quality: str = "1080p"         # 720p | 1080p | 4k
    tts_voice: str = "km-KH-SreymomNeural"
    tts_rate: str = "+0%"


@dataclass
class FullRemixInputs:
    """Inputs exclusive to Mode 4: Full Remix."""
    source_video: str                     # User-owned source video
    audio_mode: str = "translate"         # "translate" | "custom"
    target_language: str = "khmer"        # Output language: khmer|vietnamese|english|thai|...
    tts_voice: str = ""                   # Edge-TTS voice (empty = auto-resolved from target_language)
    script: str = ""                      # Custom script text if audio_mode == "custom"
    on_screen_text: str = ""              # Custom text to overlay on the video (optional)
    mask_style: str = "box"               # "box" | "blur" | "none"
    mask_color: str = "black"             # Color for box overlay
    create_remix: bool = True             # Output remix re-cut video(s)
    num_remixes: int = 2                  # Number of remix variants to generate (default 2)
    broll_query: str = ""                 # B-roll keyword (empty = AI auto-analyzes video)
    scrape_broll_keyword: str = ""
    music_energy: str = "upbeat"          # Background music energy: calm | upbeat | urgent
    ugc_intensity: str = "medium"         # UGC camera shake: subtle | medium | strong
    tts_rate: str = "+0%"
    style_profile_id: str = ""            # ID of saved style profile to apply (optional)


@dataclass
class PipelineInputs:
    """Full input bundle passed to the router."""
    mode:          WorkflowMode
    product_image: str                      # global — optional for dub/news
    auto:          Optional[AutoInputs]      = None
    manual:        Optional[ManualInputs]    = None
    news_auto:     Optional[NewsAutoInputs]  = None
    dub_only:      Optional[DubOnlyInputs]   = None
    full_remix:    Optional[FullRemixInputs] = None
    polish:        Optional[PolishInputs]    = None
    news_pro:      Optional[NewsProInputs]   = None
    news_ads:      Optional[NewsAdsInputs]   = None
    pro_editor:    Optional[ProEditorInputs] = None
    output_dir:    str                       = "output"
    ultimate_ad:   Optional[UltimateAdInputs] = None


# ──────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────

def validate_inputs(inputs: PipelineInputs) -> None:
    """Raise ValueError with a clear message if required fields are missing."""
    if inputs.mode in [WorkflowMode.AUTO_AUTONOMOUS, WorkflowMode.MANUAL_OVERRIDE, WorkflowMode.PRO_EDITOR]:
        if not inputs.product_image or not Path(inputs.product_image).is_file():
            raise ValueError(f"Product image not found: {inputs.product_image}")

    if inputs.mode == WorkflowMode.AUTO_AUTONOMOUS:
        if not inputs.auto or not inputs.auto.category_keyword.strip():
            raise ValueError("Auto mode requires a non-empty category_keyword.")

    elif inputs.mode == WorkflowMode.MANUAL_OVERRIDE:
        if not inputs.manual:
            raise ValueError("Manual mode requires ManualInputs to be provided.")
        if not Path(inputs.manual.ref_video_path).is_file():
            raise ValueError(
                f"Reference video not found: {inputs.manual.ref_video_path}"
            )
        if not inputs.manual.script.strip():
            raise ValueError("Manual mode requires a non-empty script.")
        if not inputs.manual.prompt.strip():
            raise ValueError("Manual mode requires a non-empty prompt.")

    elif inputs.mode == WorkflowMode.NEWS_AUTO:
        if not inputs.news_auto or not inputs.news_auto.json_payload.strip():
            raise ValueError("News Auto mode requires a non-empty json_payload.")

    elif inputs.mode == WorkflowMode.DUB_ONLY:
        if not inputs.dub_only or not Path(inputs.dub_only.source_video_path).is_file():
            raise ValueError(f"Dub Only mode requires a valid source_video path: {inputs.dub_only.source_video_path if inputs.dub_only else None}")

    elif inputs.mode == WorkflowMode.FULL_REMIX:
        if not inputs.full_remix or not Path(inputs.full_remix.source_video).is_file():
            raise ValueError(f"Full Remix mode requires a valid source_video path: {inputs.full_remix.source_video if inputs.full_remix else None}")

    elif inputs.mode == WorkflowMode.POLISH:
        if not inputs.polish or not Path(inputs.polish.source_video_path).is_file():
            raise ValueError(f"Polish mode requires a valid source_video path: {inputs.polish.source_video_path if inputs.polish else None}")

    elif inputs.mode == WorkflowMode.PRO_EDITOR:
        if not inputs.pro_editor:
            raise ValueError("Pro Editor mode requires ProEditorInputs to be provided.")
        if not inputs.pro_editor.product_name.strip() and not inputs.pro_editor.product_image:
            raise ValueError("Pro Editor mode requires a product name or image.")

    elif inputs.mode == WorkflowMode.NEWS_ADS:
        if not inputs.news_ads:
            raise ValueError("News Ads mode requires NewsAdsInputs to be provided.")
        if inputs.news_ads.source_type == "product" and not inputs.news_ads.product_name.strip() and not inputs.news_ads.product_image:
            raise ValueError("News Ads mode (product source) requires a product name or image.")

    elif inputs.mode == WorkflowMode.NEWS_PRO:
        if not inputs.news_pro:
            raise ValueError("News Pro mode requires NewsProInputs to be provided.")
        if inputs.news_pro.step == "analyze-image" and not inputs.product_image:
            raise ValueError("News Pro mode (analyze-image step) requires a product image.")
        if inputs.news_pro.step == "render-from-script" and not inputs.news_pro.script_json.strip():
            raise ValueError("News Pro mode (render-from-script step) requires script_json.")

    elif inputs.mode == WorkflowMode.ULTIMATE_AD:
        if not inputs.ultimate_ad:
            raise ValueError("Ultimate Ad mode requires UltimateAdInputs to be provided.")
        if not inputs.ultimate_ad.product_name.strip():
            raise ValueError("Ultimate Ad mode requires a non-empty product_name.")
        if not inputs.ultimate_ad.target_language.strip():
            raise ValueError(
                "Ultimate Ad mode requires target_language to be set explicitly "
                "(\"vietnamese\" | \"khmer\" | \"english\"). No default is provided."
            )
        valid_langs = {"vietnamese", "khmer", "english"}
        if inputs.ultimate_ad.target_language.lower() not in valid_langs:
            raise ValueError(
                f"target_language must be one of {valid_langs}, "
                f"got: '{inputs.ultimate_ad.target_language}'"
            )
        valid_sub = {"auto", "template", "pipeline_ass"}
        if inputs.ultimate_ad.subtitle_source not in valid_sub:
            raise ValueError(
                f"subtitle_source must be one of {valid_sub}, "
                f"got: '{inputs.ultimate_ad.subtitle_source}'"
            )


# ──────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────

def run_pipeline(inputs: PipelineInputs, cfg: Optional[PipelineConfig] = None) -> str:
    """
    Central routing function.

    Parameters
    ----------
    inputs : PipelineInputs
        All user-supplied parameters.
    cfg : PipelineConfig, optional
        Pre-loaded config (loaded fresh if not provided).

    Returns
    -------
    str
        Absolute path to the final rendered MP4 file.
    """
    if cfg is None:
        cfg = load_config()

    # Ensure working directories exist
    cfg.output_dir = inputs.output_dir
    cfg.ensure_dirs()

    # Validate all inputs before doing any heavy work
    validate_inputs(inputs)

    logger.info("═" * 60)
    logger.info("  Hybrid Zero-Cost Video Pipeline  v3.0")
    logger.info(f"  Mode  : {inputs.mode.value.upper()}")
    if inputs.product_image:
        logger.info(f"  Image : {inputs.product_image}")
    logger.info("═" * 60)

    if inputs.mode == WorkflowMode.AUTO_AUTONOMOUS:
        # Validate Gemini key is present for auto mode
        cfg.apis.validate()

        from modes.auto.auto_pipeline import run_auto_pipeline
        output_path = run_auto_pipeline(inputs, cfg)

    elif inputs.mode == WorkflowMode.MANUAL_OVERRIDE:
        from modes.manual.manual_pipeline import run_manual_pipeline
        output_path = run_manual_pipeline(inputs, cfg)

    elif inputs.mode == WorkflowMode.NEWS_AUTO:
        from modes.news_auto.news_auto_pipeline import run_news_auto_pipeline
        output_path = run_news_auto_pipeline(inputs.news_auto, cfg.output_dir, cfg.temp_dir)

    elif inputs.mode == WorkflowMode.DUB_ONLY:
        from modes.dub_only.dub_only_pipeline import run_dub_only_pipeline
        output_path = run_dub_only_pipeline(inputs.dub_only, cfg.output_dir, cfg.temp_dir)

    elif inputs.mode == WorkflowMode.FULL_REMIX:
        from modes.full_remix.full_remix_pipeline import run_full_remix_pipeline
        output_path = run_full_remix_pipeline(inputs.full_remix, cfg.output_dir, cfg.temp_dir)

    elif inputs.mode == WorkflowMode.POLISH:
        from modes.polish.polish_pipeline import run_polish_pipeline
        output_paths = run_polish_pipeline(inputs.polish, cfg.output_dir, cfg.temp_dir)
        output_path = output_paths[0] if output_paths else ""

    elif inputs.mode == WorkflowMode.PRO_EDITOR:
        from modes.pro_editor.pro_editor_pipeline import run_pro_editor_pipeline
        # Pro editor can return multiple files (one per hook), returning the first one or a summary string
        output_paths = run_pro_editor_pipeline(inputs.pro_editor, cfg.output_dir, cfg.temp_dir)
        output_path = output_paths[0] if output_paths else ""

    elif inputs.mode == WorkflowMode.NEWS_ADS:
        from modes.news_ads.news_ads_pipeline import run_news_ads_pipeline
        output_paths = run_news_ads_pipeline(inputs.news_ads, cfg.output_dir, cfg.temp_dir)
        output_path = output_paths[0] if output_paths else ""

    elif inputs.mode == WorkflowMode.NEWS_PRO:
        from modes.news_pro.news_pro_pipeline import analyze_image_and_research, render_from_script
        if inputs.news_pro.step == "analyze-image":
            res = analyze_image_and_research(inputs.product_image, cfg.apis.gemini_api_key, cfg.temp_dir, hint_name=inputs.news_pro.product_name)
            import json
            output_path = json.dumps(res, ensure_ascii=False)
            if hasattr(inputs.news_pro, "output_prompt") and getattr(inputs.news_pro, "output_prompt"):
                p = getattr(inputs.news_pro, "output_prompt")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(output_path)
                output_path = p
        elif inputs.news_pro.step == "render-from-script":
            output_paths = render_from_script(inputs.news_pro, cfg.output_dir, cfg.temp_dir)
            output_path = output_paths[0] if output_paths else ""
        else:
            raise ValueError(f"Unknown step for NEWS_PRO: {inputs.news_pro.step}")

    elif inputs.mode == WorkflowMode.ULTIMATE_AD:
        from modes.ultimate_ad.ultimate_ad_pipeline import run_ultimate_ad_pipeline
        output_paths = run_ultimate_ad_pipeline(
            inputs.ultimate_ad,
            cfg.output_dir,
            cfg.temp_dir,
        )
        output_path = output_paths[0] if output_paths else ""

    else:
        raise ValueError(f"Unknown workflow mode: {inputs.mode}")

    logger.info(f"\n[OK]  Pipeline complete -> {output_path}")
    return output_path
