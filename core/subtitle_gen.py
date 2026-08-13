"""
====================================================================
  Hybrid Zero-Cost Video Pipeline
  File: core/subtitle_gen.py — ASS Subtitle Generator (Khmer)
====================================================================
"""

import logging
import os
import textwrap
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Addendum 4: Caption Style Presets
CAPTION_PRESETS = {
    "classic_box": {
        "BorderStyle": 3,
        "BackColour": "&H90000000",
        "PrimaryColour": "&H00FFFFFF",
        "SecondaryColour": "&H000000FF",
        "OutlineColour": "&H00000000",
        "Bold": 1,
        "FontSize": 52,
        "Outline": 2.5,
        "Shadow": 1,
    },
    "outline_bold": {
        "BorderStyle": 1,
        "BackColour": "&H80000000",
        "PrimaryColour": "&H00FFFFFF",
        "SecondaryColour": "&H000000FF",
        "OutlineColour": "&H00000000",
        "Bold": 1,
        "FontSize": 52,
        "Outline": 4.0,
        "Shadow": 1.5,
    },
    "karaoke_highlight": {
        "BorderStyle": 1,
        "BackColour": "&H80000000",
        "PrimaryColour": "&H00FFFFFF",
        "SecondaryColour": "&H0000D7FF",
        "OutlineColour": "&H00000000",
        "Bold": 1,
        "FontSize": 52,
        "Outline": 3.0,
        "Shadow": 1.5,
    },
    "minimal_clean": {
        "BorderStyle": 1,
        "BackColour": "&H80000000",
        "PrimaryColour": "&H00FFFFFF",
        "SecondaryColour": "&H000000FF",
        "OutlineColour": "&H00000000",
        "Bold": 0,
        "FontSize": 42,
        "Outline": 1.5,
        "Shadow": 2.0,
    },
}

_ASS_HEADER_TEMPLATE = """\
[Script Info]
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Khmer,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},{bold},0,0,0,100,100,0,0,{border_style},{outline_width:.1f},{shadow},{alignment},30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert float seconds -> ASS timestamp H:MM:SS.cc"""
    if seconds < 0:
        seconds = 0.0
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _split_into_lines(text: str, max_chars: int = 32) -> str:
    raw_lines = text.replace("។", "។\n").replace("॥", "॥\n").split("\n")
    result = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        if len(line) > max_chars:
            wrapped = textwrap.wrap(line, width=max_chars, break_long_words=True)
            result.extend(wrapped)
        else:
            result.append(line)
    return r"\N".join(result)


def generate_ass_file(
    script_text:     str,
    timestamps:      list[float],
    output_path:     str,
    preset_name:     str = "classic_box",
    word_timestamps: Optional[list[dict]] = None,
    font_name:       str = "Hanuman",
    alignment:       int = 2,
    margin_v:        int = 140,
    res_x:           int = 1080,
    res_y:           int = 1920,
) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Validate preset
    if preset_name not in CAPTION_PRESETS:
        logger.warning(f"[SubtitleGen] Preset '{preset_name}' unknown. Using 'classic_box'.")
        preset_name = "classic_box"

    # Rule 22: Enforce true WordBoundary availability for karaoke_highlight
    has_word_ts = (
        word_timestamps is not None
        and len(word_timestamps) > 0
        and any(w.get("type") == "WordBoundary" for w in word_timestamps)
    )
    if preset_name == "karaoke_highlight" and not has_word_ts:
        logger.warning(
            "[SubtitleGen] Rule 22: 'karaoke_highlight' requested but no true WordBoundary "
            "timestamps available. Automatically falling back to 'classic_box'."
        )
        preset_name = "classic_box"

    preset = CAPTION_PRESETS[preset_name]

    # Build Header
    header = _ASS_HEADER_TEMPLATE.format(
        res_x=res_x,
        res_y=res_y,
        font_name=font_name,
        font_size=preset.get("FontSize", 52),
        primary_color=preset.get("PrimaryColour", "&H00FFFFFF"),
        secondary_color=preset.get("SecondaryColour", "&H000000FF"),
        outline_color=preset.get("OutlineColour", "&H00000000"),
        back_color=preset.get("BackColour", "&H80000000"),
        bold=preset.get("Bold", 0),
        border_style=preset.get("BorderStyle", 1),
        outline_width=preset.get("Outline", 2.5),
        shadow=preset.get("Shadow", 1),
        alignment=alignment,
        margin_v=margin_v,
    )

    dialogue_lines = []

    if preset_name == "karaoke_highlight" and has_word_ts:
        # ── Karaoke Highlight Logic (Rule 23) ──
        words = [w for w in word_timestamps if w.get("type") == "WordBoundary"]
        
        # Group words into lines of max 5 words
        line_chunks = []
        chunk = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 5:
                line_chunks.append(chunk)
                chunk = []
        if chunk:
            line_chunks.append(chunk)
        
        for chk in line_chunks:
            line_start = chk[0]["start"]
            line_end   = chk[-1]["end"]
            
            # Format text with \k tags
            karaoke_text = ""
            for i, w in enumerate(chk):
                if i < len(chk) - 1:
                    dur_sec = chk[i+1]["start"] - w["start"]
                else:
                    dur_sec = w["duration"]
                
                if dur_sec < 0: dur_sec = 0
                dur_cs = int(round(dur_sec * 100))
                # Add word and a space
                karaoke_text += f"{{\\k{dur_cs}}}{w['text']} "
            
            t_start = _seconds_to_ass_time(line_start)
            t_end   = _seconds_to_ass_time(line_end + 0.1)  # small pad
            dialogue_lines.append(
                f"Dialogue: 0,{t_start},{t_end},Khmer,,0,0,0,,{karaoke_text.strip()}"
            )
    else:
        # ── Classic Cut-point Logic ──
        sorted_ts = sorted(set([0.0] + [t for t in timestamps if t > 0]))
        if len(sorted_ts) < 2:
            sorted_ts = [0.0, 5.0]

        cue_windows = [
            (sorted_ts[i], sorted_ts[i + 1])
            for i in range(len(sorted_ts) - 1)
        ]
        sentences = [s.strip() for s in script_text.replace("។", "។|").split("|") if s.strip()]

        if len(sentences) >= len(cue_windows):
            chunks = sentences[: len(cue_windows) - 1]
            chunks.append(" ".join(sentences[len(cue_windows) - 1 :]))
        elif len(sentences) == 0:
            chunks = [""] * len(cue_windows)
        else:
            chunks = []
            for i in range(len(cue_windows)):
                chunks.append(sentences[i % len(sentences)])

        for (start, end), text in zip(cue_windows, chunks):
            safe_text = _split_into_lines(text)
            t_start   = _seconds_to_ass_time(start)
            t_end     = _seconds_to_ass_time(end)
            dialogue_lines.append(
                f"Dialogue: 0,{t_start},{t_end},Khmer,,0,0,0,,{safe_text}"
            )

    ass_content = header + "\n".join(dialogue_lines) + "\n"
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)

    logger.info(f"📄  ASS subtitle generated: {output_path}  (Style: {preset_name})")
    return output_path


def ensure_caption_style_previews(
    font_name: str = "Hanuman",
    output_dir: str = "assets/caption_style_previews",
    force_rebuild: bool = False
) -> list[str]:
    """
    Generate static thumbnail PNGs for the UI gallery (Rule 24).
    Only rebuilds if files are missing or force_rebuild is True.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    
    sample_text = "សួស្តី! នេះជាវីដេអូគំរូ។"
    
    for preset_name in CAPTION_PRESETS.keys():
        out_path = os.path.join(output_dir, f"{preset_name}.png")
        generated_files.append(out_path)
        
        if not force_rebuild and os.path.exists(out_path):
            continue
            
        logger.info(f"[SubtitleGen] Generating preview for {preset_name}...")
        ass_path = os.path.join(output_dir, f"temp_{preset_name}.ass")
        
        # For karaoke, we manually inject colors to simulate the \k effect dynamically
        if preset_name == "karaoke_highlight":
            preset = CAPTION_PRESETS[preset_name]
            sc = preset["SecondaryColour"]
            pc = preset["PrimaryColour"]
            # First word in Secondary (highlighted), rest in Primary
            styled_text = f"{{\\c{sc}&}}សួស្តី! {{\\c{pc}&}}នេះជាវីដេអូគំរូ។"
        else:
            styled_text = sample_text
            
        header = _ASS_HEADER_TEMPLATE.format(
            res_x=540,
            res_y=960,
            font_name=font_name,
            font_size=CAPTION_PRESETS[preset_name].get("FontSize", 52) * 0.5, # scale down
            primary_color=CAPTION_PRESETS[preset_name].get("PrimaryColour", "&H00FFFFFF"),
            secondary_color=CAPTION_PRESETS[preset_name].get("SecondaryColour", "&H000000FF"),
            outline_color=CAPTION_PRESETS[preset_name].get("OutlineColour", "&H00000000"),
            back_color=CAPTION_PRESETS[preset_name].get("BackColour", "&H80000000"),
            bold=CAPTION_PRESETS[preset_name].get("Bold", 0),
            border_style=CAPTION_PRESETS[preset_name].get("BorderStyle", 1),
            outline_width=CAPTION_PRESETS[preset_name].get("Outline", 2.5) * 0.5,
            shadow=CAPTION_PRESETS[preset_name].get("Shadow", 1) * 0.5,
            alignment=2,
            margin_v=70,
        )
        ass_content = header + f"Dialogue: 0,0:00:00.00,0:00:05.00,Khmer,,0,0,0,,{styled_text}\n"
        
        with open(ass_path, "w", encoding="utf-8-sig") as f:
            f.write(ass_content)
            
        # Draw on dark background using ffmpeg
        fontsdir = os.path.abspath("assets/fonts").replace("\\", "/").replace(":", "\\:")
        ass_path_ff = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=0x1e1e2e:s=540x960:d=1",
            "-vf", f"subtitles='{ass_path_ff}':fontsdir='{fontsdir}'",
            "-vframes", "1",
            out_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"[SubtitleGen] Preview render failed for {preset_name}: {e.stderr.decode()}")
        
        if os.path.exists(ass_path):
            os.remove(ass_path)
            
    return generated_files


def generate_subtitles(
    input_video: str,
    audio_path: str,
    output_video: str,
    style: str = "classic_box",
    font_name: str = "Hanuman",
) -> Optional[str]:
    """
    Alias đơn giản hóa cho video_assembly_engine và scene_machine_engine.
    Tự động:
      1. Sinh file .ass từ audio (ước lượng thời lượng).
      2. Burn phụ đề vào video bằng FFmpeg.

    Parameters
    ----------
    input_video : str
        Video đầu vào (chưa có phụ đề).
    audio_path : str
        File audio MP3 (dùng để ước lượng thời lượng phân cảnh).
    output_video : str
        Đường dẫn video đầu ra đã có phụ đề.
    style : str
        Tên preset subtitle (classic_box, outline_bold, karaoke_highlight, minimal_clean).
    font_name : str
        Tên font chữ (mặc định Hanuman cho Khmer).

    Returns
    -------
    str hoặc None
        Đường dẫn video output nếu thành công, None nếu lỗi.
    """
    try:
        from mutagen.mp3 import MP3
        duration = MP3(audio_path).info.length if os.path.isfile(audio_path) else 10.0
    except Exception:
        duration = 10.0

    # Sinh file ASS tạm
    ass_path = str(Path(output_video).with_suffix(".ass"))
    try:
        generate_ass_file(
            script_text="",
            timestamps=[duration],
            output_path=ass_path,
            preset_name=style if style in CAPTION_PRESETS else "classic_box",
            font_name=font_name,
        )
    except Exception as e:
        logger.warning(f"[SubtitleGen] Không tạo được ASS: {e}")
        # Fallback: copy input thẳng ra output
        import shutil
        shutil.copy(input_video, output_video)
        return output_video

    # Burn subtitle
    fonts_dir = os.path.abspath("assets/fonts")
    ass_abs = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")
    fonts_abs = fonts_dir.replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y", "-i", input_video,
        "-vf", f"subtitles='{ass_abs}':fontsdir='{fonts_abs}'",
        "-c:a", "copy", output_video,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.isfile(output_video):
            logger.info(f"[SubtitleGen] Đã burn subtitle: {output_video}")
            return output_video
        else:
            logger.error(f"[SubtitleGen] FFmpeg lỗi: {result.stderr[-200:]}")
            import shutil
            shutil.copy(input_video, output_video)
            return output_video
    except Exception as e:
        logger.error(f"[SubtitleGen] Lỗi burn: {e}")
        import shutil
        shutil.copy(input_video, output_video)
        return output_video
    finally:
        if os.path.isfile(ass_path):
            os.remove(ass_path)
