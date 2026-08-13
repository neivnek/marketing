# 📘 HƯỚNG DẪN VẬN HÀNH TOÀN DIỆN — FB Shorts Ads Generator v3.0
### Hybrid Zero-Cost Khmer Video Pipeline — 5 chế độ + Product Intelligence

> **Cách dùng file này:** Chỉ cần sao chép lệnh, dán vào PowerShell và nhấn Enter.  
> Không cần biết lập trình. Mọi lệnh đều đã được kiểm tra và hoạt động.

---

## 🛠️ PHẦN 1: CÀI ĐẶT LẦN ĐẦU (Chỉ chạy 1 lần duy nhất)

Mở **PowerShell** hoặc **Terminal trong VS Code**, dán toàn bộ khối lệnh sau:

```powershell
cd d:\ADS\pipeline
python -m venv .venv
.venv\Scripts\Activate.ps1
.venv\Scripts\pip install -r requirements.txt edge-tts mutagen nest-asyncio gradio requests
python smoke_test.py
```

✅ Khi thấy `[OK] All imports OK!` là cài đặt thành công.

---

## 🔑 PHẦN 2: CẤU HÌNH API KEY (Bắt buộc trước khi dùng)

Mở file `d:\ADS\pipeline\.env` bằng Notepad và điền vào:

```ini
# ── BẮT BUỘC ──────────────────────────────────────────────────────
# Google Gemini Key (lấy miễn phí tại: https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=Dán_Key_Gemini_Vào_Đây

# ── TÙY CHỌN (thêm thì tốt hơn, bỏ qua vẫn chạy được) ───────────
# Pexels — tìm video B-roll chất lượng cao (https://www.pexels.com/api/)
PEXELS_API_KEY=Dán_Key_Pexels_Vào_Đây

# Pixabay — nguồn B-roll thay thế (https://pixabay.com/api/docs/)
PIXABAY_API_KEY=Dán_Key_Pixabay_Vào_Đây

# YouTube Data API v3 — tìm video review sản phẩm cho Mode 7
# (Lấy miễn phí: https://console.cloud.google.com → Enable YouTube Data API v3)
YOUTUBE_API_KEY=Dán_Key_YouTube_Vào_Đây
```

> **Lưu ý:** Nếu chưa có key Pexels/Pixabay/YouTube thì vẫn chạy được.  
> Hệ thống sẽ tự dùng ảnh sản phẩm Ken Burns khi không có B-roll.

---

## 🎬 PHẦN 3: CÀI NHẠC NỀN CHO MODE 7 (Tùy chọn nhưng khuyến nghị)

Mode 7 tự động mix nhạc nền. Tải nhạc miễn phí bản quyền và bỏ vào đúng thư mục:

| Thư mục | Dùng cho | Tải tại |
|---|---|---|
| `assets/local_music/calm/` | Đoạn kể vấn đề, cảm xúc buồn | https://pixabay.com/music/ |
| `assets/local_music/upbeat/` | Đoạn giới thiệu sản phẩm | https://pixabay.com/music/ |
| `assets/local_music/urgent/` | Đoạn kêu gọi mua hàng CTA | https://pixabay.com/music/ |

Chấp nhận định dạng: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`

---

## 🚀 PHẦN 4: GIAO DIỆN WEB (Cách dùng dễ nhất — Không cần gõ lệnh)

```powershell
cd d:\ADS\pipeline
.venv\Scripts\Activate.ps1
python app2.py
```

Sau đó mở trình duyệt vào: **http://localhost:7860**

Các tab chính có sẵn trên giao diện:
- **Auto / Manual** — Tự động hoàn toàn / Nhập kịch bản tay
- **Dub Only** — Chỉ lồng giọng đọc Khmer + phụ đề vào video có sẵn
- **Full Remix** — Remix video (cắt ghép) + Đọc thoại + Nhạc nền + Giá
- **Polish** — Đánh bóng video (đóng watermark, giá, thêm Review/Rating, và nối N Hook biến thể A/B test)
- **Pro Editor** — Kịch bản chuyên nghiệp + A/B test Hook

---

## ⚡ PHẦN 5: DÒNG LỆNH CLI (Cho người dùng nâng cao)

Kích hoạt môi trường trước (chạy 1 lần mỗi phiên làm việc):
```powershell
cd d:\ADS\pipeline
.venv\Scripts\Activate.ps1
```

---

### 🟢 Chế độ 1: Auto-Autonomous
> Tự tìm video CC + Gemini viết kịch bản Khmer + Xuất video 9:16

```powershell
python main.py `
    --mode auto `
    --product-image "d:/ADS/gel.jpg" `
    --keyword "hair gel cambodia" `
    --output "d:/ADS/output"
```

---

### 🔵 Chế độ 2: Manual Override
> Tự nhập kịch bản Khmer + Chọn phong cách camera

```powershell
python main.py `
    --mode manual `
    --product-image "d:/ADS/gel.jpg" `
    --script "ហ្សែលក្ដៅ! ធ្វើឱ្យសក់របស់អ្នករឹងប៉ូវ និងស្អាត។ ទទួលដឹកជញ្ជូនឥតគិតថ្លៃ!" `
    --prompt "warm cinematic slow zoom" `
    --output "d:/ADS/output"
```

---

### 🟣 Chế độ 3: Dub Only
> Lồng giọng đọc Khmer + phụ đề vào video có sẵn

```powershell
python main.py `
    --mode dub_only `
    --dub-only-source "d:/ADS/MANG12.mp4" `
    --dub-only-script "ហ្សែលក្ដៅ! ធ្វើឱ្យសក់របស់អ្នករឹងប៉ូវ និងស្អាត។" `
    --dub-only-burn-subtitle `
    --output "d:/ADS/output"
```

---

### 🔴 Chế độ 4: Full Remix
> Remix video (lồng tiếng, che chữ cũ, tạo bản dựng re-cut remix)

```powershell
python main.py `
    --mode full_remix `
    --full-remix-source "d:/ADS/MANG12.mp4" `
    --script "ហ្សែលក្ដៅ! ធ្វើឱ្យសក់របស់អ្នករឹងប៉ូវ និងស្អាត។" `
    --full-remix-mask-style box `
    --full-remix-create-remix `
    --output "d:/ADS/output"
```

---

### ⚪ Chế độ 6: Polish (Đánh Bóng Video)
> Thêm hiệu ứng, Watermark, Giá, Đánh giá (Social Proof), và N biến thể Hook vào video đã có

```powershell
python main.py `
    --mode polish `
    --polish-source "d:/ADS/MANG12_remix.mp4" `
    --polish-watermark "KHMER DAILY" `
    --polish-add-price `
    --price "15,000 KHR" `
    --polish-add-social `
    --polish-hooks 3 `
    --output "d:/ADS/output"
```

---

### 🟡 Chế độ 7: Pro Editor — A/B Test Hook Variants

> Quy trình đầy đủ: **Nhận diện sản phẩm từ ảnh → Nghiên cứu web thật → Viết kịch bản PAS → Lấy B-roll → Mix nhạc → Phụ đề → Tạo N bản video với Hook khác nhau**

Có **3 cách dùng** tùy mức độ tự động hóa:

#### 🤖 Cách A — Hoàn toàn tự động (chỉ cần ảnh sản phẩm)
Hệ thống tự đọc chữ trên bao bì (OCR), nhận diện sản phẩm, nghiên cứu web,
tìm review thật từ khách hàng, rồi viết kịch bản và xuất video.

```powershell
python main.py `
    --mode pro_editor `
    --product-image "d:/ADS/gel.jpg" `
    --hook-variants 3 `
    --caption-style karaoke_highlight `
    --output "d:/ADS/output"
```

#### ✏️ Cách B — Có sẵn tên sản phẩm (bỏ nhận diện ảnh, vẫn nghiên cứu web)

```powershell
python main.py `
    --mode pro_editor `
    --product-image "d:/ADS/gel.jpg" `
    --product-name "Gôm Vuốt Tóc Kềm" `
    --price "15,000 KHR" `
    --hook-variants 3 `
    --output "d:/ADS/output"
```

#### ⚡ Cách C — Nhập tay toàn bộ, bỏ qua nghiên cứu (nhanh nhất, offline)

```powershell
python main.py `
    --mode pro_editor `
    --product-image "d:/ADS/gel.jpg" `
    --product-name "Gôm Vuốt Tóc Kềm" `
    --price "15,000 KHR" `
    --benefits "Giữ nếp 24h,Thơm mát,Không bết dính" `
    --pain-points "Tóc rối,Xẹp mũ bảo hiểm" `
    --hook-variants 3 `
    --skip-product-research `
    --output "d:/ADS/output"
```

#### 🔁 Flags bổ sung cho Mode 7

| Flag | Tác dụng |
|---|---|
| `--caption-style` | Kiểu phụ đề: `classic_box`, `outline_bold`, `karaoke_highlight`, `minimal_clean` |
| `--hook-variants 3` | Số bản video A/B test (mặc định: 3, tối đa: 5) |
| `--skip-product-research` | Bỏ qua nghiên cứu web, dùng `--benefits`/`--pain-points` trực tiếp |
| `--force-refresh-research` | Bỏ qua cache 30 ngày, chạy lại nghiên cứu từ đầu |
| `--allow-scraped-footage` | Cho phép dùng footage từ Meta Ads scraper |

---

## 📁 PHẦN 6: THƯ MỤC OUTPUT VÀ CACHE

```
d:\ADS\pipeline\
├── output\                    ← Video thành phẩm (.mp4) lưu ở đây
├── temp\                      ← File tạm (tự xoá sau mỗi lần chạy)
│   ├── broll_manifest.db      ← Lịch sử B-roll đã dùng (tránh lặp, 30 ngày)
│   ├── broll_api_cache.db     ← Cache JSON từ Pexels/Pixabay (24h, theo ToS)
│   └── product_research_cache.db ← Cache nghiên cứu sản phẩm (30 ngày)
└── assets\
    └── local_music\           ← Nhạc nền tự thêm vào đây
        ├── calm\
        ├── upbeat\
        └── urgent\
```

Mở thư mục output:
```powershell
explorer d:\ADS\pipeline\output
```

---

## 🩺 PHẦN 7: KIỂM TRA HỆ THỐNG & XỬ LÝ LỖI

### Kiểm tra import (chạy bất cứ lúc nào để verify):
```powershell
cd d:\ADS\pipeline
.venv\Scripts\Activate.ps1
python smoke_test.py
```

### Nếu gặp lỗi "cannot import name ...":
```powershell
.venv\Scripts\pip install -r requirements.txt --upgrade
```

### Nếu gặp lỗi FFmpeg:
Đảm bảo `ffmpeg` đã được cài và có trong PATH:
```powershell
ffmpeg -version
```
Nếu chưa có: Tải tại https://ffmpeg.org/download.html và thêm vào PATH.

### Xem log chi tiết khi pipeline chạy:
Tất cả log tự hiện trên Terminal theo thời gian thực. Tìm dòng `[OK]` để biết từng bước đã xong.

---

> **Video thành phẩm:** `d:\ADS\pipeline\output\` — Mỗi lần chạy Mode 7 tạo ra N file `*_hook_1.mp4`, `*_hook_2.mp4`...  
> Đăng cả N bản lên Facebook Ads Manager để so sánh CTR và tìm bản thắng.
