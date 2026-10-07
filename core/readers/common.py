"""Kiểu dữ liệu và hàm dùng chung cho các bộ đọc file."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Ký hiệu engine OCR được yêu cầu chèn vào chỗ chữ không đọc nổi.
UNREADABLE_MARK = "[không đọc được]"

_VIET_SPECIFIC = re.compile(
    r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệ"
    r"ìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-zÀ-ỹ]{2,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f﻿​]")


@dataclass
class PageInfo:
    """Kết quả đọc của MỘT trang PDF (hoặc một ảnh nhúng)."""

    number: int                      # số trang, tính từ 1
    method: str                      # "text" | "ocr" | "blank" | "skipped" | "failed"
    engine: str = ""                 # engine đã dùng (pdfplumber, Gemini, Tesseract...)
    chars: int = 0                   # số ký tự đọc được
    confidence: float | None = None  # 0..1 — chỉ có với engine OCR tự báo độ tin cậy
    issues: list[str] = field(default_factory=list)  # vấn đề riêng của trang


@dataclass
class ExtractionResult:
    """Kết quả đọc một file đầu vào, kèm thông tin để cảnh báo người dùng."""

    text: str
    file_type: str                   # "docx" | "doc" | "rtf" | "pdf"
    method: str = ""                 # mô tả ngắn cách đã đọc
    used_ocr: bool = False
    ocr_engine: str = ""
    pages: list[PageInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ocr_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.method == "ocr"]

    @property
    def problem_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.issues or p.method in ("failed", "skipped")]

    @property
    def needs_review(self) -> bool:
        """True nếu người dùng NÊN đối chiếu lại với bản gốc trước khi dùng."""
        return self.used_ocr or bool(self.warnings) or bool(self.problem_pages)


def clean_text(text: str) -> str:
    """Chuẩn hóa văn bản sau khi đọc: Unicode NFC, bỏ ký tự điều khiển,
    gọn khoảng trắng thừa. Không đổi nội dung chữ."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = _CONTROL.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def score_text(text: str) -> int:
    """Điểm "chất lượng" của văn bản trích được — dùng để chọn kết quả tốt
    nhất giữa nhiều cách đọc. Từ có dấu tiếng Việt được tính nặng hơn."""
    if not text:
        return -1
    tokens = _WORD.findall(text)
    if not tokens:
        return -1
    viet = sum(1 for t in tokens if _VIET_SPECIFIC.search(t))
    return len(tokens) * 2 + viet * 5


def text_stats(text: str) -> dict:
    """Vài số đo để đánh giá văn bản có "giống tiếng Việt đọc được" không."""
    tokens = _WORD.findall(text or "")
    nonspace = [c for c in (text or "") if not c.isspace()]
    viet = sum(1 for t in tokens if _VIET_SPECIFIC.search(t))
    bad = sum(
        1 for c in nonspace
        if c == "�" or "" <= c <= "" or (ord(c) < 32)
    )
    bad += 6 * len(re.findall(r"\(cid:\d+\)", text or ""))
    return {
        "chars": len(nonspace),
        "words": len(tokens),
        "viet_ratio": viet / len(tokens) if tokens else 0.0,
        "bad_ratio": bad / len(nonspace) if nonspace else 0.0,
        "unreadable_marks": (text or "").lower().count(UNREADABLE_MARK),
    }


# ---------------------------------------------------------------------------
# Bảng mã tiếng Việt cũ TCVN3 (ABC — font .VnTime, .VnArial...)
# Văn bản gõ bằng bảng mã này lưu mỗi chữ có dấu bằng MỘT byte Latin-1, nên
# khi đọc ra sẽ thành "ViÖt Nam", "QuyÕt ®Þnh". Bảng dưới chuyển về Unicode.
# ---------------------------------------------------------------------------
_TCVN3_MAP = {
    "µ": "à", "¶": "ả", "·": "ã", "¸": "á", "¹": "ạ",
    "¨": "ă", "»": "ằ", "¼": "ẳ", "½": "ẵ", "¾": "ắ", "Æ": "ặ",
    "©": "â", "Ç": "ầ", "È": "ẩ", "É": "ẫ", "Ê": "ấ", "Ë": "ậ",
    "®": "đ",
    "Ì": "è", "Î": "ẻ", "Ï": "ẽ", "Ð": "é", "Ñ": "ẹ",
    "ª": "ê", "Ò": "ề", "Ó": "ể", "Ô": "ễ", "Õ": "ế", "Ö": "ệ",
    "×": "ì", "Ø": "ỉ", "Ü": "ĩ", "Ý": "í", "Þ": "ị",
    "ß": "ò", "á": "ỏ", "â": "õ", "ã": "ó", "ä": "ọ",
    "«": "ô", "å": "ồ", "æ": "ổ", "ç": "ỗ", "è": "ố", "é": "ộ",
    "¬": "ơ", "ê": "ờ", "ë": "ở", "ì": "ỡ", "í": "ớ", "î": "ợ",
    "ï": "ù", "ñ": "ủ", "ò": "ũ", "ó": "ú", "ô": "ụ",
    "­": "ư", "õ": "ừ", "ö": "ử", "÷": "ữ", "ø": "ứ", "ù": "ự",
    "ú": "ỳ", "û": "ỷ", "ü": "ỹ", "ý": "ý", "þ": "ỵ",
    "¡": "Ă", "¢": "Â", "£": "Ê", "¤": "Ô", "¥": "Ơ", "¦": "Ư", "§": "Đ",
}
_TCVN3_TABLE = str.maketrans(_TCVN3_MAP)
# Các ký tự CHỈ xuất hiện dày đặc khi văn bản là TCVN3 (không trùng chữ
# tiếng Việt Unicode thông thường như ã, â, ê, ô, ó...).
_TCVN3_SIGNATURE = re.compile("[µ¶·¸¹¨»¼½¾Æ©ÇÈÉÊË®ÌÎÏÐÑªÒÓÔÕÖ×ØÜÝÞß«¬­¡¢£¤¥¦§÷øþ]")
_UNICODE_VIET_ONLY = re.compile(r"[ĂăĐđĨĩŨũƠơƯưẠ-ỹ]")
# Bảng mã VNI-Windows: nguyên âm + ký tự dấu rời ("vieät", "ngöôøi").
_VNI_SIGNATURE = re.compile(r"[aeiouyAEIOUYöô][øùûõïâáàåãäêéèúüë]")


def fix_legacy_vietnamese(text: str) -> tuple[str, str | None]:
    """Phát hiện văn bản gõ bằng bảng mã cũ và chuyển về Unicode nếu được.

    Trả về (văn bản, tên bảng mã phát hiện được hoặc None).
    - TCVN3: tự chuyển.
    - VNI: chỉ phát hiện để cảnh báo (không tự chuyển vì dễ sai)."""
    if not text:
        return text, None
    unicode_viet = len(_UNICODE_VIET_ONLY.findall(text))
    tcvn3 = len(_TCVN3_SIGNATURE.findall(text))
    if tcvn3 >= 15 and tcvn3 > 5 * unicode_viet:
        return unicodedata.normalize("NFC", text.translate(_TCVN3_TABLE)), "TCVN3"
    vni = len(_VNI_SIGNATURE.findall(text))
    letters = sum(1 for c in text if c.isalpha())
    if vni >= 15 and vni > 5 * unicode_viet and vni > letters * 0.04:
        return text, "VNI"
    return text, None
