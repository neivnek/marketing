"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: main.py — CLI Entry Point
====================================================================

Usage Examples
--------------
# Mode 1: Auto-Autonomous
python main.py --mode auto \
    --product-image "d:/ADS/gel.jpg" \
    --keyword "hair gel cambodia" \
    --output "d:/ADS/output"

# Mode 2: Manual Override
python main.py --mode manual \
    --product-image "d:/ADS/gel.jpg" \
    --ref-video "d:/ADS/ref_ad.mp4" \
    --script "ផលិតផលល្អបំផុត។ ទទួលដឹកជញ្ជូនឥតគិតថ្លៃ!" \
    --prompt "warm cinematic slow zoom" \
    --output "d:/ADS/output"
====================================================================
"""

import argparse
import logging
import os
import sys

# ── Logging setup ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Hybrid Zero-Cost Khmer Ad Video Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Global arguments ──────────────────────────────────────────
    parser.add_argument(
        "--mode",
        choices=["auto", "manual", "news_auto", "pro_editor", "news_ads", "news_pro", "dub_only", "full_remix", "polish"],
        required=True,
        help="Workflow mode: 'auto', 'manual', 'news_auto', 'pro_editor', 'news_ads', 'news_pro', 'dub_only', 'full_remix', 'polish'.",
    )
    parser.add_argument(
        "--product-image",
        default="",
        metavar="PATH",
        help="Path to product image file (required for auto/manual).",
    )
    parser.add_argument(
        "--output",
        default="output",
        metavar="DIR",
        help="Output directory for final MP4. Default: ./output",
    )
    parser.add_argument(
        "--tts-voice",
        default="km-KH-SreymomNeural",
        choices=["km-KH-SreymomNeural", "km-KH-PisethNeural"],
        help="TTS voice. Default: km-KH-SreymomNeural (female).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity. Default: INFO.",
    )

    # ── Mode 1 arguments ─────────────────────────────────────────
    auto_grp = parser.add_argument_group("Mode 1: Auto-Autonomous")
    auto_grp.add_argument(
        "--keyword",
        metavar="TEXT",
        help="Category keyword for Meta Ads Library search (e.g., 'shampoo cambodia').",
    )

    # ── Mode 2 arguments ─────────────────────────────────────────
    manual_grp = parser.add_argument_group("Mode 2: Manual Override")
    manual_grp.add_argument(
        "--ref-video",
        metavar="PATH",
        help="Path to reference video for pacing/scene cut extraction.",
    )
    manual_grp.add_argument(
        "--script",
        metavar="TEXT",
        help="Khmer voiceover script text.",
    )
    manual_grp.add_argument(
        "--prompt",
        metavar="TEXT",
        help="Motion style prompt (e.g., 'warm cinematic slow zoom').",
    )

    # ── Mode 5 arguments ─────────────────────────────────────────
    news_grp = parser.add_argument_group("Mode 5: News Auto Video")
    news_grp.add_argument(
        "--json-input",
        metavar="JSON_OR_PATH",
        help="JSON string payload or path to JSON script file.",
    )
    news_grp.add_argument(
        "--channel-name",
        default="",
        metavar="NAME",
        help="Channel name for watermark overlay.",
    )
    news_grp.add_argument(
        "--quality",
        default="1080p",
        choices=["720p", "1080p", "4k"],
        help="Output resolution quality (720p/1080p/4k). Default: 1080p",
    )

    # ── Mode: Dub Only ─────────────────────────────────────────
    dub_only_grp = parser.add_argument_group("Mode: Dub Only")
    dub_only_grp.add_argument(
        "--dub-only-source",
        metavar="PATH",
        help="Path to source video.",
    )
    dub_only_grp.add_argument(
        "--dub-only-script",
        default="",
        metavar="TEXT",
        help="Script text for dubbing.",
    )
    dub_only_grp.add_argument(
        "--dub-only-burn-subtitle",
        action="store_true",
        help="Burn subtitle on the video.",
    )

    # ── Mode: Full Remix ────────────────────────────────────────
    full_remix_grp = parser.add_argument_group("Mode: Full Remix")
    full_remix_grp.add_argument(
        "--full-remix-source",
        metavar="PATH",
        help="Path to source video.",
    )
    full_remix_grp.add_argument(
        "--full-remix-mask-style",
        default="box",
        choices=["box", "blur", "branded_title_frame", "none"],
        help="Text mask style.",
    )
    full_remix_grp.add_argument(
        "--full-remix-create-remix",
        action="store_true",
        help="Output a 2nd re-cut remix version of the video.",
    )

    # ── Mode: Polish ────────────────────────────────────────────
    polish_grp = parser.add_argument_group("Mode: Polish")
    polish_grp.add_argument(
        "--polish-source",
        metavar="PATH",
        help="Path to source video.",
    )
    polish_grp.add_argument(
        "--polish-add-price",
        action="store_true",
        help="Add price badge.",
    )
    polish_grp.add_argument(
        "--polish-add-social",
        action="store_true",
        help="Add social proof.",
    )
    polish_grp.add_argument(
        "--polish-hooks",
        type=int,
        default=0,
        help="Number of hook variants.",
    )
    polish_grp.add_argument(
        "--polish-watermark",
        default="",
        metavar="TEXT",
        help="Watermark text.",
    )

    # ── Mode 7 arguments ─────────────────────────────────────────
    pro_grp = parser.add_argument_group("Mode 7: Pro Editor")
    pro_grp.add_argument(
        "--product-name",
        default="",
        metavar="TEXT",
        help="Product display name.",
    )
    pro_grp.add_argument(
        "--price",
        default="",
        metavar="TEXT",
        help="Price string (e.g., '15000 KHR').",
    )
    pro_grp.add_argument(
        "--benefits",
        default="",
        metavar="TEXT",
        help="Comma-separated list of key benefits.",
    )
    pro_grp.add_argument(
        "--pain-points",
        default="",
        metavar="TEXT",
        help="Comma-separated list of audience pain points.",
    )
    pro_grp.add_argument(
        "--hook-variants",
        type=int,
        default=3,
        help="Number of hook variants to generate (min 2). Default: 3",
    )
    pro_grp.add_argument(
        "--allow-scraped-footage",
        action="store_true",
        help="Allow using footage from scraped Meta Ads.",
    )
    pro_grp.add_argument(
        "--caption-style",
        default="classic_box",
        choices=["classic_box", "outline_bold", "karaoke_highlight", "minimal_clean"],
        help="Subtitle preset style. Default: classic_box",
    )
    pro_grp.add_argument(
        "--skip-product-research",
        action="store_true",
        help="Skip AI product research (Steps 0a-0d). Use --benefits and --pain-points directly.",
    )
    pro_grp.add_argument(
        "--force-refresh-research",
        action="store_true",
        help="Ignore 30-day cache and re-run full product research.",
    )

    # ── Mode 8 arguments ─────────────────────────────────────────
    news_ads_grp = parser.add_argument_group("Mode 8: News Ads")
    news_ads_grp.add_argument(
        "--source-type",
        default="product",
        choices=["topic", "article", "product"],
        help="Source material type for news ad. Default: product",
    )
    news_ads_grp.add_argument(
        "--source-content",
        default="",
        metavar="TEXT",
        help="Topic, article text/URL, or product description.",
    )
    news_ads_grp.add_argument(
        "--format-style",
        default="news_style_ad",
        choices=["pure_news", "news_style_ad", "direct_ad"],
        help="Ad style format. Default: news_style_ad",
    )

    # ── Mode 9 arguments ─────────────────────────────────────────
    news_pro_grp = parser.add_argument_group("Mode 9: News Pro")
    news_pro_grp.add_argument(
        "--step",
        choices=["analyze-image", "render-from-script"],
        help="Step for Mode 9.",
    )
    news_pro_grp.add_argument(
        "--output-prompt",
        metavar="PATH",
        help="File path to save the JSON output (analyze-image step).",
    )
    news_pro_grp.add_argument(
        "--script-file",
        metavar="PATH",
        help="File path to the JSON script generated by the user (render-from-script step).",
    )

    return parser


def main():
    parser = build_parser()
    args   = parser.parse_args()

    # Update log level
    logging.getLogger().setLevel(args.log_level)

    # ── Import after logging is configured ───────────────────────
    from core.config import WorkflowMode, load_config
    from core.router import (
        PipelineInputs,
        AutoInputs,
        ManualInputs,
        NewsAutoInputs,
        run_pipeline,
    )
    from core.config import ProEditorInputs, NewsAdsInputs, DubOnlyInputs, PolishInputs
    # Note: DubRemixInputs is reused for Full Remix in router

    cfg = load_config()
    cfg.constraints.tts_voice = args.tts_voice

    # ── Build inputs ──────────────────────────────────────────────
    if args.mode == "auto":
        if not args.keyword:
            parser.error("--keyword is required for mode 'auto'.")
        if not args.product_image:
            parser.error("--product-image is required for mode 'auto'.")
        inputs = PipelineInputs(
            mode=WorkflowMode.AUTO_AUTONOMOUS,
            product_image=args.product_image,
            auto=AutoInputs(category_keyword=args.keyword),
            output_dir=args.output,
        )

    elif args.mode == "manual":
        if not args.product_image:
            parser.error("--product-image is required for mode 'manual'.")
        missing = []
        if not args.ref_video: missing.append("--ref-video")
        if not args.script:    missing.append("--script")
        if not args.prompt:    missing.append("--prompt")
        if missing:
            parser.error(f"Manual mode requires: {', '.join(missing)}")

        inputs = PipelineInputs(
            mode=WorkflowMode.MANUAL_OVERRIDE,
            product_image=args.product_image,
            manual=ManualInputs(
                ref_video_path=args.ref_video,
                script=args.script,
                prompt=args.prompt,
            ),
            output_dir=args.output,
        )

    elif args.mode == "news_auto":
        if not args.json_input:
            parser.error("--json-input is required for mode 'news_auto'.")
        inputs = PipelineInputs(
            mode=WorkflowMode.NEWS_AUTO,
            product_image=args.product_image,
            news_auto=NewsAutoInputs(
                json_payload=args.json_input,
                channel_name=args.channel_name,
                output_quality=args.quality,
                tts_voice=args.tts_voice,
            ),
            output_dir=args.output,
        )

    elif args.mode == "dub_only":
        if not args.dub_only_source:
            parser.error("--dub-only-source is required for mode 'dub_only'.")
        inputs = PipelineInputs(
            mode=WorkflowMode.DUB_ONLY,
            product_image=args.product_image,
            dub_only=DubOnlyInputs(
                source_video_path=args.dub_only_source,
                script_text=args.dub_only_script,
                voice=args.tts_voice,
                burn_subtitle=args.dub_only_burn_subtitle,
            ),
            output_dir=args.output,
        )

    elif args.mode == "full_remix":
        if not args.full_remix_source:
            parser.error("--full-remix-source is required for mode 'full_remix'.")
        from core.router import FullRemixInputs
        inputs = PipelineInputs(
            mode=WorkflowMode.FULL_REMIX,
            product_image=args.product_image,
            full_remix=FullRemixInputs(
                source_video=args.full_remix_source,
                script=args.script if hasattr(args, 'script') and args.script else "",
                mask_style=args.full_remix_mask_style,
                create_remix=args.full_remix_create_remix,
                tts_voice=args.tts_voice,
            ),
            output_dir=args.output,
        )

    elif args.mode == "polish":
        if not args.polish_source:
            parser.error("--polish-source is required for mode 'polish'.")
        inputs = PipelineInputs(
            mode=WorkflowMode.POLISH,
            product_image=args.product_image,
            polish=PolishInputs(
                source_video_path=args.polish_source,
                add_price_badge=args.polish_add_price,
                price=args.price if hasattr(args, 'price') else "",
                add_social_proof=args.polish_add_social,
                hook_variants=args.polish_hooks,
                watermark_text=args.polish_watermark,
            ),
            output_dir=args.output,
        )

    elif args.mode == "pro_editor":
        if not args.product_image:
            parser.error("--product-image is required for mode 'pro_editor'.")
        if not args.product_name:
            parser.error("--product-name is required for mode 'pro_editor'.")
        
        inputs = PipelineInputs(
            mode=WorkflowMode.PRO_EDITOR,
            product_image=args.product_image,
            pro_editor=ProEditorInputs(
                product_image=args.product_image,
                product_name=args.product_name,
                price=args.price,
                key_benefits=[b.strip() for b in args.benefits.split(",") if b.strip()],
                pain_points=[p.strip() for p in args.pain_points.split(",") if p.strip()],
                reference_video_path=args.ref_video if args.ref_video else "",
                num_hook_variants=args.hook_variants,
                allow_scraped_footage=args.allow_scraped_footage,
                output_quality=args.quality if hasattr(args, 'quality') else "1080p",
                tts_voice=args.tts_voice,
                caption_style=args.caption_style,
                skip_product_research=args.skip_product_research,
                force_refresh_research=args.force_refresh_research,
            ),
            output_dir=args.output,
        )

    elif args.mode == "news_ads":
        if args.source_type == "product" and not args.product_name and not args.product_image:
            parser.error("--product-name or --product-image is required for news_ads with source_type='product'.")
        
        inputs = PipelineInputs(
            mode=WorkflowMode.NEWS_ADS,
            product_image=args.product_image,
            news_ads=NewsAdsInputs(
                source_type=args.source_type,
                source_content=args.source_content,
                product_name=args.product_name,
                product_image=args.product_image,
                price=args.price,
                key_benefits=[b.strip() for b in args.benefits.split(",") if b.strip()],
                pain_points=[p.strip() for p in args.pain_points.split(",") if p.strip()],
                format_style=args.format_style,
                channel_name=args.channel_name,
                target_duration_sec=90,
                target_language="khmer",
                num_hook_variants=args.hook_variants,
                output_quality=args.quality if hasattr(args, 'quality') else "1080p",
                tts_voice=args.tts_voice,
            ),
            output_dir=args.output,
        )

    elif args.mode == "news_pro":
        if not args.step:
            parser.error("--step is required for mode 'news_pro'.")
        
        script_json_str = ""
        if args.step == "render-from-script":
            if not args.script_file or not os.path.isfile(args.script_file):
                parser.error("--script-file is required and must exist for step 'render-from-script'.")
            with open(args.script_file, "r", encoding="utf-8") as f:
                script_json_str = f.read()
        
        inputs = PipelineInputs(
            mode=WorkflowMode.NEWS_PRO,
            product_image=args.product_image,
            news_pro=NewsProInputs(
                step=args.step,
                product_image=args.product_image,
                product_name=args.product_name if hasattr(args, "product_name") else "",
                target_duration_sec=90,
                num_hook_variants=args.hook_variants if hasattr(args, "hook_variants") else 3,
                script_json=script_json_str,
                channel_name=args.channel_name if hasattr(args, "channel_name") else "KHMER NEWS DAILY",
                output_quality=args.quality if hasattr(args, 'quality') else "1080p",
                tts_voice=args.tts_voice,
            ),
            output_dir=args.output,
        )
        if args.step == "analyze-image":
            inputs.news_pro.output_prompt = args.output_prompt

    # ── Run ───────────────────────────────────────────────────────
    try:
        output_path = run_pipeline(inputs, cfg)
        print(f"\n{'═'*60}")
        print(f"  OUTPUT: {output_path}")
        print(f"{'═'*60}\n")
        return 0
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
