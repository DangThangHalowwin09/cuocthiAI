"""
Xuất văn bản Cáo trạng ra file .docx theo thể thức cơ bản của văn bản tố
tụng hình sự Việt Nam.

LƯU Ý: đây là khung thể thức tối giản (quốc hiệu, tiêu ngữ, tiêu đề,
nội dung). Trước khi dùng chính thức, đội thi nên đối chiếu và bổ sung
thêm phần "Nơi nhận", chữ ký, con dấu... theo đúng mẫu thật của đơn vị.
"""

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH


TITLES = {
    "HINH_SU": "CÁO TRẠNG",
    "DAN_SU_HANH_CHINH": "PHÁT BIỂU CỦA KIỂM SÁT VIÊN\nTẠI PHIÊN TÒA (PHIÊN HỌP) SƠ THẨM",
}


def write_result_docx(
    final_text: str,
    case_type: str,
    output_path: str,
    unit_name: str = "VIỆN KIỂM SÁT NHÂN DÂN TỈNH NGHỆ AN",
) -> str:
    doc = Document()

    # Tên đơn vị (góc trái, in hoa)
    p_unit = doc.add_paragraph()
    run_unit = p_unit.add_run(unit_name)
    run_unit.bold = True

    doc.add_paragraph()

    # Quốc hiệu, tiêu ngữ (căn giữa)
    p1 = doc.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p1.add_run("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    r1.bold = True

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run("Độc lập - Tự do - Hạnh phúc")
    r2.bold = True

    doc.add_paragraph()

    # Tiêu đề văn bản
    title_text = TITLES.get(case_type, "VĂN BẢN TỐ TỤNG")
    for line in title_text.split("\n"):
        tp = doc.add_paragraph()
        tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        trun = tp.add_run(line)
        trun.bold = True
        trun.font.size = Pt(14)

    doc.add_paragraph()

    # Nội dung chính — mỗi dòng trong final_text thành 1 đoạn văn
    for line in final_text.split("\n"):
        line = line.strip()
        if not line:
            doc.add_paragraph()
            continue
        doc.add_paragraph(line)

    doc.add_paragraph()
    note = doc.add_paragraph()
    note_run = note.add_run(
        "* Văn bản do AI hỗ trợ soạn thảo. Kiểm sát viên có trách nhiệm "
        "kiểm tra, chỉnh sửa trước khi ban hành chính thức."
    )
    note_run.italic = True
    note_run.font.size = Pt(9)

    doc.save(output_path)
    return output_path
