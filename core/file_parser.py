"""
Đọc nội dung đề thi / hồ sơ vụ án từ file .docx, .doc, .rtf hoặc .pdf.

Điểm vào chính:
    extract_input_file(path, ...) -> ExtractionResult
        Trả về văn bản KÈM thông tin cách đọc và các cảnh báo (trang nào phải
        OCR, trang nào mờ, có Track Changes, có ảnh nhúng chưa đọc...).
    read_input_file(path, ...) -> str
        Giữ lại cho code cũ: chỉ trả về văn bản.

Loại file được nhận diện theo NỘI DUNG (vài byte đầu) chứ không tin đuôi
file — file RTF bị đổi đuôi thành .doc, hay .docx đặt mật khẩu, đều được
xử lý đúng hoặc báo lỗi rõ ràng.

Chi tiết từng định dạng nằm trong core/readers/.
"""

from __future__ import annotations

import pathlib

from .readers.common import ExtractionResult, PageInfo, score_text  # noqa: F401
from .readers.ocr import OcrOptions, detect_ocr_capability  # noqa: F401

DOC_MIME = "application/msword"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
RTF_MIME = "application/rtf"
PDF_MIME = "application/pdf"

SUPPORTED_EXTENSIONS = ("docx", "doc", "rtf", "pdf")

# Mục LƯU Ý hiển thị cố định trên giao diện (và ghi trong README).
PDF_NOTICE = """\
**PDF có lớp chữ** (xuất từ Word, tải từ cổng văn bản): đọc trực tiếp, chính xác như file Word.

**PDF là bản scan / ảnh chụp**: hệ thống phải *nhận dạng chữ từ ảnh (OCR)* — kết quả **không bao giờ chính xác tuyệt đối**, và sai nhiều hơn khi:
- bản scan **mờ, nhòe, chữ nhạt**, độ phân giải thấp (dưới ~200 dpi), chụp bằng điện thoại bị nghiêng, bóng, lóa;
- **con dấu, chữ ký, ghi chú tay** đè lên chữ; giấy nhàu, ố, bị che góc;
- **chữ viết tay**, bảng biểu nhiều cột, chữ quá nhỏ.

Lỗi OCR hay gặp là **sai/mất dấu tiếng Việt, sai họ tên, ngày tháng, số tiền, số điều luật**. Với OCR bằng AI (Gemini), chỗ đọc sai có thể **trông vẫn rất hợp lý** nên khó nhận ra nếu không so với bản gốc.

**Vì vậy:** sau khi tải file scan lên, hãy đọc soát phần *Nội dung đã đọc* (sửa trực tiếp được) và so với bản gốc **trước khi** bấm Chạy xử lý. Nếu có file Word hoặc PDF gốc (không phải bản scan) thì nên dùng file đó.
"""

_MAGIC_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def sniff_file_type(path: str) -> str | None:
    """Nhận diện loại file theo nội dung. Trả về "docx" | "doc" | "rtf" | "pdf"
    hoặc None nếu không nhận ra."""
    try:
        with open(path, "rb") as f:
            head = f.read(2048)
    except OSError:
        return None
    stripped = head.lstrip()
    if b"%PDF-" in head[:1024]:
        return "pdf"
    if stripped.startswith(b"{\\rtf"):
        return "rtf"
    if head.startswith(b"PK\x03\x04"):
        return "docx"
    if head.startswith(_MAGIC_OLE):
        return "doc"
    return None


def mime_type_for_path(path: str) -> str | None:
    return {
        ".doc": DOC_MIME, ".docx": DOCX_MIME, ".rtf": RTF_MIME, ".pdf": PDF_MIME,
    }.get(pathlib.Path(path).suffix.lower())


def extract_input_file(path: str, *, ocr: OcrOptions | None = None, progress=None) -> ExtractionResult:
    """Đọc file đầu vào.

    ocr:      tùy chọn OCR cho PDF scan / ảnh nhúng (mặc định: tự động).
    progress: hàm progress(đã_xong, tổng, thông_báo) để giao diện hiện tiến độ.
    Ném ValueError kèm hướng dẫn khắc phục nếu không đọc được."""
    ocr = ocr or OcrOptions()
    ext = pathlib.Path(path).suffix.lower().lstrip(".")
    kind = sniff_file_type(path)
    if kind is None:
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Định dạng file không được hỗ trợ: .{ext} (chỉ nhận .docx, .doc, .rtf hoặc .pdf)"
            )
        kind = ext

    if kind == "pdf":
        from .readers.pdf import extract_pdf

        result = extract_pdf(path, ocr, progress)
    elif kind == "docx":
        from .readers.word_docx import extract_docx

        result = extract_docx(path, ocr_options=ocr)
    elif kind == "rtf":
        from .readers.rtf import extract_rtf

        result = extract_rtf(path)
    else:
        from .readers.word_doc import extract_doc

        if ext == "docx":
            # Đuôi .docx nhưng ruột là file OLE: gần như chắc chắn là file
            # Word đặt mật khẩu mở (Word bọc file mã hóa trong vỏ OLE).
            try:
                result = extract_doc(path)
            except ValueError as e:
                raise ValueError(
                    "File .docx này đang được đặt mật khẩu mở hoặc không đúng định dạng. "
                    "Hãy mở bằng Word, bỏ mật khẩu rồi Lưu lại. (Chi tiết: " + str(e) + ")"
                ) from e
        else:
            result = extract_doc(path)

    if not result.text.strip():
        raise ValueError(_empty_message(result))
    return result


def _empty_message(result: ExtractionResult) -> str:
    return (
        "File không có nội dung chữ đọc được (có thể chỉ chứa ảnh, hoặc đang đặt mật "
        "khẩu). Hãy mở file để kiểm tra; nếu là ảnh scan thì xuất thành PDF rồi tải "
        "lên để hệ thống nhận dạng chữ (OCR)."
    )


def read_input_file(path: str, *,
                    pdf_force_ocr: bool = False,
                    pdf_ocr_dpi: int = 220,
                    pdf_ocr_langs: str = "vie+eng",
                    pdf_max_ocr_pages: int = 60) -> str:
    """Tương thích ngược: chỉ trả về văn bản. Code mới nên dùng extract_input_file()."""
    options = OcrOptions(
        mode="always" if pdf_force_ocr else "auto",
        dpi=pdf_ocr_dpi,
        langs=pdf_ocr_langs,
        max_pages=pdf_max_ocr_pages,
    )
    return extract_input_file(path, ocr=options).text


# --- Các hàm giữ tên cũ để script/đoạn code khác còn import được -------------
def read_docx(path: str) -> str:
    from .readers.word_docx import extract_docx

    return extract_docx(path).text


def read_doc(path: str) -> str:
    from .readers.word_doc import extract_doc

    return extract_doc(path).text


def read_rtf(path: str) -> str:
    from .readers.rtf import extract_rtf

    return extract_rtf(path).text


def read_pdf(path: str, *, force_ocr: bool = False, ocr_dpi: int = 220,
             ocr_langs: str = "vie+eng", max_ocr_pages: int = 60) -> str:
    from .readers.pdf import extract_pdf

    options = OcrOptions(mode="always" if force_ocr else "auto", dpi=ocr_dpi,
                         langs=ocr_langs, max_pages=max_ocr_pages)
    return extract_pdf(path, options).text


_score_extracted_text = score_text  # tên cũ
