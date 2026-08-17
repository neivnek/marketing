# 🗂️ SPRINT BACKLOG — Hybrid Zero-Cost Video Pipeline

> Danh sách lỗi đang mở (6 mục), đã xác minh bằng chạy thật. Hai mục P0 đã đóng ở `d013c95`, `VID-05` ở `6af6e93`, `VID-03`/`VID-04`/`VID-06` ở `33ea93d`. Mỗi mục ghi rõ: triệu chứng đo được,
> nguyên nhân gốc, vị trí trong code, cách tái hiện, hướng sửa và điều kiện nghiệm thu.

| | |
|---|---|
| **Branch** | `fix/gemini-pool-and-playwright` |
| **Mốc code** | `538e50a` |
| **Ngày kiểm thử** | 2026-08-14 |
| **Môi trường** | Docker `python:3.11-slim` + FFmpeg 7.1.5 + Gradio 6.24, key thật trong `.env`, mạng thật |
| **Cách kiểm thử** | Chạy trực tiếp từng module và từng pipeline, đo kết quả bằng `ffprobe` và so vân tay khung hình |

## Tổng quan

| Mức | Còn mở | Nghĩa là |
|---|---|---|
| **P0** | 0 | ~~Chặn sử dụng~~ — đã đóng cả 2 ở `d013c95` |
| **P1** | 1 | Ra file nhưng nội dung sai, không dùng để chạy quảng cáo được |
| **P2** | 4 | Mất tính năng hoặc giảm chất lượng, không chặn |
| **SEC** | 1 | Bảo mật |

**Đề xuất thứ tự làm:** `VID-07` (bỏ map audio cứng) → `SCR-01` (quyết định số phận TikTok scraper)
→ `SEC-01` (rotate key) → chạy kiểm thử 4 pipeline nặng AI còn lại.

---

## P1 — Ra file nhưng nội dung sai

### VID-07 · Ghép B-roll trong bản remix luôn thất bại

**Triệu chứng.**

```
_mux_broll_with_audio stderr: set value '1:a:0' for option 'map': Invalid argument
Error parsing options for output file .../remix0_broll_02_merged.mp4
Segment 2 → B-roll mux failed, using original
```

**Nguyên nhân gốc.** Code map cứng `-map 1:a:0` trong khi clip B-roll (tải từ Pexels/Pixabay/YouTube)
thường **không có luồng audio**. Lỗi bị nuốt rồi lặng lẽ "dùng bản gốc", nên B-roll không bao giờ
được chèn vào bản remix.

**Vị trí.** `modes/full_remix/remix_cut_generator.py::_mux_broll_with_audio`

**Hướng sửa.** Kiểm tra clip có luồng audio không (`ffprobe`) rồi mới map; hoặc dùng
`-map 1:a:0?` (dấu `?` = optional) để ffmpeg bỏ qua khi không có.

**Nghiệm thu.** Chạy remix với B-roll không tiếng: log không còn dòng "B-roll mux failed", và bản
remix thực sự có cảnh B-roll.

---

## P2 — Mất tính năng / giảm chất lượng

### SCR-01 · Scraper TikTok chết hoàn toàn (cả 3 đường)

**Triệu chứng.** `scrape_tiktok_clips("kem chong nang", n=1)` → 0 clip. Chạy tay từng URL:

| Đường | Lỗi |
|---|---|
| `tiktok.com/search?q=...` | `ERROR: Unsupported URL` — yt-dlp **chưa bao giờ** hỗ trợ URL tìm kiếm TikTok |
| `tiktok.com/tag/...` | `ERROR: No working app info is available` |
| Video lẻ | `Your IP address is blocked from accessing this post` (IP datacenter bị chặn) |

**Vị trí.** `core/tiktok_scraper.py::_build_search_urls` (URL search sai từ lúc viết) ·
`_ytdlp_list_urls`

**Ảnh hưởng.** Không chặn — nằm trong `try/except` nên chuỗi fallback đi tiếp, chỉ tốn ~4s mỗi lần
gọi và ghi cảnh báo. Nhưng đây là một nguồn B-roll được quảng cáo trong tài liệu mà thực tế không
hoạt động.

**Hướng sửa.** Chọn một: (a) gỡ khỏi chuỗi fallback và khỏi tài liệu; (b) chuyển sang tìm bằng
YouTube Shorts (`ytsearch` đang chạy tốt) rồi lọc theo tỉ lệ khung hình dọc; (c) giữ nhưng chỉ bật
khi người dùng cấu hình cookie TikTok.

**Nghiệm thu.** Hoặc hàm bị gỡ sạch, hoặc trả về clip thật trong môi trường Docker.

---

### AST-01 · Kho nhạc nền rỗng nên mọi video đều không có nhạc

**Triệu chứng.** `assets/local_music/**/*.mp3` → **0 file**. `pick_track("upbeat")` trả `None`.

```
[Music] No local music tracks found. Add MP3 files to assets/local_music/calm|upbeat|urgent/.
Copying video without background music.
```

**Ảnh hưởng.** Xử lý êm (không sập), nhưng video quảng cáo không có nhạc nền — ảnh hưởng trực tiếp
tới chất lượng cảm nhận.

**Hướng sửa.** Việc của người dùng: tải nhạc no-copyright bỏ vào `calm/`, `upbeat/`, `urgent/`
(xem `assets/local_music/README_MUSIC.txt`). Về phía code: hiện cảnh báo rõ trên Web UI thay vì chỉ
log ở terminal.

---

### UI-01 · Chữ tiếng Việt mất dấu ở phần đầu giao diện

**Triệu chứng.** Dòng mô tả và các chip ở hero hiển thị *"Tao video quang cao 9:16 (1080x1920) tu
dong — Giong doc Khmer — Co phu de"*, `edge-tts Mien phi`, `Gia tien Overlay`.

**Nguyên nhân gốc.** Di chứng của script `fix_emoji.py` ngày xưa (đã xóa) từng chuyển văn bản sang
ASCII.

**Vị trí.** `app2.py` — khối `gr.HTML` dựng hero (khoảng dòng 229–240)

**Nghiệm thu.** Toàn bộ chữ tiếng Việt trên giao diện có dấu đầy đủ.

---

### OPS-01 · Model Gemini chính hay trả về phản hồi rỗng

**Triệu chứng.** Quan sát trong lúc chạy pipeline thật:

```
[API Pool] Model gemini-3.6-flash trả về phản hồi rỗng, thử model tiếp theo.
```

Ngoài ra một lần gọi Gemini đơn giản mất **15.7s**.

**Ảnh hưởng.** Không sai kết quả (pool tự lùi sang model kế tiếp) nhưng tốn thêm một vòng gọi và
thời gian cho mỗi lần sinh nội dung.

**Hướng sửa.** Theo dõi tần suất; nếu lặp lại nhiều thì đảo thứ tự `DEFAULT_MODELS` trong
`core/gemini_pool.py` để model ổn định hơn đứng trước.

---

## SEC — Bảo mật

### SEC-01 · TikTok client key nằm trong git history của repo public

**Triệu chứng.** Key TikTok cũ nằm trong `AI_SYSTEM_CONTEXT.md` ở commit gốc `729df3f`. File đã bị
xóa khi gộp tài liệu, **nhưng xóa file không xóa được khỏi lịch sử** — vẫn đọc được bằng `git log -p`.
Repo `neivnek/marketing` hiện ở chế độ **PUBLIC** và branch đã được push kèm toàn bộ history.

**Hướng sửa.** Rotate key bên TikTok for Developers (bắt buộc, không còn là phòng ngừa). Nếu muốn
xoá hẳn khỏi lịch sử thì phải `git filter-repo` rồi force push — sẽ viết lại mọi commit sau đó nên
cần thống nhất trước.

**Nghiệm thu.** Key cũ vô hiệu; `.env` mới không nằm trong git (đã có trong `.gitignore`).

---

## Chưa kiểm chứng — cần chạy tiếp

Mỗi lần chạy tốn nhiều phút vì gọi Gemini nhiều vòng, chưa đưa vào đợt test này:

- **Magic One-Click** (2 bản) — ảnh sản phẩm → video hoàn chỉnh
- **Ultimate Ad (Mode 10)** — chế độ được quảng cáo là mạnh nhất
- **Pro Editor (Mode 7)** — luồng nghiên cứu sản phẩm + PAS + A/B hook
- **Google Scene Machine** — storyboard 4 cảnh
- **URL → Multi-Variant Ads** · **Quảng Cáo Tiệm** · **Visual Search** · **Ad Spy**

Lưu ý: `VID-05` (hook trùng nhau) rất có thể cũng ảnh hưởng Pro Editor và Ultimate Ad vì cả hai
dùng chung `hook_variant_generator`.

---

## Đã đóng trong đợt vừa rồi

| Commit | Nội dung |
|---|---|
| `4b24505` | Dọn 52MB rác `.part`, gộp 8 file tài liệu còn 3, sửa font (`Hanuman.ttf` không tồn tại → Noto), thống nhất cổng 7860 |
| `2f40801` | Đưa toàn bộ 18 call site Gemini về pool, sửa Groq fallback (JSON mode, chặn multimodal, nhận diện quota), thêm Playwright vào image |
| `5fb9b39` | Sửa `adjust_audio_speed` luôn tạo output, `_create_silent_mp3` không ghi file 0 byte, dọn `.part` của stockpile, đóng SQLite khi lỗi, thư mục tạm riêng mỗi lần chạy, tắt share mặc định, nối `DUB_REMIX` vào router |
| `538e50a` | Sửa giao diện Gradio 6: thanh tab hiện đủ 9 tab đồng nhất, header bảng kịch bản không còn vỡ khi bấm, sửa `.select()` lambda |
| `33ea93d` | **VID-03 / VID-04 / VID-06** — thêm `mux_audio_to_video()` áp một quy tắc chung: hình là chuẩn, tiếng đệm `apad` rồi cắt theo hình. `dub_only` hết cắt cụt (8.00s), `full_remix` tiếng phủ hết video, `polish` hết lệch (11.00s hình / 11.02s tiếng) nhờ khớp sample rate track im lặng của hook với body |
| `6af6e93` | **VID-05** — `polish` dựng hook theo góc tiếp cận khác nhau từ dữ liệu thật (giá, lượt bán, đánh giá, thương hiệu) thay vì N bản `"🔥🔥🔥"` giống hệt; generator xoay vòng 5 preset chuyển động Ken Burns theo từng biến thể nên khác nhau cả về thị giác. Kiểm chứng: 3 bản cho ra vân tay khung hình khác nhau từng cặp |
| `d013c95` | **VID-02** — TTS có thang retry (nguyên văn → bỏ dấu câu cuối → đổi giọng cùng ngôn ngữ), kiểm tra audio khác rỗng và đọc được thời lượng, dọn file hỏng giữa các lần thử.<br>**VID-01** — `news_auto` thay đoạn TTS hỏng bằng im lặng đúng độ dài thay vì đẩy file 0 byte vào concat; báo lỗi rõ ràng khi mọi đoạn đều hỏng. Kiểm chứng: câu gây lỗi giờ thành công ở lần thử 2 (14.976 byte), `news_auto` xuất MP4 2.8MB với hình 7.40s / tiếng 7.35s |

## Những phần đã kiểm và chạy tốt

Để khỏi mất công test lại:

- **Cào video**: Meta Ads Library (tải được ad thật 21.6MB), YouTube Shorts qua yt-dlp, Pexels,
  Pixabay, chuỗi fallback của `broll_aggregator` (trả 2 clip 1080×1920).
- **Xử lý video**: Ken Burns, chuẩn hoá CFR, nối clip, phụ đề ASS + hardsub (Việt và Khmer), xoá
  logo, lọc UGC, overlay giá, chuẩn hoá âm lượng — tất cả xuất file 1080×1920 hợp lệ.
- **Hạ tầng**: Gemini, Groq, YouTube Data API, edge-tts (trừ trường hợp `VID-02`), toàn bộ 53 module
  import sạch, giao diện Web trả HTTP 200 và không có lỗi JS.
