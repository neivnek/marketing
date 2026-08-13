# AI_SYSTEM_CONTEXT.md
> **Tài liệu này được tối ưu hóa cho các trợ lý AI, LLM, Chatbot khác đọc để lập tức hiểu toàn bộ bối cảnh, kiến trúc, và các thành phần của hệ thống `ADS Pipeline`.**

## 1. MỤC TIÊU HỆ THỐNG (SYSTEM PURPOSE)
* **Tên dự án**: Hybrid Zero-Cost Video Pipeline v3.5
* **Mục tiêu**: Tự động hóa 100% quy trình sản xuất video quảng cáo ngắn (TikTok, YouTube Shorts, FB Reels) theo tiêu chuẩn Agency (chất lượng cao) với chi phí 0 VNĐ.
* **Đầu vào (Input)**: Hình ảnh tĩnh của sản phẩm + tên/từ khóa sản phẩm.
* **Đầu ra (Output)**: File video quảng cáo `.mp4` hoàn chỉnh với kịch bản chuẩn, hình ảnh/B-roll minh họa, nhạc nền, giọng đọc AI tiếng Việt (TTS), phụ đề và hiệu ứng.

## 2. KIẾN TRÚC & CÔNG NGHỆ (ARCHITECTURE & TECH STACK)
* **Ngôn ngữ**: Python 3.10+
* **Core Framework**: Gradio (Web UI).
* **AI & LLM**: Google Gemini (`gemini-3.6-flash`, `gemini-flash-latest`) dùng cho NLP, phân tích hình ảnh, sinh kịch bản.
* **Computer Vision**: TensorFlow (ResNet50) + `scikit-learn` dùng để trích xuất đặc trưng ảnh (Feature Extraction) và so sánh độ tương đồng (Cosine Similarity).
* **Video/Audio Processing**: FFmpeg (dựng video, cắt ghép, chèn audio, delogo, blur) + `edge-tts` (Microsoft Edge Text-to-Speech).
* **Web Scraping & Fetching**: `yt-dlp` (cào B-roll từ YouTube/TikTok), Pexels API, Pixabay API.
* **Database**: SQLite (`products.sqlite`) - Offline vector/metadata DB.

## 3. CÁC TÍCH HỢP NÂNG CAO (ADVANCED INTEGRATIONS)
Hệ thống được fork/kế thừa từ các dự án mã nguồn mở hàng đầu:
1. **Google Scene Machine** (`google-marketing-solutions/scene-machine`): 
   - Tự động chia kịch bản thành Storyboard 4-cảnh (Hook, Problem, Solution, CTA) và dựng video từng cảnh ráp lại với nhau.
2. **Stockpile AI B-Roll Curator** (`sasoder/stockpile`): 
   - Ứng dụng AI phân tích từ khóa -> Dùng `yt-dlp` cào hàng loạt clip Shorts/Reels thực tế HD -> Tự động lưu vào kho B-roll local (`assets/local_broll/`).
3. **Logo & Watermark Remover** (`shijincai/remove-logo-from-video`): 
   - Tự động xóa hoặc làm mờ Logo/ID TikTok, watermark rác trên các clip B-roll bằng FFmpeg (`delogo`, `boxblur`).

## 4. CẤU TRÚC THƯ MỤC VÀ MODULE (PROJECT STRUCTURE)
```text
d:\ADS\pipeline\
│
├── .env                          # Chứa API Keys: GEMINI_API_KEY, PEXELS_API_KEY, TIKTOK_CLIENT_KEY...
├── app2.py                       # File chạy chính chứa Gradio Web UI (7 Tabs chức năng)
├── KHOI_DONG.bat                 # Script khởi động 1-click cho người dùng Windows
├── CAI_DAT.bat                   # Script cài đặt môi trường ban đầu
├── products.sqlite               # Cơ sở dữ liệu offline lưu trữ thông tin & vector ảnh sản phẩm
│
├── core/                         # Các module AI & xử lý cốt lõi
│   ├── product_vision_index.py   # ResNet50 + SQLite (Visual Search Engine)
│   ├── scene_machine_engine.py   # Google Scene Machine (Tạo Storyboard 4-cảnh)
│   ├── stockpile_broll_curator.py# AI cào B-roll bằng yt-dlp
│   ├── logo_remover.py           # Xóa logo/watermark bằng FFmpeg
│   ├── broll_aggregator.py       # Thu thập B-roll từ Local, Pixabay, Pexels, AI
│   ├── subtitle_gen.py           # Tạo và chèn phụ đề vào video
│   ├── tts_engine.py             # Sinh giọng nói tiếng Việt bằng edge-tts
│   ├── ffmpeg_utils.py           # Các hàm render, concat video bằng FFmpeg
│   └── tiktok_api_client.py      # Tương tác với TikTok Commercial API (Ad Spy)
│
├── assets/                       # Thư viện tài nguyên local
│   ├── local_broll/              # Nơi chứa các clip B-roll cào được từ Stockpile
│   ├── music/                    # Kho nhạc nền no-copyright
│   └── sfx/                      # Kho hiệu ứng âm thanh (Pop, Whoosh)
│
├── output/                       # Nơi lưu các video hoàn chỉnh xuất ra
└── temp/                         # Chứa các file trung gian (ảnh cắt, audio tạm) khi dựng video
```

## 5. CÁC TÍNH NĂNG CHÍNH (GRADIO WEB UI TABS - `app2.py`)
1. **Ultimate Ad (Mode 10)**: Tạo 3-5 video A/B Testing chỉ từ 1 ảnh sản phẩm. Dựng kịch bản PAS tự động.
2. **Google Scene Machine**: Tạo video storyboard theo quy trình chuẩn của Google Marketing.
3. **Stockpile AI B-Roll Curator**: Nhập keyword -> AI cào video B-roll HD về máy lưu trữ.
4. **Xóa Logo Video (Logo Remover)**: Upload video dính logo -> AI dùng FFmpeg delogo làm sạch 100%.
5. **Visual Search Engine**: Upload ảnh bất kỳ -> Hệ thống Deep Learning quét và tìm thông tin, kịch bản cũ trong DB offline.
6. **Ad Spy (Meta & TikTok)**: Phân tích ads triệu view của đối thủ để tạo kịch bản học hỏi.
7. **Pro Editor (Mode 7)**: Chỉnh sửa thủ công Hook, Body, CTA cho người dùng chuyên nghiệp.

## 6. LƯU Ý KHI LẬP TRÌNH BẢO TRÌ (FOR AI ASSISTANTS)
* **Encoding & CMD**: Nếu viết Batch script (.bat) cần đảm bảo lưu ở chuẩn ANSI (cp1252) hoặc thêm `chcp 65001` để tránh lỗi font chữ tiếng Việt trên Windows CMD. Không dùng UTF-8 BOM.
* **Giao tiếp API**: Hệ thống Gemini đã được nâng cấp dùng thư viện `google.genai`. Model mặc định phải là `gemini-3.6-flash`, sau đó fallback sang `gemini-flash-latest`. Tuyệt đối không dùng model đã bị khai tử (`gemini-2.5-flash`).
* **Hoạt động Offline/Local**: Hệ thống chú trọng tính năng hoạt động offline hoặc lưu trữ local tối đa (như DB SQLite, kho nhạc, kho broll cào về máy). Mọi thư viện đều được cài trong `.venv`.
* **Khởi động an toàn**: Luôn đặt tham số `inbrowser=True` và KHÔNG hardcode cổng `server_port` trong phương thức `app.launch()` của `app2.py` để tránh lỗi đụng port.
