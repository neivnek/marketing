# 📐 CẤU TRÚC HỆ THỐNG VÀ THƯ MỤC - Video Pipeline v3.0

Hệ thống **Hybrid Zero-Cost Video Pipeline v3.0** được thiết kế theo hướng module hóa (Decoupled Processing Modules) để dễ dàng bảo trì và mở rộng. Tất cả quá trình xử lý AI, TTS, FFmpeg đều được tách biệt.

---

## 1. CẤU TRÚC THƯ MỤC TỔNG QUAN

```text
d:\ADS\pipeline\
│
├── main.py                     # File chạy chính CLI & Chuyển hướng các chế độ (Router Dispatcher)
├── app2.py                     # Giao diện Web Gradio (Chạy ở Port 7860)
├── smoke_test.py               # Script kiểm tra import và môi trường
├── requirements.txt            # Danh sách thư viện Python cần thiết
├── .env                        # Chứa các biến môi trường (GEMINI_API_KEY, PEXELS_API_KEY)
├── .env.example                # File mẫu để thiết lập .env
├── START.md                    # Hướng dẫn thao tác nhanh bằng lệnh cơ bản
├── SYSTEM_ARCHITECTURE.md      # Tài liệu kiến trúc hệ thống chuyên sâu của pipeline
│
├── core/                       # ⚙️ MODULE CỐT LÕI (Xử lý Độc Lập)
│   ├── config.py               # Quản lý toàn bộ cấu hình dataclasses & WorkflowMode
│   ├── router.py               # Bộ định tuyến xác thực đầu vào & chạy Pipeline
│   ├── tts_engine.py           # Sinh giọng nói tiếng Khmer bằng Edge-TTS
│   ├── subtitle_gen.py         # Tạo file phụ đề (.ASS) với nhiều style font Khmer
│   ├── ffmpeg_utils.py         # Chứa các lệnh FFmpeg (Ken Burns, Hardsub, cắt ghép, màu sắc)
│   ├── pexels_client.py        # Kéo video B-roll miễn phí từ Pexels API
│   ├── overlay_renderer.py     # Sinh ảnh overlay cho nhãn giá & banner khuyến mãi
│   ├── ugc_filters.py          # Bộ lọc UGC (Thêm nhiễu, rung camera)
│   ├── concat_helper.py        # Hỗ trợ FFmpeg ghép các clip mượt mà, đồng bộ FPS
│   ├── broll_aggregator.py     # Xử lý tổng hợp B-roll & chống trùng lặp bằng SQLite
│   ├── prosody_mapper.py       # Điểu chỉnh tốc độ/âm lượng giọng TTS theo cảm xúc
│   ├── social_proof_overlay.py # Thêm đánh giá 5 sao & lượt bán giả lập vào video
│   └── music_library.py        # Quản lý nhạc nền (calm, upbeat, urgent)
│
├── modes/                      # 🛠️ CÁC CHẾ ĐỘ QUY TRÌNH (Workflow Pipelines)
│   ├── auto/                   # Chế độ 1: Tự động (Auto Mode)
│   │   ├── auto_pipeline.py    # Điều phối quy trình tự động
│   │   ├── scraper.py          # Tool lấy dữ liệu video mẫu từ Meta Ads Library
│   │   └── ai_analyzer.py      # AI Gemini đánh giá video và viết kịch bản
│   │
│   ├── manual/                 # Chế độ 2: Chỉnh tay (Manual Mode)
│   │   ├── manual_pipeline.py
│   │   ├── pacing_analyzer.py  # Đọc nhịp điệu cắt cảnh từ file FFprobe
│   │   └── prompt_interpreter.py # Chuyển đổi lệnh mô tả thành hiệu ứng Ken Burns
│   │
│   ├── dub_only/               # Chế độ 3: Chỉ Lồng tiếng (Dub Only)
│   │   └── dub_only_pipeline.py
│   │
│   ├── full_remix/             # Chế độ 4: Remix Toàn phần (Full Remix)
│   │   ├── full_remix_pipeline.py
│   │   ├── audio_replace.py    # Xóa audio gốc, thay thế bằng âm thanh mới
│   │   ├── text_mask_overlay.py # Làm mờ/che text cũ trên video
│   │   └── remix_cut_generator.py # Trộn cắt ngẫu nhiên tạo bản remix UGC
│   │
│   ├── news_auto/              # Chế độ 5: Làm tin tức tự động (News Auto)
│   │   ├── news_auto_pipeline.py
│   │   └── ...
│   │
│   ├── polish/                 # Chế độ 6: Đánh bóng (Polish)
│   │   └── polish_pipeline.py  # Thêm watermark, giá cả, social proof
│   │
│   └── pro_editor/             # Chế độ 7: Biên Tập Viên Chuyên Nghiệp (Pro Editor)
│       ├── pro_editor_pipeline.py # Phối hợp AI tạo A/B test hàng loạt
│       ├── creative_director.py # Phân tích và sinh kịch bản JSON theo khung PAS
│       ├── shotlist_planner.py  # Lên kế hoạch cảnh quay theo script
│       └── hook_variant_generator.py # Tạo ra N video Intro (Hook) ngắn khác nhau
│
├── assets/                     # 🎨 TÀI NGUYÊN (Tĩnh)
│   ├── fonts/                  # Font Khmer (Hanuman.ttf, Battambang.ttf, Moul.ttf)
│   └── local_music/            # Nhạc nền chia theo cảm xúc (calm, upbeat, urgent)
│
├── temp/                       # 🗑️ THƯ MỤC TẠM (Tự động xóa nội dung sau khi chạy xong)
└── output/                     # 💾 THƯ MỤC XUẤT VIDEO (.mp4, thành phẩm lưu ở đây)
```

---

## 2. QUY TRÌNH LUỒNG DỮ LIỆU CƠ BẢN (DATA FLOW)

1. **User Input:** Nhập dữ liệu qua Gradio (Web UI) hoặc lệnh CLI (Termial/PowerShell).
2. **Router (`core/router.py`):** Kiểm tra cờ (flags), tham số và điều hướng tới thư mục `modes/` tương ứng.
3. **AI Generation (`modes/*/ai_analyzer.py` hoặc `creative_director.py`):** Gửi yêu cầu qua Google Gemini API để lấy kịch bản tiếng Khmer (dạng JSON hoặc Text).
4. **TTS Generation (`core/tts_engine.py`):** Đọc file kịch bản, kết nối đến Edge-TTS để tải file MP3 âm thanh.
5. **Assets & Visuals (`core/pexels_client.py` & `ffmpeg_utils.py`):** Tìm kiếm clip B-roll, tạo hiệu ứng chuyển động Ken Burns cho ảnh sản phẩm, xử lý âm thanh đồng bộ với FPS.
6. **Final Composition:** Sử dụng FFmpeg để chèn Audio mới vào Video, Burn phụ đề (Hardsub) tiếng Khmer (`core/subtitle_gen.py`), chèn các lớp đồ họa giá/logo (`core/overlay_renderer.py`).
7. **Output:** Trả về file MP4 thành phẩm nằm trong thư mục `output/`.
