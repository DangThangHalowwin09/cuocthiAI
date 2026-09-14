"""
Script CHẠY 1 LẦN (hoặc chạy lại khi luật có sửa đổi) — tách toàn văn
NHIỀU bộ luật (.docx và/hoặc .pdf) thành dữ liệu có cấu trúc (JSON), mỗi
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

from docx import Document
import pdfplumber

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = BASE_DIR / "data" / "laws" / "source"
OUTPUT_DIR = BASE_DIR / "data" / "laws"

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
]

DIEU_PATTERN_RAW = r"^Điều\s+(\d+)\.\s*(.*)$"
STRUCTURE_PATTERNS_RAW = [
    r"^Phần\s+(thứ\s+\w+|[IVXLC]+)",
    r"^Chương\s+[IVXLC\d]+",
    r"^Mục\s+\d+",
]


def normalize(text: str) -> str:
    """Chuẩn hóa Unicode về dạng NFC, đồng thời sửa lỗi ký tự dễ nhầm lẫn
    trong văn bản gốc (chuyển từ .doc/.pdf scan/OCR của Công báo):
    - Chuẩn hóa NFC: một số dòng lưu ký tự có dấu ở dạng tổ hợp (NFD)
      khác dạng chuẩn (NFC) dùng trong regex, khiến regex âm thầm KHÔNG
      khớp một số dòng "Điều N." mà không báo lỗi gì.
    - "Ð" (U+00D0, chữ Eth của Iceland) dễ bị gõ nhầm với "Đ" (U+0110,
      chữ Đ tiếng Việt) vì hình dạng gần như giống hệt."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00d0", "\u0110")  # Ð (Eth) -> Đ (tiếng Việt)
    return text


DIEU_PATTERN = re.compile(normalize(DIEU_PATTERN_RAW))
STRUCTURE_PATTERNS = [re.compile(normalize(p), re.IGNORECASE) for p in STRUCTURE_PATTERNS_RAW]


def is_structure_heading(text: str) -> bool:
    return any(p.match(text) for p in STRUCTURE_PATTERNS)


def read_paragraphs_from_docx(path: Path) -> list[str]:
    doc = Document(path)
    result = []
    for p in doc.paragraphs:
        text = normalize(p.text.strip())
        if text:
            result.append(text)
    return result


def read_paragraphs_from_pdf(path: Path) -> list[str]:
    result = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                line = normalize(line.strip())
                if line:
                    result.append(line)
    return result


def read_paragraphs_in_order(source_paths: list[Path]) -> list[str]:
    all_paras = []
    for path in source_paths:
        if path.suffix.lower() == ".docx":
            all_paras.extend(read_paragraphs_from_docx(path))
        elif path.suffix.lower() == ".pdf":
            all_paras.extend(read_paragraphs_from_pdf(path))
        else:
            raise ValueError(f"Không hỗ trợ định dạng: {path}")
    return all_paras


def parse_articles(paragraphs: list[str]) -> list[dict]:
    articles = []
    current = None
    current_structure = {"phan": "", "chuong": "", "muc": ""}

    for text in paragraphs:
        m = DIEU_PATTERN.match(text)
        if m:
            if current is not None:
                articles.append(current)
            dieu_so, tieu_de_dong_dau = m.group(1), m.group(2)
            current = {
                "dieu_so": dieu_so,
                "tieu_de": tieu_de_dong_dau,
                "noi_dung": tieu_de_dong_dau,
                "phan": current_structure["phan"],
                "chuong": current_structure["chuong"],
                "muc": current_structure["muc"],
            }
            continue

        if is_structure_heading(text):
            if text.lower().startswith("phần"):
                current_structure["phan"] = text
                current_structure["chuong"] = ""
                current_structure["muc"] = ""
            elif text.lower().startswith("chương"):
                current_structure["chuong"] = text
                current_structure["muc"] = ""
            elif text.lower().startswith("mục"):
                current_structure["muc"] = text
            continue

        if current is not None:
            current["noi_dung"] += "\n" + text

    if current is not None:
        articles.append(current)

    return articles


def validate_sequence(ten_luat: str, articles: list[dict], paragraphs: list[str]) -> None:
    if not articles:
        print(f"⚠️  CẢNH BÁO — {ten_luat}: không tách được điều nào! Kiểm tra lại nguồn.")
        return

    numbers = [int(a["dieu_so"]) for a in articles]
    expected = list(range(numbers[0], numbers[-1] + 1))
    missing = sorted(set(expected) - set(numbers))
    duplicates = [n for n in set(numbers) if numbers.count(n) > 1]

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

    print(f"--- {ten_luat} ---")
    print(f"  Tổng số điều tách được: {len(articles)} (Điều {numbers[0]} → Điều {numbers[-1]})")
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
