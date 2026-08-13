"""
fix_emoji.py — Chỉ thay emoji trong các file pipeline của dự án.
Chạy từ: d:\\ADS\\pipeline
"""

import pathlib

# Chỉ xử lý các file trong pipeline (loại trừ .venv và các thư mục hệ thống)
PIPELINE_FILES = [
    "core/config.py",
    "core/ffmpeg_utils.py",
    "core/router.py",
    "core/subtitle_gen.py",
    "core/tts_engine.py",
    "modes/auto/ai_analyzer.py",
    "modes/auto/auto_pipeline.py",
    "modes/auto/scraper.py",
    "modes/manual/manual_pipeline.py",
    "modes/manual/pacing_analyzer.py",
    "modes/manual/prompt_interpreter.py",
    "app.py",
    "main.py",
    "smoke_test.py",
]

# Map emoji cụ thể → ASCII (chỉ emoji trong logger calls)
REPLACEMENTS = {
    "\U0001f3ac": "[VIDEO]",   # 🎬
    "\U0001f3a8": "[COLOR]",   # 🎨
    "\U0001f517": "[LINK]",    # 🔗
    "\U0001f4dd": "[SUB]",     # 📝
    "\U0001f9f9": "[CLEAN]",   # 🧹
    "\U0001f916": "[AI]",      # 🤖
    "\U0001f4ca": "[STATS]",   # 📊
    "\U0001f3a4": "[TTS]",     # 🎤
    "\u2705":     "[OK]",      # ✅
    "\u274c":     "[ERR]",     # ❌
    "\u2714":     "[v]",       # ✔
}

base = pathlib.Path(__file__).parent
changed = 0

for rel in PIPELINE_FILES:
    f = base / rel
    if not f.exists():
        print(f"  [skip] not found: {rel}")
        continue
    text = f.read_text(encoding="utf-8", errors="replace")
    new = text
    for emoji, asc in REPLACEMENTS.items():
        new = new.replace(emoji, asc)
    if new != text:
        f.write_text(new, encoding="utf-8")
        print(f"  [fixed] {rel}")
        changed += 1
    else:
        print(f"  [clean] {rel}")

print(f"\nDone: {changed} pipeline file(s) updated.")
