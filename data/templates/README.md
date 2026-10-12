# Template mẫu văn bản đầu ra

Hệ thống phân loại hồ sơ rồi chọn đúng template:

| Loại vụ việc | Văn bản | Template |
|---|---|---|
| Hình sự | Cáo trạng (Mẫu 156/HS) | `156-Cáo trạng.docx` |
| Dân sự, HNGĐ, KDTM, lao động, hành chính | Phát biểu của Kiểm sát viên (Mẫu 36/DS, 35/HC) | `36-Phat-bieu.docx` |

## Mẫu 156 (Cáo trạng)
Ứng dụng nhận diện vùng nội dung bằng hai đoạn neo có sẵn trong file:

- Đoạn bắt đầu bằng `Căn cứ các điều`.
- Đoạn kết thúc bằng dòng `…………………………../.`.

Giữ nguyên bảng header, tiêu đề, bảng nơi nhận và phần ký tên; chỉ thay vùng
hướng dẫn ở giữa. Biến môi trường `CAO_TRANG_TEMPLATE_PATH` trỏ tới file mẫu khác.

## Mẫu Phát biểu
`36-Phat-bieu.docx` là file Word thường, có thể mở ra chỉnh font, lề, tiêu đề.
Nếu chưa có, ứng dụng tự tạo lại. Các token được thay khi xuất kết quả:

`{{DON_VI_CAP_TREN}}`, `{{DON_VI_BAN_HANH}}`, `{{SO_KY_HIEU}}`, `{{DIA_DANH}}`, `{{NAM}}`,
`{{LOAI_PHIEN_TOA}}`, `{{TEN_VU_AN}}`, `{{KIEM_SAT_VIEN}}`, và vùng nội dung
`{{NOI_DUNG_PHAT_BIEU}}` (bắt buộc). Biến môi trường `PHAT_BIEU_TEMPLATE_PATH`
trỏ tới file mẫu khác (ví dụ mẫu chính thức của đơn vị).
