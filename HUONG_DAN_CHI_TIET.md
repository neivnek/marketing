# 📘 HƯỚNG DẪN SỬ DỤNG CHI TIẾT - Hybrid Zero-Cost Video Pipeline v3.0

Hệ thống cung cấp một quy trình tự động hóa hoàn toàn việc tạo video ngắn (9:16) dành cho nền tảng Facebook Shorts, Reels, và TikTok. Ngôn ngữ hỗ trợ chính là tiếng Khmer.

---

## 🚀 1. CÀI ĐẶT VÀ CẤU HÌNH BAN ĐẦU

### 1.1. Cài đặt môi trường
Bạn chỉ cần thực hiện 1 lần duy nhất trên máy tính (yêu cầu đã cài đặt Python 3.9+ và FFmpeg).
Mở PowerShell tại thư mục `d:\ADS\pipeline` và chạy:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
.venv\Scripts\pip install -r requirements.txt
python smoke_test.py
```
*(Nếu thấy `[OK] All imports OK!` nghĩa là đã cài thành công).*

### 1.2. Cấu hình API Key
Mở (hoặc tạo) file `.env` tại `d:\ADS\pipeline\.env` và điền thông tin:
```ini
# Bắt buộc - Google Gemini Flash Free Tier
GEMINI_API_KEY=YOUR_GEMINI_KEY

# Tuỳ chọn - Lấy B-roll chất lượng cao
PEXELS_API_KEY=YOUR_PEXELS_KEY
PIXABAY_API_KEY=YOUR_PIXABAY_KEY
YOUTUBE_API_KEY=YOUR_YOUTUBE_KEY
```

---

## 🎬 2. CHẠY GIAO DIỆN WEB (UI)

Đây là cách sử dụng dễ dàng nhất cho người không quen dùng lệnh.
```powershell
cd d:\ADS\pipeline
.venv\Scripts\Activate.ps1
python app2.py
```
- Mở trình duyệt và truy cập: **http://localhost:7860**
- Giao diện có các tab tương ứng với các chế độ như **Auto / Manual**, **Dub Only**, **Full Remix**, **Polish**, và **Pro Editor**.

---

## ⚡ 3. SỬ DỤNG BẰNG DÒNG LỆNH (CLI) - CÁC CHẾ ĐỘ CHI TIẾT

Luôn kích hoạt môi trường trước khi chạy lệnh:
```powershell
.venv\Scripts\Activate.ps1
```

### 🟢 3.1. Mode 1: Auto-Autonomous (Tự động hoàn toàn)
Hệ thống tự động tìm video mẫu, Gemini viết kịch bản tiếng Khmer và xuất video.
```powershell
python main.py --mode auto --product-image "d:/ADS/image.jpg" --keyword "từ khóa sản phẩm" --output "d:/ADS/output"
```

### 🔵 3.2. Mode 2: Manual Override (Chế độ thủ công)
Tự nhập kịch bản và chọn góc quay (camera style) thay vì để AI quyết định.
```powershell
python main.py --mode manual --product-image "d:/ADS/image.jpg" --script "Nội dung kịch bản Khmer..." --prompt "warm cinematic slow zoom" --output "d:/ADS/output"
```

### 🟣 3.3. Mode 3: Dub Only (Chỉ lồng tiếng)
Lồng giọng đọc tiếng Khmer và chèn phụ đề vào một video đã có sẵn.
```powershell
python main.py --mode dub_only --dub-only-source "d:/ADS/video.mp4" --dub-only-script "Kịch bản tiếng Khmer" --dub-only-burn-subtitle --output "d:/ADS/output"
```

### 🔴 3.4. Mode 4: Full Remix (Remix Video Cũ)
Lồng tiếng mới, che chữ cũ, thêm nhạc nền, tạo bản re-cut remix với hiệu ứng UGC.
```powershell
python main.py --mode full_remix --full-remix-source "d:/ADS/video.mp4" --script "Kịch bản Khmer" --full-remix-mask-style box --full-remix-create-remix --output "d:/ADS/output"
```

### ⚪ 3.5. Mode 6: Polish (Đánh bóng Video)
Chèn watermark, hiển thị giá sản phẩm, thêm Social Proof (đánh giá, lượt bán) và tạo ra nhiều phiên bản (Hook Variants) cho A/B testing.
```powershell
python main.py --mode polish --polish-source "d:/ADS/video_remix.mp4" --polish-watermark "TEN THUONG HIEU" --polish-add-price --price "15,000 KHR" --polish-add-social --polish-hooks 3 --output "d:/ADS/output"
```

### 🟡 3.6. Mode 7: Pro Editor (Trình Edit Chuyên Nghiệp)
Tự động quy trình: Nhận diện ảnh -> Nghiên cứu Web -> Kịch bản PAS -> Lấy B-roll -> Mix Nhạc -> Tạo N video với Hook khác nhau.
```powershell
python main.py --mode pro_editor --product-image "d:/ADS/image.jpg" --product-name "Tên Sản Phẩm" --price "15,000 KHR" --hook-variants 3 --caption-style karaoke_highlight --output "d:/ADS/output"
```
*(Nếu muốn tự viết tính năng/nỗi đau mà không cần AI nghiên cứu, thêm flag `--skip-product-research` cùng với `--benefits "..."` và `--pain-points "..."`)*.

---

## 📁 4. THƯ MỤC LƯU TRỮ VÀ QUẢN LÝ TÀI NGUYÊN

- **Video hoàn thiện:** Lưu tại `d:\ADS\pipeline\output\`
- **Nhạc nền tùy chỉnh:** Bạn có thể copy nhạc `.mp3` miễn phí bản quyền vào các thư mục:
  - `assets/local_music/calm/` (dành cho đoạn nêu vấn đề, kể chuyện buồn)
  - `assets/local_music/upbeat/` (dành cho đoạn giới thiệu sản phẩm)
  - `assets/local_music/urgent/` (dành cho đoạn kêu gọi hành động)

---

## 🩺 5. KHẮC PHỤC SỰ CỐ (TROUBLESHOOTING)

1. **Lỗi `cannot import name ...`:** Cập nhật lại thư viện: `pip install -r requirements.txt --upgrade`.
2. **Lỗi FFmpeg không tìm thấy lệnh:** Đảm bảo bạn đã cài FFmpeg và thiết lập biến môi trường PATH cho FFmpeg.
3. **Lỗi API Gemini:** Đảm bảo bạn sử dụng đúng API key ở file `.env` và có kết nối mạng ổn định. Mặc định hệ thống dùng `gemini-3.6-flash`.
