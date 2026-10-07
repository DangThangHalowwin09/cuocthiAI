"""
Đọc nội dung đề thi từ file .doc, .docx hoặc .pdf.
- .doc: Word 97-2003 (định dạng nhị phân OLE) — dùng olefile trích xuất.
- .docx: Word OpenXML — dùng python-docx.
- .pdf: — dùng pdfplumber.
"""

import pathlib
import re
import struct
from zipfile import ZipFile, BadZipFile

from docx import Document
from docx.oxml.ns import qn
import pdfplumber
import olefile

DOC_MIME = "application/msword"
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
PDF_MIME = "application/pdf"


def _paragraphs_from_container(container) -> list[str]:
    parts = []
    for para in container.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())
    for table in container.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return parts


def _textbox_texts(doc: Document) -> list[str]:
    parts = []
    for textbox in doc.element.iter(qn("w:txbxContent")):
        texts = [
            node.text.strip()
            for node in textbox.iter(qn("w:t"))
            if node.text and node.text.strip()
        ]
        if texts:
            parts.append(" ".join(texts))
    return parts


def _xml_fallback_text(path: str) -> str:
    """Đọc thô word/document.xml khi python-docx bỏ sót nội dung."""
    try:
        with ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError, OSError):
        return ""

    from xml.etree import ElementTree

    root = ElementTree.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    chunks = []
    for node in root.findall(".//w:t", ns):
        if node.text and node.text.strip():
            chunks.append(node.text.strip())
    return "\n".join(chunks)


def read_docx(path: str) -> str:
    doc = Document(path)
    parts = []

    for section in doc.sections:
        parts.extend(_paragraphs_from_container(section.header))
        parts.extend(_paragraphs_from_container(section.footer))

    parts.extend(_paragraphs_from_container(doc))
    parts.extend(_textbox_texts(doc))

    text = "\n".join(parts).strip()
    if not text:
        text = _xml_fallback_text(path)
    return text


def read_pdf(path: str) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Trình đọc .doc (Word 97-2003, OLE Compound Binary)
# Sử dụng olefile + phân tích PieceTable của FIB (File Information Block)
# ---------------------------------------------------------------------------

def _read_fib_value(stream: bytes, offset: int, fmt: str):
    """Đọc 1 giá trị từ WordDocument stream theo format struct."""
    size = struct.calcsize(fmt)
    if offset + size > len(stream):
        return None
    return struct.unpack_from(fmt, stream, offset)[0]


def _extract_text_via_piece_table(word_doc: bytes, table_stream: bytes) -> str:
    """Trích xuất văn bản từ .doc bằng cách parse PieceTable (phương pháp chuẩn).
    Trả về chuỗi rỗng nếu table stream không hợp lệ."""
    if not table_stream:
        return ""

    # Đọc từ FIB trong WordDocument stream:
    #   fcClx (offset 0x01FA, 4 bytes): vị trí CLX trong table stream
    #   lcbClx (offset 0x01FE, 4 bytes): độ dài CLX
    fcClx = _read_fib_value(word_doc, 0x01FA, "<I")
    lcbClx = _read_fib_value(word_doc, 0x01FE, "<I")
    if fcClx is None or lcbClx is None or lcbClx == 0:
        return ""
    if fcClx + lcbClx > len(table_stream):
        return ""

    clx = table_stream[fcClx: fcClx + lcbClx]

    # CLX chứa các Prc s + 1 Pcdt. Bỏ qua các Prc (type 0x01),
    # tìm Pcdt (type 0x02).
    pos = 0
    pcdt = None
    while pos < len(clx):
        if pos + 1 >= len(clx):
            break
        clxt = clx[pos]
        pos += 1
        if clxt == 0x01:
            # Prc: cbGrpprl (2 bytes) + data
            if pos + 2 > len(clx):
                break
            cb = struct.unpack_from("<H", clx, pos)[0]
            pos += 2 + cb
        elif clxt == 0x02:
            # Pcdt: lcb (4 bytes) + PlcPcd
            if pos + 4 > len(clx):
                break
            lcb = struct.unpack_from("<I", clx, pos)[0]
            pos += 4
            pcdt = clx[pos: pos + lcb]
            break
        else:
            break

    if not pcdt:
        return ""

    # PlcPcd: (n+1) CPs (4 bytes mỗi) + n PCDs (8 bytes mỗi)
    n = (len(pcdt) - 4) // 12  # Vì (n+1)*4 + n*8 = 12n + 4
    if n <= 0:
        return ""

    cps = [struct.unpack_from("<I", pcdt, i * 4)[0] for i in range(n + 1)]

    text_parts = []
    for i in range(n):
        pcd_offset = (n + 1) * 4 + i * 8
        if pcd_offset + 8 > len(pcdt):
            break
        fc_field = struct.unpack_from("<I", pcdt, pcd_offset + 2)[0]
        is_compressed = bool(fc_field & 0x40000000)
        fc = fc_field & ~0x40000000
        ccp = cps[i + 1] - cps[i]

        if is_compressed:
            # Mã hóa ANSI (CP1252 / Windows-1252), mỗi ký tự 1 byte
            byte_start = fc // 2
            raw = word_doc[byte_start: byte_start + ccp]
            try:
                decoded = raw.decode("cp1252", errors="replace")
            except Exception:
                decoded = raw.decode("latin-1", errors="replace")
        else:
            # Unicode UTF-16LE, mỗi ký tự 2 bytes
            byte_start = fc
            raw = word_doc[byte_start: byte_start + ccp * 2]
            try:
                decoded = raw.decode("utf-16-le", errors="replace")
            except Exception:
                decoded = ""
        text_parts.append(decoded)

    return "".join(text_parts)


def _brute_extract_text_from_stream(word_doc: bytes) -> str:
    """Phương pháp dự phòng: quét toàn bộ WordDocument stream để lấy các
    đoạn text dễ đọc (khi PieceTable parse thất bại do định dạng cũ/dị thường)."""
    results = []

    # 1) Quét UTF-16LE (tiếng Việt lưu dưới dạng Unicode trong .doc mới hơn)
    try:
        decoded16 = word_doc.decode("utf-16-le", errors="ignore")
        # Giữ lại các đoạn có độ dài >= 2 ký tự in được (bao gồm chữ Việt)
        matches = re.findall(r"[\w\u00C0-\u1EF9 ,.;:!?()\"'\-–—\n\t]{2,}", decoded16)
        matches = [m.strip() for m in matches if re.search(r"[A-Za-z\u00C0-\u1EF9]", m)]
        if matches:
            results.extend(matches)
    except Exception:
        pass

    # 2) Quét CP1252 (Word 97, lưu dạng ANSI)
    if not results:
        try:
            decoded1252 = word_doc.decode("cp1252", errors="ignore")
            matches = re.findall(r"[\w\u00C0-\u1EF9 ,.;:!?()\"'\-–—\n\t]{2,}", decoded1252)
            matches = [m.strip() for m in matches if re.search(r"[A-Za-z\u00C0-\u1EF9]", m)]
            if matches:
                results.extend(matches)
        except Exception:
            pass

    # 3) Cuối cùng: TCVN3 fallback (không phổ biến lắm)
    if not results:
        try:
            decoded_latin = word_doc.decode("latin-1", errors="ignore")
            matches = re.findall(r"[\w ,.;:!?()\"'\-–—\n\t]{4,}", decoded_latin)
            matches = [m.strip() for m in matches if re.search(r"[A-Za-z]", m)]
            if matches:
                results.extend(matches)
        except Exception:
            pass

    # Loại bỏ các đoạn ngắn không có nghĩa, gộp lại
    meaningful = [m for m in results if len(m) >= 3]
    return "\n".join(meaningful)


def read_doc(path: str) -> str:
    """Đọc file .doc (Word 97-2003) bằng olefile.
    Ưu tiên dùng PieceTable (chính xác), nếu lỗi thì dùng phương pháp quét thô."""
    if not olefile.isOleFile(path):
        raise ValueError(
            "File này không phải là định dạng .doc hợp lệ (không phải OLE Compound File). "
            "Nếu file bị hỏng, hãy mở bằng Word rồi Lưu lại thành .docx."
        )

    with olefile.OleFileIO(path) as ole:
        required = ["WordDocument"]
        if not ole.exists(required[0]):
            raise ValueError(
                "File .doc này không có stream 'WordDocument' — có thể file bị hỏng "
                "hoặc không phải file Word thật. Hãy mở bằng Word rồi Lưu thành .docx."
            )

        word_doc = ole.openstream("WordDocument").read()

        # Xác định nên dùng 1Table hay 0Table: bit 9 của wFlags (offset 0x000A)
        table_name = None
        if len(word_doc) >= 0x000C:
            w_flags = struct.unpack_from("<H", word_doc, 0x000A)[0]
            table_name = "1Table" if (w_flags & 0x0200) else "0Table"

        table_stream = b""
        if table_name and ole.exists(table_name):
            try:
                table_stream = ole.openstream(table_name).read()
            except Exception:
                table_stream = b""

        # Thử đọc theo PieceTable (chuẩn)
        text = _extract_text_via_piece_table(word_doc, table_stream)

        # Nếu không đọc được (do FIB dị thường / .doc rất cũ), dùng quét thô
        if not text.strip():
            text = _brute_extract_text_from_stream(word_doc)

        # Nếu vẫn rỗng, thử mở stream "SummaryInformation" / "DocumentSummaryInformation"
        # để lấy ít nhất metadata (hỗ trợ tối thiểu)
        if not text.strip():
            try:
                meta = ole.get_metadata()
                title = (meta.title or "").strip()
                subject = (meta.subject or "").strip()
                author = (meta.author or "").strip()
                parts = [p for p in [title, subject, author] if p]
                text = "\n".join(parts)
            except Exception:
                pass

        return text.strip()


def mime_type_for_path(path: str) -> str | None:
    ext = pathlib.Path(path).suffix.lower()
    if ext == ".doc":
        return DOC_MIME
    if ext == ".docx":
        return DOCX_MIME
    if ext == ".pdf":
        return PDF_MIME
    return None


def read_input_file(path: str) -> str:
    ext = pathlib.Path(path).suffix.lower()
    if ext == ".doc":
        text = read_doc(path)
    elif ext == ".docx":
        text = read_docx(path)
    elif ext == ".pdf":
        text = read_pdf(path)
    else:
        raise ValueError(
            f"Định dạng file không được hỗ trợ: {ext} (chỉ nhận .doc, .docx hoặc .pdf)"
        )

    if not text.strip():
        raise ValueError(
            "Không trích xuất được nội dung văn bản từ file. "
            "Nếu đây là file scan/ảnh, hãy chuyển sang PDF có chữ hoặc gõ lại nội dung. "
            "Nếu là file .doc rất cũ, hãy mở bằng Word rồi Lưu thành .docx."
        )
    return text
