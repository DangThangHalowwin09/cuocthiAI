# Hệ thống AI hỗ trợ soạn thảo văn bản tố tụng

Ứng dụng hỗ trợ Cuộc thi ứng dụng AI vào công tác chuyên môn, nghiệp vụ
năm 2026 — VKSND tỉnh Nghệ An. **Phạm vi: Hình sự (Cáo trạng) + Dân
sự/Hành chính (Phát biểu của Kiểm sát viên tại phiên tòa sơ thẩm)**.

## 1. Kiến trúc

```
Đề thi (.docx / .doc / .rtf / .pdf — kể cả PDF scan)
   → Bước 0: Đọc file; với bản scan thì nhận dạng chữ (OCR) và CẢNH BÁO
             để người dùng đọc soát, sửa nội dung trước khi chạy
   → Bước 1: Phân loại vụ việc (Hình sự / Dân sự-Hành chính)
   → Bước 2: Trích xuất dữ kiện có cấu trúc (JSON) — đúng nhánh
   → Bước 3: Tra cứu điều luật liên quan (10 văn bản luật đã nạp sẵn, tự
             động, không cần biết trước case_type thuộc luật nào)
   → Bước 4: Soạn bản thảo (Cáo trạng / Phát biểu của KSV)
   → Bước 5: Tự kiểm tra (chống bịa đặt, thiếu mục, xử lý ngoại lệ)
   → Xuất file .docx
```

```
ai-vksnd-project/
├── app.py                  # Giao diện Streamlit (chỉ dùng Gemini)
├── render.yaml              # Cấu hình deploy Render (1-click)
├── .streamlit/config.toml   # Cấu hình Streamlit cho server
├── core/
│   ├── config.py            # Model mặc định + chế độ tra cứu luật
│   ├── model_clients.py     # Gọi Gemini (giữ sẵn code Claude/OpenAI, không dùng)
│   ├── file_parser.py       # Điểm vào đọc đề thi (.docx/.doc/.rtf/.pdf)
│   ├── readers/             # Bộ đọc từng định dạng
│   │   ├── word_docx.py     #   .docx — đúng thứ tự, bảng, chú thích, số tự động
│   │   ├── word_doc.py      #   .doc (Word 97-2003)
│   │   ├── rtf.py           #   .rtf (kể cả RTF đổi đuôi .doc)
│   │   ├── pdf.py           #   .pdf — lớp chữ / scan / lẫn cả hai
│   │   ├── ocr.py           #   OCR: Gemini → EasyOCR → Tesseract
│   │   └── common.py        #   Kiểu kết quả, chấm chất lượng, bảng mã TCVN3
│   ├── prompts.py           # TÀI LIỆU 03 — Bộ Prompt (2 nhánh HS + DS/HC)
│   ├── pipeline.py          # Điều phối 5 bước xử lý
│   ├── law_lookup.py        # Tra cứu luật (offline hoặc hybrid)
│   └── docx_writer.py       # Xuất kết quả ra .docx
├── scripts/
│   ├── build_law_database.py  # Script tách luật (chạy 1 lần)
│   └── doc_thu_file.py        # Đọc thử 1 file, in cách đọc + cảnh báo
├── data/
│   ├── laws/*.json            # 10 văn bản luật đã tách sẵn (3.170 điều)
│   ├── laws/source/*.docx,pdf # Nguồn gốc (giữ lại để tách lại khi cần)
│   └── samples/                # Tình huống mẫu để test
├── requirements.txt
└── requirements-ocr-offline.txt  # Tùy chọn: OCR ngoại tuyến (EasyOCR)
```

## 1b. Định dạng file đầu vào

| Định dạng | Cách đọc | Ghi chú |
| --------- | -------- | ------- |
| `.docx` | Đọc trực tiếp, đúng thứ tự văn bản | Giữ vị trí bảng, chú thích cuối trang (chèn `[Chú thích: ...]`), số thứ tự tự động, text box, đầu/chân trang. File bật Track Changes: đọc theo bản đã chấp nhận thay đổi (có cảnh báo). Ảnh nhúng: cảnh báo; nếu file chỉ toàn ảnh thì tự OCR. |
| `.doc` | Đọc theo cấu trúc chuẩn Word 97-2003 | Số thứ tự tự động (1., a)) KHÔNG lấy được từ `.doc` — nếu quan trọng, lưu lại thành `.docx`. Tự chuyển bảng mã cũ TCVN3 (.VnTime) sang Unicode; bảng mã VNI chỉ cảnh báo. |
| `.rtf` | Đọc trực tiếp | Kể cả file RTF bị đổi đuôi thành `.doc`. |
| `.pdf` có lớp chữ | Đọc trực tiếp | Kể cả PDF bị "chặn sao chép". PDF đặt mật khẩu MỞ thì không đọc được. |
| `.pdf` scan / ảnh chụp | **OCR từng trang** | Xem lưu ý bên dưới. PDF lẫn trang chữ và trang scan: chỉ OCR trang scan. |

Loại file được nhận diện theo nội dung chứ không theo đuôi file.

### ⚠️ LƯU Ý khi dùng PDF / bản scan

PDF **có lớp chữ** (xuất từ Word, tải từ cổng văn bản) đọc chính xác như file
Word. PDF **scan / ảnh chụp** phải qua nhận dạng chữ từ ảnh (OCR) — kết quả
**không bao giờ chính xác tuyệt đối**, và sai nhiều hơn khi:

- bản scan **mờ, nhòe, chữ nhạt**, độ phân giải thấp (dưới ~200 dpi), chụp
  bằng điện thoại bị nghiêng, bóng, lóa;
- **con dấu, chữ ký, ghi chú tay** đè lên chữ; giấy nhàu, ố, bị che góc;
- **chữ viết tay**, bảng biểu nhiều cột, chữ quá nhỏ.

Lỗi hay gặp: **sai/mất dấu tiếng Việt, sai họ tên, ngày tháng, số tiền, số
điều luật**. Với OCR bằng AI (Gemini), chỗ đọc sai có thể **trông vẫn rất hợp
lý** nên khó nhận ra nếu không so với bản gốc.

Vì vậy ứng dụng luôn: (1) báo rõ trang nào đọc bằng OCR, trang nào mờ / độ
phân giải thấp / không đọc được / bị bỏ qua; (2) hiện **nội dung đã đọc** trong
ô sửa được để người dùng đọc soát **trước khi** bấm Chạy xử lý; (3) nhắc mô
hình không tự "sửa giúp" tên riêng, con số, và đánh dấu `[THIẾU DỮ LIỆU]` ở
chỗ `[không đọc được]`; (4) ghi nguồn đầu vào là OCR vào phụ lục kiểm tra nội
bộ. **Nếu có file Word hoặc PDF gốc thì nên dùng file đó thay cho bản scan.**

Kết quả đo trên đề mẫu dựng lại thành bản scan nhân tạo, OCR bằng Tesseract
(tỷ lệ từ đọc đúng; chỉ để hình dung mức độ, không phải cam kết):

| Bản scan | Từ đọc đúng | Hệ thống cảnh báo |
| -------- | ----------- | ----------------- |
| Rõ nét, 200 dpi | ~97% | Chỉ cảnh báo chung "đọc bằng OCR" |
| Mờ nặng | ~75% | "ảnh mờ / nhòe" |
| 100 dpi | ~94% | "độ phân giải thấp" |
| 72 dpi | ~62% | "độ phân giải thấp" |
| Chữ nhạt | ~97% | "chữ nhạt / thiếu tương phản" |

Ngay cả bản rõ nét vẫn sai khoảng 3% số từ, chủ yếu là mất dấu ở tên riêng
("Ngọc" → "Ngoc", "Đào" → "Dao") — đúng loại lỗi nguy hiểm nhất với cáo trạng.

### Công cụ OCR

Thử theo thứ tự (chọn được ở thanh bên của ứng dụng):

1. **Gemini** (mặc định) — gửi ảnh từng trang cho Gemini để chép lại nguyên
   văn. Không cần cài thêm gì, chạy được trên hosting miễn phí. Cần mạng và
   `GOOGLE_API_KEY`. Ảnh tài liệu được gửi tới cùng dịch vụ đang nhận nội dung
   hồ sơ để soạn văn bản.
2. **EasyOCR** (ngoại tuyến) — `pip install -r requirements-ocr-offline.txt`
   (nặng ~2 GB do PyTorch).
3. **Tesseract** (ngoại tuyến) — cài Tesseract (Windows: bản UB-Mannheim, nhớ
   chọn gói **Vietnamese**); ứng dụng tự tìm ở `C:\Program Files\Tesseract-OCR`.

Kiểm tra nhanh một file trước buổi thi, không tốn lượt gọi soạn văn bản:

```bash
python scripts/doc_thu_file.py "duong/dan/de_thi.pdf"
```

## 2. Dữ liệu luật đã nạp — 10 văn bản, 3.170 điều

| Văn bản                              | Mã                                   | Số điều                                  | Dùng chủ yếu cho                    |
| ------------------------------------ | ------------------------------------ | ---------------------------------------- | ----------------------------------- |
| Bộ luật Hình sự (VBHN 2025)          | `blhs`                               | 410 (gồm 217a, 256a; 18 điều đã bãi bỏ)  | Hình sự                             |
| Bộ luật Tố tụng hình sự (VBHN)       | `blttths`                            | 511 (gồm 506a)                           | Hình sự (thủ tục)                   |
| Bộ luật Dân sự                       | `blds`                               | 689                                      | Dân sự                              |
| Bộ luật Tố tụng dân sự               | `blttds`                             | 517                                      | Dân sự (thủ tục)                    |
| Luật sửa đổi BLTTDS/LTTHC (2025)     | `blttds_suadoi_2025`                 | 6                                        | Bổ sung                             |
| Luật Tố tụng hành chính              | `lthc`                               | 372                                      | Hành chính                          |
| Luật Đất đai                         | `luat_dat_dai`                       | 260                                      | Dân sự/Hành chính liên quan đất đai |
| Bộ luật Lao động                     | `luat_lao_dong`                      | 220                                      | Dân sự liên quan lao động           |
| Luật Tư pháp người chưa thành niên   | `luat_tu_phap_nguoi_chua_thanh_nien` | 179                                      | Hình sự (người dưới 18 tuổi)        |
| Nghị quyết 04/2025 (tình tiết giảm nhẹ) | `nq04_2025_tinh_tiet_giam_nhe`    | 6                                        | Hình sự                             |

Đã kiểm tra: **không thiếu điều nào** ngoài 18 điều BLHS (90–107) đã bị bãi
bỏ hợp pháp; không trùng số điều. Script tách luật xử lý được:

- điều chèn thêm có chữ cái (`Điều 217a`, `256a`, `506a`) — tách thành điều riêng;
- tên Phần/Chương/Mục/Tiểu mục — ghi vào trường `phan`/`chuong`/`muc`/`tieu_muc`
  của điều, không lẫn vào nội dung điều đứng trước;
- nguồn PDF — ghép lại các dòng bị ngắt giữa câu, bỏ ký hiệu chú thích `[n]`
  và phần "Xác thực văn bản hợp nhất" ở cuối.

⚠️ `blttds.json` và `lthc.json` là bản gốc; các sửa đổi năm 2025 nằm riêng
trong `blttds_suadoi_2025.json` (chưa hợp nhất vào từng điều). Khi trích điều
về thẩm quyền Tòa án cần đối chiếu cả hai.

**Cách tra cứu:** hoàn toàn bằng code (so khớp từ khóa), tìm trên TOÀN
BỘ 10 văn bản cùng lúc — không cần biết trước đề thi dùng luật nào, điểm
số từ khóa tự quyết định điều nào liên quan nhất.

## 3. Hai chế độ tra cứu luật (`core/config.py`, biến `LAW_SEARCH_MODE`)

| Chế độ                 | Mô tả                                                                         | Khi nào dùng                                                                                 |
| ---------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `"offline"` (mặc định) | CHỈ tra cứu trong các văn bản đã nạp                                           | **Khuyến nghị cho buổi thi chính thức** — nhanh, miễn phí, không phụ thuộc mạng lúc BTC chấm |
| `"hybrid"`             | Offline trước; nếu không tìm đủ, tự động nhờ Gemini tra Google Search bổ sung | Khi đề thi có thể đụng tội danh/quan hệ pháp luật ngoài các văn bản đã nạp                    |

Đổi chế độ: sửa 1 dòng trong `core/config.py`, không cần sửa code khác.
Ở chế độ hybrid, kết quả tra mạng được đánh dấu rõ nguồn khác với dữ
liệu offline, và AI được yêu cầu đánh dấu [CẦN KIỂM TRA LẠI ĐIỀU LUẬT]
khi dùng nguồn này.

## 4. Mẫu văn bản đã nhúng

- **Cáo trạng**: Mẫu số 144/HS-15 (VKSTC ban hành) — bản đầy đủ, có
  hướng dẫn chi tiết từng phần.
- **Phát biểu của Kiểm sát viên (Dân sự/HNGĐ/KDTM/Lao động)**: Mẫu số
  36/DS (QĐ 195/QĐ-VKSTC, 30/6/2026).
- **Phát biểu của Kiểm sát viên (Hành chính)**: Mẫu số 35/HC (cùng QĐ
  195/QĐ-VKSTC) — dùng căn cứ Luật Tố tụng hành chính thay vì BLTTDS.

Hệ thống **tự động chọn đúng mẫu 35 hay 36** dựa vào trường
`loai_vu_viec` được trích xuất ở Bước 2 (xem `core/pipeline.py`, hàm
`_is_hanh_chinh`) — không cần người dùng chỉ định thủ công.

## 4b. Định dạng đầu ra theo Nghị định 30/2020/NĐ-CP

File `.docx` xuất ra tuân theo thể thức tại Phụ lục I, Nghị định
30/2020/NĐ-CP về công tác văn thư (`core/docx_writer.py`):

| Thành phần                        | Quy cách áp dụng                            |
| --------------------------------- | ------------------------------------------- |
| Khổ giấy, lề                      | A4; lề trên/dưới 20mm, trái 30mm, phải 20mm |
| Phông chữ                         | Times New Roman, toàn bộ văn bản            |
| Quốc hiệu / Tiêu ngữ              | In hoa/thường, đậm, cỡ 13/14, có gạch chân  |
| Tên cơ quan ban hành              | In hoa, đậm, cỡ 13, có gạch chân ngắn       |
| Số, ký hiệu / Địa danh ngày tháng | Cỡ 13-14; địa danh-ngày tháng in NGHIÊNG    |
| Tên loại văn bản                  | In hoa, đậm, cỡ 14, canh giữa               |
| Phần "Căn cứ..."                  | In NGHIÊNG (đúng quy định)                  |
| Nội dung                          | Cỡ 14, đứng                                 |
| Chức vụ người ký / Nơi nhận       | 2 cột, đúng cỡ chữ quy định                 |

⚠️ Đây là bản triển khai bám sát Phụ lục I ở mức khung thể thức chính.
Nên đối chiếu trực quan với 1 văn bản mẫu thật của đơn vị trước khi
dùng chính thức, để tinh chỉnh thêm nếu cần (ví dụ độ dài chính xác của
đường gạch chân, khoảng cách dòng chi tiết hơn).

## 5. Cài đặt & chạy local (để test trước khi deploy)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
export GOOGLE_API_KEY="AIzaSy..."  # Windows PowerShell: $env:GOOGLE_API_KEY="..."
streamlit run app.py
```

Người dùng cuối (Ban Tổ chức) **không cần nhập bất kỳ key nào** — chỉ
cần tải đề lên và bấm chạy. Key đọc từ biến môi trường server.

## 6. Nếu cần tách lại dữ liệu luật (luật sửa đổi, hoặc bổ sung luật mới)

1. Đặt file `.docx`/`.doc`/`.pdf` (PDF có lớp chữ) toàn văn luật mới vào `data/laws/source/`
2. Thêm 1 mục vào `LAWS_CONFIG` trong `scripts/build_law_database.py`
3. Chạy: `python scripts/build_law_database.py`
4. Xem log — script tự báo điều nào lỗi tách, điều nào bãi bỏ hợp pháp,
   điều chèn thêm (217a...), và dòng nào giống tiêu đề điều mà không tách được

## 7. Các đánh dấu đặc biệt trong kết quả

| Đánh dấu                                    | Ý nghĩa                                                                            |
| ------------------------------------------- | ---------------------------------------------------------------------------------- |
| `[THIẾU DỮ LIỆU: ...]`                      | Hồ sơ không đủ thông tin cho mục này                                               |
| `[CẦN KIỂM TRA LẠI ĐIỀU LUẬT]`              | AI không chắc chắn về điều luật trích dẫn (hoặc dùng nguồn online ở chế độ hybrid) |
| `[TÌNH TIẾT MÂU THUẪN - CẦN XÁC MINH: ...]` | Phát hiện mâu thuẫn giữa các phần hồ sơ                                            |

## 8. Lưu ý an toàn thông tin

- Không đưa dữ liệu thuộc danh mục bí mật nhà nước/bí mật ngành vào hệ
  thống khi chưa được mã hóa hoặc phê duyệt.
- API key lưu ở biến môi trường server, không commit lên git.
- Kết quả AI tạo ra chỉ là bản thảo hỗ trợ — Kiểm sát viên chịu trách
  nhiệm kiểm tra và quyết định cuối cùng.

## 9. Deploy lên web (Render.com, hỗ trợ domain riêng)

Xem hướng dẫn chi tiết đã trao đổi trong quá trình phát triển — tóm tắt:

1. Đẩy code lên GitHub
2. Tạo Web Service trên render.com, trỏ vào repo (đã có sẵn `render.yaml`)
3. Thêm biến môi trường `GOOGLE_API_KEY` trong Render Dashboard
4. Gắn Custom Domain trong Settings, thêm bản ghi CNAME ở nhà cung cấp domain
5. **Nên nâng lên gói Starter (7 USD/tháng)** ít nhất trong ngày thi để
   tránh app "ngủ" (cold start ~30s) đúng lúc BTC chấm — vì chỉ chạy 1 lần.
