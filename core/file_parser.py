"""
Đọc nội dung đề thi từ file .doc, .docx hoặc .pdf.
- .doc: Word 97-2003 (định dạng nhị phân OLE) — dùng olefile trích xuất.
- .docx: Word OpenXML — dùng python-docx.
- .pdf: pdfplumber → PyMuPDF → pdfminer.six (3 thư viện song song, giữ kết quả tốt nhất).
- .pdf ảnh (scan): tự fallback OCR (nếu tesseract được cài, optional).
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


def _score_extracted_text(s: str) -> int:
    """Đánh giá độ "chất lượng" văn bản được trích xuất (để chọn ra thư viện nào tốt nhất).
    Điểm số: số từ English/Việt token * 2 + bonus từ Việt * 5. Dùng chung cho PDF và .doc."""
    if not s:
        return -1
    tokens = re.findall(r"[A-Za-z\u00C0-\u1EF9]{2,}", s)
    if not tokens:
        return -1
    viet_tokens = sum(
        1 for t in tokens
        if re.search(
            r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệ"
            r"ìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]",
            t, flags=re.IGNORECASE,
        )
    )
    return len(tokens) * 2 + viet_tokens * 5


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
    """Đọc PDF bằng nhiều thư viện, giữ kết quả tốt nhất dựa theo heuristic điểm số.
    Thứ tự ưu tiên:
      1) pdfplumber (mạnh với bảng dữ liệu, mặc định của dự án)
      2) PyMuPDF (fitz) — tốt với vector text, PDF tạo ra từ Word cũ
      3) pdfminer.six — fallback gốc (đã được pdfplumber dùng nhưng gọi thẳng cho dễ debug)
      4) OCR — fallback cuối, chỉ dùng khi 3 thư viện trên không lấy được chữ
        (Yêu cầu: máy đã cài Tesseract + pytesseract/PIL; nếu không thì bỏ qua)
    Giữ text có điểm _score_extracted_text cao nhất.
    """
    candidates = []

    # -------------------------------------------------
    # 1) pdfplumber
    # -------------------------------------------------
    try:
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(text)
        text_pdfplumber = "\n".join(parts)
        candidates.append(("pdfplumber", text_pdfplumber))
    except Exception:
        candidates.append(("pdfplumber", ""))

    # -------------------------------------------------
    # 2) PyMuPDF (fitz / pymupdf)
    # -------------------------------------------------
    try:
        try:
            import pymupdf as fitz  # PyMuPDF >= 1.24+ (tên mới)
        except Exception:
            import fitz  # PyMuPDF cũ (deprecated alias)
        parts = []
        with fitz.open(path) as doc:
            for page in doc:
                t = page.get_text("text") or ""
                if t.strip():
                    parts.append(t)
        text_fitz = "\n".join(parts)
        candidates.append(("PyMuPDF", text_fitz))
    except Exception:
        candidates.append(("PyMuPDF", ""))

    # -------------------------------------------------
    # 3) pdfminer.six (thẳng gọi qua high-level API)
    # -------------------------------------------------
    try:
        from pdfminer.high_level import extract_text as _miner_extract
        text_miner = _miner_extract(path) or ""
        candidates.append(("pdfminer.six", text_miner))
    except Exception:
        candidates.append(("pdfminer.six", ""))

    # Chọn ra ứng viên có điểm tốt nhất
    best_name, best_text = "", ""
    best_score = -1
    for name, text in candidates:
        sc = _score_extracted_text(text)
        if sc > best_score:
            best_score = sc
            best_text = text
            best_name = name

    # -------------------------------------------------
    # 4) Nếu điểm quá thấp => có thể PDF là ảnh scan => thử OCR
    #    (OPTIONAL: không bắt buộc cài tesseract)
    # -------------------------------------------------
    if best_score < 15:
        try:
            ocr_text = _ocr_pdf_maybe(path)
            ocr_score = _score_extracted_text(ocr_text)
            if ocr_score > best_score:
                best_text = ocr_text
                best_name = best_name + "+OCR"
                best_score = ocr_score
        except Exception:
            pass

    return best_text.strip()


def _ocr_pdf_maybe(path: str) -> str:
    """OCR PDF scan/ảnh nếu tesseract được cài (tùy chọn, không throw lỗi nếu không)."""
    import io
    try:
        try:
            import pymupdf as fitz  # PyMuPDF mới
        except Exception:
            import fitz  # PyMuPDF cũ
        from PIL import Image
        import pytesseract
    except Exception:
        return ""

    # Các ngôn ngữ ưu tiên: vie (tiếng Việt) + eng (tiếng Anh)
    # Nếu user không có ngôn ngữ vie thì fallback sang eng
    try:
        _ = pytesseract.get_tesseract_version()
    except Exception:
        return ""

    langs_candidates = ["vie+eng", "eng"]
    best_ocr = ""
    best_sc = -1
    with fitz.open(path) as doc:
        # Giới hạn 30 trang để không bị chạy quá lâu trong cuộc thi
        pages_to_ocr = list(doc)[:30]
        for lang in langs_candidates:
            try:
                parts = []
                for page in pages_to_ocr:
                    # Render page ra ảnh 200 DPI (đủ OCR)
                    pix = page.get_pixmap(dpi=200, alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    txt = pytesseract.image_to_string(img, lang=lang)
                    if txt.strip():
                        parts.append(txt)
                merged = "\n".join(parts)
                sc = _score_extracted_text(merged)
                if sc > best_sc:
                    best_sc = sc
                    best_ocr = merged
            except pytesseract.TesseractError:
                # Language pack không tồn tại, bỏ qua
                continue
            except Exception:
                continue
    return best_ocr


# ---------------------------------------------------------------------------
# Trình đọc .doc (Word 97-2003, OLE Compound Binary) + xử lý các case đặc biệt
# Sử dụng olefile + phân tích PieceTable của FIB (File Information Block)
# Dự phòng: RTF (đổi đuôi .doc), bảng mã TCVN3 (ABC), VNI-Windows
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

    fcClx = _read_fib_value(word_doc, 0x01FA, "<I")
    lcbClx = _read_fib_value(word_doc, 0x01FE, "<I")
    if fcClx is None or lcbClx is None or lcbClx == 0:
        return ""
    if fcClx + lcbClx > len(table_stream):
        return ""

    clx = table_stream[fcClx: fcClx + lcbClx]
    pos = 0
    pcdt = None
    while pos < len(clx):
        if pos + 1 >= len(clx):
            break
        clxt = clx[pos]
        pos += 1
        if clxt == 0x01:
            if pos + 2 > len(clx):
                break
            cb = struct.unpack_from("<H", clx, pos)[0]
            pos += 2 + cb
        elif clxt == 0x02:
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

    n = (len(pcdt) - 4) // 12
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
        if ccp <= 0:
            continue

        if is_compressed:
            byte_start = fc // 2
            raw = word_doc[byte_start: byte_start + ccp]
            decoded = _decode_ansi_with_legacy_fallbacks(raw)
        else:
            byte_start = fc
            raw = word_doc[byte_start: byte_start + ccp * 2]
            try:
                decoded = raw.decode("utf-16-le", errors="replace")
            except Exception:
                decoded = ""
        text_parts.append(decoded)

    return "".join(text_parts)


# ---------------------------------------------------------------------------
# Bảng mã di sản Việt Nam (TCVN3 / VNI-Windows) → Unicode
# Dùng khi file .doc rất cũ lưu theo bảng mã ABC/VNI
# ---------------------------------------------------------------------------

_TCVN3_TO_UNICODE = str.maketrans({
    "\u00b5": "à", "\u00b8": "á", "\u00b6": "ả", "\u00b7": "ã", "\u00b9": "ạ",
    "\u00a8": "ă", "\u00be": "ằ", "\u00ac": "ắ", "\u00bc": "ẳ", "\u00bd": "ẵ",
    "\u00c6": "ặ",
    "\u00a9": "â", "\u00ca": "ầ", "\u00cb": "ấ", "\u00c7": "ẩ", "\u00c8": "ẫ",
    "\u00d7": "ậ",
    "\u00cc": "è", "\u00d0": "é", "\u00ce": "ẻ", "\u00cf": "ẽ", "\u00d1": "ẹ",
    "\u00ad": "ê", "\u00c9": "ề", "\u00d8": "ế", "\u00c6": "ể", "\u00c5": "ễ",
    "\u00de": "ệ",
    "\u00f0": "đ", "\u00d0": "Đ",
    "\u00b2": "ì", "\u00b3": "í", "\u00b4": "ỉ", "\u00b1": "ĩ", "\u00b0": "ị",
    "\u00df": "ò", "\u00e3": "ó", "\u00e1": "ỏ", "\u00e2": "õ", "\u00e4": "ọ",
    "\u00e5": "ô", "\u00e7": "ồ", "\u00e9": "ố", "\u00e8": "ổ", "\u00ea": "ỗ",
    "\u00eb": "ộ",
    "\u00ec": "ơ", "\u00ed": "ờ", "\u00ee": "ớ", "\u00f1": "ở", "\u00ef": "ỡ",
    "\u00f2": "ợ",
    "\u00f8": "ù", "\u00a7": "ú", "\u00a4": "ủ", "\u00a5": "ũ", "\u00a6": "ụ",
    "\u00f5": "ư", "\u00f6": "ừ", "\u00f7": "ứ", "\u00fa": "ử", "\u00fb": "ữ",
    "\u00fc": "ự",
    "\u00ef": "ỳ", "\u00fd": "ý", "\u00fe": "ỷ", "\u00ff": "ỹ", "\u00a1": "ỵ",
})


def _try_tcvn3_decode(raw: bytes) -> str:
    """Thử giải mã raw bytes theo TCVN3 (ABC) cũ.
    Phương pháp: decode Latin-1 rồi dùng bảng tra.translate."""
    try:
        latin = raw.decode("latin-1", errors="ignore")
        translated = latin.translate(_TCVN3_TO_UNICODE)
        # Kiểm tra có đủ lượng ký tự tiếng Việt hợp lý không
        viet_chars = re.findall(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệđìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]",
                                translated, flags=re.IGNORECASE)
        if len(viet_chars) >= max(3, len(translated) // 40):
            return translated
    except Exception:
        pass
    return ""


def _decode_ansi_with_legacy_fallbacks(raw: bytes) -> str:
    """Giải mã chuỗi bytes ANSI: thử CP1252 → nếu ít ký tự Việt hợp lý thì
    thử tiếp TCVN3, VNI (dự đoán heuristics)."""
    if not raw:
        return ""

    # Ưu tiên 1: CP1252 (tiêu chuẩn Windows)
    try:
        decoded = raw.decode("cp1252", errors="replace")
    except Exception:
        decoded = raw.decode("latin-1", errors="replace")

    # Nếu CP1252 cho ra nhiều "ký tự lạ" (>30% là \x80-\x9F hoặc biểu tượng)
    # thì thử bảng mã di sản
    weird = sum(1 for c in decoded if ord(c) in range(0x80, 0xA0) or ord(c) == 0xFFFD)
    ratio = weird / max(1, len(decoded))
    has_viet = bool(re.search(r"[àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]",
                              decoded, flags=re.IGNORECASE))

    if ratio > 0.08 and not has_viet:
        # Thử TCVN3 (phổ biến nhất của VN trước đây)
        tcvn = _try_tcvn3_decode(raw)
        if tcvn:
            return tcvn
    return decoded


def _brute_extract_text_from_stream(word_doc: bytes) -> str:
    """Phương pháp dự phòng: quét toàn bộ WordDocument stream, thử nhiều
    bảng mã (UTF-16LE → CP1252+legacy → TCVN3 thô) và giữ kết quả tốt nhất."""

    best_text = ""
    best_score = -1

    # 1) UTF-16LE (Word 2000+ lưu Unicode)
    try:
        dec = word_doc.decode("utf-16-le", errors="ignore")
        txt = "\n".join(
            m.strip() for m in re.findall(r"[\w\u00C0-\u1EF9 ,.;:!?()\"'\-–—\n\t/]{2,}", dec)
            if re.search(r"[A-Za-z\u00C0-\u1EF9]", m)
        )
        sc = _score_extracted_text(txt)
        if sc > best_score:
            best_score, best_text = sc, txt
    except Exception:
        pass

    # 2) CP1252 + fallback bảng mã di sản
    try:
        decoded_cp1252 = _decode_ansi_with_legacy_fallbacks(word_doc)
        txt = "\n".join(
            m.strip() for m in re.findall(r"[\w\u00C0-\u1EF9 ,.;:!?()\"'\-–—\n\t/]{2,}", decoded_cp1252)
            if re.search(r"[A-Za-z\u00C0-\u1EF9]", m)
        )
        sc = _score_extracted_text(txt)
        if sc > best_score:
            best_score, best_text = sc, txt
    except Exception:
        pass

    # 3) TCVN3 decode thô trên toàn bộ bytes
    try:
        tcvn_txt = _try_tcvn3_decode(word_doc)
        if tcvn_txt:
            txt = "\n".join(
                m.strip() for m in re.findall(r"[\w\u00C0-\u1EF9 ,.;:!?()\"'\-–—\n\t/]{2,}", tcvn_txt)
                if re.search(r"[A-Za-z\u00C0-\u1EF9]", m)
            )
            sc = _score_extracted_text(txt)
            if sc > best_score:
                best_score, best_text = sc, txt
    except Exception:
        pass

    # 4) Latin-1 cuối cùng
    if best_score <= 0:
        try:
            dec = word_doc.decode("latin-1", errors="ignore")
            txt = "\n".join(
                m.strip() for m in re.findall(r"[\w ,.;:!?()\"'\-–—\n\t/]{4,}", dec)
                if re.search(r"[A-Za-z]", m)
            )
            best_text = txt
        except Exception:
            pass

    meaningful = [m for m in best_text.split("\n") if len(m.strip()) >= 3]
    return "\n".join(meaningful)


# ---------------------------------------------------------------------------
# Trình đọc RTF (phổ biến: người dùng lưu RTF rồi đổi đuôi thành .doc)
# Parse manual: loại bỏ control words, giữ plain text, giải mã các escape
# ---------------------------------------------------------------------------

_RTF_CTRL_WORD = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?")
_RTF_HEX_BYTE = re.compile(r"\\'([0-9a-fA-F]{2})")


def read_rtf(path_or_bytes) -> str:
    """Đọc file RTF (có thể là file .doc bị đổi đuôi). Trả về plain text.
    Hỗ trợ \\uNNNN (Unicode escape) và \\'xx (hex byte ANSI)."""
    if isinstance(path_or_bytes, (str, pathlib.Path)):
        with open(path_or_bytes, "rb") as f:
            raw = f.read()
    else:
        raw = path_or_bytes

    # Bước 0: Kiểm tra header
    if not raw.lstrip().startswith(b"{\\rtf"):
        return ""

    try:
        text = raw.decode("latin-1", errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")

    # Thay thế Unicode escape \uNNNN? trước (lưu mã Unicode)
    def _replace_unicode(m):
        try:
            code = int(m.group(1))
            if code < 0:
                code += 65536
            return chr(code) + (m.group(2) or "")
        except Exception:
            return m.group(0)

    text = re.sub(r"\\u(-?\d+)(.?)", _replace_unicode, text)

    # Thay thế các hex-byte \'xx (thường là ký tự Việt theo CP1252 / TCVN3)
    # Gom các \'xx liền kề thành 1 bytes block rồi decode
    out_parts = []
    i = 0
    hex_buf = bytearray()
    n = len(text)

    def _flush_hex():
        nonlocal hex_buf
        if hex_buf:
            out_parts.append(_decode_ansi_with_legacy_fallbacks(bytes(hex_buf)))
            hex_buf = bytearray()

    while i < n:
        ch = text[i]
        if ch == "\\" and i + 2 < n and text[i + 1] == "'":
            hx = text[i + 2:i + 4]
            if re.fullmatch(r"[0-9a-fA-F]{2}", hx):
                hex_buf.append(int(hx, 16))
                i += 4
                continue
            else:
                _flush_hex()
                out_parts.append(ch)
                i += 1
                continue
        else:
            _flush_hex()

        if ch == "\\":
            # \* -> bỏ destination flag (tiếp theo là \*\NỘI_DUNG_BỎ)
            if i + 1 < n and text[i + 1] == "*":
                i += 2
                # bỏ skip group tiếp theo: \NỀN... {group bỏ}
                depth = 0
                started = False
                while i < n:
                    c = text[i]
                    if c == "{":
                        if not started:
                            started = True
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if started and depth <= 0:
                            i += 1
                            break
                    elif c == "\\" and i + 1 < n and text[i + 1] in "{}\\":
                        i += 2
                        continue
                    i += 1
                continue

            m = _RTF_CTRL_WORD.match(text, i)
            if m:
                word = m.group(1)
                param = m.group(2)
                i = m.end()
                # Các control word ngắt dòng / đoạn
                if word in ("par", "pard", "line", "lquote", "rquote",
                            "cell", "row", "sect", "page", "column", "tab"):
                    out_parts.append("\n" if word != "tab" else "\t")
                elif word in ("b", "i", "u", "strike", "plain", "f",
                              "fs", "cf", "cb", "qc", "ql", "qr", "qj",
                              "li", "ri", "fi", "sa", "sb", "sl",
                              "marg", "paper", "landscape", "pntext"):
                    pass  # định dạng thôi, bỏ qua
                elif word == "upr" or word == "ud":
                    pass
                elif word in ("ansicpg", "deff", "deflang", "deftab",
                              "fonttbl", "colortbl", "stylesheet",
                              "info", "title", "author", "operator",
                              "keywords", "comment", "doccomm", "vern"):
                    pass  # metadata/control, bỏ
                else:
                    pass
                continue

            # Escape \~ (non-breaking space) và \- (non-breaking hyphen)
            if i + 1 < n and text[i + 1] in "{}\\~-_|":
                out_parts.append(" " if text[i + 1] in ("~", "_") else text[i + 1])
                i += 2
                continue

            out_parts.append(ch)
            i += 1
            continue

        if ch == "{":
            # Group mở: bỏ qua các destination group như {\*\fonttbl ...}
            # Đơn giản: chỉ tăng depth mental, không xử lý group đặc biệt
            # (đã xử lý \* ở trên)
            i += 1
            continue
        if ch == "}":
            i += 1
            continue

        out_parts.append(ch)
        i += 1

    _flush_hex()
    result = "".join(out_parts)
    # Chuẩn hóa dòng trống thừa
    result = re.sub(r"[ \t]+\n", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


def _is_likely_rtf(path: str) -> bool:
    """Kiểm tra 512 byte đầu: có header {\\rtf1 hay không (dấu hiệu RTF đổi đuôi .doc)."""
    try:
        with open(path, "rb") as f:
            head = f.read(512).lstrip()
        return head.startswith(b"{\\rtf")
    except Exception:
        return False


def _is_likely_image_only(doc_bytes: bytes) -> bool:
    """Kiểm tra sơ bộ: nếu file chỉ chứa header OLE + payload PNG/JPEG/WMF
    (không có stream text đáng kể)."""
    # Nếu có PNG/JPEG signature ở nhiều vị trí và không tìm thấy ký tự text thông thường
    png_count = doc_bytes.count(b"\x89PNG\r\n")
    jpeg_count = doc_bytes.count(b"\xff\xd8\xff")
    emf_count = doc_bytes.count(b"\x01\x00\x00\x00")  # EMF header
    # Dấu hiệu: nhiều ảnh / ít ký tự ASCII chữ cái
    letter = sum(1 for b in doc_bytes if (65 <= b <= 90) or (97 <= b <= 122))
    ratio = letter / max(1, len(doc_bytes))
    return (png_count + jpeg_count + emf_count) >= 1 and ratio < 0.02


def read_doc(path: str) -> str:
    """Đọc file .doc (Word 97-2003) bằng nhiều fallback:
    1. RTF đổi đuôi → parse RTF (phổ biến #1)
    2. OLE chuẩn → PieceTable (chính xác)
    3. PieceTable thất bại → brute quét nhiều bảng mã (UTF-16LE / CP1252 / TCVN3 / VNI)
    4. Vẫn rỗng → metadata SummaryInformation.
    NẾU vẫn rỗng: raise ValueError với lý do cụ thể (không báo chung chung nữa)."""

    # Đọc toàn bộ bytes một lần (RTF check + image check cần)
    with open(path, "rb") as f:
        full_bytes = f.read()

    if not full_bytes:
        raise ValueError("File .doc này rỗng (0 bytes). Kiểm tra lại file nguồn.")

    # ---------------------------------------------------------------
    # Trường hợp 1: RTF đổi đuôi thành .doc (rất phổ biến ở Việt Nam)
    # ---------------------------------------------------------------
    if full_bytes.lstrip().startswith(b"{\\rtf"):
        text = read_rtf(full_bytes)
        if text.strip():
            return text.strip()

    # ---------------------------------------------------------------
    # Trường hợp 2: File OLE Compound (Word .doc thật)
    # ---------------------------------------------------------------
    if not olefile.isOleFile(path):
        # Không phải OLE, không phải RTF → có thể là scan lưu dạng image đơn thuần
        if _is_likely_image_only(full_bytes):
            raise ValueError(
                "File này trông giống ảnh/scan được lưu nhầm đuôi .doc "
                "(chứa PNG/JPEG/WMF, không có text). Hãy OCR sang PDF có text "
                "hoặc gõ lại nội dung đề thi."
            )
        # Không rõ format gì
        head_hex = full_bytes[:16].hex()
        raise ValueError(
            f"File .doc này không phải định dạng OLE Word hợp lệ (cũng không phải RTF). "
            f"16 bytes đầu: {head_hex}. Nếu là file .doc Word 6.0 cũ, hãy mở bằng Word "
            f"rồi Lưu thành .docx / PDF có text."
        )

    with olefile.OleFileIO(path) as ole:
        if not ole.exists("WordDocument"):
            streams = ole.listdir()
            msg_extra = (
                " (File này chứa các stream: " + ", ".join("/".join(s) for s in streams[:8]) + ")"
            )
            raise ValueError(
                "File .doc này không có nội dung text (stream 'WordDocument' không tồn tại)."
                + msg_extra
                + " Hãy mở bằng Microsoft Word rồi Lưu thành .docx / PDF."
            )

        word_doc = ole.openstream("WordDocument").read()
        if len(word_doc) < 12:
            raise ValueError("Stream WordDocument quá ngắn — file .doc có thể bị hỏng.")

        # Xác định 0/1 Table
        w_flags = struct.unpack_from("<H", word_doc, 0x000A)[0]
        table_name = "1Table" if (w_flags & 0x0200) else "0Table"
        table_stream = b""
        if ole.exists(table_name):
            try:
                table_stream = ole.openstream(table_name).read()
            except Exception:
                table_stream = b""

        text = _extract_text_via_piece_table(word_doc, table_stream)
        if not text.strip():
            text = _brute_extract_text_from_stream(word_doc)

        # Vẫn rỗng → thử metadata
        if not text.strip():
            try:
                meta = ole.get_metadata()
                parts = [
                    p.strip() for p in [
                        meta.title, meta.subject, meta.author, meta.keywords, meta.comments
                    ] if isinstance(p, str) and p.strip()
                ]
                text = "\n".join(parts)
            except Exception:
                pass

        if text.strip():
            return text.strip()

        # ---------------------------------------------------------------
        # Đến đây vẫn rỗng → báo lý do cụ thể thay vì "không đọc được"
        # ---------------------------------------------------------------
        if _is_likely_image_only(word_doc + table_stream):
            raise ValueError(
                "File .doc này là file ảnh scan/nhúng hình (không chữ bên trong). "
                "Hãy OCR (Adobe Acrobat / Google Drive) thành PDF có text, hoặc "
                "mở bằng Microsoft Word, Ctrl+A, Ctrl+C rồi dán lại vào file mới."
            )
        else:
            raise ValueError(
                "Không thể trích xuất text từ file .doc này. Có thể file dùng "
                "bảng mã VNI / VSCII rất cổ, hoặc nội dung được bảo vệ mật khẩu. "
                "Cách khắc phục nhanh nhất: mở = Word → 'Lưu thành' → chọn .docx "
                "rồi tải lên lại."
            )


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
