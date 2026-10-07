"""Đọc file .docx (Word OpenXML) theo ĐÚNG THỨ TỰ trong văn bản.

Bộ đọc cũ lấy `doc.paragraphs` rồi mới tới `doc.tables`, nên:
  - bảng bị dồn xuống cuối, mất vị trí so với đoạn văn xung quanh;
  - ô gộp (merge) bị lặp nội dung; khung văn bản (text box) bị lặp 2 lần;
  - chú thích cuối trang, số thứ tự tự động ("1.", "a)"), chữ chèn bằng
    Track Changes, chữ trong content control... bị bỏ sót.

Bộ đọc này duyệt trực tiếp cây XML của thân văn bản nên giữ được thứ tự và
đọc đủ các thành phần trên.
"""

from __future__ import annotations

import io
import re
import zipfile

from .common import ExtractionResult, clean_text

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _w(tag: str) -> str:
    return f"{{{W}}}{tag}"


_P, _TBL, _TR, _TC = _w("p"), _w("tbl"), _w("tr"), _w("tc")
_T, _TAB, _BR, _CR = _w("t"), _w("tab"), _w("br"), _w("cr")
_TXBX = _w("txbxContent")
_ALT, _CHOICE, _FALLBACK = f"{{{MC}}}AlternateContent", f"{{{MC}}}Choice", f"{{{MC}}}Fallback"
# Không lấy: chữ đã bị xóa (Track Changes), mã trường (field code).
_SKIP = {_w("delText"), _w("instrText"), _w("del"), _w("moveFrom")}
_VAL = _w("val")


class _Numbering:
    """Tính lại nhãn đánh số tự động của Word ("1.", "a)", "-"...).

    Word không lưu chữ "1." trong đoạn văn mà chỉ lưu "đoạn này thuộc danh
    sách X, cấp Y" — nếu không tính lại thì danh sách bị can/điều khoản đánh
    số tự động sẽ mất hết số thứ tự."""

    def __init__(self, numbering_root, styles_root):
        self.abstract: dict[str, dict[int, dict]] = {}
        self.num_to_abstract: dict[str, str] = {}
        self.start_override: dict[tuple[str, int], int] = {}
        self.style_numpr: dict[str, tuple[str, int]] = {}
        self.counters: dict[str, dict[int, int]] = {}
        self.seen_nums: set[str] = set()

        if numbering_root is not None:
            for an in numbering_root.iter(_w("abstractNum")):
                levels = {}
                for lvl in an.iter(_w("lvl")):
                    ilvl = int(lvl.get(_w("ilvl"), "0"))
                    levels[ilvl] = {
                        "start": self._int(lvl.find(_w("start")), 1),
                        "fmt": self._val(lvl.find(_w("numFmt")), "decimal"),
                        "text": self._val(lvl.find(_w("lvlText")), ""),
                    }
                self.abstract[an.get(_w("abstractNumId"))] = levels
            for num in numbering_root.iter(_w("num")):
                num_id = num.get(_w("numId"))
                ref = num.find(_w("abstractNumId"))
                if ref is not None:
                    self.num_to_abstract[num_id] = ref.get(_VAL)
                for ov in num.iter(_w("lvlOverride")):
                    so = ov.find(_w("startOverride"))
                    if so is not None:
                        self.start_override[(num_id, int(ov.get(_w("ilvl"), "0")))] = int(so.get(_VAL))

        if styles_root is not None:
            for style in styles_root.iter(_w("style")):
                numpr = style.find(f"{_w('pPr')}/{_w('numPr')}")
                if numpr is not None:
                    num_id = self._val(numpr.find(_w("numId")), None)
                    if num_id and num_id != "0":
                        ilvl = self._int(numpr.find(_w("ilvl")), 0)
                        self.style_numpr[style.get(_w("styleId"))] = (num_id, ilvl)

    @staticmethod
    def _val(el, default):
        return el.get(_VAL) if el is not None and el.get(_VAL) is not None else default

    @staticmethod
    def _int(el, default):
        try:
            return int(el.get(_VAL))
        except (AttributeError, TypeError, ValueError):
            return default

    @staticmethod
    def _format(n: int, fmt: str) -> str:
        if fmt in ("lowerLetter", "upperLetter"):
            s, n = "", max(n, 1)
            while n > 0:
                n, r = divmod(n - 1, 26)
                s = chr(97 + r) + s
            return s.upper() if fmt == "upperLetter" else s
        if fmt in ("lowerRoman", "upperRoman"):
            s, n = "", max(n, 1)
            for value, sym in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                               (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
                while n >= value:
                    s += sym
                    n -= value
            return s.upper() if fmt == "upperRoman" else s
        if fmt == "decimalZero":
            return f"{n:02d}"
        return str(n)

    def label(self, p) -> str:
        """Nhãn đánh số của đoạn `p` ("" nếu đoạn không đánh số)."""
        ppr = p.find(_w("pPr"))
        num_id, ilvl = None, 0
        if ppr is not None:
            numpr = ppr.find(_w("numPr"))
            if numpr is not None:
                num_id = self._val(numpr.find(_w("numId")), None)
                ilvl = self._int(numpr.find(_w("ilvl")), 0)
            if num_id is None:
                style = ppr.find(_w("pStyle"))
                if style is not None and style.get(_VAL) in self.style_numpr:
                    num_id, ilvl = self.style_numpr[style.get(_VAL)]
        if not num_id or num_id == "0":
            return ""
        abstract_id = self.num_to_abstract.get(num_id)
        levels = self.abstract.get(abstract_id)
        if not levels or ilvl not in levels:
            return ""
        level = levels[ilvl]
        if level["fmt"] == "bullet":
            return "- "
        if level["fmt"] == "none":
            return ""

        # Các danh sách dùng chung một abstractNum thì đếm nối tiếp nhau,
        # trừ khi danh sách mới có startOverride (bắt đầu lại từ đầu).
        counters = self.counters.setdefault(abstract_id, {})
        first_use = num_id not in self.seen_nums
        self.seen_nums.add(num_id)
        if first_use and (num_id, ilvl) in self.start_override:
            counters[ilvl] = self.start_override[(num_id, ilvl)] - 1
        counters[ilvl] = counters.get(ilvl, level["start"] - 1) + 1
        for deeper in [k for k in counters if k > ilvl]:
            del counters[deeper]

        def repl(m):
            idx = int(m.group(1)) - 1
            lv = levels.get(idx)
            if lv is None:
                return ""
            return self._format(counters.get(idx, lv["start"]), lv["fmt"])

        text = re.sub(r"%(\d)", repl, level["text"]).strip()
        return text + " " if text else ""


class _DocxWalker:
    def __init__(self, package: zipfile.ZipFile):
        from lxml import etree  # lxml luôn có sẵn vì python-docx phụ thuộc vào nó

        self._etree = etree
        self.zip = package
        self.names = set(package.namelist())
        self.notes = {
            "footnote": self._load_notes("word/footnotes.xml", "footnote"),
            "endnote": self._load_notes("word/endnotes.xml", "endnote"),
        }
        self.numbering = _Numbering(self._xml("word/numbering.xml"), self._xml("word/styles.xml"))
        self.tracked_insertions = 0
        self.tracked_deletions = 0
        self.textboxes = 0

    def _xml(self, name: str):
        if name not in self.names:
            return None
        try:
            return self._etree.fromstring(self.zip.read(name))
        except Exception:  # noqa: BLE001 - phần phụ hỏng thì bỏ qua, vẫn đọc thân văn bản
            return None

    def _load_notes(self, name: str, tag: str) -> dict:
        root = self._xml(name)
        notes = {}
        if root is None:
            return notes
        for note in root.iter(_w(tag)):
            # Bỏ 2 mục kỹ thuật "separator"/"continuationSeparator".
            if note.get(_w("type")) in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            notes[note.get(_w("id"))] = note
        return notes

    # ------------------------------------------------------------------ đoạn văn
    def paragraph(self, p, *, with_label: bool = True) -> tuple[str, list[str]]:
        """Trả về (chữ của đoạn, danh sách dòng của các text box neo vào đoạn)."""
        parts: list[str] = []
        boxes: list[str] = []
        self._inline(p, parts, boxes)
        text = "".join(parts)
        text = re.sub(r"[ \t ]+", " ", text).strip()
        if with_label:
            # Gọi cả khi đoạn rỗng: Word vẫn tính số cho đoạn rỗng có đánh số.
            label = self.numbering.label(p)
            if text:
                text = label + text
        return text, boxes

    def _inline(self, node, parts: list[str], boxes: list[str]) -> None:
        for child in node:
            tag = child.tag
            if not isinstance(tag, str):
                continue  # comment / processing instruction
            if tag in _SKIP:
                if tag in (_w("del"), _w("moveFrom")):
                    self.tracked_deletions += 1
                continue
            if tag == _T:
                parts.append(child.text or "")
            elif tag == _TAB:
                parts.append("\t")
            elif tag in (_BR, _CR):
                parts.append("\n")
            elif tag == _w("noBreakHyphen"):
                parts.append("-")
            elif tag == _w("footnoteReference") or tag == _w("endnoteReference"):
                kind = "footnote" if tag == _w("footnoteReference") else "endnote"
                note = self.notes[kind].get(child.get(_w("id")))
                if note is not None:
                    note_text = " ".join(self.blocks(note))
                    if note_text:
                        parts.append(f" [Chú thích: {note_text}]")
            elif tag == _TXBX:
                # Text box: nội dung độc lập, không trộn vào giữa câu của đoạn neo.
                self.textboxes += 1
                box_lines = self.blocks(child)
                if box_lines:
                    boxes.append("[Khung văn bản] " + " / ".join(box_lines))
            elif tag == _ALT:
                # Word lưu cùng một hình/text box 2 lần (bản mới + bản tương
                # thích). Chỉ đọc MỘT nhánh để không bị lặp nội dung.
                branch = child.find(_CHOICE)
                if branch is None:
                    branch = child.find(_FALLBACK)
                if branch is not None:
                    self._inline(branch, parts, boxes)
            else:
                if tag in (_w("ins"), _w("moveTo")):
                    self.tracked_insertions += 1
                self._inline(child, parts, boxes)

    # ------------------------------------------------------------------ khối
    def blocks(self, container) -> list[str]:
        """Duyệt các khối (đoạn văn, bảng) của `container` theo thứ tự."""
        lines: list[str] = []
        for child in container:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            if tag == _P:
                text, boxes = self.paragraph(child)
                if text:
                    lines.extend(part.strip() for part in text.split("\n") if part.strip())
                lines.extend(boxes)
            elif tag == _TBL:
                lines.extend(self.table(child))
            elif tag in _SKIP:
                continue
            elif tag in (_w("sectPr"), _w("tblPr"), _w("tblGrid"), _w("tcPr"), _w("trPr")):
                continue
            else:
                # Vỏ bọc: content control (w:sdt/w:sdtContent), customXml,
                # smartTag, chèn bằng Track Changes ở cấp khối...
                lines.extend(self.blocks(child))
        return lines

    def table(self, tbl) -> list[str]:
        rows = []
        for tr in tbl.iter(_TR):
            if self._owner_table(tr) is not tbl:
                continue  # hàng của bảng lồng bên trong — đã xử lý khi đọc ô
            cells = []
            for tc in tr.iter(_TC):
                if self._owner_table(tc) is not tbl:
                    continue
                cells.append(" / ".join(self.blocks(tc)))
            if any(cells):
                rows.append(" | ".join(cells))
        return rows

    @staticmethod
    def _owner_table(node):
        parent = node.getparent()
        while parent is not None and parent.tag != _TBL:
            parent = parent.getparent()
        return parent


def _image_blobs(package: zipfile.ZipFile) -> list[tuple[str, bytes]]:
    blobs = []
    for name in package.namelist():
        if name.startswith("word/media/") and name.lower().endswith(
            (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif")
        ):
            blobs.append((name, package.read(name)))
    return blobs


def _large_images(blobs: list[tuple[str, bytes]], min_side: int = 500) -> list:
    """Ảnh đủ lớn để có thể là trang tài liệu chụp/scan (bỏ logo, con dấu nhỏ)."""
    from PIL import Image

    images = []
    for _name, data in blobs:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception:  # noqa: BLE001
            continue
        if min(img.size) >= min_side:
            images.append(img)
    return images


def extract_docx(path: str, *, ocr_options=None) -> ExtractionResult:
    """Đọc .docx. `ocr_options` (core.readers.ocr.OcrOptions) chỉ dùng khi
    file gần như không có chữ mà chứa ảnh chụp/scan."""
    try:
        package = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise ValueError(
            "File .docx này không mở được (không đúng cấu trúc Word). Có thể file "
            "bị hỏng, tải chưa xong, hoặc đang đặt mật khẩu. Hãy mở bằng Word, "
            "bỏ mật khẩu (nếu có) rồi Lưu lại."
        ) from e

    with package:
        names = set(package.namelist())
        if "word/document.xml" not in names:
            if "content.xml" in names:
                raise ValueError(
                    "Đây là file OpenDocument (.odt) chứ không phải .docx. Hãy mở "
                    "bằng Word/LibreOffice rồi Lưu thành .docx."
                )
            raise ValueError("File .docx này không có phần nội dung văn bản (word/document.xml).")

        walker = _DocxWalker(package)
        root = walker._xml("word/document.xml")
        if root is None:
            raise ValueError("Nội dung file .docx bị hỏng (không phân tích được XML).")
        body = root.find(_w("body"))
        body_lines = walker.blocks(body if body is not None else root)

        # Đầu trang / chân trang: đọc sau thân văn bản, bỏ dòng trùng lặp.
        header_lines, footer_lines = [], []
        for name in sorted(names):
            m = re.fullmatch(r"word/(header|footer)\d*\.xml", name)
            if not m:
                continue
            part_root = walker._xml(name)
            if part_root is None:
                continue
            target = header_lines if m.group(1) == "header" else footer_lines
            for line in walker.blocks(part_root):
                if line not in target and not re.fullmatch(r"[\d\s/\-–]*", line):
                    target.append(line)

        blobs = _image_blobs(package)

    parts = []
    if header_lines:
        parts.append("[Đầu trang] " + " / ".join(header_lines))
    parts.extend(body_lines)
    if footer_lines:
        parts.append("[Chân trang] " + " / ".join(footer_lines))
    text = clean_text("\n".join(parts))

    result = ExtractionResult(text=text, file_type="docx", method="Word .docx — đọc trực tiếp nội dung chữ")

    if walker.tracked_insertions or walker.tracked_deletions:
        result.warnings.append(
            "File đang bật Theo dõi thay đổi (Track Changes): hệ thống đọc theo bản "
            "ĐÃ CHẤP NHẬN mọi thay đổi (lấy phần chèn thêm, bỏ phần đã xóa). Nên "
            "chấp nhận/từ chối thay đổi trong Word trước nếu muốn chắc chắn."
        )

    # Ảnh nhúng: chữ nằm trong ảnh không nằm trong phần text của Word.
    body_chars = sum(len(line) for line in body_lines)
    big_images = _large_images(blobs) if blobs else []
    if big_images:
        if body_chars < 200 and ocr_options is not None and ocr_options.mode != "never":
            from .ocr import ocr_images

            ocr_text, pages, engine, ocr_warnings = ocr_images(big_images, ocr_options)
            if ocr_text.strip():
                result.text = clean_text((text + "\n\n" if text else "") + ocr_text)
                result.used_ocr = True
                result.ocr_engine = engine
                result.pages = pages
                result.method = f"Word .docx chứa ảnh chụp/scan — nhận dạng chữ (OCR) bằng {engine}"
                result.warnings.append(
                    f"File Word gần như không có chữ, nội dung nằm trong {len(big_images)} ảnh nhúng và "
                    f"được NHẬN DẠNG BẰNG OCR ({engine}) nên có thể sai chữ, sai dấu, sai số. Hãy đối "
                    "chiếu với bản gốc — nhất là họ tên, ngày tháng, số tiền, số điều luật."
                )
                bad = [p for p in pages if p.issues]
                if bad:
                    result.warnings.append("Ảnh có chất lượng kém, cần xem kỹ — " + "; ".join(
                        f"ảnh {p.number}: {', '.join(p.issues)}" for p in bad[:8]
                    ) + ".")
            result.warnings.extend(ocr_warnings)
            if not ocr_text.strip():
                result.warnings.append(
                    f"File có {len(big_images)} ảnh lớn nhưng không nhận dạng được chữ trong ảnh."
                )
        else:
            result.warnings.append(
                f"File có {len(big_images)} ảnh lớn nhúng trong văn bản. Chữ nằm TRONG ẢNH "
                "(ví dụ trang tài liệu chụp lại, biên bản scan dán vào Word) KHÔNG được đọc — "
                "nếu ảnh chứa nội dung hồ sơ, hãy gõ lại hoặc gửi bản PDF scan của tài liệu đó."
            )
    return result
