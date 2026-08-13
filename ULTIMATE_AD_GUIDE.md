# Hướng Dẫn Sử Dụng: HỆ THỐNG ULTIMATE AD (Bao gồm Visual Search & Ad Spy)

Chào mừng bạn đến với hệ thống tạo quảng cáo video tự động (Hybrid Zero-Cost Pipeline). Phiên bản này đã được nâng cấp với **3 tính năng cốt lõi** để giúp bạn tạo ra những video quảng cáo chất lượng Agency ($3000) mà hoàn toàn miễn phí.

---

## TÍNH NĂNG 1: TẠO VIDEO QUẢNG CÁO (ULTIMATE AD - MODE 10)
Đây là chế độ mạnh nhất của hệ thống, tự động hóa 100% quy trình sản xuất video từ lúc ném ảnh vào đến lúc ra file mp4 hoàn chỉnh.

### Điểm nổi bật:
- **Tự động viết kịch bản (Gemini)** chuẩn mô hình Hook - Thân bài - Kêu gọi hành động.
- **Tự động tìm B-Roll (Video nền)** từ Pexels, NTD-Labs, hoặc AI sinh ra.
- **Hiệu ứng xịn xò**: Nhạc nền tự động khớp nhịp, Âm thanh SFX (tiếng pop, whoosh), Zoom Ken-Burns.
- **Tự sinh A/B Testing**: Một lần chạy sinh ra 3-5 video với các đoạn mở đầu (Hook) khác nhau để test Ads.

### Cách dùng:
1. Chạy Web UI: `python app2.py`
2. Mở trình duyệt, vào Tab **Quảng Cáo & Thương Mại > Ultimate Ad (Mode 10)**.
3. Upload ảnh sản phẩm, nhập tên, giá tiền.
4. Bấm **Tạo Video** và đợi phép màu xảy ra.

---

## TÍNH NĂNG 2: QUẢN LÝ KHO SẢN PHẨM (VISUAL SEARCH 2-TIER)
Hệ thống được tích hợp **AI Deep Learning (ResNet50)** và **Cơ sở dữ liệu SQLite** chạy hoàn toàn offline trên máy tính của bạn.

### Nó hoạt động thế nào?
- Mỗi khi bạn tạo video ở Tính năng 1, Gemini sẽ tự "cắt" phần hình ảnh sản phẩm sạch sẽ nhất, đọc giá tiền, công dụng trên bao bì và lưu kín vào cơ sở dữ liệu (`products.sqlite`).
- Tại Web UI, bạn chuyển sang Tab **Visual Search Engine 🔍**.
- Khi bạn upload một bức ảnh, hệ thống sẽ dùng AI đối chiếu hình ảnh đó với kho dữ liệu và lôi ra cho bạn: **Tên sản phẩm, Giá tiền đã lưu, Lợi ích sản phẩm, và Hình ảnh tương đồng**.

---

## TÍNH NĂNG 3: THEO DÕI QUẢNG CÁO ĐỐI THỦ (AD SPY ENGINE)
Đây là tính năng tình báo, cho phép bạn "quét" trực tiếp các bài quảng cáo đang chạy thực tế trên Facebook và TikTok.

### Câu hỏi: "Tôi có bắt buộc phải lấy API Tiktok hay Facebook không?"
👉 **Trả lời: KHÔNG BẮT BUỘC, NHƯNG NẾU CÓ THÌ RẤT MẠNH.**
- Nếu bạn KHÔNG điền API: Hệ thống tạo Video (Mode 10) và Tìm kiếm ảnh (Visual Search) vẫn hoạt động bình thường 100%. Tính năng Ad Spy sẽ báo lỗi.
- Nếu bạn ĐIỀN API: Bạn có thể nhập từ khóa (VD: "Kem trị mụn") vào Tab **Ad Spy 🕵️**. Hệ thống sẽ lôi về cho bạn *Toàn bộ lời thoại kịch bản (Copywriting)* mà các đối thủ đang chạy quảng cáo. Bạn chỉ việc copy lời thoại đó, quăng vào phần Kịch bản của Mode 10 để AI làm ra video cho bạn. Không bao giờ bị bí ý tưởng!

### Hướng Dẫn Lấy API Key (Để dùng Ad Spy)
Nếu bạn quyết định dùng tính năng này, hãy làm theo các bước sau và lưu vào file `.env` nằm ở thư mục gốc (`d:\ADS\pipeline\.env`):

**1. Cách lấy META_AD_ACCESS_TOKEN (Dùng cho Facebook)**
- Truy cập [Meta for Developers](https://developers.facebook.com/) và tạo một App (loại None hoặc Business).
- Vào phần **Settings > Basic**, copy `App ID` và `App Secret`.
- Đảm bảo tài khoản Facebook cá nhân của bạn đã được Xác minh danh tính.
- Thêm sản phẩm **Marketing API** vào App.
- Vào phần **Graph API Explorer**, tạo Token với quyền `ads_read`.
- Mở file `.env` và thêm dòng: 
  `META_AD_ACCESS_TOKEN=chuỗi_token_của_bạn`

**2. Cách lấy TIKTOK_AD_ACCESS_TOKEN (Dùng cho TikTok)**
- Truy cập [TikTok for Developers](https://developers.tiktok.com/).
- Đăng ký tài khoản Developer và tạo App.
- Yêu cầu cấp quyền sử dụng **Commercial Content API**.
- Lấy Access Token trong màn hình quản lý App.
- Mở file `.env` và thêm dòng: 
  `TIKTOK_AD_ACCESS_TOKEN=chuỗi_token_của_bạn`

---

## TỔNG QUAN CHI PHÍ
Toàn bộ hệ thống này được thiết kế theo tư duy Zero-Cost (Không tốn tiền):
| Tính năng | Dịch vụ | Chi phí thực tế |
|---|---|---|
| Viết kịch bản / Bóc tách ảnh | Gemini 2.5 Flash | Miễn phí (Free Tier cực dư dả) |
| Giọng đọc (Voiceover) | edge-tts (Microsoft) | Miễn phí (Không giới hạn) |
| Tìm B-Roll | Pexels / Pixabay | Miễn phí (Bản quyền an toàn) |
| Vector Tìm Hình Ảnh | ResNet50 + SQLite | Hoàn toàn Offline (Chạy bằng máy bạn) |
| Quét Quảng Cáo Đối Thủ | Meta / TikTok API | Miễn phí (Dữ liệu công khai) |
| Render / Ghép nhạc | FFmpeg | Hoàn toàn Offline |

---

## KIỂM TRA NHANH (TEST MÔI TRƯỜNG)
Để chắc chắn hệ thống của bạn đã sẵn sàng, hãy mở CMD/Terminal và chạy lệnh sau:
```bash
cd d:\ADS\pipeline
python -c "from core.config import UltimateAdInputs; print('Môi trường Sẵn Sàng!')"
```
Nếu màn hình in ra chữ `Môi trường Sẵn Sàng!`, bạn có thể gõ `python app2.py` để bắt đầu kiếm tiền từ việc làm video quảng cáo!
