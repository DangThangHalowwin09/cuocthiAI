"""
Xuất văn bản kết quả (Cáo trạng / Phát biểu của Kiểm sát viên) ra file
.docx ĐÚNG THỂ THỨC theo Phụ lục I, Nghị định số 30/2020/NĐ-CP ngày
05/3/2020 của Chính phủ về công tác văn thư.

Các quy định chính đã áp dụng (trích Phụ lục I):
- Khổ A4; lề trên/dưới 20-25mm, trái 30-35mm, phải 15-20mm
- Phông chữ Times New Roman, bộ mã Unicode, màu đen
- Quốc hiệu: in hoa, cỡ 12-13, đứng, đậm
- Tiêu ngữ: in thường, cỡ 13-14, đứng, đậm, có gạch chân bằng độ dài dòng
- Tên cơ quan ban hành: in hoa, cỡ 12-13, đứng, đậm, có gạch chân 1/3-1/2 dòng
- Số, ký hiệu: "Số" in thường cỡ 13; ký hiệu in hoa cỡ 13, đứng
- Địa danh, ngày tháng: in thường, cỡ 13-14, NGHIÊNG
- Tên loại văn bản: in hoa, cỡ 13-14, đứng, đậm, canh giữa
- Trích yếu: in thường, cỡ 13-14, đứng, đậm, canh giữa, có gạch chân 1/3-1/2 dòng
- Căn cứ ban hành: in thường, NGHIÊNG, cỡ 13-14
- Nội dung văn bản: in thường, cỡ 13-14, đứng
- Chức vụ người ký: in hoa, đứng, đậm, cỡ 13-14, canh giữa
- Nơi nhận: "Nơi nhận:" nghiêng đậm cỡ 12; danh sách thường cỡ 11
- Dòng cách: dòng đơn (tối thiểu theo quy định; tối đa cho phép 1.5 dòng)

LƯU Ý: đây là bản triển khai bám sát Phụ lục I ở mức độ khung thể thức
chính. Trước khi dùng chính thức, nên đối chiếu trực quan với 1 văn bản
mẫu đã có sẵn của đơn vị để tinh chỉnh thêm nếu cần.
"""

from docx import Document
from docx.shared import Pt, Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT_NAME = "Times New Roman"

TITLES = {
    "HINH_SU": "CÁO TRẠNG",
    "DAN_SU_HANH_CHINH": "PHÁT BIỂU",
}

SUBTITLES = {
    "HINH_SU": None,
    "DAN_SU": "Của Kiểm sát viên tại phiên tòa (phiên họp) sơ thẩm",
    "HANH_CHINH": "Của Kiểm sát viên tại phiên tòa hành chính sơ thẩm",
}


def _set_font(run, size: int, bold: bool = False, italic: bool = False):
    run.font.name = FONT_NAME
    # Đảm bảo áp dụng đúng font cho cả ký tự Đông Á (một số bản Word cần dòng này)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), FONT_NAME)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic


def _add_run(paragraph, text: str, size: int, bold: bool = False, italic: bool = False):
    run = paragraph.add_run(text)
    _set_font(run, size, bold, italic)
    return run


def _set_single_spacing(paragraph, space_after: int = 0, space_before: int = 0):
    pf = paragraph.paragraph_format
    pf.line_spacing = 1.0
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)


def _add_bottom_border(paragraph, width_pct: int = 100):
    """Thêm đường kẻ ngang bên dưới đoạn văn (dùng cho Tiêu ngữ, tên cơ
    quan ban hành, trích yếu — theo đúng yêu cầu 'phía dưới có đường kẻ
    ngang, nét liền' của Phụ lục I). width_pct: độ dài tương đối bằng
    cách thụt lề 2 bên để tạo cảm giác đường kẻ ngắn hơn dòng chữ."""
    p_el = paragraph._p
    pPr = p_el.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _set_margins(doc: Document):
    section = doc.sections[0]
    section.page_height = Mm(297)
    section.page_width = Mm(210)
    section.top_margin = Mm(20)
    section.bottom_margin = Mm(20)
    section.left_margin = Mm(30)
    section.right_margin = Mm(20)


def _add_header_table(doc: Document, unit_name: str, unit_parent: str, so_ky_hieu: str, dia_danh_ngay: str):
    """Bảng 2 cột không viền: trái = tên cơ quan, phải = Quốc hiệu/Tiêu
    ngữ — đúng bố cục truyền thống của văn bản hành chính Việt Nam."""
    table = doc.add_table(rows=1, cols=2)
    table.autofit = True
    left_cell, right_cell = table.rows[0].cells

    # Xóa viền bảng (mặc định python-docx table có thể không viền sẵn,
    # nhưng đảm bảo chắc chắn bằng cách set border None qua style)
    table.style = None

    # --- CỘT TRÁI: tên cơ quan chủ quản + tên cơ quan ban hành + số ký hiệu ---
    p1 = left_cell.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(p1)
    _add_run(p1, unit_parent, size=13, bold=False)

    p2 = left_cell.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(p2)
    _add_run(p2, unit_name, size=13, bold=True)
    _add_bottom_border(p2)

    p3 = left_cell.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(p3)
    _add_run(p3, so_ky_hieu, size=13, bold=False)

    # --- CỘT PHẢI: Quốc hiệu, Tiêu ngữ, Địa danh ngày tháng ---
    q1 = right_cell.paragraphs[0]
    q1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(q1)
    _add_run(q1, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", size=13, bold=True)

    q2 = right_cell.add_paragraph()
    q2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(q2)
    _add_run(q2, "Độc lập - Tự do - Hạnh phúc", size=14, bold=True)
    _add_bottom_border(q2)

    q3 = right_cell.add_paragraph()
    q3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(q3)
    _add_run(q3, dia_danh_ngay, size=14, italic=True)

    return table


def write_result_docx(
    final_text: str,
    case_type: str,
    output_path: str,
    is_hanh_chinh: bool = False,
    unit_name: str = "VIỆN KIỂM SÁT NHÂN DÂN TỈNH NGHỆ AN",
    unit_parent: str = "VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO",
) -> str:
    doc = Document()
    _set_margins(doc)

    # Font mặc định cho toàn tài liệu (phòng khi có đoạn không set font riêng)
    normal_style = doc.styles["Normal"]
    normal_style.font.name = FONT_NAME
    normal_style.font.size = Pt(14)

    ky_hieu = "CT" if case_type == "HINH_SU" else ("PB-HC" if is_hanh_chinh else "PB")
    so_ky_hieu = f"Số: ..../{ky_hieu}-VKS...-..."
    dia_danh_ngay = "......., ngày .... tháng .... năm 20...."

    _add_header_table(doc, unit_name, unit_parent, so_ky_hieu, dia_danh_ngay)

    doc.add_paragraph()  # dòng trống trước tên loại văn bản

    # --- TÊN LOẠI VĂN BẢN ---
    title_text = TITLES.get(case_type, "VĂN BẢN")
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(p_title)
    _add_run(p_title, title_text, size=14, bold=True)

    # --- TRÍCH YẾU (subtitle, chỉ áp dụng cho Phát biểu) ---
    subtitle_key = "HANH_CHINH" if is_hanh_chinh else ("DAN_SU" if case_type != "HINH_SU" else None)
    subtitle = SUBTITLES.get(subtitle_key) if subtitle_key else None
    if subtitle:
        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_single_spacing(p_sub)
        _add_run(p_sub, subtitle, size=14, bold=True)
        _add_bottom_border(p_sub, width_pct=50)

    doc.add_paragraph()  # dòng trống trước nội dung

    # --- NỘI DUNG VĂN BẢN ---
    # "Căn cứ..." trình bày nghiêng theo quy định; các đoạn khác trình
    # bày đứng. Nhận diện dòng "Căn cứ" bằng tiền tố để áp dụng nghiêng.
    for line in final_text.split("\n"):
        line = line.strip()
        if not line:
            doc.add_paragraph()
            continue

        p = doc.add_paragraph()
        _set_single_spacing(p, space_after=6)
        is_can_cu = line.startswith("Căn cứ")
        # Các dòng tiêu đề mục lớn (I., II., III., KẾT LUẬN, QUYẾT ĐỊNH)
        is_section_header = (
            line.upper() == line and len(line) < 60 and any(c.isalpha() for c in line)
        )
        if is_section_header:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _add_run(p, line, size=14, bold=True)
        else:
            _add_run(p, line, size=14, italic=is_can_cu)

    doc.add_paragraph()

    # --- CHỨC VỤ, HỌ TÊN NGƯỜI KÝ + NƠI NHẬN (2 cột) ---
    footer_table = doc.add_table(rows=1, cols=2)
    footer_table.autofit = True
    nhan_cell, ky_cell = footer_table.rows[0].cells

    p_nn_title = nhan_cell.paragraphs[0]
    _set_single_spacing(p_nn_title)
    _add_run(p_nn_title, "Nơi nhận:", size=12, bold=True, italic=True)

    for line in ["- Như trên;", "- Lãnh đạo đơn vị (để báo cáo);", "- Lưu: VT, HSKS."]:
        p_nn = nhan_cell.add_paragraph()
        _set_single_spacing(p_nn)
        _add_run(p_nn, line, size=11)

    p_ky_title = ky_cell.paragraphs[0]
    p_ky_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(p_ky_title)
    chuc_danh = "VIỆN TRƯỞNG" if case_type == "HINH_SU" else "KIỂM SÁT VIÊN"
    _add_run(p_ky_title, chuc_danh, size=14, bold=True)

    for _ in range(4):
        ky_cell.add_paragraph()

    p_ten = ky_cell.add_paragraph()
    p_ten.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_single_spacing(p_ten)
    _add_run(p_ten, "(Ký, ghi rõ họ tên, đóng dấu)", size=13, italic=True)

    doc.add_paragraph()
    note = doc.add_paragraph()
    _add_run(
        note,
        "* Văn bản do AI hỗ trợ soạn thảo theo thể thức Nghị định 30/2020/NĐ-CP. "
        "Kiểm sát viên có trách nhiệm kiểm tra, chỉnh sửa trước khi ban hành chính thức.",
        size=9,
        italic=True,
    )

    doc.save(output_path)
    return output_path
