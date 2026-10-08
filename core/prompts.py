"""
BỘ PROMPT VÀ QUY TRÌNH XỬ LÝ
================================================================
File này chính là nội dung kỹ thuật của "TÀI LIỆU 03 - Bộ Prompt và quy
trình xử lý" trong hồ sơ dự thi. Khi viết Báo cáo mô tả mô hình AI và
Tài liệu hướng dẫn sử dụng, hãy trích dẫn/diễn giải lại các prompt ở đây
để đảm bảo 3 tài liệu khớp nhau.

Phạm vi: Hình sự (Cáo trạng) + Dân sự/Hành chính (Phát biểu của Kiểm
sát viên tại phiên tòa sơ thẩm).

LƯU Ý: điều luật KHÔNG còn nhúng cứng trong file này — hệ thống tra cứu
tự động từ data/laws/*.json (xem core/law_lookup.py), phủ 8 bộ luật:
BLHS, BLTTHS, BLDS, BLTTDS, Luật sửa đổi BLTTDS/LTTHC 2025, LTTHC, Luật
Đất đai, Bộ luật Lao động.
"""

# ---------------------------------------------------------------------------
# 0. SYSTEM PROMPT NỀN (áp dụng cho MỌI bước, MỌI loại vụ việc)
# ---------------------------------------------------------------------------
SYSTEM_BASE = """Bạn là hệ thống AI hỗ trợ Kiểm sát viên Viện Kiểm sát nhân dân
soạn thảo văn bản tố tụng (Cáo trạng / Phát biểu của Kiểm sát viên tại
phiên tòa sơ thẩm).

NGUYÊN TẮC BẮT BUỘC (không được vi phạm trong bất kỳ trường hợp nào):
1. CHỈ sử dụng thông tin có trong hồ sơ vụ án được cung cấp. TUYỆT ĐỐI
   KHÔNG tự suy đoán, bịa đặt tình tiết, số liệu, tên người, ngày tháng
   không có trong hồ sơ.
2. Nếu hồ sơ THIẾU dữ liệu cần thiết để hoàn thành một mục nào đó: đánh
   dấu rõ bằng cú pháp [THIẾU DỮ LIỆU: <mô tả cần bổ sung>] tại đúng vị
   trí đó, không tự điền cho đủ.
3. Khi trích dẫn điều luật, CHỈ trích dẫn điều luật có trong phần tài
   liệu tham chiếu được cung cấp kèm theo (mục "NGUỒN: DỮ LIỆU LUẬT ĐÃ
   NẠP SẴN"). Nếu tài liệu tham chiếu có thêm mục "NGUỒN: TRA CỨU BỔ
   SUNG TRÊN INTERNET", chỉ dùng khi thực sự không có lựa chọn nào từ
   dữ liệu nạp sẵn, và PHẢI đánh dấu [CẦN KIỂM TRA LẠI ĐIỀU LUẬT] ngay
   sau điều đó. Nếu không tìm thấy căn cứ phù hợp ở bất kỳ nguồn nào,
   đánh dấu [CẦN KIỂM TRA LẠI ĐIỀU LUẬT] thay vì tự đoán số điều.
4. Nếu yêu cầu vượt ngoài phạm vi soạn thảo văn bản tố tụng (ví dụ: đưa
   ra phán quyết thay thẩm phán, tư vấn ngoài hồ sơ), từ chối và giải
   thích ngắn gọn phạm vi hệ thống có thể hỗ trợ.
5. AI CHỈ hỗ trợ soạn thảo bản thảo. Mọi bản thảo đều phải được Kiểm sát
   viên kiểm tra, chỉnh sửa và chịu trách nhiệm trước khi ban hành chính
   thức. Không được trình bày kết quả như một quyết định cuối cùng.
6. Văn phong: trang trọng, đúng thể thức văn bản hành chính - tố tụng
   Việt Nam, khách quan, không suy diễn theo hướng có lợi hoặc bất lợi
   cho bất kỳ bên nào ngoài căn cứ đã nêu trong hồ sơ.
7. Nếu gặp cụm từ chỉ nơi nộp tiền/thi hành án như "phòng thi hành án",
   "phòng thi hành án dân sự khu vực..." hoặc "thi hành án khu vực...",
   phải chuẩn hóa thành "Cơ quan Thi hành án dân sự có thẩm quyền".
"""

# ---------------------------------------------------------------------------
# GHI CHÚ ĐẦU VÀO KHI HỒ SƠ ĐƯỢC ĐỌC BẰNG OCR (PDF scan / ảnh chụp)
# Được chèn vào TRƯỚC nội dung hồ sơ ở Bước 1 và Bước 2 để mô hình không
# "sửa giúp" các chỗ OCR đọc sai, mà đánh dấu theo đúng quy ước sẵn có.
# ---------------------------------------------------------------------------
OCR_INPUT_NOTE = """[LƯU Ý CỦA HỆ THỐNG — KHÔNG PHẢI NỘI DUNG HỒ SƠ]
Văn bản hồ sơ dưới đây được NHẬN DẠNG TỰ ĐỘNG (OCR) từ bản scan/ảnh chụp nên
có thể sai chữ, sai dấu, sai số. Khi xử lý:
(1) Giữ nguyên họ tên, con số, ngày tháng, số tiền đúng như văn bản; KHÔNG tự
    sửa theo phỏng đoán.
(2) Chỗ có ký hiệu [không đọc được] hoặc chữ vô nghĩa do nhận dạng lỗi: coi là
    thiếu thông tin và đánh dấu [THIẾU DỮ LIỆU: ...], không tự điền.
(3) Nếu cùng một tên/con số xuất hiện với các cách viết khác nhau: ghi nhận là
    [TÌNH TIẾT MÂU THUẪN - CẦN XÁC MINH: ...], không tự chọn một phương án.
[HẾT LƯU Ý]"""

# ---------------------------------------------------------------------------
# BƯỚC 1: PHÂN LOẠI VỤ VIỆC
# ---------------------------------------------------------------------------
CLASSIFY_PROMPT = """Đọc nội dung hồ sơ vụ án dưới đây và xác định đây là:
- "HINH_SU" nếu là vụ án hình sự (có bị can, hành vi bị nghi phạm tội, tội danh theo Bộ luật Hình sự)
- "DAN_SU_HANH_CHINH" nếu là vụ án dân sự, hôn nhân gia đình, kinh doanh thương mại,
  lao động, hoặc khiếu kiện hành chính (có nguyên đơn/bị đơn hoặc người khởi kiện/người bị kiện)

CHỈ trả lời đúng một trong hai từ trên, không giải thích thêm.

--- NỘI DUNG HỒ SƠ ---
{input_text}
--- HẾT HỒ SƠ ---
"""

# ---------------------------------------------------------------------------
# BƯỚC 2: TRÍCH XUẤT DỮ KIỆN CÓ CẤU TRÚC
# ---------------------------------------------------------------------------
EXTRACT_PROMPT_HS = """Nhiệm vụ: trích xuất ĐẦY ĐỦ dữ kiện từ hồ sơ vụ án HÌNH SỰ dưới đây
thành định dạng JSON có cấu trúc. Chỉ lấy thông tin CÓ TRONG hồ sơ.

QUY TẮC TRÍCH XUẤT:
- Đọc kỹ TOÀN BỘ hồ sơ (phần căn cứ, nội dung vụ án, lý lịch, vật chứng, kết
  luận…). Hồ sơ thường là Bản kết luận điều tra hoặc tóm tắt tình huống: số,
  ngày, cơ quan ra quyết định, lý lịch từng bị can… thường nằm ngay ở đó.
- CHÉP NGUYÊN VĂN số hiệu, ngày tháng, tên cơ quan, họ tên, địa chỉ, số tiền.
  Không tóm tắt làm mất chi tiết, không đổi cách viết.
- Chỉ ghi "THIẾU DỮ LIỆU" cho một trường khi hồ sơ THẬT SỰ không nhắc tới ở
  bất kỳ chỗ nào. Nếu hồ sơ chỉ có một phần (ví dụ chỉ có năm sinh) thì ghi
  đúng phần đó (ví dụ "1966"), không ghi THIẾU DỮ LIỆU.
- "tien_an", "tien_su": chép đúng như mục "Tiền án, tiền sự" của hồ sơ. Nếu
  hồ sơ ghi "Không" thì ghi "Không"; nếu hồ sơ để trống mục này thì ghi
  "THIẾU DỮ LIỆU" — KHÔNG tự suy ra là "không có". Các bản án/xử phạt hành
  chính liệt kê ở mục "Nhân thân" thì đưa NGUYÊN VĂN vào "nhan_than", TUYỆT
  ĐỐI không chuyển thành tiền án/tiền sự (đó là đánh giá pháp lý của Kiểm sát viên).
- "vai_tro": CHỈ ghi vai trò nếu hồ sơ nêu rõ (chủ mưu, cầm đầu, giúp sức,
  người thực hành…). Hồ sơ không nêu thì ghi "THIẾU DỮ LIỆU" — không tự đặt
  vai trò. Giữ nguyên THỨ TỰ các bị can như hồ sơ liệt kê.
- Hành vi: ghi riêng hành vi CỤ THỂ của TỪNG bị can (làm gì, ở đâu, dùng vật gì,
  đối với ai, hậu quả), chép sát hồ sơ.
- Mỗi bị can là một phần tử riêng; sắp xếp theo vai trò từ cao xuống thấp
  (chủ mưu/cầm đầu/chủ chốt → đồng phạm tích cực → giúp sức).

Cấu trúc JSON cần trả về:
{{
  "vks_truy_to": {{
    "cap": "khu vực | tỉnh | THIẾU DỮ LIỆU",
    "so_khu_vuc": "số hiệu VKSND khu vực nếu có (ví dụ 4), không có thì để rỗng",
    "tinh_thanh": "tên tỉnh/thành phố, ví dụ Nghệ An",
    "ten_day_du": "ví dụ: Viện kiểm sát nhân dân khu vực 4 tỉnh Nghệ An",
    "co_so_xac_dinh": "nêu ngắn gọn dựa vào đâu (VKS đã phê chuẩn khởi tố bị can / nơi xảy ra tội phạm / cơ quan điều tra)"
  }},
  "co_quan_dieu_tra": "",
  "noi_xay_ra_toi_pham": "",
  "quyet_dinh_khoi_to_vu_an": [
    {{"so": "", "ngay": "", "co_quan": "", "toi_danh": "", "dieu_khoan": "", "ghi_chu": "quyết định thay đổi/bổ sung nếu có"}}
  ],
  "quyet_dinh_khoi_to_bi_can": [
    {{"bi_can": "", "so": "", "ngay": "", "co_quan": "",
      "phe_chuan": {{"so": "", "ngay": "", "co_quan": ""}},
      "toi_danh": "", "dieu_khoan": ""}}
  ],
  "quyet_dinh_khac": [
    {{"loai": "nhập | tách | phục hồi | thay đổi, bổ sung | khác", "so": "", "ngay": "", "co_quan": ""}}
  ],
  "ket_luan_dieu_tra": {{"so": "", "ngay": "", "co_quan": "", "ket_luan_bo_sung": ""}},
  "bi_can": [
    {{
      "ho_ten": "", "ten_goi_khac": "", "gioi_tinh": "",
      "ngay_sinh": "", "noi_sinh": "",
      "noi_cu_tru": "", "quoc_tich": "", "dan_toc": "", "ton_giao": "",
      "nghe_nghiep": "", "chuc_vu": "", "trinh_do_hoc_van": "",
      "cha_me_vo_con": "", "tien_an": "", "tien_su": "",
      "nhan_than": "chép ĐẦY ĐỦ từng mục nhân thân hồ sơ nêu (ngày, cơ quan, hình thức xử phạt, tội danh/hành vi); không có thì để rỗng",
      "bien_phap_ngan_chan": "loại biện pháp, từ ngày nào, tại đâu",
      "nam_sinh": "", "vai_tro": "",
      "toi_danh_dieu_khoan_theo_ho_so": "tội danh, điểm/khoản/điều theo hồ sơ nêu"
    }}
  ],
  "bi_hai": [{{"ho_ten": "", "thong_tin_khac": ""}}],
  "nguoi_lien_quan_nguoi_lam_chung": [{{"ho_ten": "", "tu_cach": ""}}],
  "tuoi_tai_thoi_diem_pham_toi": "",
  "la_nguoi_duoi_18_tuoi": "có | không | THIẾU DỮ LIỆU",
  "toi_danh_nghi_van": "",
  "dieu_luat_blhs_duoc_nhac_toi": ["chỉ số điều của Bộ luật Hình sự được hồ sơ nêu, ví dụ 318, 178"],
  "hanh_vi_pham_toi_tom_tat": "",
  "hanh_vi_tung_bi_can": [{{"bi_can": "", "hanh_vi_cu_the": "", "toi_danh_dieu_khoan": ""}}],
  "thiet_hai_va_ty_le_thuong_tich": ["giá trị thiệt hại tài sản, tỷ lệ tổn thương cơ thể, số tiền định giá… kèm đối tượng bị thiệt hại"],
  "hanh_vi_khong_truy_to_hoac_xu_ly_khac": ["hành vi/đối tượng hồ sơ nêu là không cấu thành tội phạm, xử lý hành chính, nhắc nhở, không khởi tố… kèm lý do và căn cứ"],
  "nguyen_nhan_dieu_kien": "",
  "toa_an_co_tham_quyen": "tên Tòa án nếu hồ sơ nêu hoặc suy ra chắc chắn từ nơi xảy ra tội phạm/Viện kiểm sát truy tố; không chắc thì THIẾU DỮ LIỆU",
  "thoi_gian_dia_diem": "",
  "chung_cu": ["..."],
  "tinh_tiet_tang_nang": ["tình tiết tăng nặng của TỪNG bị can, ghi rõ ai + điều khoản nếu hồ sơ nêu"],
  "tinh_tiet_giam_nhe": ["tình tiết giảm nhẹ của TỪNG bị can, ghi rõ ai + điều khoản nếu hồ sơ nêu"],
  "vat_chung_tai_lieu": ["đồ vật, tiền, phương tiện thu giữ/tạm giữ và việc xử lý"],
  "phan_dan_su": "bồi thường, khắc phục hậu quả, yêu cầu của bị hại (nếu có)",
  "ho_so": {{"so_tap": "", "so_to": ""}},
  "qua_trinh_dieu_tra_tom_tat": "",
  "ghi_chu_thieu_du_lieu": ["liệt kê các thông tin quan trọng THẬT SỰ không có trong hồ sơ"]
}}

CHỈ trả về JSON hợp lệ, không thêm văn bản giải thích trước/sau.

--- NỘI DUNG HỒ SƠ ---
{input_text}
--- HẾT HỒ SƠ ---
"""

EXTRACT_PROMPT_DS = """Nhiệm vụ: trích xuất dữ kiện từ hồ sơ vụ án DÂN SỰ/HÔN NHÂN GIA
ĐÌNH/KINH DOANH THƯƠNG MẠI/LAO ĐỘNG/HÀNH CHÍNH dưới đây thành định dạng
JSON có cấu trúc. Chỉ lấy thông tin CÓ TRONG hồ sơ. Trường nào không có
thông tin thì ghi giá trị "THIẾU DỮ LIỆU".

Cấu trúc JSON cần trả về:
{{
  "loai_vu_viec": "dân sự | hôn nhân gia đình | kinh doanh thương mại | lao động | hành chính",
  "nguyen_don_nguoi_khoi_kien": [{{"ho_ten": ""}}],
  "bi_don_nguoi_bi_kien": [{{"ho_ten": ""}}],
  "nguoi_co_quyen_loi_nghia_vu_lien_quan": [{{"ho_ten": ""}}],
  "quan_he_phap_luat_tranh_chap": "",
  "yeu_cau_khoi_kien": "",
  "chung_cu_tai_lieu": ["..."],
  "qua_trinh_to_tung_tom_tat": "",
  "toa_an_thu_ly": "",
  "ghi_chu_thieu_du_lieu": ["liệt kê các thông tin quan trọng còn thiếu"]
}}

CHỈ trả về JSON hợp lệ, không thêm văn bản giải thích trước/sau.

--- NỘI DUNG HỒ SƠ ---
{input_text}
--- HẾT HỒ SƠ ---
"""

# ---------------------------------------------------------------------------
# MẪU THAM CHIẾU (thể thức chuẩn) — lấy từ mẫu chính thức do đội thi cung cấp
# ---------------------------------------------------------------------------

# Mẫu Cáo trạng — theo Mẫu số 144/HS-15 (QĐ-VKSTC), bản đầy đủ có
# footnote hướng dẫn từng phần.
MAU_CAO_TRANG_THAM_CHIEU = """
Mẫu số 144/HS-15 (Ban hành theo Quyết định của VKSND tối cao)

[TÊN VIỆN KIỂM SÁT CẤP TRÊN TRỰC TIẾP]                 CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
[TÊN VIỆN KIỂM SÁT BAN HÀNH]                            Độc lập - Tự do - Hạnh phúc
Số: .../CT-VKS...-...                                   [Địa danh], ngày ... tháng ... năm 20...

CÁO TRẠNG

VIỆN TRƯỞNG VIỆN KIỂM SÁT [tên đơn vị]

Căn cứ các điều 41, 236, 239 và 243 Bộ luật Tố tụng hình sự;

Căn cứ Quyết định khởi tố vụ án hình sự số... ngày... tháng... năm...
của... về tội... quy định tại khoản... Điều... Bộ luật Hình sự (hoặc
Quyết định thay đổi, bổ sung quyết định khởi tố vụ án hình sự, nếu có);

Căn cứ Quyết định khởi tố bị can số... ngày... tháng... năm... của...
đối với... về tội... quy định tại khoản... Điều... Bộ luật Hình sự
(hoặc Quyết định thay đổi, bổ sung quyết định khởi tố bị can, nếu có);

Căn cứ Bản kết luận điều tra số... ngày... tháng... năm... của... và
Bản kết luận điều tra bổ sung số... ngày... tháng... năm... (nếu có).

Trên cơ sở kết quả điều tra đã xác định được như sau:

- Diễn biến hành vi phạm tội (hành vi của bị can; ngày, giờ, tháng, năm;
  địa điểm; thủ đoạn; động cơ, mục đích; tính chất mức độ thiệt hại do
  hành vi phạm tội gây ra; nguyên nhân, điều kiện...);
- Phân tích, đánh giá tình tiết tăng nặng, giảm nhẹ và tình tiết khác có
  ý nghĩa đối với vụ án;
- Việc thu giữ, tạm giữ tài liệu, đồ vật; xử lý vật chứng;
- Phần dân sự (nếu có);

Căn cứ vào các tình tiết và chứng cứ nêu trên,

KẾT LUẬN

- Tổng hợp ngắn gọn hành vi phạm tội của bị can hoặc từng bị can; tính
  chất, mức độ, hậu quả của hành vi phạm tội; vai trò của từng bị can
  trong vụ án (sắp xếp theo mức độ nguy hiểm của hành vi, từ tội đặc
  biệt nghiêm trọng đến ít nghiêm trọng).
- Như vậy có đủ căn cứ để xác định các bị can có lý lịch dưới đây đã
  phạm tội (các tội) như sau:
  + Họ và tên, tên gọi khác; giới tính, ngày, tháng, năm sinh, nơi sinh,
    nơi cư trú, quốc tịch, dân tộc, tôn giáo, nghề nghiệp, chức vụ trước
    khi phạm tội, trình độ học vấn;
  + Họ và tên cha, mẹ, anh chị em ruột, vợ/chồng, con;
  + Tiền sự (chỉ ghi tiền sự còn thời hạn xem xét); Tiền án (ngày xét
    xử, Tòa án xét xử, tội danh, điểm/khoản/điều BLHS, hình phạt);
  + Biện pháp ngăn chặn, biện pháp cưỡng chế đang áp dụng (nếu có), từ
    ngày nào đến ngày nào, tại đâu.
- Khẳng định: Bị can... phạm tội gì, theo quy định tại điểm, khoản,
  điều nào của Bộ luật Hình sự (lưu ý trích dẫn điều luật chính xác).
  Được áp dụng tình tiết tăng nặng, giảm nhẹ trách nhiệm hình sự theo
  quy định tại điểm, khoản, điều nào của Bộ luật Hình sự.

Bởi các lẽ trên,

QUYẾT ĐỊNH

1. Truy tố ra trước Tòa án [tên Tòa án có thẩm quyền] để xét xử bị can
   (hoặc các bị can) có lý lịch và hành vi nêu trên về tội hoặc các tội
   [ghi rõ tội danh, điểm, khoản, điều của Bộ luật Hình sự].

2. Kèm theo Cáo trạng có:
   - Hồ sơ vụ án gồm:... tập, bằng... tờ; đánh số thứ tự từ 01 đến...
   - Bản kê vật chứng (nếu có).
   - Danh sách những người Viện kiểm sát đề nghị Tòa án triệu tập đến
     phiên tòa.

Nơi nhận:                                          VIỆN TRƯỞNG
- Tòa án có thẩm quyền xét xử;                     (Ký tên, đóng dấu)
- VKS cấp trên trực tiếp;
- Bị can;
- Lưu: HSVA, HSKS, VP.
"""

# Mẫu Phát biểu của Kiểm sát viên — Mẫu số 36/DS (theo QĐ số 195/QĐ-VKSTC
# ngày 30/6/2026), dùng cho phiên tòa/phiên họp sơ thẩm dân sự, hôn nhân
# gia đình, kinh doanh thương mại, lao động.
MAU_BAI_PHAT_BIEU_THAM_CHIEU = """
Mẫu số 36/DS (theo Quyết định số 195/QĐ-VKSTC ngày 30/6/2026)

[VIỆN KIỂM SÁT NHÂN DÂN CẤP TRÊN]                       CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
[VIỆN KIỂM SÁT NHÂN DÂN BAN HÀNH]                       Độc lập - Tự do - Hạnh phúc
Số:.../PB-VKS-...                                       [Địa danh], ngày... tháng... năm 20...

PHÁT BIỂU
Của Kiểm sát viên tại phiên tòa (phiên họp) sơ thẩm...

Căn cứ Điều 27 Luật Tổ chức Viện kiểm sát nhân dân năm 2014 (sửa đổi,
bổ sung bởi Luật số 82/2025/QH15);

Căn cứ các điều 21, 58,... Bộ luật Tố tụng dân sự (đã được sửa đổi, bổ
sung); [Nếu là vụ án hành chính, thay bằng căn cứ tương ứng của Luật Tố
tụng hành chính]

Hôm nay, Tòa án nhân dân... mở phiên tòa (phiên họp) sơ thẩm giải quyết
vụ án (việc)... về..., giữa các đương sự: [ghi đầy đủ thông tin đương
sự và người tham gia tố tụng khác nếu có]

Qua nghiên cứu hồ sơ vụ án (việc)..., kết quả kiểm sát việc tuân theo
pháp luật của Tòa án nhân dân... và tham gia phiên tòa (phiên họp) sơ
thẩm hôm nay, đại diện Viện kiểm sát nhân dân... phát biểu ý kiến như
sau:

I. VỀ VIỆC TUÂN THEO PHÁP LUẬT TỐ TỤNG

1. Việc tuân theo pháp luật tố tụng của Thẩm phán
[Nêu rõ Thẩm phán đã thực hiện đúng, đầy đủ hay chưa đúng quy định về
thụ lý, xác minh thu thập chứng cứ, giao nộp/tiếp cận/công khai chứng
cứ, áp dụng biện pháp khẩn cấp tạm thời (nếu có)...]

2. Việc tuân theo pháp luật tố tụng của Hội đồng xét xử, Thư ký phiên tòa
[Nêu rõ HĐXX, Thư ký đã thực hiện đúng, đầy đủ hay chưa đúng quy định]

3. Việc chấp hành pháp luật của người tham gia tố tụng
[Nêu rõ đương sự và người tham gia tố tụng khác đã thực hiện đúng, đầy
đủ quyền và nghĩa vụ tố tụng hay chưa]

II. VỀ VIỆC GIẢI QUYẾT VỤ ÁN (VIỆC)...
[Phân tích chứng cứ, quan hệ pháp luật tranh chấp, căn cứ pháp luật áp
dụng, quan điểm của Viện kiểm sát về hướng giải quyết]

III. YÊU CẦU, KIẾN NGHỊ KHẮC PHỤC VI PHẠM (NẾU CÓ)
[Nếu phát hiện vi phạm tố tụng nghiêm trọng, nêu rõ nội dung kiến nghị]

Trên đây là ý kiến của đại diện Viện kiểm sát nhân dân... về việc tuân
theo pháp luật tố tụng và giải quyết vụ án (việc)... nêu trên.

Nơi nhận:                                          KIỂM SÁT VIÊN
- Tòa án xét xử sơ thẩm;                           (Ký tên, ghi rõ họ tên)
- Lãnh đạo cơ quan, đơn vị phụ trách (để báo cáo);
- Lưu: VT, HSKS.
"""

# Mẫu Phát biểu của Kiểm sát viên tại phiên tòa HÀNH CHÍNH — Mẫu số
# 35/HC (theo QĐ số 195/QĐ-VKSTC ngày 30/6/2026). Dùng riêng cho vụ án
# hành chính, KHÁC với Mẫu 36/DS (dân sự/HNGĐ/KDTM/lao động) — căn cứ
# pháp lý và một số chi tiết khác nhau (Luật TTHC thay vì BLTTDS).
MAU_PHAT_BIEU_HANH_CHINH_THAM_CHIEU = """
Mẫu số 35/HC (theo Quyết định số 195/QĐ-VKSTC ngày 30/6/2026)

[VIỆN KIỂM SÁT NHÂN DÂN CẤP TRÊN]                       CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
[VIỆN KIỂM SÁT NHÂN DÂN BAN HÀNH]                       Độc lập - Tự do - Hạnh phúc
Số:.../PB-VKS-HC                                        [Địa danh], ngày... tháng... năm 20...

PHÁT BIỂU
Của Kiểm sát viên tại phiên tòa hành chính sơ thẩm

Căn cứ Luật Tổ chức Viện kiểm sát nhân dân số 63/2014/QH13 đã được sửa
đổi, bổ sung bởi Luật số 82/2025/QH15;

Căn cứ các điều 25, 43,... Luật Tố tụng hành chính số 93/2015/QH13 đã
được sửa đổi, bổ sung bởi Luật số 55/2019/QH14, Luật số 34/2024/QH15 và
Luật số 85/2025/QH15. [Thủ tục thông thường: dẫn Điều 190 LTTHC; thủ
tục rút gọn: dẫn Điều 249 LTTHC]

Căn cứ Điều 28 Thông tư liên tịch số 08/2026/TTLT-VKSNDTC-TANDTC ngày
10/3/2026 quy định việc phối hợp giữa Viện kiểm sát nhân dân và Tòa án
nhân dân trong việc thi hành một số quy định của Luật Tố tụng hành chính.

Hôm nay, Tòa án nhân dân... mở phiên tòa sơ thẩm giải quyết vụ án hành
chính về... (ghi trích yếu khiếu kiện, ví dụ: Khiếu kiện quyết định thu
hồi đất), giữa: [ghi đầy đủ thông tin đương sự và người tham gia tố
tụng khác nếu có]

Qua nghiên cứu hồ sơ vụ án, kết quả kiểm sát việc tuân theo pháp luật
của Tòa án nhân dân... và tham gia phiên tòa hành chính sơ thẩm hôm
nay, đại diện Viện kiểm sát nhân dân... phát biểu ý kiến như sau:

I. VỀ VIỆC TUÂN THEO PHÁP LUẬT TỐ TỤNG

1. Việc tuân theo pháp luật tố tụng của Thẩm phán
[Nêu rõ Thẩm phán được phân công thụ lý đã thực hiện đúng, đầy đủ hay
chưa đúng quy định về thụ lý vụ án; xác minh thu thập tài liệu, chứng
cứ; giao nộp/tiếp cận/công khai chứng cứ và đối thoại; áp dụng (thay
đổi, hủy bỏ) biện pháp khẩn cấp tạm thời (nếu có). Nếu là thủ tục rút
gọn thì bỏ phần nhận xét về Hội đồng xét xử ở mục 2.]

2. Việc tuân theo pháp luật tố tụng của Hội đồng xét xử, Thư ký phiên tòa
[Nêu rõ HĐXX, Thư ký đã thực hiện đúng, đầy đủ hay chưa đúng quy định
của Luật Tố tụng hành chính về việc xét xử sơ thẩm]

3. Việc chấp hành pháp luật của người tham gia tố tụng
[Nêu rõ người khởi kiện, người bị kiện, người có quyền lợi nghĩa vụ
liên quan và người tham gia tố tụng khác đã thực hiện đúng, đầy đủ
quyền và nghĩa vụ tố tụng hay chưa]

II. VỀ VIỆC GIẢI QUYẾT VỤ ÁN
[Phân tích tính hợp pháp của quyết định hành chính/hành vi hành chính
bị khiếu kiện, căn cứ pháp luật áp dụng, quan điểm của Viện kiểm sát về
hướng giải quyết]

III. YÊU CẦU, KIẾN NGHỊ KHẮC PHỤC VI PHẠM (NẾU CÓ)
[Nếu phát hiện vi phạm tố tụng, nêu rõ tư cách tố tụng của người vi
phạm, nội dung vi phạm, quy định bị vi phạm, tác động đến việc xét xử,
và yêu cầu Hội đồng xét xử có biện pháp xử lý]

Trên đây là ý kiến của đại diện Viện kiểm sát nhân dân... về việc tuân
theo pháp luật tố tụng và giải quyết vụ án hành chính nêu trên.

Nơi nhận:                                          KIỂM SÁT VIÊN
- Tòa án xét xử sơ thẩm;                           (Ký tên, ghi rõ họ tên)
- Lãnh đạo cơ quan, đơn vị phụ trách (để báo cáo);
- Lưu: VT, HSKS.
"""

# ---------------------------------------------------------------------------
# BƯỚC 3: SOẠN BẢN THẢO
# ---------------------------------------------------------------------------
DRAFT_PROMPT_HS = """Dựa trên dữ kiện JSON dưới đây, soạn phần NỘI DUNG CÁO TRẠNG
theo đúng cấu trúc mẫu tham chiếu. Cấu trúc bắt buộc:

- Phần căn cứ (Quyết định khởi tố vụ án, khởi tố bị can, kết luận điều tra)
- Phần diễn biến hành vi phạm tội, tình tiết tăng nặng/giảm nhẹ
- KẾT LUẬN (tổng hợp hành vi, lý lịch bị can, khẳng định tội danh + điều luật)
- QUYẾT ĐỊNH (truy tố, hồ sơ kèm theo)

NGUYÊN TẮC ĐIỀN DỮ LIỆU — QUAN TRỌNG NHẤT:
(a) DỮ KIỆN ĐÃ CÓ THÌ PHẢI ĐIỀN. Cấm viết "số... ngày... tháng... năm..." hay
    [THIẾU DỮ LIỆU] cho thông tin mà JSON đã có. Chỉ để dấu hiệu thiếu khi
    JSON thật sự ghi "THIẾU DỮ LIỆU" hoặc để trống.
(b) PHẦN CĂN CỨ: mỗi quyết định một đoạn "Căn cứ ..." điền đủ số, ngày, cơ quan
    ban hành, tội danh, điều khoản lấy từ "quyet_dinh_khoi_to_vu_an",
    "quyet_dinh_khoi_to_bi_can" (mỗi bị can một đoạn, kèm quyết định phê chuẩn
    của Viện kiểm sát nếu có), "quyet_dinh_khac", "ket_luan_dieu_tra".
(c) TÌNH TIẾT TĂNG NẶNG / GIẢM NHẸ: liệt kê cụ thể từng tình tiết của từng bị
    can từ "tinh_tiet_tang_nang", "tinh_tiet_giam_nhe", kèm điểm/khoản Điều 51,
    Điều 52 BLHS nếu hồ sơ nêu hoặc điều luật tra cứu đủ để xác định. Nếu hồ
    sơ không có tình tiết nào thì viết rõ "không có tình tiết tăng nặng
    trách nhiệm hình sự" / "không có tình tiết giảm nhẹ..." theo hồ sơ — chỉ
    ghi [THIẾU DỮ LIỆU] khi hồ sơ không cho phép kết luận.
(d) TỘI DANH: nếu hồ sơ đã nêu tội danh, điểm, khoản, điều (kết luận điều tra,
    quyết định khởi tố) thì ghi đúng như vậy trong phần Khẳng định và phần
    QUYẾT ĐỊNH, KHÔNG viết thành gợi ý hay [THIẾU DỮ LIỆU]. Nếu hồ sơ chưa nêu
    nhưng hành vi và con số trong hồ sơ ĐỦ dấu hiệu của một tội mà điều luật
    đó có trong mục "ĐIỀU LUẬT LIÊN QUAN" thì HÃY KẾT LUẬN tội danh và xác
    định điểm/khoản/điều bằng cách đối chiếu trực tiếp với văn bản điều luật
    (ví dụ mức tiền, vai trò tổ chức, tái phạm), đồng thời ghi thêm một dòng
    đúng mẫu "[GỢI Ý CỦA AI, KSV CẦN XÁC NHẬN LẠI: ... ]" nêu căn cứ đối
    chiếu. Chỉ dùng [THIẾU DỮ LIỆU: tội danh] khi hồ sơ không đủ dấu hiệu
    của bất kỳ tội nào trong điều luật đã tra cứu.
(e) Khi hồ sơ có nhiều bị can, KẾT LUẬN phải nêu riêng từng bị can: phạm tội
    gì, điều khoản nào, áp dụng tình tiết nào.
(f) THỨ TỰ BỊ CAN: dùng MỘT thứ tự duy nhất (thứ tự trong "bi_can") ở MỌI nơi:
    căn cứ khởi tố, tình tiết, lý lịch, khẳng định, quyết định truy tố.
(g) KHÔNG TỰ ĐẶT VAI TRÒ: chỉ nêu "chủ mưu", "cầm đầu", "đồng phạm tích cực",
    "giúp sức"… khi JSON có ghi. Hồ sơ không nêu thì chỉ mô tả hành vi cụ thể
    của từng người, không gán nhãn vai trò.
(h) TIỀN ÁN, TIỀN SỰ, NHÂN THÂN: chép đúng JSON. Không đổi các lần xử phạt
    hành chính / bản án ở "nhan_than" thành tiền án hoặc tiền sự. Nếu "tien_an"
    hoặc "tien_su" là THIẾU DỮ LIỆU thì ghi [THIẾU DỮ LIỆU: hồ sơ để trống mục
    tiền án, tiền sự], không tự điền "Không".
(i) DIỄN BIẾN HÀNH VI PHẠM TỘI phải ĐẦY ĐỦ, không tóm tắt một đoạn chung:
    - mở đầu: thời gian, địa điểm, nguyên nhân/mâu thuẫn, diễn biến chung;
    - tiếp theo: MỖI bị can một đoạn nêu hành vi cụ thể ("hanh_vi_tung_bi_can");
    - hậu quả: thiệt hại tài sản (kèm giá trị), tỷ lệ thương tích, người bị hại
      ("thiet_hai_va_ty_le_thuong_tich");
    - nguyên nhân, điều kiện ("nguyen_nhan_dieu_kien");
    - nêu các hành vi/đối tượng mà hồ sơ đã xử lý khác (không truy tố, xử phạt
      hành chính, nhắc nhở) trong "hanh_vi_khong_truy_to_hoac_xu_ly_khac".
(j) TÒA ÁN trong QUYẾT ĐỊNH: ghi tên Tòa án ở "toa_an_co_tham_quyen" nếu có; chỉ
    khi đó trống mới ghi [THIẾU DỮ LIỆU: tên Tòa án có thẩm quyền].

LÝ LỊCH BỊ CAN: mỗi bị can một khối, đánh số THỨ TỰ 1, 2, 3, ... (không lặp
số 1), sắp xếp theo vai trò từ cao xuống thấp. Dùng đúng cấu trúc:
[SỐ THỨ TỰ]. Bị can: [HỌ TÊN]
- Tên gọi khác: [giá trị] - Giới tính: [giá trị]
- Sinh ngày: [ngày sinh] tại: [nơi sinh]
- Cư trú: [địa chỉ]
- Quốc tịch: [giá trị] - Dân tộc: [giá trị] - Tôn giáo: [giá trị]
- Nghề nghiệp: [giá trị] - Trình độ học vấn: [giá trị]
- Họ tên cha, mẹ, vợ/chồng, con: [giá trị]
- Tiền án, tiền sự: [giá trị]
- Nhân thân: [liệt kê đầy đủ từng mục trong "nhan_than"; bỏ dòng này nếu JSON không có nhân thân]
- Biện pháp ngăn chặn, biện pháp cưỡng chế đang áp dụng: [giá trị]
Điền giá trị lấy từ JSON. Trường nào JSON không có thì ghi [THIẾU DỮ LIỆU],
nhưng nếu nhiều trường liền nhau cùng thiếu thì gộp thành MỘT dấu
[THIẾU DỮ LIỆU: ...] duy nhất cho cả dòng. Chỉ có năm sinh thì ghi đúng năm sinh.

Hai tiêu đề KẾT LUẬN và QUYẾT ĐỊNH phải nằm RIÊNG MỘT DÒNG, chỉ gồm đúng chữ
"KẾT LUẬN" / "QUYẾT ĐỊNH" (không thêm chú thích, ngoặc đơn hay ký hiệu).

CHỈ trích dẫn điều luật có trong mục "ĐIỀU LUẬT LIÊN QUAN" bên dưới. Không
tự bịa tình tiết, số liệu, tên người không có trong JSON.

CHỈ xuất phần nội dung từ "Căn cứ..." đến hết phần "QUYẾT ĐỊNH". Không
xuất quốc hiệu, tiêu ngữ, tên cơ quan, số ký hiệu, địa danh ngày tháng,
tiêu đề CÁO TRẠNG, dòng "VIỆN TRƯỞNG VIỆN KIỂM SÁT ...", phần Nơi nhận, chức
danh hoặc chữ ký; các phần đó đã được giữ nguyên/điền trong template mẫu 156.

--- MẪU THAM CHIẾU ---
{mau_tham_chieu}

--- ĐIỀU LUẬT LIÊN QUAN ---
{dieu_luat_lien_quan}

--- DỮ KIỆN VỤ ÁN (JSON) ---
{facts_json}
"""

DRAFT_PROMPT_DS = """Dựa trên dữ kiện JSON dưới đây, soạn bản thảo PHÁT BIỂU CỦA
KIỂM SÁT VIÊN tại phiên tòa sơ thẩm, theo đúng thể thức mẫu tham chiếu
được cung cấp bên dưới (mẫu đã được chọn đúng theo loại vụ việc — dân
sự/HNGĐ/KDTM/lao động dùng Mẫu 36/DS, hành chính dùng Mẫu 35/HC). Cấu
trúc bắt buộc:

I. VỀ VIỆC TUÂN THEO PHÁP LUẬT TỐ TỤNG (3 mục nhỏ: Thẩm phán; Hội đồng
   xét xử/Thư ký; người tham gia tố tụng)
II. VỀ VIỆC GIẢI QUYẾT VỤ ÁN (phân tích chứng cứ, quan hệ pháp luật
    tranh chấp/tính hợp pháp của quyết định hành chính, căn cứ pháp
    luật, quan điểm/đề nghị của VKS)
III. YÊU CẦU, KIẾN NGHỊ KHẮC PHỤC VI PHẠM (NẾU CÓ)

CHỈ trích dẫn điều luật có trong mục "ĐIỀU LUẬT LIÊN QUAN" bên dưới. Nếu
JSON có trường ghi "THIẾU DỮ LIỆU" ở mục quan trọng, phải thể hiện rõ
[THIẾU DỮ LIỆU: ...] tại đúng vị trí trong bản thảo, không tự bịa cho đủ.

--- MẪU THAM CHIẾU ---
{mau_tham_chieu}

--- ĐIỀU LUẬT LIÊN QUAN ---
{dieu_luat_lien_quan}

--- DỮ KIỆN VỤ ÁN (JSON) ---
{facts_json}
"""

# ---------------------------------------------------------------------------
# BƯỚC 4: TỰ KIỂM TRA (chống hallucination + xử lý ngoại lệ)
# ---------------------------------------------------------------------------
SELF_CHECK_PROMPT = """Bạn đóng vai người kiểm tra chất lượng độc lập. Đọc lại BẢN
THẢO dưới đây, đối chiếu với DỮ KIỆN GỐC (JSON), và thực hiện:

1. Liệt kê bất kỳ chi tiết nào trong bản thảo KHÔNG có căn cứ trong dữ
   kiện gốc (nghi ngờ bịa đặt) — nếu có, chỉ rõ câu/đoạn đó.
2. Kiểm tra bản thảo có đủ các mục bắt buộc theo đúng loại văn bản
   ({case_type}) hay không.
3. Kiểm tra các điều luật được trích dẫn có nằm trong tài liệu tham
   chiếu đã cung cấp ở bước soạn thảo hay không — nếu trích dẫn điều
   luật KHÔNG rõ nguồn, đánh dấu lại thành [CẦN KIỂM TRA LẠI ĐIỀU LUẬT].
4. Áp dụng quy tắc xử lý ngoại lệ sau nếu phát hiện:
   - Thiếu dữ liệu → giữ nguyên đánh dấu [THIẾU DỮ LIỆU: ...], không tự suy đoán.
   - Không tìm thấy căn cứ pháp luật phù hợp → đánh dấu [CẦN KIỂM TRA LẠI ĐIỀU LUẬT].
   - Tình tiết mâu thuẫn giữa các phần của hồ sơ → đánh dấu [TÌNH TIẾT MÂU THUẪN -
     CẦN XÁC MINH: mô tả mâu thuẫn], không tự chọn phương án nào.
   - TUYỆT ĐỐI không đổi thông tin ĐÃ CÓ trong dữ kiện gốc thành [THIẾU DỮ
     LIỆU] hay "số... ngày...". Nếu bản thảo để trống/THIẾU ở chỗ dữ kiện gốc
     đã có (số quyết định, ngày, cơ quan, lý lịch, tình tiết, tội danh, điều
     khoản) thì PHẢI điền từ dữ kiện gốc vào.
   - Giữ nguyên đánh số THỨ TỰ 1, 2, 3... của khối lý lịch bị can (không để
     tất cả cùng số 1) và giữ hai tiêu đề KẾT LUẬN, QUYẾT ĐỊNH nằm riêng
     một dòng, không kèm chú thích.
   - Xóa mọi nhãn vai trò (chủ mưu, cầm đầu, đồng phạm tích cực, giúp sức…)
     nếu dữ kiện gốc không ghi vai trò đó.
   - Nếu bản thảo ghi một người có "tiền án/tiền sự" hoặc "Tiền án: Không" mà
     dữ kiện gốc để trống hoặc chỉ có ở mục nhân thân thì sửa lại theo dữ kiện gốc.
   - Thứ tự các bị can phải giống nhau ở lý lịch, khẳng định và quyết định truy tố.
   - Nếu phần diễn biến chỉ là một đoạn chung mà dữ kiện gốc có hành vi riêng của
     từng bị can, giá trị thiệt hại, tỷ lệ thương tích thì bổ sung đầy đủ.
    - Dòng có nhãn [GỢI Ý CỦA AI, KSV CẦN XÁC NHẬN LẠI: ...] là đề xuất
       hỗ trợ, không phải kết luận truy tố. Nếu đề xuất khớp với điều luật
       trong tài liệu tham chiếu và không trái dữ kiện, phải giữ nguyên;
       không chuyển dòng này thành [THIẾU DỮ LIỆU]. Nếu điều luật đề xuất
       không có trong tài liệu tham chiếu, giữ ý tưởng nhưng thay phần căn cứ
       bằng [CẦN KIỂM TRA LẠI ĐIỀU LUẬT].

Sau đó, xuất ra bản thảo ĐÃ CHỈNH SỬA (giữ nguyên các đoạn không có vấn
đề, chỉ sửa/đánh dấu những chỗ phát hiện lỗi ở trên). Báo cáo kiểm tra
phải nằm SAU CÙNG, sau toàn bộ nội dung cáo trạng, theo đúng mẫu sau:

--- PHỤ LỤC KIỂM TRA NỘI BỘ ---
1. KIỂM TRA DỮ KIỆN: [kết luận ngắn gọn về chi tiết không có căn cứ;
   nếu không phát hiện thì ghi rõ không phát hiện và xác nhận các chỗ
   thiếu đã đánh dấu [THIẾU DỮ LIỆU]].
2. KIỂM TRA CẤU TRÚC: [kết luận về các mục bắt buộc của loại văn bản].
3. KIỂM TRA ĐIỀU LUẬT: [đối chiếu với tài liệu tham chiếu; nếu thiếu
   tội danh/điều khoản thì ghi rõ [THIẾU DỮ LIỆU], không tự suy đoán].
--- HẾT PHỤ LỤC KIỂM TRA NỘI BỘ ---

Tuyệt đối không đặt phần phụ lục này ở đầu văn bản, không chèn nhận xét
kiểm tra vào giữa các mục của cáo trạng, và không thêm lời giải thích
ngoài ba mục trên.

--- LOẠI VỤ VIỆC ---
{case_type}

--- DỮ KIỆN GỐC (JSON) ---
{facts_json}

--- ĐIỀU LUẬT ĐÃ TRA CỨU Ở BƯỚC SOẠN THẢO ---
{dieu_luat_lien_quan}

--- BẢN THẢO CẦN KIỂM TRA ---
{draft_text}
"""
