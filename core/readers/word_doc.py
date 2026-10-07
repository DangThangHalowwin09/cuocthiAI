"""Đọc file .doc (Word 97-2003, định dạng nhị phân OLE).

Cách đọc chuẩn: lấy "piece table" (bảng mô tả các mảnh văn bản) trong luồng
Table, ghép các mảnh từ luồng WordDocument. Vị trí của piece table ghi trong
FIB (File Information Block) tại offset 0x01A2 (fcClx) / 0x01A6 (lcbClx).

LƯU Ý: bản cũ của file này đọc nhầm offset 0x01FA nên KHÔNG BAO GIỜ tìm thấy
piece table, luôn rơi xuống chế độ "quét thô" — chế độ đó làm mất các ký tự
như "%", ngoặc kép cong, dấu "+", "=" ... và sinh thêm ký tự rác ở cuối.
"""

from __future__ import annotations

import re
import struct

from .common import ExtractionResult, clean_text, fix_legacy_vietnamese, score_text

# Offset trong FIB (Word 97 trở lên)
_FIB_FLAGS = 0x000A
_FIB_FCMIN, _FIB_FCMAC = 0x0018, 0x001C          # Word 6/95: vùng chữ
_FIB_CCP_TEXT = 0x004C                           # số ký tự thân văn bản
_FIB_CCP_FTN, _FIB_CCP_HDD = 0x0050, 0x0054      # chú thích cuối trang, đầu/chân trang
_FIB_CCP_MCR, _FIB_CCP_ATN = 0x0058, 0x005C      # macro, ghi chú (comment)
_FIB_CCP_EDN, _FIB_CCP_TXBX = 0x0060, 0x0064     # chú thích cuối văn bản, text box
_FIB_CCP_HDRTXBX = 0x0068
_FIB_FCCLX, _FIB_LCBCLX = 0x01A2, 0x01A6

_F_ENCRYPTED = 0x0100
_F_WHICH_TABLE = 0x0200


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0] if offset + 2 <= len(data) else 0


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0] if offset + 4 <= len(data) else 0


def _piece_table_text(word_doc: bytes, table: bytes) -> str:
    """Ghép toàn bộ chữ của file theo piece table. Trả "" nếu không hợp lệ."""
    fc_clx, lcb_clx = _u32(word_doc, _FIB_FCCLX), _u32(word_doc, _FIB_LCBCLX)
    if not lcb_clx or fc_clx + lcb_clx > len(table):
        return ""
    clx = table[fc_clx: fc_clx + lcb_clx]

    # Clx = [các Prc (0x01, bỏ qua)] + Pcdt (0x02 + độ dài + PlcPcd)
    pos, plc = 0, None
    while pos < len(clx):
        kind = clx[pos]
        if kind == 0x01:
            pos += 3 + _u16(clx, pos + 1)
        elif kind == 0x02:
            size = _u32(clx, pos + 1)
            plc = clx[pos + 5: pos + 5 + size]
            break
        else:
            return ""
    if not plc or len(plc) < 16:
        return ""

    n = (len(plc) - 4) // 12            # n mảnh: (n+1) CP 4 byte + n PCD 8 byte
    cps = [_u32(plc, i * 4) for i in range(n + 1)]
    out = []
    for i in range(n):
        count = cps[i + 1] - cps[i]
        if count <= 0:
            continue
        fc_raw = _u32(plc, (n + 1) * 4 + i * 8 + 2)
        compressed = bool(fc_raw & 0x40000000)
        fc = fc_raw & 0x3FFFFFFF
        if compressed:      # 1 byte/ký tự, bảng mã Windows-1252
            chunk = word_doc[fc // 2: fc // 2 + count]
            out.append(chunk.decode("cp1252", errors="replace"))
        else:               # 2 byte/ký tự, UTF-16LE
            chunk = word_doc[fc: fc + count * 2]
            out.append(chunk.decode("utf-16-le", errors="replace"))
    return "".join(out)


def _strip_fields(text: str) -> str:
    """Bỏ mã trường của Word, giữ kết quả hiển thị.
    Cấu trúc: 0x13 <mã lệnh> 0x14 <kết quả hiển thị> 0x15."""
    out = []
    stack = []  # mỗi phần tử: True = đang ở phần mã lệnh (không lấy)
    for ch in text:
        if ch == "\x13":
            stack.append(True)
        elif ch == "\x14":
            if stack:
                stack[-1] = False
        elif ch == "\x15":
            if stack:
                stack.pop()
        elif not any(stack):
            out.append(ch)
    return "".join(out)


def _cleanup_story(text: str) -> str:
    """Đổi các ký tự điều khiển của Word thành văn bản thường."""
    text = _strip_fields(text)
    # Bảng: mỗi ô kết thúc bằng 0x07, cuối hàng có thêm một 0x07 nữa.
    text = text.replace("\x07\x07", " |\n").replace("\x07", " | ")
    text = text.replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    text = text.replace("\x1e", "-").replace("\x1f", "").replace("\xa0", " ")
    # 0x01 hình ảnh, 0x02 số chú thích tự động, 0x05 dấu ghi chú, 0x08 hình vẽ...
    text = re.sub(r"[\x00-\x08\x0e-\x1f]", "", text)
    text = re.sub(r"^ \|\n", "", text)
    return text


def _split_notes(story: str) -> list[str]:
    """Tách vùng chú thích thành từng chú thích (mỗi cái mở đầu bằng 0x02)."""
    notes = [n for n in story.split("\x02")]
    if notes and not notes[0].strip("\r\n "):
        notes = notes[1:]
    return [clean_text(_cleanup_story(n)).replace("\n", " ") for n in notes]


def _inline_notes(main: str, notes: list[str]) -> tuple[str, list[str]]:
    """Chèn nội dung chú thích vào đúng chỗ đánh dấu (0x02) trong thân văn bản.
    Nếu số lượng không khớp thì trả lại danh sách để nối xuống cuối."""
    notes = [n for n in notes if n]
    if not notes:
        return main, []
    if main.count("\x02") == len(notes):
        it = iter(notes)
        return re.sub("\x02", lambda _m: f" [Chú thích: {next(it)}]", main), []
    return main, notes


def _brute_force_text(word_doc: bytes) -> str:
    """Dự phòng khi không đọc được piece table (file hỏng/không chuẩn): quét
    cả luồng theo UTF-16LE và Windows-1252, giữ các đoạn đọc được."""
    pattern = re.compile(r"[^\x00-\x08\x0e-\x1f�\ud800-￿ɐ-᷿℀-￿]{4,}")
    best, best_score = "", -1
    for encoding in ("utf-16-le", "cp1252"):
        decoded = word_doc.decode(encoding, errors="replace")
        runs = [
            m.group(0).strip() for m in pattern.finditer(decoded)
            if len(re.findall(r"[A-Za-zÀ-ỹ]", m.group(0))) >= 3
        ]
        candidate = "\n".join(runs).replace("\r", "\n")
        score = score_text(candidate)
        if score > best_score:
            best, best_score = candidate, score
    return best


def extract_doc(path: str) -> ExtractionResult:
    try:
        import olefile
    except ImportError as e:
        raise ValueError(
            "Chưa cài thư viện 'olefile' nên chưa đọc được file .doc. Chạy: "
            "pip install olefile — hoặc mở file bằng Word rồi Lưu thành .docx."
        ) from e

    if not olefile.isOleFile(path):
        raise ValueError(
            "File .doc này không phải định dạng Word 97-2003 hợp lệ. Hãy mở bằng "
            "Word rồi Lưu thành .docx hoặc PDF."
        )

    with olefile.OleFileIO(path) as ole:
        if ole.exists("EncryptedPackage"):
            raise ValueError(
                "File đang được đặt mật khẩu mở (mã hóa). Hãy mở bằng Word, bỏ mật "
                "khẩu (File → Info → Protect Document) rồi Lưu lại."
            )
        if not ole.exists("WordDocument"):
            streams = ", ".join("/".join(s) for s in ole.listdir()[:6])
            raise ValueError(
                "File .doc này không chứa văn bản Word (thiếu luồng 'WordDocument'; "
                f"file chứa: {streams}). Hãy mở bằng Word rồi Lưu thành .docx."
            )
        word_doc = ole.openstream("WordDocument").read()
        if len(word_doc) < 0x60:
            raise ValueError("File .doc bị hỏng (phần đầu file quá ngắn).")

        flags = _u16(word_doc, _FIB_FLAGS)
        if flags & _F_ENCRYPTED:
            raise ValueError(
                "File .doc đang được đặt mật khẩu (mã hóa) nên không đọc được nội "
                "dung. Hãy mở bằng Word, bỏ mật khẩu rồi Lưu lại."
            )
        table_name = "1Table" if flags & _F_WHICH_TABLE else "0Table"
        table = ole.openstream(table_name).read() if ole.exists(table_name) else b""

    warnings: list[str] = []
    method = "Word .doc — đọc theo cấu trúc chuẩn (piece table)"
    n_fib = _u16(word_doc, 2)

    full = _piece_table_text(word_doc, table) if table else ""
    if full:
        sizes = [_u32(word_doc, off) for off in (
            _FIB_CCP_TEXT, _FIB_CCP_FTN, _FIB_CCP_HDD, _FIB_CCP_MCR,
            _FIB_CCP_ATN, _FIB_CCP_EDN, _FIB_CCP_TXBX, _FIB_CCP_HDRTXBX,
        )]
        if sizes[0] == 0 or sum(sizes) > len(full) + 8:
            sizes = [len(full), 0, 0, 0, 0, 0, 0, 0]   # FIB bất thường: coi tất cả là thân văn bản
        stories, pos = [], 0
        for size in sizes:
            stories.append(full[pos: pos + size])
            pos += size
        main, footnotes, headers, _macros, _comments, endnotes, textboxes, _hdr_boxes = stories

        main, leftover = _inline_notes(main, _split_notes(footnotes) + _split_notes(endnotes))
        parts = [_cleanup_story(main)]
        if leftover:
            parts.append("[Chú thích]\n" + "\n".join(leftover))
        box_text = clean_text(_cleanup_story(textboxes))
        if box_text:
            parts.append("[Khung văn bản]\n" + box_text)
        header_lines = []
        for line in clean_text(_cleanup_story(headers)).split("\n"):
            line = line.strip()
            if line and line not in header_lines and not re.fullmatch(r"[\d\s/\-–]*", line):
                header_lines.append(line)
        if header_lines:
            parts.append("[Đầu trang / chân trang] " + " / ".join(header_lines))
        text = "\n".join(parts)
    elif n_fib and n_fib < 0x00C1:
        # Word 6.0/95: chữ 1 byte/ký tự nằm liền nhau từ fcMin đến fcMac.
        raw = word_doc[_u32(word_doc, _FIB_FCMIN): _u32(word_doc, _FIB_FCMAC)]
        text = _cleanup_story(raw.decode("cp1252", errors="replace"))
        method = "Word .doc đời cũ (Word 6.0/95)"
    else:
        text = _brute_force_text(word_doc)
        method = "Word .doc — chế độ dự phòng (quét thô)"
        if text.strip():
            warnings.append(
                "Không đọc được cấu trúc chuẩn của file .doc nên phải dùng chế độ dự "
                "phòng: có thể THIẾU hoặc SAI ký tự, lẫn ký tự rác. Nên mở file bằng "
                "Word → Lưu thành .docx rồi tải lên lại."
            )

    text, legacy = fix_legacy_vietnamese(text)
    if legacy == "TCVN3":
        warnings.append(
            "Văn bản gõ bằng bảng mã cũ TCVN3 (font .VnTime...) — đã tự chuyển sang "
            "Unicode. Chữ IN HOA có dấu (font .VnTimeH) có thể bị thành chữ thường; "
            "cần đọc soát lại."
        )
    elif legacy == "VNI":
        warnings.append(
            "Văn bản có vẻ gõ bằng bảng mã cũ VNI nên chữ có dấu hiển thị sai. Hãy "
            "chuyển mã sang Unicode (Unikey → Công cụ chuyển mã) rồi tải lên lại."
        )

    text = clean_text(text)
    if not text:
        raise ValueError(
            "File .doc này không có nội dung chữ đọc được (có thể chỉ chứa ảnh "
            "chụp/scan). Nếu là bản scan, hãy xuất thành PDF rồi tải lên để hệ "
            "thống nhận dạng chữ (OCR)."
        )
    return ExtractionResult(text=text, file_type="doc", method=method, warnings=warnings)
