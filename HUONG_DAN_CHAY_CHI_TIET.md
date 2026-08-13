# TỔNG QUAN CHI TIẾT HỆ THỐNG: HYBRID ZERO-COST VIDEO PIPELINE v3.5
*(Tích hợp Google Scene Machine, Stockpile AI B-Roll Curator & Logo Remover Engine)*

---

## 🌟 1. TỔNG QUAN HỆ THỐNG
Hệ thống là một giải pháp sản xuất video quảng cáo ngắn (TikTok, Facebook Reels, YouTube Shorts) tự động 100%, thiết kế theo tư duy **Zero-Cost (Chi phí 0 VNĐ)**. 

Hệ thống cho phép bạn:
* Ném ảnh sản phẩm + Nhập tên/giá tiền ➡️ Sinh ra 3 - 5 video quảng cáo chất lượng Agency ($3,000) với các phiên bản mở đầu (Hook) khác nhau để A/B Testing.
* Tự động cào video B-Roll minh họa, tự xóa Logo/Watermark, tự động viết kịch bản AI, lồng tiếng AI tiếng Việt & chèn phụ đề hiệu ứng.

---

## 🧩 2. CÁC CÔNG NGHỆ CỐT LÕI ĐÃ TÍCH HỢP

### 1️⃣ **Google Gemini 3.6 Flash (Trí tuệ nhân tạo thế hệ mới nhất)**
* Viết kịch bản quảng cáo thương mại chuẩn mô hình **Hook - Problem - Solution - Call to Action**.
* Tự động phân tích hình ảnh sản phẩm, nhận diện thương hiệu & viết kịch bản Spy Ads.

### 2️⃣ **Google Scene Machine Integration (`google-marketing-solutions/scene-machine`)**
* Dựng video theo chuẩn quy trình **Storyboard 4-Cảnh** của Google:
  * *Scene 1 (Hook)*: Giữ chân người xem trong 3s đầu.
  * *Scene 2 (Problem)*: Nêu bật vấn đề/nỗi đau của khách hàng.
  * *Scene 3 (Solution)*: Trình diễn tính năng/giải pháp của sản phẩm.
  * *Scene 4 (CTA)*: Kêu gọi hành động & ưu đãi.

### 3️⃣ **Stockpile AI B-Roll Curator (`sasoder/stockpile`)**
* AI mở rộng từ khóa tìm kiếm & dùng `yt-dlp` cào các đoạn video clip B-roll HD thực tế trên internet.
* Tự động tải & phân loại vào thư viện `assets/local_broll/<từ_khóa>/` để làm video nền.

### 4️⃣ **Logo & Watermark Remover Engine (`shijincai/remove-logo-from-video`)**
* Sử dụng bộ lọc nội suy **FFmpeg Delogo & Boxblur** để tự động xóa logo, ID TikTok, watermark rác ở góc trên & góc dưới của các video clip B-roll.

### 5️⃣ **Visual Search Engine 2-Tier (Offline 100%)**
* Tích hợp model Deep Learning **ResNet50 + CSDL SQLite** (`products.sqlite`).
* Nhận diện và đối chiếu hình ảnh sản phẩm từ kho dữ liệu mà không cần kết nối mạng.

### 6️⃣ **Xử Lý Âm Thanh & Phụ Đề (Audio & Caption Engine)**
* **Giọng đọc AI**: edge-tts (Microsoft) lồng tiếng Nam/Nữ tiếng Việt mượt mà.
* **Hiệu ứng SFX & Nhạc nền**: Tự động chèn nhạc nền, tiếng Pop, Whoosh khớp theo nhịp video.
* **Phụ đề động**: Tự sinh phụ đề hiệu ứng nổi bật (TikTok Style).

---

## 📊 3. TRẠNG THÁI CẤU HÌNH HỆ THỐNG (.env)

All APIs đã được kích hoạt & sẵn sàng:
* ✅ **GEMINI_API_KEY**: Đã cấu hình (Mô hình `gemini-3.6-flash`)
* ✅ **PEXELS_API_KEY**: Đã cấu hình
* ✅ **PIXABAY_API_KEY**: Đã cấu hình
* ✅ **YOUTUBE_API_KEY**: Đã cấu hình
* ✅ **TIKTOK_CLIENT_KEY / TIKTOK_AD_ACCESS_TOKEN**: Đã cấu hình (`awj4rm4xawm1zen6`)

---

## 🖥️ 4. DANH SÁCH TẤT CẢ TÍNH NĂNG TRÊN WEB UI (`python app2.py`)

Khi bật Web UI tại **`http://localhost:7860`**, bạn sẽ có 7 Tab chức năng mạnh mẽ:

| Tab Chức Năng | Công Dụng |
| :--- | :--- |
| **Ultimate Ad (Mode 10)** 🌟 | Tạo video quảng cáo tự động 100% từ 1 ảnh sản phẩm (Sinh 3-5 bản A/B Test). |
| **🎬 Google Scene Machine** | Dựng video theo cấu trúc Storyboard 4-cảnh tự động chuẩn Google Marketing. |
| **📦 Stockpile AI B-Roll Curator** | AI cào & tuyển chọn video B-roll HD từ từ khóa về kho máy tính. |
| **🧹 Xóa Logo Video (Logo Remover)** | Xóa sạch logo TikTok, watermark rác khỏi video clip. |
| **Visual Search Engine 🔍** | Quản lý kho sản phẩm & tìm kiếm ảnh sản phẩm bằng Deep Learning offline. |
| **Ad Spy (Meta & TikTok) 🕵️** | Phân tích & sinh ra các kịch bản quảng cáo triệu view từ từ khóa đối thủ. |
| **Pro Editor (Mode 7)** | Tùy chỉnh chi tiết từng đoạn Hook, PAS, B-roll & hiệu ứng rung lắc UGC. |

---

## 🚀 5. HƯỚNG DẪN KHỞI ĐỘNG NHANH (1-CLICK)

1. Mở thư mục `d:\ADS\pipeline` trên máy tính.
2. Nhấp đôi chuột vào file **`KHOI_DONG.bat`**.
3. Trình duyệt web sẽ **tự động bật lên** địa chỉ `http://localhost:7860` để bạn sử dụng ngay!
