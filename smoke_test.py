"""
Quick import smoke test — run from d:\ADS\pipeline\
python smoke_test.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

errors = []

print("Testing core imports...")
try:
    from core.config import WorkflowMode, load_config, GlobalConstraints, APIConfig
    cfg = load_config()
    assert cfg.constraints.output_width == 1080
    assert cfg.constraints.output_height == 1920
    assert cfg.constraints.tts_voice == "km-KH-SreymomNeural"
    print("  ✓ core.config")
except Exception as e:
    errors.append(f"core.config: {e}")
    print(f"  ✗ core.config: {e}")

try:
    from core.router import PipelineInputs, AutoInputs, ManualInputs, validate_inputs
    print("  ✓ core.router")
except Exception as e:
    errors.append(f"core.router: {e}")
    print(f"  ✗ core.router: {e}")

try:
    from core.tts_engine import synthesize_khmer, get_audio_duration
    print("  ✓ core.tts_engine")
except Exception as e:
    errors.append(f"core.tts_engine: {e}")
    print(f"  ✗ core.tts_engine: {e}")

try:
    from core.subtitle_gen import generate_ass_file, _seconds_to_ass_time
    assert _seconds_to_ass_time(65.25) == "0:01:05.25"
    print("  ✓ core.subtitle_gen")
except Exception as e:
    errors.append(f"core.subtitle_gen: {e}")
    print(f"  ✗ core.subtitle_gen: {e}")

try:
    from core.ffmpeg_utils import check_ffmpeg, cleanup_temp, get_video_duration
    check_ffmpeg()
    print("  ✓ core.ffmpeg_utils  (ffmpeg found in PATH)")
except Exception as e:
    errors.append(f"core.ffmpeg_utils: {e}")
    print(f"  ✗ core.ffmpeg_utils: {e}")

try:
    from core.broll_aggregator import fetch_broll_clips
    from core.prosody_mapper import get_prosody
    from core.social_proof_overlay import render_rating_stars
    from core.music_library import mix_background_music
    print("  ✓ core Mode 7 utilities (broll, prosody, overlay, music)")
except Exception as e:
    errors.append(f"core Mode 7 utilities: {e}")
    print(f"  ✗ core Mode 7 utilities: {e}")

print("\nTesting mode imports...")
try:
    from modes.auto.scraper import download_video, _build_search_url
    url = _build_search_url("hair gel cambodia")
    assert "facebook.com" in url
    print("  ✓ modes.auto.scraper")
except Exception as e:
    errors.append(f"modes.auto.scraper: {e}")
    print(f"  ✗ modes.auto.scraper: {e}")

try:
    from modes.auto.ai_analyzer import analyze_video_with_gemini
    print("  ✓ modes.auto.ai_analyzer")
except Exception as e:
    errors.append(f"modes.auto.ai_analyzer: {e}")
    print(f"  ✗ modes.auto.ai_analyzer: {e}")

try:
    from modes.manual.pacing_analyzer import extract_scene_timestamps, get_video_info
    print("  ✓ modes.manual.pacing_analyzer")
except Exception as e:
    errors.append(f"modes.manual.pacing_analyzer: {e}")
    print(f"  ✗ modes.manual.pacing_analyzer: {e}")

try:
    from modes.manual.prompt_interpreter import parse_motion_style
    style = parse_motion_style("warm cinematic slow zoom")
    assert style.zoom_speed == "slow"
    assert style.color_filter != ""
    style2 = parse_motion_style("vibrant fast right")
    assert style2.zoom_speed == "fast"
    print("  ✓ modes.manual.prompt_interpreter")
    print(f"       warm+slow -> zoom_end={style.zoom_end}, preset={style.color_preset}")
    print(f"       vibrant+fast+right -> zoom_end={style2.zoom_end}, pan={style2.pan_directions[0]}")
except Exception as e:
    errors.append(f"modes.manual.prompt_interpreter: {e}")
    print(f"  ✗ modes.manual.prompt_interpreter: {e}")

try:
    from modes.auto.auto_pipeline import run_auto_pipeline
    from modes.manual.manual_pipeline import run_manual_pipeline
    from modes.news_auto.news_auto_pipeline import run_news_auto_pipeline
    from modes.dub_only.dub_only_pipeline import run_dub_only_pipeline
    from modes.full_remix.full_remix_pipeline import run_full_remix_pipeline
    from modes.polish.polish_pipeline import run_polish_pipeline
    from modes.pro_editor.pro_editor_pipeline import run_pro_editor_pipeline
    from modes.pro_editor.creative_director import generate_creative_script
    from modes.pro_editor.shotlist_planner import build_shotlist
    from modes.pro_editor.hook_variant_generator import generate_hook_clips
    print("  ✓ pipeline orchestrators (auto, manual, news_auto, dub_only, full_remix, polish, pro_editor)")
except Exception as e:
    errors.append(f"pipeline orchestrators: {e}")
    print(f"  ✗ pipeline orchestrators: {e}")

# ── Summary ──────────────────────────────────────────────────────
print("\n" + "═"*50)
if errors:
    print(f"[ERR]  {len(errors)} import error(s):")
    for e in errors:
        print(f"    • {e}")
    sys.exit(1)
else:
    print("[OK]  All imports OK! Pipeline is ready to run.")
    print("    Next step: copy .env.example -> .env and add your GEMINI_API_KEY")
    sys.exit(0)
