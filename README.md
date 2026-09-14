# Hệ thống AI hỗ trợ soạn thảo văn bản tố tụng

Ứng dụng hỗ trợ Cuộc thi ứng dụng AI vào công tác chuyên môn, nghiệp vụ
năm 2026 — VKSND tỉnh Nghệ An. **Phạm vi: Hình sự (Cáo trạng) + Dân
sự/Hành chính (Phát biểu của Kiểm sát viên tại phiên tòa sơ thẩm)**.

## 1. Kiến trúc

```
Đề thi (.docx/.pdf)
   → Bước 1: Phân loại vụ việc (Hình sự / Dân sự-Hành chính)
   → Bước 2: Trích xuất dữ kiện có cấu trúc (JSON) — đúng nhánh
   → Bước 3: Tra cứu điều luật liên quan (8 bộ luật đã nạp sẵn, tự
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
│   ├── file_parser.py       # Đọc đề thi .docx/.pdf
│   ├── prompts.py           # TÀI LIỆU 03 — Bộ Prompt (2 nhánh HS + DS/HC)
│   ├── pipeline.py          # Điều phối 5 bước xử lý
│   ├── law_lookup.py        # Tra cứu luật (offline hoặc hybrid)
│   └── docx_writer.py       # Xuất kết quả ra .docx
├── scripts/
│   └── build_law_database.py  # Script tách luật (chạy 1 lần)
├── data/
│   ├── laws/*.json            # 8 bộ luật đã tách sẵn (2.982 điều)
│   ├── laws/source/*.docx,pdf # Nguồn gốc (giữ lại để tách lại khi cần)
│   └── samples/                # Tình huống mẫu để test
└── requirements.txt
```

## 2. Dữ liệu luật đã nạp — 8 bộ luật, 2.982 điều

| Bộ luật | Mã | Số điều | Dùng chủ yếu cho |
|---|---|---|---|
| Bộ luật Hình sự | `blhs` | 408 (426 - 18 điều đã bãi bỏ) | Hình sự |
| Bộ luật Tố tụng hình sự | `blttths` | 510 | Hình sự (thủ tục) |
| Bộ luật Dân sự | `blds` | 689 | Dân sự |
| Bộ luật Tố tụng dân sự | `blttds` | 517 | Dân sự (thủ tục) |
| Luật sửa đổi BLTTDS/LTTHC (2025) | `blttds_suadoi_2025` | 6 | Bổ sung |
| Luật Tố tụng hành chính | `lthc` | 372 | Hành chính |
| Luật Đất đai | `luat_dat_dai` | 260 | Dân sự/Hành chính liên quan đất đai |
| Bộ luật Lao động | `luat_lao_dong` | 220 | Dân sự liên quan lao động |

Đã kiểm tra: **không thiếu điều nào** ngoài các điều đã bị bãi bỏ hợp
pháp (18 điều BLHS về người dưới 18 tuổi, do Luật Tư pháp người chưa
thành niên 2024 thay thế).

**Cách tra cứu:** hoàn toàn bằng code (so khớp từ khóa), tìm trên TOÀN
BỘ 8 bộ luật cùng lúc — không cần biết trước đề thi dùng luật nào, điểm
số từ khóa tự quyết định điều nào liên quan nhất.

## 3. Hai chế độ tra cứu luật (`core/config.py`, biến `LAW_SEARCH_MODE`)

| Chế độ | Mô tả | Khi nào dùng |
|---|---|---|
| `"offline"` (mặc định) | CHỈ tra cứu trong 8 bộ luật đã nạp | **Khuyến nghị cho buổi thi chính thức** — nhanh, miễn phí, không phụ thuộc mạng lúc BTC chấm |
| `"hybrid"` | Offline trước; nếu không tìm đủ, tự động nhờ Gemini tra Google Search bổ sung | Khi đề thi có thể đụng tội danh/quan hệ pháp luật ngoài 8 bộ luật đã nạp |

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

| Thành phần | Quy cách áp dụng |
|---|---|
| Khổ giấy, lề | A4; lề trên/dưới 20mm, trái 30mm, phải 20mm |
| Phông chữ | Times New Roman, toàn bộ văn bản |
| Quốc hiệu / Tiêu ngữ | In hoa/thường, đậm, cỡ 13/14, có gạch chân |
| Tên cơ quan ban hành | In hoa, đậm, cỡ 13, có gạch chân ngắn |
| Số, ký hiệu / Địa danh ngày tháng | Cỡ 13-14; địa danh-ngày tháng in NGHIÊNG |
| Tên loại văn bản | In hoa, đậm, cỡ 14, canh giữa |
| Phần "Căn cứ..." | In NGHIÊNG (đúng quy định) |
| Nội dung | Cỡ 14, đứng |
| Chức vụ người ký / Nơi nhận | 2 cột, đúng cỡ chữ quy định |

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

1. Đặt file `.docx`/`.pdf` toàn văn luật mới vào `data/laws/source/`
2. Thêm 1 mục vào `LAWS_CONFIG` trong `scripts/build_law_database.py`
3. Chạy: `python scripts/build_law_database.py`
4. Xem log — script tự báo điều nào lỗi tách, điều nào bãi bỏ hợp pháp

## 7. Các đánh dấu đặc biệt trong kết quả

| Đánh dấu | Ý nghĩa |
|---|---|
| `[THIẾU DỮ LIỆU: ...]` | Hồ sơ không đủ thông tin cho mục này |
| `[CẦN KIỂM TRA LẠI ĐIỀU LUẬT]` | AI không chắc chắn về điều luật trích dẫn (hoặc dùng nguồn online ở chế độ hybrid) |
| `[TÌNH TIẾT MÂU THUẪN - CẦN XÁC MINH: ...]` | Phát hiện mâu thuẫn giữa các phần hồ sơ |

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
