"""Đọc file PDF: có lớp chữ, bản scan (ảnh), hoặc lẫn cả hai.

Quy trình cho TỪNG TRANG:
  1. Lấy lớp chữ có sẵn bằng nhiều thư viện (pdfplumber, pdfium, PyMuPDF nếu
     có) và giữ bản tốt nhất.
  2. Đánh giá lớp chữ đó: rỗng? rác (font lỗi, ký tự lạ)? bảng mã cũ TCVN3?
     hay là lớp chữ do máy scan tự tạo?
  3. Trang nào không có lớp chữ dùng được → dựng thành ảnh và OCR.
     (chế độ "always": OCR mọi trang; "never": không OCR.)
  4. Ghi lại cách đọc + vấn đề của từng trang để giao diện cảnh báo.

Dựng ảnh trang dùng pypdfium2 — thư viện này luôn có sẵn vì pdfplumber phụ
thuộc vào nó, nên KHÔNG cần cài thêm gì để đọc PDF scan bằng Gemini.
"""

from __future__ import annotations

from .common import ExtractionResult, PageInfo, clean_text, fix_legacy_vietnamese, score_text, text_stats
from .ocr import OcrError, OcrOptions, engine_chain, no_engine_message, run_ocr

# Trang có ít hơn ngần này ký tự (không tính khoảng trắng) coi như không có lớp chữ.
_MIN_TEXT_CHARS = 25
# Ảnh phủ từ ngần này diện tích trang trở lên → trang là ảnh scan/chụp.
_SCAN_COVERAGE = 0.5


def _open_pdfium(path: str):
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(path)
    except Exception as e:  # noqa: BLE001 - PdfiumError
        message = str(e).lower()
        if "password" in message:
            raise ValueError(
                "File PDF đang đặt MẬT KHẨU MỞ nên không đọc được. Hãy mở file bằng "
                "mật khẩu, in ra PDF mới (Print → Microsoft Print to PDF) rồi tải lên lại."
            ) from e
        raise ValueError(
            "Không mở được file PDF (file hỏng, tải chưa xong hoặc không phải PDF thật)."
        ) from e


def _text_layers(path: str, n_pages: int, pdfium_doc) -> tuple[list[dict], list[dict]]:
    """Lớp chữ của từng trang theo từng thư viện + thông tin ảnh trên trang.

    Trả về (candidates, images):
      candidates[i] = {"pdfplumber": "...", "pdfium": "...", "PyMuPDF": "..."}
      images[i]     = {"coverage": tỉ lệ diện tích ảnh, "dpi": dpi thực của ảnh lớn nhất}"""
    candidates = [dict() for _ in range(n_pages)]
    images = [{"coverage": 0.0, "dpi": None} for _ in range(n_pages)]

    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages[:n_pages]):
                try:
                    candidates[i]["pdfplumber"] = page.extract_text() or ""
                except Exception:  # noqa: BLE001 - một trang lỗi không làm hỏng cả file
                    pass
                try:
                    area = float(page.width) * float(page.height) or 1.0
                    best = 0.0
                    for im in page.images:
                        w = max(0.0, min(im["x1"], page.width) - max(im["x0"], 0))
                        h = max(0.0, min(im["bottom"], page.height) - max(im["top"], 0))
                        if w * h > best:
                            best = w * h
                            src_w = (im.get("srcsize") or (0, 0))[0]
                            images[i]["dpi"] = src_w / (w / 72.0) if w and src_w else None
                    images[i]["coverage"] = min(1.0, best / area)
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001 - pdfplumber không mở được: còn pdfium bên dưới
        pass

    for i in range(n_pages):
        try:
            textpage = pdfium_doc[i].get_textpage()
            candidates[i]["pdfium"] = (textpage.get_text_bounded() or "").replace("\r\n", "\n").replace("\r", "\n")
        except Exception:  # noqa: BLE001
            pass

    try:  # PyMuPDF là tùy chọn — có thì thêm một ứng viên
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        with fitz.open(path) as doc:
            if doc.needs_pass:
                doc.authenticate("")
            for i, page in enumerate(doc):
                if i >= n_pages:
                    break
                candidates[i]["PyMuPDF"] = page.get_text("text") or ""
    except Exception:  # noqa: BLE001
        pass

    return candidates, images


def _best_layer(layers: dict) -> tuple[str, str]:
    best_name, best_text, best_score = "", "", -1
    for name, text in layers.items():
        # Văn bản rác được chấm thấp để không thắng bản sạch.
        stats = text_stats(text)
        score = score_text(text) * (1.0 - min(0.9, stats["bad_ratio"] * 10))
        if score > best_score or (score == best_score and len(text) > len(best_text)):
            best_name, best_text, best_score = name, text, score
    return best_name, best_text


def _judge_text_layer(text: str, coverage: float) -> tuple[str, list[str]]:
    """Phân loại lớp chữ của một trang.
    Trả về (loại, vấn đề) với loại ∈ "good" | "empty" | "garbage" | "suspect"."""
    stats = text_stats(text)
    if stats["chars"] < _MIN_TEXT_CHARS:
        return "empty", []
    if stats["bad_ratio"] > 0.05:
        return "garbage", ["lớp chữ trong PDF bị lỗi font (ký tự rác)"]
    scanned = coverage >= _SCAN_COVERAGE
    letters = sum(1 for c in text if c.isalpha())
    if scanned and (stats["words"] < 8 or letters < stats["chars"] * 0.4):
        # Trang scan mà lớp chữ chỉ có lèo tèo số/ký hiệu: lớp chữ hỏng.
        return "garbage", ["lớp chữ có sẵn của trang scan gần như không có chữ"]
    if stats["words"] >= 40 and stats["viet_ratio"] < 0.15:
        # Tiếng Việt thật thì trên nửa số từ có dấu. Ít dấu bất thường: hoặc
        # lớp chữ do máy scan nhận dạng sai, hoặc văn bản không phải tiếng Việt.
        return "suspect", [
            "lớp chữ gần như không có dấu tiếng Việt (văn bản không dấu / không phải "
            "tiếng Việt, hoặc lớp chữ bị lỗi)"
        ]
    if scanned:
        return "good", [
            "trang là ảnh scan, chữ lấy từ lớp chữ do phần mềm scan tạo sẵn (chưa kiểm chứng)"
        ]
    return "good", []


def extract_pdf(path: str, options: OcrOptions | None = None, progress=None) -> ExtractionResult:
    options = options or OcrOptions()
    pdfium_doc = _open_pdfium(path)
    try:
        return _extract(path, pdfium_doc, options, progress)
    finally:
        try:
            pdfium_doc.close()
        except Exception:  # noqa: BLE001
            pass


def _extract(path: str, pdfium_doc, options: OcrOptions, progress) -> ExtractionResult:
    n_pages = len(pdfium_doc)
    if n_pages == 0:
        raise ValueError("File PDF không có trang nào.")
    if progress:
        progress(0, n_pages, f"Đang đọc lớp chữ của {n_pages} trang...")

    candidates, images = _text_layers(path, n_pages, pdfium_doc)

    pages: list[PageInfo] = []
    texts: list[str] = [""] * n_pages
    need_ocr: list[int] = []          # chỉ số trang (từ 0) cần OCR
    fallback_text: dict[int, str] = {}  # lớp chữ kém, dùng tạm nếu OCR thất bại
    legacy_pages = 0

    for i in range(n_pages):
        engine, raw = _best_layer(candidates[i])
        raw, legacy = fix_legacy_vietnamese(raw)
        if legacy == "TCVN3":
            legacy_pages += 1
        text = clean_text(raw)
        kind, issues = _judge_text_layer(text, images[i]["coverage"])
        if legacy == "VNI":
            issues.append("chữ gõ bằng bảng mã cũ VNI — dấu tiếng Việt hiển thị sai")
        info = PageInfo(i + 1, "text", engine, len(text), None, issues)

        if options.mode == "always":
            fallback_text[i] = text
            need_ocr.append(i)
        elif kind == "good" or options.mode == "never":
            texts[i] = text
            if kind == "empty":
                info.method = "blank"
                info.issues = [] if _is_blank(pdfium_doc, i) else ["trang ảnh không có lớp chữ, chưa OCR"]
        else:
            # "empty" / "garbage" / "suspect" → thử OCR. Trang "suspect" chỉ
            # OCR khi thực sự là ảnh scan; nếu không thì giữ nguyên lớp chữ.
            if kind == "suspect" and images[i]["coverage"] < _SCAN_COVERAGE:
                texts[i] = text
            else:
                fallback_text[i] = text if kind != "empty" else ""
                need_ocr.append(i)
        pages.append(info)

    result = ExtractionResult(text="", file_type="pdf")
    warnings = result.warnings

    # ------------------------------------------------------------------ OCR
    skipped: list[int] = []
    ocr_error_message = ""
    if need_ocr:
        # Trang trắng thật (không chữ, không hình) thì khỏi OCR cho đỡ tốn.
        to_ocr = []
        for i in need_ocr:
            if options.mode != "always" and not fallback_text.get(i) and _is_blank(pdfium_doc, i):
                pages[i].method, pages[i].issues = "blank", []
            else:
                to_ocr.append(i)
        if len(to_ocr) > options.max_pages:
            skipped = to_ocr[options.max_pages:]
            to_ocr = to_ocr[: options.max_pages]

        ocr_results, ocr_error = {}, ""
        if to_ocr:
            chain, unavailable = engine_chain(options)
            if not chain:
                ocr_error = no_engine_message(unavailable)
            else:
                def jobs():
                    for i in to_ocr:
                        yield i + 1, _render(pdfium_doc, i, options.dpi), images[i]["dpi"]

                try:
                    ocr_results, ocr_warnings = run_ocr(jobs(), options, len(to_ocr), progress)
                    warnings.extend(ocr_warnings)
                except OcrError as e:
                    ocr_error = str(e)

        engines_used = []
        for i in to_ocr:
            page = ocr_results.get(i + 1)
            info = pages[i]
            if page is None or page.error:
                reason = (page.error if page else ocr_error) or "OCR thất bại"
                texts[i] = fallback_text.get(i, "")
                if texts[i]:
                    info.method = "text"
                    info.issues.append("OCR thất bại — tạm dùng lớp chữ có sẵn (chất lượng kém)")
                else:
                    info.method, info.engine, info.chars = "failed", "", 0
                    info.issues = [f"không đọc được: {reason[:160]}"]
                continue
            # Trang "suspect": chỉ thay lớp chữ cũ nếu bản OCR rõ ràng tốt hơn.
            old = fallback_text.get(i, "")
            if options.mode != "always" and old and score_text(page.text) < score_text(old):
                texts[i] = old
                info.issues.append("đã thử OCR nhưng kết quả không tốt hơn lớp chữ có sẵn")
                continue
            texts[i] = page.text
            info.method, info.engine = "ocr", page.engine
            info.chars, info.confidence = len(page.text), page.confidence
            info.issues = list(page.issues)
            if not page.text:
                info.issues.append("OCR không thấy chữ nào trên trang")
            if page.engine not in engines_used:
                engines_used.append(page.engine)

        for i in skipped:
            texts[i] = fallback_text.get(i, "")
            pages[i].method = "skipped"
            pages[i].issues = [f"vượt giới hạn {options.max_pages} trang OCR — CHƯA được đọc"]

        result.used_ocr = bool(engines_used)
        result.ocr_engine = " + ".join(engines_used)
        if ocr_error and not engines_used:
            ocr_error_message = ocr_error
            warnings.append(ocr_error)

    # ------------------------------------------------------------- tổng hợp
    result.pages = pages
    result.text = clean_text("\n\n".join(t for t in texts if t))

    def fmt(numbers: list[int]) -> str:
        return _format_page_list(numbers)

    ocr_pages = [p.number for p in pages if p.method == "ocr"]
    text_pages = [p.number for p in pages if p.method == "text"]
    failed = [p.number for p in pages if p.method == "failed"]
    unread_blank = [p.number for p in pages if p.method == "blank" and p.issues]
    scanner_layer = [p.number for p in pages if p.method == "text" and any("phần mềm scan" in s for s in p.issues)]
    quality = [p.number for p in pages if p.method == "ocr" and p.issues]

    if ocr_pages and not text_pages:
        result.method = f"PDF scan/ảnh — nhận dạng chữ (OCR) bằng {result.ocr_engine}"
    elif ocr_pages:
        result.method = f"PDF lẫn trang chữ và trang scan — OCR {len(ocr_pages)}/{n_pages} trang bằng {result.ocr_engine}"
    else:
        result.method = "PDF có lớp chữ — đọc trực tiếp"

    if ocr_pages:
        warnings.insert(0, (
            f"Trang {fmt(ocr_pages)} là ảnh scan/chụp, nội dung được NHẬN DẠNG BẰNG OCR "
            f"({result.ocr_engine}) nên có thể sai chữ, sai dấu, sai số. Hãy đối chiếu với "
            "bản gốc — nhất là họ tên, ngày tháng, số tiền, số điều luật."
        ))
    if quality:
        details = "; ".join(
            f"trang {p.number}: {', '.join(p.issues)}" for p in pages if p.number in quality
        )
        warnings.append(f"Trang có chất lượng scan/nhận dạng kém, cần xem kỹ — {details}.")
    if failed:
        reason = pages[failed[0] - 1].issues[0] if pages[failed[0] - 1].issues else ""
        reason = reason.removeprefix("không đọc được: ")
        already = any(reason[:60] in w for w in warnings) if reason else True
        warnings.append(
            f"KHÔNG đọc được trang {fmt(failed)} — nội dung các trang này bị THIẾU."
            + ("" if already else f" Lý do: {reason}")
        )
    if skipped:
        warnings.append(
            f"File có nhiều trang scan hơn giới hạn OCR ({options.max_pages} trang): trang "
            f"{fmt([i + 1 for i in skipped])} CHƯA được đọc. Tăng 'Số trang OCR tối đa' ở thanh bên rồi đọc lại."
        )
    if unread_blank:
        warnings.append(
            f"Trang {fmt(unread_blank)} không có lớp chữ và OCR đang TẮT nên không được đọc."
        )
    if scanner_layer:
        warnings.append(
            f"Trang {fmt(scanner_layer)} là ảnh scan nhưng đã có sẵn lớp chữ do phần mềm scan tạo; "
            "hệ thống dùng lớp chữ đó (chưa kiểm chứng độ chính xác). Nếu thấy sai nhiều, chọn "
            "'Luôn OCR lại mọi trang' ở thanh bên."
        )
    other_text_issues = [
        p for p in pages
        if p.method == "text" and p.issues and p.number not in scanner_layer
    ]
    if other_text_issues:
        warnings.append("Lớp chữ của PDF có vấn đề — " + "; ".join(
            f"trang {p.number}: {', '.join(p.issues)}" for p in other_text_issues[:8]
        ) + ".")
    if legacy_pages:
        warnings.append(
            f"{legacy_pages} trang dùng font bảng mã cũ TCVN3 (.VnTime...) — đã tự chuyển sang "
            "Unicode; chữ IN HOA có dấu có thể bị thành chữ thường."
        )

    if not result.text:
        if options.mode == "never":
            reason = (
                "File là bản scan/ảnh (không có lớp chữ) mà chế độ OCR đang đặt 'Không OCR'. "
                "Hãy chọn 'Tự động' ở mục Đọc PDF scan (OCR) rồi đọc lại."
            )
        elif ocr_error_message:
            reason = ocr_error_message
        elif failed:
            reason = "OCR thất bại ở mọi trang. " + pages[failed[0] - 1].issues[0]
        elif all(p.method == "blank" for p in pages):
            reason = "Tất cả các trang đều trắng."
        else:
            reason = (
                "Đã OCR nhưng không nhận ra chữ nào — bản scan có thể quá mờ/nhạt hoặc trang "
                "không có chữ. Hãy scan lại rõ hơn (khoảng 300 dpi) hoặc dùng file Word/PDF gốc."
            )
        raise ValueError("Không đọc được chữ nào từ file PDF này. " + reason)
    return result


def _render(pdfium_doc, index: int, dpi: int):
    """Dựng trang thành ảnh PIL. Giới hạn kích thước để trang khổ lớn không ngốn RAM."""
    page = pdfium_doc[index]
    scale = dpi / 72.0
    longest = max(page.get_width(), page.get_height()) * scale
    if longest > 4200:
        scale *= 4200 / longest
    return page.render(scale=scale).to_pil()


def _is_blank(pdfium_doc, index: int) -> bool:
    """Trang trắng thật sự (dựng ảnh nhỏ, gần như không có điểm tối)."""
    try:
        from PIL import ImageStat

        page = pdfium_doc[index]
        scale = 600 / max(page.get_width(), page.get_height())
        gray = page.render(scale=scale, grayscale=True).to_pil().convert("L")
        histogram = gray.histogram()
        dark = sum(histogram[:200])
        return dark / max(1, sum(histogram)) < 0.0008 and ImageStat.Stat(gray).stddev[0] < 6
    except Exception:  # noqa: BLE001 - không chắc thì coi như có nội dung
        return False


def _format_page_list(numbers: list[int]) -> str:
    """[1,2,3,5,7,8] → "1–3, 5, 7–8"."""
    if not numbers:
        return ""
    numbers = sorted(numbers)
    ranges, start, prev = [], numbers[0], numbers[0]
    for n in numbers[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append((start, prev))
        start = prev = n
    ranges.append((start, prev))
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in ranges)


__all__ = ["extract_pdf", "OcrOptions"]
