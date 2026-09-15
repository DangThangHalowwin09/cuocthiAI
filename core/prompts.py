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
"""

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
EXTRACT_PROMPT_HS = """Nhiệm vụ: trích xuất dữ kiện từ hồ sơ vụ án HÌNH SỰ dưới đây
thành định dạng JSON có cấu trúc. Chỉ lấy thông tin CÓ TRONG hồ sơ.
Trường nào không có thông tin thì ghi giá trị "THIẾU DỮ LIỆU".

Cấu trúc JSON cần trả về:
{{
  "bi_can": [{{"ho_ten": "", "nam_sinh": "", "vai_tro": ""}}],
  "bi_hai": [{{"ho_ten": ""}}],
   "tuoi_tai_thoi_diem_pham_toi": "",
   "la_nguoi_duoi_18_tuoi": "có | không | THIẾU DỮ LIỆU",
  "toi_danh_nghi_van": "",
  "hanh_vi_pham_toi_tom_tat": "",
  "thoi_gian_dia_diem": "",
  "chung_cu": ["..."],
  "tinh_tiet_tang_nang": ["..."],
  "tinh_tiet_giam_nhe": ["..."],
  "qua_trinh_dieu_tra_tom_tat": "",
  "ghi_chu_thieu_du_lieu": ["liệt kê các thông tin quan trọng còn thiếu"]
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

CHỈ trích dẫn điều luật có trong mục "ĐIỀU LUẬT LIÊN QUAN" bên dưới. Nếu
JSON có trường ghi "THIẾU DỮ LIỆU" ở mục quan trọng, phải thể hiện rõ
[THIẾU DỮ LIỆU: ...] tại đúng vị trí trong bản thảo, không tự bịa cho đủ.

CHỈ xuất phần nội dung từ "Căn cứ..." đến hết phần "QUYẾT ĐỊNH". Không
xuất quốc hiệu, tiêu ngữ, tên cơ quan, số ký hiệu, địa danh ngày tháng,
tiêu đề CÁO TRẠNG, phần Nơi nhận, chức danh hoặc chữ ký; các phần đó đã
được giữ nguyên trong template mẫu 156.

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

Sau đó, xuất ra bản thảo ĐÃ CHỈNH SỬA (giữ nguyên các đoạn không có vấn
đề, chỉ sửa/đánh dấu những chỗ phát hiện lỗi ở trên). Báo cáo kiểm tra
phải nằm SAU CÙNG, sau toàn bộ nội dung cáo trạng, theo đúng mẫu sau:

--- PHỤ LỤC KIỂM TRA NỘI BỘ (ĐẶT Ở CUỐI VĂN BẢN) ---
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
