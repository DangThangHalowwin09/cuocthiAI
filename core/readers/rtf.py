"""Đọc file RTF (kể cả RTF bị đổi đuôi thành .doc — khá phổ biến).

Bộ đọc cũ có 3 lỗi làm kết quả gần như không dùng được với RTF thật:
  - không bỏ bảng font/bảng style nên tên font, tên style lẫn vào đầu văn bản;
  - sau mỗi ký tự Unicode (\\uN) RTF luôn kèm một ký tự "dự phòng" phải BỎ
    QUA, bản cũ giữ lại nên chữ có dấu bị lặp/thêm dấu "?" ("châân", "lụ?c");
  - bỏ mất chú thích cuối trang.
"""

from __future__ import annotations

import re

from .common import ExtractionResult, clean_text, fix_legacy_vietnamese

# Nhóm "đích" không chứa nội dung văn bản → bỏ nguyên cả nhóm.
_SKIP_DESTINATIONS = frozenset((
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "objdata",
    "themedata", "colorschememapping", "datastore", "latentstyles", "listtable",
    "listoverridetable", "revtbl", "rsidtbl", "generator", "xmlnstbl", "mmathPr",
    "filetbl", "fontemb", "fontfile", "expandedcolortbl", "pgdsctbl", "pgdsc",
    "header", "headerl", "headerr", "headerf", "footer", "footerl", "footerr",
    "footerf", "ftnsep", "ftnsepc", "ftncn", "aftnsep", "aftnsepc", "aftncn",
    "fldinst", "bkmkstart", "bkmkend", "nonshppict", "shppict", "sp", "sn",
    "background", "atnid", "atnauthor", "annotation", "atrfstart", "atrfend",
    "template", "private", "passwordhash", "wgrffmtfilter", "userprops",
    "operator", "author", "title", "subject", "keywords", "comment", "doccomm",
    "company", "manager", "category", "hlinkbase", "printim", "creatim", "revtim",
    "buptim", "panose", "falt", "listname", "liststylename", "pnseclvl",
    "listtext", "pntext", "sv", "shprslt",
))
# Ghi chú: "listtext"/"pntext" chứa nhãn đánh số dạng chữ ("1.", "a)") — được
# xử lý riêng bên dưới để GIỮ lại, nên không thực sự bị bỏ.
# "shpinst"/"shptxt": chữ trong text box (hình vẽ) — cũng giữ lại.
_KEEP_TEXT_DESTINATIONS = frozenset(("listtext", "pntext", "shpinst", "shptxt"))

_SPECIAL = {
    "par": "\n", "sect": "\n", "page": "\n", "line": "\n", "row": "\n",
    "tab": "\t", "cell": " | ", "nestcell": " | ", "nestrow": "\n",
    "emdash": "—", "endash": "–", "emspace": " ", "enspace": " ", "qmspace": " ",
    "bullet": "•", "lquote": "‘", "rquote": "’", "ldblquote": "“", "rdblquote": "”",
}

_TOKEN = re.compile(
    r"\\([a-zA-Z]{1,32})(-?\d{1,10})?[ ]?"   # control word (+ tham số) + 1 dấu cách phân tách
    r"|\\'([0-9a-fA-F]{2})"                  # byte hex theo bảng mã ANSI
    r"|\\([^a-zA-Z])"                        # control symbol
    r"|([{}])"                               # mở/đóng nhóm
    r"|[\r\n]+"                              # xuống dòng trong file RTF: không có nghĩa
    r"|([^\\{}\r\n]+)",                      # chữ thường
    re.DOTALL,
)


def rtf_to_text(data: bytes) -> str:
    """Chuyển nội dung RTF thành văn bản thường."""
    source = data.decode("latin-1")
    codec = "cp1252"
    out: list[str] = []
    pending = bytearray()           # các byte \'xx liền nhau, giải mã một lượt
    # Trạng thái theo nhóm: (bỏ qua?, số ký tự dự phòng sau \u, đang ở chú thích?)
    stack: list[tuple[bool, int, bool]] = []
    ignore, uc_skip, in_note = False, 1, False
    skip_chars = 0                  # số ký tự dự phòng còn phải bỏ sau \uN
    after_star = False              # vừa gặp \* → nhóm đích tùy chọn

    def flush():
        if pending:
            try:
                out.append(bytes(pending).decode(codec, errors="replace"))
            except LookupError:
                out.append(bytes(pending).decode("cp1252", errors="replace"))
            pending.clear()

    for m in _TOKEN.finditer(source):
        word, param, hexbyte, symbol, brace, text = m.groups()

        if brace == "{":
            flush()
            stack.append((ignore, uc_skip, in_note))
            skip_chars = 0
            continue
        if brace == "}":
            flush()
            was_note = in_note
            if stack:
                ignore, uc_skip, in_note = stack.pop()
            if was_note and not in_note:
                out.append("]")
            skip_chars = 0
            after_star = False
            continue

        if word:
            flush()
            if after_star:
                # {\*\đích_không_biết ...}: theo chuẩn RTF được phép bỏ qua.
                after_star = False
                if word not in _KEEP_TEXT_DESTINATIONS and word not in ("footnote",):
                    ignore = True
                    continue
            if word == "ansicpg" and param:
                codec = f"cp{param}"
            elif word == "uc" and param is not None:
                uc_skip = max(0, int(param))
            elif word == "u" and param is not None:
                if not ignore:
                    code = int(param)
                    out.append(chr(code + 65536 if code < 0 else code))
                skip_chars = uc_skip
            elif word == "footnote":
                if not ignore:
                    out.append(" [Chú thích: ")
                    in_note = True
            elif word in _KEEP_TEXT_DESTINATIONS:
                pass
            elif word in _SKIP_DESTINATIONS:
                ignore = True
            elif word == "chftn":
                pass  # số chú thích tự động — không cần
            elif word in _SPECIAL and not ignore:
                out.append(_SPECIAL[word])
            continue

        if hexbyte:
            if skip_chars:
                skip_chars -= 1
            elif not ignore:
                pending.append(int(hexbyte, 16))
            continue

        if symbol:
            flush()
            if symbol == "*":
                after_star = True
            elif skip_chars:
                skip_chars -= 1
            elif not ignore:
                if symbol in "{}\\":
                    out.append(symbol)
                elif symbol == "~":
                    out.append(" ")
                elif symbol == "_":
                    out.append("-")
                elif symbol in "\r\n":
                    out.append("\n")
            continue

        if text:
            flush()
            if skip_chars:
                cut = min(skip_chars, len(text))
                text, skip_chars = text[cut:], skip_chars - cut
            if text and not ignore:
                out.append(text)

    flush()
    result = "".join(out)
    # Dọn bảng: bỏ dấu "|" thừa ở cuối hàng.
    result = re.sub(r"[ \t]*\|[ \t]*\n", "\n", result)
    result = re.sub(r"\[Chú thích:\s+", "[Chú thích: ", result)
    result = re.sub(r"\s+\]", "]", result)
    result = "\n".join(line.strip() for line in result.split("\n"))
    return result


def extract_rtf(path: str) -> ExtractionResult:
    with open(path, "rb") as f:
        data = f.read()
    if not data.lstrip()[:5] == b"{\\rtf":
        raise ValueError("File này không phải định dạng RTF hợp lệ.")

    text, legacy = fix_legacy_vietnamese(rtf_to_text(data))
    warnings = []
    if legacy == "TCVN3":
        warnings.append(
            "Văn bản gõ bằng bảng mã cũ TCVN3 (font .VnTime...) — đã tự chuyển sang "
            "Unicode. Chữ IN HOA có dấu có thể bị thành chữ thường; cần đọc soát lại."
        )
    elif legacy == "VNI":
        warnings.append(
            "Văn bản có vẻ gõ bằng bảng mã cũ VNI nên chữ có dấu hiển thị sai. Hãy "
            "chuyển mã sang Unicode (Unikey → Công cụ chuyển mã) rồi tải lên lại."
        )
    text = clean_text(text)
    if not text:
        raise ValueError(
            "File RTF này không có nội dung chữ đọc được (có thể chỉ chứa ảnh). "
            "Nếu là bản scan, hãy xuất thành PDF rồi tải lên để nhận dạng chữ (OCR)."
        )
    return ExtractionResult(text=text, file_type="rtf", method="RTF — đọc trực tiếp nội dung chữ", warnings=warnings)
