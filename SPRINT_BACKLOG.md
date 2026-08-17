# 🗂️ SPRINT BACKLOG — Hybrid Zero-Cost Video Pipeline

> Danh sách lỗi đang mở (10 mục), đã xác minh bằng chạy thật. Hai mục P0 đã đóng ở `d013c95`. Mỗi mục ghi rõ: triệu chứng đo được,
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
| **P1** | 5 | Ra file nhưng nội dung sai, không dùng để chạy quảng cáo được |
| **P2** | 4 | Mất tính năng hoặc giảm chất lượng, không chặn |
| **SEC** | 1 | Bảo mật |

**Đề xuất thứ tự làm:** `VID-05` (tính năng bán hàng chính đang vô nghĩa)
→ nhóm lệch tiếng/hình `VID-03` + `VID-04` + `VID-06` (cùng một họ, nên sửa chung một lượt)
→ `VID-07` → `SCR-01` → phần còn lại.

---

## P1 — Ra file nhưng nội dung sai

### VID-03 · `dub_only` cắt cụt đuôi video

**Triệu chứng.** Video nguồn 8.00s → file xuất ra **6.42s**, mất 1.58s cuối.

```
dub_only_raw_tts.mp3        3.24s   (lời đọc gốc)
dub_only_adjusted_tts.mp3   6.48s   (đã kéo giãn hết cỡ)
dub_only_muxed.mp4          6.42s   ← video bị cắt theo audio
```

**Nguyên nhân gốc.** `adjust_audio_speed` kẹp `atempo` trong khoảng `[0.5, 2.0]`, nên lời đọc 3.24s
chỉ kéo được tới 6.48s chứ không tới 8s. Sau đó lệnh mux dùng `-shortest` nên cắt video theo audio.
Lời đọc càng ngắn so với video thì mất càng nhiều.

**Vị trí.** `core/ffmpeg_utils.py::adjust_audio_speed` (kẹp tỉ lệ) ·
`modes/dub_only/dub_only_pipeline.py` (`-shortest` trong `cmd_merge`)

**Hướng sửa.** Không cắt video theo audio. Khi audio ngắn hơn: đệm im lặng cho đủ độ dài video
(`apad` / `-af apad`) và bỏ `-shortest`, hoặc chỉ dùng `-shortest` khi audio dài hơn video.

**Nghiệm thu.** Video ra luôn bằng đúng độ dài video nguồn (sai số < 0.1s) với lời đọc dài, ngắn và
rất ngắn.

---

### VID-04 · `polish`: audio dài hơn video 9 giây, cuối video đứng hình

**Triệu chứng.** File khai 19.98s nhưng luồng video chỉ có 11.00s:

```
src_hook1_polished.mp4:  video=11.00s   audio=19.98s   container=19.98s
```

Trích khung hình từ giây 11 trở đi: không có gì. Người xem thấy video đứng hình 9 giây cuối.

**Nguyên nhân gốc.** Bước nối hook + video đã polish không đồng bộ độ dài 2 luồng — audio được nối
dài hơn phần hình.

**Vị trí.** `modes/polish/polish_pipeline.py` (bước ghép hook) · `core/concat_helper.py`

**Hướng sửa.** Sau khi nối, cắt hoặc đệm để hai luồng khớp nhau; thêm một bước kiểm tra cuối
(`ffprobe` so `video.duration` với `audio.duration`, lệch quá ngưỡng thì sửa hoặc báo lỗi).

**Nghiệm thu.** Mọi file xuất ra có `|video.duration − audio.duration| < 0.2s`.

---

### VID-05 · `polish`: các bản hook A/B giống hệt nhau

**Triệu chứng.** Xuất 2 bản hook, so vân tay MD5 khung hình tại 0.5s / 1.5s / 2.5s / 5s / 10s —
**trùng khớp toàn bộ**. Ngay cả clip hook thô trước khi ghép cũng giống nhau:

```
hook_1_text.mp4  frame@1.5s = d13263d12a
hook_2_text.mp4  frame@1.5s = d13263d12a   ← giống hệt
```

Hai file cuối cùng dung lượng bằng nhau chính xác (596.306 byte).

**Nguyên nhân gốc.** Chưa xác định — cần xem `hook_variant_generator` nhận được gì: nhiều khả năng
mọi biến thể đều rơi về cùng một câu hook mặc định khi không có dữ liệu hook riêng cho từng bản.

**Vị trí.** `modes/pro_editor/hook_variant_generator.py::generate_hook_clips` ·
`modes/polish/polish_pipeline.py` (chỗ truyền danh sách hook)

**Ảnh hưởng.** Đây là tính năng bán hàng chính của hệ thống ("sinh 3–5 bản hook khác nhau để A/B
test"). Hiện tại nó xuất ra N bản sao y hệt → chạy quảng cáo A/B không có ý nghĩa thống kê.

**Nghiệm thu.** Với `hook_variants=3`, ba file khác nhau về nội dung hook (khác vân tay khung hình
trong khoảng thời gian của hook), và log in ra 3 câu hook khác nhau.

---

### VID-06 · `full_remix`: hơn 5 giây cuối im lặng

**Triệu chứng.** Video 8.00s, audio chỉ 2.83s — không cắt hình (tốt hơn `VID-03`) nhưng phần cuối
không có tiếng.

```
src_main.mp4:  video=8.000000   audio=2.832000
[FR.1] ✓ New TTS audio: 2.8s  (video: 8.0s)
```

**Nguyên nhân gốc.** Cùng họ với `VID-03`: kịch bản ngắn hơn video và không có bước đệm/kéo giãn cho
khớp.

**Vị trí.** `modes/full_remix/audio_replace.py`

**Hướng sửa.** Dùng chung giải pháp với `VID-03` — đệm im lặng tới hết video, hoặc lặp/kéo nhạc nền
lấp phần trống nếu có nhạc.

**Nghiệm thu.** Không có đoạn im lặng > 1s ở cuối video khi kịch bản ngắn.

---

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
| `d013c95` | **VID-02** — TTS có thang retry (nguyên văn → bỏ dấu câu cuối → đổi giọng cùng ngôn ngữ), kiểm tra audio khác rỗng và đọc được thời lượng, dọn file hỏng giữa các lần thử.<br>**VID-01** — `news_auto` thay đoạn TTS hỏng bằng im lặng đúng độ dài thay vì đẩy file 0 byte vào concat; báo lỗi rõ ràng khi mọi đoạn đều hỏng. Kiểm chứng: câu gây lỗi giờ thành công ở lần thử 2 (14.976 byte), `news_auto` xuất MP4 2.8MB với hình 7.40s / tiếng 7.35s |

## Những phần đã kiểm và chạy tốt

Để khỏi mất công test lại:

- **Cào video**: Meta Ads Library (tải được ad thật 21.6MB), YouTube Shorts qua yt-dlp, Pexels,
  Pixabay, chuỗi fallback của `broll_aggregator` (trả 2 clip 1080×1920).
- **Xử lý video**: Ken Burns, chuẩn hoá CFR, nối clip, phụ đề ASS + hardsub (Việt và Khmer), xoá
  logo, lọc UGC, overlay giá, chuẩn hoá âm lượng — tất cả xuất file 1080×1920 hợp lệ.
- **Hạ tầng**: Gemini, Groq, YouTube Data API, edge-tts (trừ trường hợp `VID-02`), toàn bộ 53 module
  import sạch, giao diện Web trả HTTP 200 và không có lỗi JS.
