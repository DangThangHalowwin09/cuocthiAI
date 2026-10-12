# Template mẫu văn bản đầu ra

Sau khi nhận hồ sơ, hệ thống phân loại vụ việc rồi chọn đúng mẫu:

| Loại vụ việc | Văn bản | File template trong thư mục này |
|---|---|---|
| Hình sự | Cáo trạng (Mẫu 156/HS) | `156-Cáo trạng.docx` |
| Dân sự, hôn nhân gia đình, kinh doanh thương mại, lao động | Phát biểu của Kiểm sát viên (Mẫu 36/DS) | `Mẫu số 36-….docx` (tên bắt đầu bằng "Mẫu số 36") |
| Hành chính | Phát biểu của Kiểm sát viên (Mẫu 35/HC) | `Mẫu số 35-….docx` (tên bắt đầu bằng "Mẫu số 35") |

Cách nhận diện file: tên bắt đầu bằng `Mẫu số 36` hoặc `Mẫu số 35`. Muốn dùng file ở nơi
khác thì đặt biến môi trường `PHAT_BIEU_DS_TEMPLATE_PATH`, `PHAT_BIEU_HC_TEMPLATE_PATH`
(Phát biểu) hoặc `CAO_TRANG_TEMPLATE_PATH` (Cáo trạng).

## Mẫu 156 (Cáo trạng)
Nhận diện vùng nội dung bằng hai đoạn neo: đoạn bắt đầu `Căn cứ các điều` và dòng kết thúc
`…………………………../.`. Giữ nguyên bảng header, tiêu đề, bảng nơi nhận và chữ ký.

## Mẫu 35 / 36 (Phát biểu)
Hệ thống dùng nguyên file mẫu chính thức và:
- bỏ khung "Mẫu số …/Theo QĐ …" và toàn bộ phần "Hướng dẫn sử dụng" ở cuối;
- điền các ô `…(1)…` đến `…(n)…` trong phần đầu trang, căn cứ, "Hôm nay…", "Qua nghiên cứu…",
  số hiệu, ngày tháng, tên vụ án, câu kết;
- thay các ô nội dung `……(9)……`…`……(14)……` (Mẫu 36) hoặc `(6)`…`(11)` (Mẫu 35) bằng: đương sự,
  I.1, I.2, I.3, II, III (mục III bị bỏ nếu không có kiến nghị);
- điền tên Kiểm sát viên ở phần chữ ký.

Nếu thay bằng phiên bản mẫu khác, cần giữ nguyên thứ tự 6 ô nội dung và các đoạn "Hôm nay…",
"Qua nghiên cứu…". Nếu không khớp, hệ thống tự dựng bố cục từ đầu thay vì báo lỗi.
