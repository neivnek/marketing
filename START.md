# 📘 HƯỚNG DẪN SỬ DỤNG — Hybrid Zero-Cost Video Pipeline v3.5

Hệ thống tự động sản xuất video quảng cáo dọc 9:16 (TikTok / Facebook Reels / YouTube Shorts)
với chi phí **0 đồng**: ném ảnh sản phẩm vào → nhận về 3–5 video quảng cáo hoàn chỉnh có kịch bản
AI, B-roll, lồng tiếng, phụ đề, nhạc nền và hiệu ứng, mỗi bản một Hook khác nhau để A/B test.

> **Cách dùng file này:** copy lệnh, dán vào Terminal/PowerShell, Enter. Không cần biết lập trình.
> Tài liệu kỹ thuật dành cho lập trình viên & trợ lý AI: [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md).

---

## 🛠️ PHẦN 1: CÀI ĐẶT (chỉ làm 1 lần)

Yêu cầu: **Python 3.10+** và **FFmpeg** đã có trong PATH.

### Windows — cách dễ nhất
Nhấp đôi vào **`CAI_DAT.bat`**. Script tự kiểm tra Python, tạo `.venv` và cài thư viện.

### Windows / macOS / Linux — cài bằng lệnh

```bash
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python smoke_test.py
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python smoke_test.py
```

✅ Thấy `[OK] All imports OK!` là cài xong.

---

## 🔑 PHẦN 2: CẤU HÌNH API KEY

Copy `.env.example` thành `.env` rồi điền key vào. **Chỉ `GEMINI_API_KEY` là bắt buộc**, còn lại
thiếu vẫn chạy được (hệ thống tự lùi về hiệu ứng Ken Burns trên ảnh sản phẩm + B-roll có sẵn).

```ini
# ── BẮT BUỘC ───────────────────────────────────────────────────
GEMINI_API_KEY=       # https://aistudio.google.com/app/apikey

# ── NÊN CÓ ────────────────────────────────────────────────────
GROQ_API_KEY=         # https://console.groq.com/keys — dự phòng khi Gemini hết quota (14.400 lượt/ngày miễn phí)
PEXELS_API_KEY=       # https://www.pexels.com/api/ — B-roll chất lượng cao
PIXABAY_API_KEY=      # https://pixabay.com/api/docs/ — nguồn B-roll thay thế

# ── TÙY CHỌN ──────────────────────────────────────────────────
YOUTUBE_API_KEY=      # tìm video review sản phẩm (Pro Editor)
META_AD_ACCESS_TOKEN= # Ad Spy Facebook — xem PHẦN 6
TIKTOK_AD_ACCESS_TOKEN= # Ad Spy TikTok — xem PHẦN 6
```

> Có thể thêm nhiều key dự phòng: `GROQ_API_KEY_2`, `GROQ_API_KEY_3`… Hệ thống tự xoay vòng khi
> một key hết lượt.

---

## 🎵 PHẦN 3: THÊM NHẠC NỀN (khuyến nghị)

Hệ thống tự chọn nhạc theo cảm xúc từng đoạn. Tải nhạc miễn phí bản quyền
(https://pixabay.com/music/ hoặc YouTube Audio Library) và bỏ vào đúng thư mục:

| Thư mục | Dùng cho |
|---|---|
| `assets/local_music/calm/` | Đoạn nêu vấn đề, cảm xúc trầm |
| `assets/local_music/upbeat/` | Đoạn giới thiệu sản phẩm & bằng chứng |
| `assets/local_music/urgent/` | Đoạn kêu gọi mua hàng (CTA) |

Định dạng nhận: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`

---

## 🚀 PHẦN 4: CHẠY GIAO DIỆN WEB (cách dùng chính)

```bash
# Windows: nhấp đôi KHOI_DONG.bat, hoặc:
.venv\Scripts\Activate.ps1
python app2.py
```

```bash
# macOS / Linux
source .venv/bin/activate
python app2.py
```

Trình duyệt tự mở tại **http://localhost:7860**

Muốn đổi cổng (nếu 7860 đang bận): `PORT=7871 python app2.py`

> **Link chia sẻ công khai giờ TẮT mặc định.** Trước đây app luôn tạo public URL — ai có link
> đều dùng được, và chạy bằng API key trong `.env` của bạn. Cần bật lại thì chạy:
> `GRADIO_SHARE=1 python app2.py`

### Các tính năng trên Web UI

| Tab | Công dụng |
|---|---|
| 🌟 **Magic One-Click** | Làm tất cả trong 1 nút: ảnh sản phẩm → video hoàn chỉnh |
| 🌐 **URL → Multi-Variant Ads** | Dán link sản phẩm → tự bóc thông tin → sinh nhiều biến thể quảng cáo |
| 🏪 **Quảng Cáo Tiệm (Local Store)** | Video quảng cáo cho cửa hàng địa phương |
| 🌟 **Ultimate Ad (Mode 10)** | Chế độ mạnh nhất: 1 ảnh → 3–5 video A/B test, kịch bản PAS đầy đủ |
| **Pro Editor (Mode 7)** | Tùy chỉnh chi tiết Hook / PAS / B-roll / hiệu ứng rung UGC |
| 🎬 **Google Scene Machine** | Dựng video theo storyboard 4 cảnh chuẩn Google Marketing |
| 📦 **Stockpile AI B-Roll Curator** | Nhập từ khóa → AI cào & tuyển clip B-roll HD về kho máy |
| 🧹 **Xóa Logo Video** | Xóa logo, ID TikTok, watermark rác khỏi clip |
| 🔍 **Visual Search Engine** | Upload ảnh → tra ngược sản phẩm trong kho offline (ResNet50 + SQLite) |
| 🕵️ **Ad Spy (Meta & TikTok)** | Quét kịch bản quảng cáo đối thủ đang chạy thật |
| 🔄 **Dub Only / Remix / Full Remix** | Lồng tiếng lại, che chữ cũ, dựng lại video có sẵn |
| 📰 **News Ads / News Pro / News Auto** | Video dạng bản tin để tránh "mù quảng cáo" |
| ✨ **Polish** | Đánh bóng video đã có: watermark, giá, đánh giá 5 sao, ghép N Hook |
| 🎨 **Style Profile** | Lưu & tái dùng phong cách video ưa thích |

**Quy trình dùng Ultimate Ad:** mở tab *Quảng Cáo & Thương Mại → Ultimate Ad (Mode 10)* →
upload ảnh sản phẩm, nhập tên + giá → bấm **Tạo Video** → nhận về 3–5 file mp4.

---

## ⚡ PHẦN 5: DÒNG LỆNH CLI (cho người dùng nâng cao)

Kích hoạt môi trường trước (1 lần mỗi phiên), rồi chạy `main.py`.
CLI hỗ trợ 10 chế độ (kể cả Ultimate Ad); FB Shorts / AI B-roll chỉ có trên Web UI.

### 🟢 Auto — tự động hoàn toàn
```bash
python main.py --mode auto --product-image "gel.jpg" --keyword "hair gel cambodia" --output "output"
```

### 🔵 Manual — tự nhập kịch bản
```bash
python main.py --mode manual --product-image "gel.jpg" --ref-video "ref.mp4" \
    --script "Nội dung kịch bản..." --prompt "warm cinematic slow zoom" --output "output"
```

### 🟣 Dub Only — chỉ lồng tiếng + phụ đề
```bash
python main.py --mode dub_only --dub-only-source "video.mp4" \
    --dub-only-script "Kịch bản..." --dub-only-burn-subtitle --output "output"
```

### 🔴 Full Remix — lồng tiếng, che chữ cũ, dựng lại
```bash
python main.py --mode full_remix --full-remix-source "video.mp4" --script "Kịch bản..." \
    --full-remix-mask-style box --full-remix-create-remix --output "output"
```
Xuất ra 2 file: `*_main.mp4` và `*_remix.mp4`.

### ⚪ Polish — đánh bóng video đã có
```bash
python main.py --mode polish --polish-source "video.mp4" --polish-watermark "TÊN THƯƠNG HIỆU" \
    --polish-add-price --price "15,000 KHR" --polish-add-social --polish-hooks 3 --output "output"
```

### 🟡 Pro Editor — A/B test Hook (3 cách dùng)

**Cách A — hoàn toàn tự động** (chỉ cần ảnh; hệ thống tự OCR bao bì, nhận diện, nghiên cứu web):
```bash
python main.py --mode pro_editor --product-image "gel.jpg" \
    --hook-variants 3 --caption-style karaoke_highlight --output "output"
```

**Cách B — đã biết tên sản phẩm** (bỏ nhận diện ảnh, vẫn nghiên cứu web):
```bash
python main.py --mode pro_editor --product-image "gel.jpg" --product-name "Gôm Vuốt Tóc" \
    --price "15,000 KHR" --hook-variants 3 --output "output"
```

**Cách C — nhập tay toàn bộ** (nhanh nhất, không cần mạng để nghiên cứu):
```bash
python main.py --mode pro_editor --product-image "gel.jpg" --product-name "Gôm Vuốt Tóc" \
    --price "15,000 KHR" --benefits "Giữ nếp 24h,Thơm mát,Không bết dính" \
    --pain-points "Tóc rối,Xẹp mũ bảo hiểm" --hook-variants 3 --skip-product-research --output "output"
```

### 🌟 Ultimate Ad — chế độ mạnh nhất (giờ đã dùng được từ CLI)
```bash
python main.py --mode ultimate_ad --product-image "gel.jpg" --product-name "Gôm Vuốt Tóc" \
    --price "15,000 KHR" --target-language khmer --benefits "Giữ nếp 24h,Thơm mát" --output "output"
```

### 📰 News — video dạng bản tin
```bash
python main.py --mode news_auto --json-input "tin.json" --channel-name "KÊNH CỦA BẠN" --quality 1080p --output "output"
python main.py --mode news_ads --product-image "gel.jpg" --product-name "Tên SP" --output "output"
python main.py --mode news_pro --product-image "gel.jpg" --product-name "Tên SP" --output "output"
```

### 🔁 Flags hay dùng

| Flag | Tác dụng |
|---|---|
| `--caption-style` | `classic_box`, `outline_bold`, `karaoke_highlight`, `minimal_clean` |
| `--hook-variants N` | Số bản A/B test (mặc định 3, tối đa 5) |
| `--target-language` | Ngôn ngữ đầu ra cho `ultimate_ad`: `khmer`, `vietnamese`, `english` |
| `--tts-voice` | Đổi giọng đọc (mặc định `km-KH-SreymomNeural`; tiếng Việt: `vi-VN-HoaiMyNeural`) |
| `--skip-product-research` | Bỏ nghiên cứu web, dùng `--benefits` / `--pain-points` trực tiếp |
| `--force-refresh-research` | Bỏ cache 30 ngày, nghiên cứu lại từ đầu |
| `--allow-scraped-footage` | Cho phép dùng footage cào từ Meta Ads |
| `--log-level` | `DEBUG` để xem log chi tiết khi gỡ lỗi |

---

## 🕵️ PHẦN 6: AD SPY — CÓ BẮT BUỘC LẤY API META/TIKTOK KHÔNG?

**Không bắt buộc.** Không có key thì mọi tính năng tạo video và Visual Search vẫn chạy 100%,
chỉ riêng tab Ad Spy báo lỗi. Có key thì bạn nhập từ khóa (VD: "kem trị mụn") và lấy về nguyên
lời thoại quảng cáo đối thủ đang chạy, copy thẳng vào phần Kịch bản của Ultimate Ad.

**Lấy `META_AD_ACCESS_TOKEN`:** tạo App tại [Meta for Developers](https://developers.facebook.com/)
(loại None/Business) → *Settings > Basic* lấy App ID + Secret → xác minh danh tính tài khoản →
thêm sản phẩm **Marketing API** → vào *Graph API Explorer* tạo token có quyền `ads_read`.

**Lấy `TIKTOK_AD_ACCESS_TOKEN`:** đăng ký tại [TikTok for Developers](https://developers.tiktok.com/)
→ tạo App → xin quyền **Commercial Content API** → lấy Access Token trong màn hình quản lý App.

---

## 📁 PHẦN 7: THƯ MỤC LƯU TRỮ

```text
<thư mục dự án>/
├── output/                        ← Video thành phẩm (.mp4)
├── output_dub_only/               ← Kết quả chế độ Dub Only
├── output_full_remix/             ← Kết quả chế độ Full Remix
├── temp/                          ← File tạm & cache
│   ├── broll_manifest.db          ← Lịch sử B-roll đã dùng, tránh lặp (30 ngày)
│   ├── broll_api_cache.db         ← Cache Pexels/Pixabay (24 giờ)
│   └── product_research_cache.db  ← Cache nghiên cứu sản phẩm (30 ngày)
├── products.sqlite                ← Kho sản phẩm cho Visual Search (offline)
└── assets/
    ├── local_broll/               ← B-roll cào về từ Stockpile Curator
    ├── local_music/               ← Nhạc nền bạn tự thêm (calm/upbeat/urgent)
    └── style_profiles/            ← Phong cách video đã lưu
```

Mỗi lần chạy chế độ A/B test sẽ ra N file `*_hook_1.mp4`, `*_hook_2.mp4`… Đăng cả N bản lên
Facebook Ads Manager để so CTR và giữ lại bản thắng.

---

## 🩺 PHẦN 8: KHẮC PHỤC SỰ CỐ

**Kiểm tra môi trường bất cứ lúc nào:**
```bash
python smoke_test.py
```

| Triệu chứng | Cách xử lý |
|---|---|
| `cannot import name ...` | `pip install -r requirements.txt --upgrade` |
| `ffmpeg: command not found` | Cài FFmpeg (https://ffmpeg.org/download.html) và thêm vào PATH. Kiểm tra: `ffmpeg -version` |
| Lỗi API Gemini / hết quota | Kiểm tra `GEMINI_API_KEY` trong `.env`; thêm `GROQ_API_KEY` để hệ thống tự lùi sang Groq |
| Cổng 7860 đang bận | Chạy lại với cổng khác: `PORT=7871 python app2.py` |
| Phụ đề Khmer hiện ô vuông | Kiểm tra `assets/fonts/NotoSansKhmer-Bold.ttf` còn không; thiếu thì hệ thống tự tải lại khi chạy |
| Chữ tiếng Việt vỡ trong CMD | Chạy `chcp 65001` trước, hoặc dùng file `.bat` có sẵn |

Log chạy hiện trực tiếp trên Terminal theo thời gian thực — tìm dòng `[OK]` để biết bước nào đã xong.

---

## 💰 TỔNG QUAN CHI PHÍ

| Hạng mục | Dịch vụ | Chi phí |
|---|---|---|
| Viết kịch bản / phân tích ảnh | Gemini Flash (free tier) + Groq (dự phòng) | Miễn phí |
| Giọng đọc | edge-tts (Microsoft) | Miễn phí, không giới hạn |
| B-roll | Pexels / Pixabay / yt-dlp | Miễn phí |
| Tìm ảnh sản phẩm | ResNet50 + SQLite | Chạy offline trên máy bạn |
| Render, ghép nhạc, xóa logo | FFmpeg | Chạy offline trên máy bạn |
| Quét quảng cáo đối thủ | Meta / TikTok API | Miễn phí (dữ liệu công khai) |

---

## 🔤 GHI CHÚ VỀ FONT

Hệ thống dùng đúng 2 font nằm trong `assets/fonts/`: **Noto Sans Khmer** (tiếng Khmer) và
**Noto Sans** (tiếng Việt/Latin). Nếu xóa nhầm, hệ thống tự tải lại khi chạy overlay đầu tiên.
Không đổi tên font trong code sang font chưa có file — FFmpeg sẽ báo lỗi hoặc thay font khác.
