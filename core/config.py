"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/config.py — Centralized Config & Env Loader
====================================================================
"""

import os
from enum import Enum
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────
# Workflow Mode Enum
# ──────────────────────────────────────────────

class WorkflowMode(Enum):
    AUTO_AUTONOMOUS = "auto"
    MANUAL_OVERRIDE  = "manual"
    NEWS_AUTO        = "news_auto"
    DUB_REMIX        = "dub_remix"
    PRO_EDITOR       = "pro_editor"
    NEWS_ADS         = "news_ads"
    NEWS_PRO         = "news_pro"
    DUB_ONLY         = "dub_only"
    FULL_REMIX       = "full_remix"
    POLISH           = "polish"
    ULTIMATE_AD      = "ultimate_ad"


# ──────────────────────────────────────────────
# Global Output Constraints
# ──────────────────────────────────────────────

@dataclass
class GlobalConstraints:
    language_code:   str  = "km-KH"           # BCP-47 for Khmer
    tts_voice:       str  = "km-KH-SreymomNeural"  # default female voice
    tts_rate:        str  = "+0%"             # default playback speed
    khmer_fonts:     list = field(default_factory=lambda: [
        "Hanuman", "Battambang", "Moul", "Nokora"
    ])
    output_format:   str  = "mp4"
    output_width:    int  = 1080
    output_height:   int  = 1920
    framerate:       int  = 30
    video_codec:     str  = "libx264"
    audio_codec:     str  = "aac"
    crf:             int  = 23
    duration_min:    int  = 15   # seconds
    duration_max:    int  = 90   # seconds


# ──────────────────────────────────────────────
# API Configuration (env-driven)
# ──────────────────────────────────────────────

@dataclass
class APIConfig:
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )

    def validate(self):
        if not self.gemini_api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Auto-Autonomous mode requires a Google AI Studio API key."
            )


# ──────────────────────────────────────────────
# Ken Burns Motion Config
# ──────────────────────────────────────────────

@dataclass
class KenBurnsConfig:
    zoom_start:           float = 1.0
    zoom_end:             float = 1.08
    pan_directions:       list  = field(default_factory=lambda: [
        "left", "right", "up", "down", "center"
    ])
    transition_frames:    int   = 15


# ──────────────────────────────────────────────
# Subtitle / ASS Config
# ──────────────────────────────────────────────

@dataclass
class SubtitleConfig:
    font_name:     str   = "Hanuman"
    font_size:     int   = 52
    primary_color: str   = "&H00FFFFFF"   # white
    outline_color: str   = "&H00000000"   # black
    outline_width: float = 2.5
    shadow:        int   = 1
    margin_v:      int   = 80
    alignment:     int   = 2              # bottom-center


# ──────────────────────────────────────────────
# Master Pipeline Config
# ──────────────────────────────────────────────

@dataclass
class PipelineConfig:
    constraints: GlobalConstraints = field(default_factory=GlobalConstraints)
    apis:        APIConfig         = field(default_factory=APIConfig)
    ken_burns:   KenBurnsConfig    = field(default_factory=KenBurnsConfig)
    subtitle:    SubtitleConfig    = field(default_factory=SubtitleConfig)
    output_dir:  str = "output"
    temp_dir:    str = "temp"
    assets_dir:  str = "assets"
    fonts_dir:   str = "assets/fonts"

    def ensure_dirs(self):
        """Create all required working directories."""
        for d in [self.output_dir, self.temp_dir, self.assets_dir, self.fonts_dir]:
            os.makedirs(d, exist_ok=True)


def load_config() -> PipelineConfig:
    """Load and return the master pipeline configuration."""
    return PipelineConfig()


# ──────────────────────────────────────────────
# Mode 7: Pro Editor Dataclasses
# ──────────────────────────────────────────────

@dataclass
class ProductIdentity:
    """Result of Step 0a: Gemini vision-only product identification."""
    name_guess:          str
    brand_guess:         str   = ""
    category:            str   = ""
    ocr_text:            str   = ""
    visual_description:  str   = ""
    confidence:          float = 0.0


@dataclass
class ProductResearch:
    """Result of Step 0b: Gemini grounded web research."""
    benefits:               list  = field(default_factory=list)
    usage_instructions:     str   = ""
    ingredient_highlights:  list  = field(default_factory=list)
    common_praise:          list  = field(default_factory=list)
    common_complaints:      list  = field(default_factory=list)
    suggested_pain_points:  list  = field(default_factory=list)
    source_urls:            list  = field(default_factory=list)   # grounding traceability (Rule 13)
    research_skipped:       bool  = False
    warning_message:        str   = ""


@dataclass
class VideoRef:
    """Result of Step 0c: YouTube related video reference."""
    title:          str
    video_id:       str
    channel:        str  = ""
    view_count:     int  = 0
    url:            str  = ""
    thumbnail_url:  str  = ""


@dataclass
class ProEditorInputs:
    """
    All inputs for Mode 7: Pro Editor.
    Produces N A/B test hook variant MP4 files.
    """
    product_image:           str
    product_name:            str   = ""                 # Optional: if provided, skips vision identification
    price:                   str   = ""
    key_benefits:            list  = field(default_factory=list)  # list[str]
    pain_points:             list  = field(default_factory=list)  # list[str]
    reference_video_path:    str   = ""                  # optional: for pacing analysis
    num_hook_variants:       int   = 3                   # A/B test variants (min 2)
    allow_scraped_footage:   bool  = False               # allow footage from Meta Ads scraper
    output_quality:          str   = "1080p"             # 720p | 1080p | 4k
    tts_voice:               str   = "km-KH-SreymomNeural"
    tts_rate:                str   = "+0%"
    caption_style:           str   = "classic_box"       # Addendum 4: classic_box|outline_bold|karaoke_highlight|minimal_clean
    skip_product_research:   bool  = False               # skip Steps 0a-0d, use key_benefits/pain_points directly
    force_refresh_research:  bool  = False               # ignore cache, re-run all Steps 0a-0d


# ──────────────────────────────────────────────
# Addendum 3: B-Roll, Prosody, Shotlist Dataclasses
# ──────────────────────────────────────────────

@dataclass
class BrollClip:
    """A fetched B-roll clip ready for use in the pipeline."""
    clip_id:        str
    source:         str   = "local"   # "local" | "pexels" | "pixabay"
    url:            str   = ""
    local_path:     str   = ""
    duration:       float = 0.0
    keyword_matched: str  = ""


@dataclass
class ProsodyParams:
    """TTS prosody parameters per act segment."""
    rate:           str   = "+0%"               # edge-tts rate string (e.g. "+10%")
    volume:         str   = "+0%"               # edge-tts volume string (e.g. "+5%")
    voice_variant:  str   = "km-KH-SreymomNeural"  # voice to use


@dataclass
class ShotPlan:
    """
    Shot plan unit for one segment of the video body.
    Equivalent to ShotlistItem but used as config-level type.
    """
    segment_id:         int
    act:                str   = "solution"    # problem|agitate|solution|proof|cta
    source_type:        str   = "stock"       # stock|scraped|product_image
    b_roll_keywords_en: list  = field(default_factory=list)  # English search terms
    duration_hint:      float = 5.0
    prosody:            ProsodyParams = field(default_factory=ProsodyParams)


@dataclass
class StorySegment:
    """
    Data structure for a Micro-Story Ad segment.
    """
    id:                 int
    narrative_beat:     str   = "setup"       # hook|setup|problem|turning_point|solution|proof|cta
    emotion:            str   = "neutral"     # curious|frustrated|worried|relieved|excited|confident|urgent
    voiceover_text:     str   = ""
    on_screen_text:     str   = ""
    visual_hint:        str   = ""
    camera_hint:        str   = "medium-shot"
    duration_hint_sec:  float = 4.0


# ──────────────────────────────────────────────
# Mode 8: News Ads Dataclasses
# ──────────────────────────────────────────────

@dataclass
class NewsAdsInputs:
    """Inputs exclusive to Mode 8: News Ads."""
    source_type:         str   = "product"           # "topic" | "article" | "product"
    source_content:      str   = ""                  # Topic, article text/URL, or product description
    product_name:        str   = ""
    product_image:       str   = ""
    price:               str   = ""
    key_benefits:        list  = field(default_factory=list)
    pain_points:         list  = field(default_factory=list)
    format_style:        str   = "news_style_ad"     # "pure_news" | "news_style_ad" | "direct_ad"
    channel_name:        str   = ""
    target_duration_sec: int   = 90
    target_language:     str   = "khmer"
    num_hook_variants:   int   = 3
    output_quality:      str   = "1080p"
    tts_voice:           str   = "km-KH-SreymomNeural"
    tts_rate:            str   = "+0%"
    enable_subtitles:    bool  = False
    title_style:         str   = "Khung Xanh (Mặc định)"


# ──────────────────────────────────────────────
# Mode 9: News Pro Dataclasses
# ──────────────────────────────────────────────

@dataclass
class NewsProInputs:
    """Inputs exclusive to Mode 9: News Pro."""
    step:                str   = "analyze-image"     # "analyze-image" | "render-from-script"
    product_images:      list  = field(default_factory=list)
    product_name:        str   = ""
    target_duration_sec: int   = 90
    num_hook_variants:   int   = 3
    script_json:         str   = ""
    channel_name:        str   = "KHMER NEWS DAILY"
    output_quality:      str   = "1080p"
    tts_voice:           str   = "km-KH-SreymomNeural"
    tts_rate:            str   = "+0%"
    output_prompt:       str   = ""
    enable_subtitles:    bool  = False
    title_style:         str   = "Khung Xanh (Mặc định)"
    transition_speed:    str   = "Bình thường (3.0s)"

@dataclass
class DubOnlyInputs:
    """Inputs exclusive to Mode: Dub Only."""
    source_video_path:   str
    script_text:         str   = ""
    voice:               str   = "km-KH-SreymomNeural"
    tts_rate:            str   = "+0%"
    burn_subtitle:       bool  = False

@dataclass
class PolishInputs:
    """Inputs exclusive to Mode: Polish."""
    source_video_path:   str
    add_price_badge:     bool  = False
    price:               str   = ""
    add_social_proof:    bool  = False
    rating:              float = 5.0
    sold_count:          str   = "10K+"
    hook_variants:       int   = 0
    watermark_text:      str   = ""



# ──────────────────────────────────────────────
# Mode: Ultimate Ad Dataclasses
# ──────────────────────────────────────────────

# Templates with built-in caption (skip pipeline ASS burn)
_TEMPLATES_WITH_BUILTIN_CAPTION = {
    "motion-graphics-spot",
    "split-screen",
    "revid-story",
    "listicle-top5",
    "imessage-conversation",
}


@dataclass
class UltimateAdInputs:
    """
    Inputs for ULTIMATE_AD mode.
    Combines pipeline AI scripting, NTD-Labs AI assets,
    and fb-ad-video-studio motion templates + ElevenLabs VO.
    """
    # ── Required ───────────────────────────────────────
    product_name:       str                              # Name/description of product
    target_language:    str                              # REQUIRED: "vietnamese" | "khmer" | "english"

    # ── Content Source ──────────────────────────────
    product_image:      str   = ""                       # Path to product image (optional)
    script_text:        str   = ""                       # Pre-written script (skips Gemini if provided)
    key_benefits:       list  = field(default_factory=list)
    pain_points:        list  = field(default_factory=list)
    price:              str   = ""

    # ── Template & Visual ───────────────────────────
    ad_template:        str   = "motion-graphics-spot"   # fb-ad-studio template
    ntd_assets_dir:     str   = ""                       # Folder of NTD-Labs AI assets

    # ── Subtitle Routing (Fix 1: double-burn prevention) ──
    subtitle_source:    str   = "auto"
    # "auto"         → auto-detect by template (recommended)
    # "template"     → hyperframes owns caption; skip pipeline burn_hardsub()
    # "pipeline_ass" → pipeline ASS/Hanuman burn; disable template captions

    # ── Audio / TTS ───────────────────────────────
    tts_provider:       str   = "edge-tts"             # "edge-tts" (free default) | "elevenlabs" (paid, quota-limited)
    tts_voice_el:       str   = "iP95p4xoKVk53GoZ742B"  # ElevenLabs Chris voice ID
    tts_voice_edge:     str   = "km-KH-SreymomNeural"   # edge-tts fallback voice
    tts_rate:           str   = "+0%"
    enable_sfx:         bool  = True
    master_lufs:        float = -14.0                    # EBU R128 target (-14 LUFS)

    # ── Branding & Output ───────────────────────────
    channel_name:       str   = ""
    num_hook_variants:  int   = 3
    output_quality:     str   = "1080p"

    def resolve_subtitle_source(self) -> str:
        """Resolve 'auto' subtitle_source based on ad_template."""
        if self.subtitle_source != "auto":
            return self.subtitle_source
        if self.ad_template in _TEMPLATES_WITH_BUILTIN_CAPTION:
            return "template"
        return "pipeline_ass"
