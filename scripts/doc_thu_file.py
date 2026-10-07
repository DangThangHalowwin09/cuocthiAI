"""
Đọc thử một file đầu vào và in ra hệ thống đã đọc nó NHƯ THẾ NÀO — không gọi
AI soạn văn bản. Dùng để kiểm tra nhanh một file .docx/.doc/.rtf/.pdf (nhất
là PDF scan) trước buổi thi.

Cách dùng:
    python scripts/doc_thu_file.py "duong/dan/de_thi.pdf"
    python scripts/doc_thu_file.py de_thi.pdf --ocr always --engine tesseract
    python scripts/doc_thu_file.py de_thi.pdf --luu ket_qua.txt

OCR bằng Gemini cần GOOGLE_API_KEY (đọc từ file .env như ứng dụng chính).
"""

import argparse
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env", override=True)
except ImportError:
    pass

from core.file_parser import OcrOptions, detect_ocr_capability, extract_input_file  # noqa: E402

METHOD_LABELS = {
    "text": "lớp chữ có sẵn", "ocr": "OCR", "blank": "trang trắng",
    "skipped": "CHƯA ĐỌC", "failed": "KHÔNG ĐỌC ĐƯỢC",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Đọc thử file đầu vào và báo cáo cách đọc.")
    parser.add_argument("file", help="Đường dẫn file .docx / .doc / .rtf / .pdf")
    parser.add_argument("--ocr", choices=["auto", "always", "never"], default="auto",
                        help="auto: chỉ OCR trang scan (mặc định) | always: OCR mọi trang | never: không OCR")
    parser.add_argument("--engine", choices=["auto", "gemini", "easyocr", "tesseract"], default="auto")
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--max-pages", type=int, default=60)
    parser.add_argument("--luu", metavar="FILE.txt", help="Lưu toàn bộ nội dung đọc được ra file text")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Công cụ OCR trên máy này:")
    for info in detect_ocr_capability().values():
        print(f"  {'✔' if info['ok'] else '✘'} {info['name']}" + ("" if info["ok"] else f" — {info['reason']}"))

    options = OcrOptions(mode=args.ocr, engine=args.engine, dpi=args.dpi, max_pages=args.max_pages)
    started = time.time()
    try:
        result = extract_input_file(
            args.file, ocr=options,
            progress=lambda done, total, message: print(f"  … {message}", flush=True),
        )
    except ValueError as e:
        print(f"\n✘ KHÔNG ĐỌC ĐƯỢC FILE: {e}")
        return 1

    print(f"\n✔ Đã đọc trong {time.time() - started:.1f} giây")
    print(f"  Cách đọc : {result.method}")
    print(f"  Số ký tự : {len(result.text)}")
    if result.pages:
        print(f"  Số trang : {len(result.pages)}")
        for page in result.pages:
            conf = "" if page.confidence is None else f" · tin cậy {page.confidence:.0%}"
            issues = f" · ⚠ {'; '.join(page.issues)}" if page.issues else ""
            print(f"    Trang {page.number:>3}: {METHOD_LABELS.get(page.method, page.method)}"
                  f" ({page.engine or '—'}) · {page.chars} ký tự{conf}{issues}")
    if result.warnings:
        print("\nCẢNH BÁO:")
        for warning in result.warnings:
            print(f"  ⚠ {warning}")
    else:
        print("\nKhông có cảnh báo nào.")

    print("\n--- 800 ký tự đầu ---")
    print(result.text[:800])
    if args.luu:
        Path(args.luu).write_text(result.text, encoding="utf-8")
        print(f"\nĐã lưu toàn bộ nội dung vào: {args.luu}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
