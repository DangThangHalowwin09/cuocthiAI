"""
Script CHẠY 1 LẦN (hoặc chạy lại khi luật có sửa đổi) — tách toàn văn
NHIỀU bộ luật (.doc, .docx và/hoặc .pdf) thành dữ liệu có cấu trúc (JSON), mỗi
điều 1 mục, để hệ thống tra cứu theo từ khóa khi chạy thật (không cần
AI, không cần lên mạng).

Cách dùng:
    python scripts/build_law_database.py

Cấu hình nguồn ở LAWS_CONFIG bên dưới. Thêm bộ luật mới chỉ cần thêm 1
mục vào danh sách này, không cần sửa logic xử lý.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

from collections import Counter

from docx import Document

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "data" / "laws" / "source"
OUTPUT_DIR = BASE_DIR / "data" / "laws"

# Thêm thư mục gốc vào sys.path để import được các module trong core/
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ---------------------------------------------------------------------------
# CẤU HÌNH NGUỒN — mỗi mục là 1 bộ luật, đọc theo đúng thứ tự file liệt kê
# ---------------------------------------------------------------------------
LAWS_CONFIG = [
    {
        "ma_luat": "blhs",
        "ten_luat": "Bộ luật Hình sự",
        "nguon": [
            "2025_1351___1352_135-VBHN-VPQH.docx",
            "2025_1353___1354_135-VBHN-VPQH.docx",
            "2025_1355___1356_135-VBHN-VPQH.docx",
            "2025_1357___1358_135-VBHN-VPQH.docx",
        ],
    },
    {
        "ma_luat": "blttths",
        "ten_luat": "Bộ luật Tố tụng hình sự",
        "nguon": ["P1văn_bản_hợp_nhất_bộ_luật_tố_tụng_hình_sự.pdf"],
    },
    {
        "ma_luat": "blds",
        "ten_luat": "Bộ luật Dân sự",
        "nguon": ["Bộ_luật_dân_sự_2015.docx"],
    },
    {
        "ma_luat": "blttds",
        "ten_luat": "Bộ luật Tố tụng dân sự",
        "nguon": ["Luật_tố_tụng_dân_sự.docx"],
    },
    {
        "ma_luat": "blttds_suadoi_2025",
        "ten_luat": "Luật sửa đổi, bổ sung BLTTDS và Luật TTHC (2025)",
        "nguon": ["Luật_sửa_đổi_Luật_TTDS__TTHC.docx"],
    },
    {
        "ma_luat": "lthc",
        "ten_luat": "Luật Tố tụng hành chính",
        "nguon": ["LUẬT_TỐ_TỤNG_HÀNH_CHÍNH.docx"],
    },
    {
        "ma_luat": "luat_dat_dai",
        "ten_luat": "Luật Đất đai",
        "nguon": ["Luật_đất_đai.docx"],
    },
    {
        "ma_luat": "luat_lao_dong",
        "ten_luat": "Bộ luật Lao động",
        "nguon": ["Bộ_Luật_lao_động.docx"],
    },
    {
        "ma_luat": "luat_tu_phap_nguoi_chua_thanh_nien",
        "ten_luat": "Luật Tư pháp người chưa thành niên",
        "nguon": ["Luật tư pháp người chưa thành niên.docx"],
    },
    {
        "ma_luat": "nq04_2025_tinh_tiet_giam_nhe",
        "ten_luat": "Nghị quyết 04/2025 hướng dẫn về tình tiết giảm nhẹ",
        "nguon": ["Nghị quyết 04.2025 về hướng dẫn về tình tiết giảm nhẹ.docx"],
    },
]

# "Điều 12." và cả điều chèn thêm có chữ cái: "Điều 217a.", "Điều 506a."
DIEU_PATTERN_RAW = r"^Điều\s+(\d+[a-zđ]?)\.\s*(.*)$"

# Tiêu đề cấu trúc. Chấp nhận cả số La Mã lẫn số thường ("Mục I", "Mục 1"),
# và cấp "Tiểu mục" (Bộ luật Dân sự).
STRUCTURE_LEVELS = [
    ("phan", r"^Phần\s+(thứ\s+\w+|[IVXLC]+)\b"),
    ("chuong", r"^Chương\s+[IVXLC\d]+\b"),
    ("tieu_muc", r"^Tiểu\s+mục\s+[IVXLC\d]+\b"),
    ("muc", r"^Mục\s+[IVXLC\d]+\b"),
]
# Cấp dưới của mỗi cấp — khi sang Chương mới thì Mục/Tiểu mục cũ hết hiệu lực.
_CHILD_LEVELS = {
    "phan": ("chuong", "muc", "tieu_muc"),
    "chuong": ("muc", "tieu_muc"),
    "muc": ("tieu_muc",),
    "tieu_muc": (),
}

# Từ dòng này trở đi là phần xác thực + chú thích cuối của Văn bản hợp nhất,
# không còn là nội dung điều luật.
END_OF_LAW_MARKERS = ("XÁC THỰC VĂN BẢN HỢP NHẤT",)

# Ký hiệu chú thích cuối văn bản kiểu "[12]" chèn giữa nội dung (VBHN dạng PDF).
_ENDNOTE_MARK = re.compile(r"\[\d{1,3}\]")
_SPACES = re.compile(r"[ \t  -​ 　]+")


def normalize(text: str) -> str:
    """Chuẩn hóa văn bản luật trước khi tách điều:
    - Unicode NFC: một số dòng lưu ký tự có dấu ở dạng tổ hợp (NFD), khiến
      regex âm thầm KHÔNG khớp dòng "Điều N." mà không báo lỗi gì.
    - "Ð" (U+00D0, chữ Eth) hay bị gõ nhầm thay "Đ" (U+0110).
    - Khoảng trắng không ngắt (NBSP) và các loại khoảng trắng lạ → dấu cách
      thường; nếu để nguyên thì việc so khớp cụm từ ("tình tiết giảm nhẹ")
      sẽ trượt ở những chỗ dùng NBSP."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("Ð", "Đ")  # Ð (Eth) -> Đ (tiếng Việt)
    text = _SPACES.sub(" ", text)
    return text.strip()


DIEU_PATTERN = re.compile(normalize(DIEU_PATTERN_RAW))
STRUCTURE_PATTERNS = [
    (level, re.compile(normalize(p), re.IGNORECASE)) for level, p in STRUCTURE_LEVELS
]
# Dòng "trông giống" tiêu đề điều nhưng không khớp DIEU_PATTERN — dùng để
# cảnh báo khi kiểm tra (ví dụ "Điều 5:" hoặc "Điều 5 .").
LOOSE_DIEU_PATTERN = re.compile(normalize(r"^Điều\s*\d+[a-zđ]?\s*[:\-–.]"), re.IGNORECASE)


def structure_level(text: str) -> str | None:
    """Trả về cấp cấu trúc ("phan"/"chuong"/"muc"/"tieu_muc") nếu dòng là
    tiêu đề cấu trúc, ngược lại None."""
    for level, pattern in STRUCTURE_PATTERNS:
        if pattern.match(text):
            return level
    return None


def is_structure_heading(text: str) -> bool:
    return structure_level(text) is not None


def _is_title_line(text: str) -> bool:
    """Dòng tên chương/mục: toàn chữ IN HOA (không có chữ thường)."""
    return any(ch.isalpha() for ch in text) and text == text.upper()


_CLAUSE_START = re.compile(r"^(\d{1,3}\.|[a-zđ]\)|[a-zđ]\.\d+\))\s")


def read_paragraphs_from_pdf(path: Path) -> list[str]:
    """Đọc PDF có lớp chữ và GHÉP LẠI các dòng bị ngắt giữa câu.

    PDF lưu chữ theo từng dòng in trên trang, nên một khoản dài bị cắt thành
    nhiều dòng. Nếu để nguyên: tiêu đề điều dài bị cụt ở dòng đầu, và cụm từ
    vắt qua 2 dòng không còn so khớp được. Văn bản luật được căn đều hai
    bên, nên dòng nào chạm lề phải thì chắc chắn còn nối tiếp sang dòng
    sau; dòng kết thúc trước lề phải là dòng cuối của một đoạn."""
    import pdfplumber

    lines = []  # (text, x0, x1, in_đậm)
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in page.extract_text_lines():
                text = normalize(_ENDNOTE_MARK.sub("", line["text"]))
                if text:
                    chars = line.get("chars") or [{}]
                    bold = "bold" in str(chars[0].get("fontname", "")).lower()
                    lines.append((text, line["x0"], line["x1"], bold))
    if not lines:
        return []

    # Lề trái/phải = vị trí xuất hiện nhiều nhất.
    left = Counter(round(x0) for _, x0, _, _ in lines).most_common(1)[0][0]
    right = max(
        x for x, n in Counter(round(x1) for _, _, x1, _ in lines).most_common(3)
        if n >= len(lines) * 0.05
    ) if len(lines) > 20 else max(x1 for _, _, x1, _ in lines)

    paragraphs = []
    current = ""
    continues = False
    prev_bold = None
    for text, x0, x1, bold in lines:
        # Đoạn căn trái (không căn đều): dòng trước chưa hết câu và dòng này
        # mở đầu bằng chữ thường → chắc chắn vẫn là cùng một câu.
        mid_sentence = (
            bool(current)
            and not current.rstrip().endswith((".", ";", ":"))
            and text[:1].islower()
            and not _CLAUSE_START.match(text)
        )
        starts_new = (
            not (continues or mid_sentence)
            # Tiêu đề điều in đậm, nội dung in thường: đổi kiểu chữ = sang đoạn mới
            # (tránh nối nhầm nội dung vào tiêu đề khi tiêu đề vừa khít một dòng).
            or bold != prev_bold
            or DIEU_PATTERN.match(text)
            or is_structure_heading(text)
            # Dòng trước chạm lề phải nhưng đã hết câu, và dòng này mở đầu
            # một khoản/điểm mới ("2. ...", "b) ...") → là đoạn mới.
            or (_CLAUSE_START.match(text) and current.rstrip().endswith((".", ";", ":")))
        )
        if starts_new:
            if current:
                paragraphs.append(current)
            current = text
        else:
            current += " " + text
        prev_bold = bold
        is_flush_left = abs(x0 - left) <= 3
        continues = is_flush_left and x1 >= right - 6
        # Tên chương in hoa căn giữa dài 2 dòng: dòng đầu gần chạm cả hai lề.
        if not is_flush_left and _is_title_line(text) and x1 >= right - 30:
            continues = True
    if current:
        paragraphs.append(current)
    return paragraphs


def read_paragraphs_from_docx(path: Path) -> list[str]:
    doc = Document(path)
    result = []
    for p in doc.paragraphs:
        text = normalize(p.text)
        if text:
            result.append(text)
    return result


def read_paragraphs_from_doc(path: Path) -> list[str]:
    """Đọc file .doc (Word 97-2003) rồi tách thành từng dòng/đoạn.
    Gọi lại read_doc() đã viết trong core.file_parser để tận dụng
    logic parse PieceTable + fallback."""
    from core.file_parser import read_doc  # import lười: chỉ cần khi nguồn là .doc

    raw_text = read_doc(str(path))
    result = []
    for line in re.split(r"[\r\n]+", raw_text):
        line = normalize(line)
        if line:
            result.append(line)
    return result


def read_paragraphs_in_order(source_paths: list[Path]) -> list[str]:
    all_paras = []
    for path in source_paths:
        ext = path.suffix.lower()
        if ext == ".doc":
            all_paras.extend(read_paragraphs_from_doc(path))
        elif ext == ".docx":
            all_paras.extend(read_paragraphs_from_docx(path))
        elif ext == ".pdf":
            all_paras.extend(read_paragraphs_from_pdf(path))
        else:
            raise ValueError(f"Không hỗ trợ định dạng: {path}")
    return all_paras


def parse_articles(paragraphs: list[str]) -> list[dict]:
    articles = []
    current = None
    structure = {"phan": "", "chuong": "", "muc": "", "tieu_muc": ""}
    # Cấp cấu trúc vừa gặp và đang chờ dòng tên (IN HOA) ở các dòng kế tiếp.
    # Trước đây các dòng tên chương này bị nối nhầm vào CUỐI điều đứng trước.
    pending_level = None

    for text in paragraphs:
        if any(text.startswith(marker) for marker in END_OF_LAW_MARKERS):
            break

        m = DIEU_PATTERN.match(text)
        if m:
            pending_level = None
            if current is not None:
                articles.append(current)
            dieu_so, tieu_de = m.group(1), m.group(2)
            current = {
                "dieu_so": dieu_so,
                "tieu_de": tieu_de,
                "noi_dung": tieu_de,
                "phan": structure["phan"],
                "chuong": structure["chuong"],
                "muc": structure["muc"],
                "tieu_muc": structure["tieu_muc"],
            }
            continue

        level = structure_level(text)
        if level:
            structure[level] = text
            for child in _CHILD_LEVELS[level]:
                structure[child] = ""
            pending_level = level
            continue

        if pending_level and _is_title_line(text):
            sep = " " if structure[pending_level].endswith((".", ":")) else " – "
            if " – " in structure[pending_level]:
                sep = " "  # dòng thứ 2 của cùng một tên chương
            structure[pending_level] += sep + text
            continue
        pending_level = None

        if current is not None:
            current["noi_dung"] += "\n" + text

    if current is not None:
        articles.append(current)

    return articles


def _dieu_key(dieu_so: str) -> tuple[int, str]:
    """"217a" → (217, "a") để sắp xếp/so sánh số điều có chữ cái."""
    m = re.match(r"(\d+)(.*)", dieu_so)
    return int(m.group(1)), m.group(2)


def validate_sequence(ten_luat: str, articles: list[dict], paragraphs: list[str]) -> None:
    if not articles:
        print(f"⚠️  CẢNH BÁO — {ten_luat}: không tách được điều nào! Kiểm tra lại nguồn.")
        return

    lettered = [a["dieu_so"] for a in articles if not a["dieu_so"].isdigit()]
    numbers = [int(a["dieu_so"]) for a in articles if a["dieu_so"].isdigit()]
    all_ids = [a["dieu_so"] for a in articles]
    expected = list(range(numbers[0], numbers[-1] + 1))
    missing = sorted(set(expected) - set(numbers))
    duplicates = sorted({n for n in all_ids if all_ids.count(n) > 1}, key=_dieu_key)
    out_of_order = [
        all_ids[i] for i in range(1, len(all_ids))
        if _dieu_key(all_ids[i]) < _dieu_key(all_ids[i - 1])
    ]

    def find_para_index(dieu_so: int):
        target = f"Điều {dieu_so}."
        for i, p in enumerate(paragraphs):
            if p.startswith(target):
                return i
        return None

    ranges = []
    if missing:
        start = prev = missing[0]
        for n in missing[1:]:
            if n == prev + 1:
                prev = n
            else:
                ranges.append((start, prev))
                start = prev = n
        ranges.append((start, prev))

    repealed_numbers, genuinely_missing = [], []
    for lo, hi in ranges:
        idx_before = find_para_index(lo - 1)
        idx_after = find_para_index(hi + 1)
        is_repealed = False
        if idx_before is not None and idx_after is not None:
            between = " ".join(paragraphs[idx_before:idx_after]).lower()
            if "bãi bỏ" in between or "hết hiệu lực" in between:
                is_repealed = True
        (repealed_numbers if is_repealed else genuinely_missing).extend(range(lo, hi + 1))

    # Dòng trông giống tiêu đề điều nhưng không tách được (sai dấu chấm, v.v.)
    unparsed_headings = [
        p[:80] for p in paragraphs
        if LOOSE_DIEU_PATTERN.match(p) and not DIEU_PATTERN.match(p)
    ]
    empty_articles = [a["dieu_so"] for a in articles if len(a["noi_dung"].strip()) < 20]

    print(f"--- {ten_luat} ---")
    print(f"  Tổng số điều tách được: {len(articles)} (Điều {all_ids[0]} → Điều {all_ids[-1]})")
    if lettered:
        print(f"  ℹ️  {len(lettered)} điều chèn thêm (có chữ cái): {lettered}")
    if repealed_numbers:
        print(f"  ℹ️  {len(repealed_numbers)} điều đã bị BÃI BỎ hợp pháp: {repealed_numbers}")
    if genuinely_missing:
        print(f"  ⚠️  CẢNH BÁO — {len(genuinely_missing)} điều CÓ THỂ lỗi tách, cần kiểm tra tay: {genuinely_missing}")
    else:
        print("  ✅ Không có điều nào thiếu ngoài các điều đã bãi bỏ hợp pháp.")
    if duplicates:
        print(f"  ⚠️  CẢNH BÁO — trùng lặp số điều: {duplicates}")
    else:
        print("  ✅ Không có điều nào bị trùng số.")
    if out_of_order:
        print(f"  ⚠️  CẢNH BÁO — số điều không tăng dần tại: {out_of_order}")
    if unparsed_headings:
        print(f"  ⚠️  CẢNH BÁO — {len(unparsed_headings)} dòng giống tiêu đề điều nhưng KHÔNG tách được:")
        for h in unparsed_headings[:10]:
            print(f"       {h}")
    if empty_articles:
        print(f"  ℹ️  Điều có nội dung rất ngắn (thường là điều đã bãi bỏ): {empty_articles}")


def build_one_law(config: dict) -> None:
    ma_luat = config["ma_luat"]
    ten_luat = config["ten_luat"]
    source_paths = [SOURCE_DIR / name for name in config["nguon"]]

    missing_files = [p for p in source_paths if not p.exists()]
    if missing_files:
        print(f"⚠️  BỎ QUA {ten_luat} — thiếu file nguồn: {[p.name for p in missing_files]}")
        return

    paragraphs = read_paragraphs_in_order(source_paths)
    articles = parse_articles(paragraphs)
    for a in articles:
        a["luat"] = ten_luat
        a["ma_luat"] = ma_luat

    validate_sequence(ten_luat, articles, paragraphs)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{ma_luat}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"  Đã lưu: {out_path}\n")


def main():
    if not SOURCE_DIR.exists():
        print(f"Không tìm thấy thư mục nguồn: {SOURCE_DIR}")
        sys.exit(1)

    for config in LAWS_CONFIG:
        build_one_law(config)


if __name__ == "__main__":
    main()
