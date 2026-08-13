import os
import subprocess
import logging

logger = logging.getLogger(__name__)


def concatenate_clips(clip_paths: list, output_path: str, fps: int = 30) -> str:
    """
    Concatenate multiple video clips into one using FFmpeg concat demuxer.
    Normalizes every clip to CFR before concat to avoid desync.
    Dùng thư mục temp cố định thay vì TemporaryDirectory để tránh file bị xóa sớm.
    """
    if not clip_paths:
        raise ValueError("No clips provided for concatenation")

    # Tạo thư mục temp cố định
    norm_dir = os.path.join(os.path.dirname(output_path) or "temp", "_norm_cfr")
    os.makedirs(norm_dir, exist_ok=True)

    from core.ffmpeg_utils import normalize_segment_cfr

    normalized_paths = []
    for i, p in enumerate(clip_paths):
        if not os.path.isfile(p):
            logger.warning(f"[ConcatHelper] Bỏ qua clip không tồn tại: {p}")
            continue
        norm_p = os.path.join(norm_dir, f"norm_cfr_{i:04d}.mp4")
        try:
            normalize_segment_cfr(p, norm_p, fps=fps)
            if os.path.isfile(norm_p):
                normalized_paths.append(norm_p)
            else:
                normalized_paths.append(p)  # fallback to original
        except Exception as e:
            logger.warning(f"[ConcatHelper] normalize lỗi clip {i}: {e}. Dùng bản gốc.")
            normalized_paths.append(p)

    if not normalized_paths:
        raise ValueError("Không có clip hợp lệ để ghép!")

    # Nếu chỉ có 1 clip, copy thẳng ra
    if len(normalized_paths) == 1:
        import shutil
        shutil.copy(normalized_paths[0], output_path)
        logger.info(f"[ConcatHelper] 1 clip → copy trực tiếp: {output_path}")
        return output_path

    # Ghi concat list
    concat_list = os.path.join(norm_dir, "concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in normalized_paths:
            p_clean = os.path.abspath(p).replace("\\", "/")
            f.write(f"file '{p_clean}'\n")

    os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed:\n{result.stderr[-500:]}")

    logger.info(f"[ConcatHelper] ✓ Ghép {len(normalized_paths)} clips → {output_path}")

    # Dọn dẹp norm dir sau khi thành công
    try:
        import shutil as _sh
        _sh.rmtree(norm_dir, ignore_errors=True)
    except Exception:
        pass

    return output_path
