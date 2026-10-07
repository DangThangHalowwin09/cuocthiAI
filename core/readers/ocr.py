"""Nhận dạng chữ từ ảnh (OCR) cho trang PDF scan / ảnh nhúng.

Ba engine, thử theo thứ tự (chế độ "auto"):
  1. Gemini  — gửi ảnh trang cho chính mô hình Gemini mà hệ thống đang dùng.
               Đọc tiếng Việt, con dấu đè chữ, bản chụp nghiêng tốt nhất và
               KHÔNG cần cài thêm gì. Cần mạng + GOOGLE_API_KEY.
  2. EasyOCR — chạy ngoại tuyến trên máy (cần `pip install easyocr`, khá nặng).
  3. Tesseract — chạy ngoại tuyến (cần cài Tesseract + gói tiếng Việt "vie").

OCR KHÔNG BAO GIỜ chính xác tuyệt đối. Module này vì thế luôn trả kèm các
dấu hiệu chất lượng (độ tin cậy, ảnh mờ, độ phân giải thấp...) để giao diện
cảnh báo người dùng đối chiếu lại với bản gốc.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .common import UNREADABLE_MARK, PageInfo, clean_text, text_stats

ENGINE_LABELS = {"gemini": "Gemini", "easyocr": "EasyOCR", "tesseract": "Tesseract"}


@dataclass
class OcrOptions:
    mode: str = "auto"        # "auto": chỉ OCR trang không có lớp chữ dùng được
                              # "always": OCR mọi trang | "never": không OCR
    engine: str = "auto"      # "auto" | "gemini" | "easyocr" | "tesseract"
    dpi: int = 220            # độ phân giải khi dựng ảnh trang để OCR
    langs: str = "vie+eng"    # ngôn ngữ cho engine ngoại tuyến
    max_pages: int = 60       # số trang OCR tối đa mỗi file
    workers: int = 3          # số trang xử lý song song


@dataclass
class OcrPage:
    text: str = ""
    engine: str = ""
    confidence: float | None = None
    issues: list[str] = field(default_factory=list)
    error: str = ""


class OcrError(RuntimeError):
    """Engine không đọc được trang này (lỗi mạng, hết quota, thiếu gói...)."""


# ---------------------------------------------------------------------------
# Đánh giá chất lượng ảnh — không phụ thuộc engine
# ---------------------------------------------------------------------------
# Ngưỡng hiệu chỉnh trên trang văn bản A4 dựng lại rồi làm mờ / làm nhạt /
# giảm độ phân giải nhân tạo. Chỉ dùng để CẢNH BÁO, không chặn xử lý.
#   Độ nét = phương sai Laplacian / (độ tương phản)²  — chia cho tương phản
#   để trang chữ nhạt không bị coi nhầm là mờ.
#   Đo được: trang nét ≈ 0,8–1,0 · mờ nhẹ ≈ 0,58 · mờ nặng ≈ 0,12.
_SHARPNESS_BLURRY = 0.40
_CONTRAST_FAINT = 22.0      # trang nét bình thường ≈ 40–60, trang nhạt ≈ 10
_LOW_DPI = 140


def assess_image(image, effective_dpi: float | None = None) -> list[str]:
    """Trả về danh sách vấn đề chất lượng của ảnh trang (rỗng = ổn)."""
    from PIL import ImageFilter, ImageStat

    issues = []
    gray = image.convert("L")
    # Đưa về cùng bề rộng để số đo so sánh được giữa các độ phân giải.
    target_w = 1000
    if gray.width != target_w:
        gray = gray.resize((target_w, max(1, round(gray.height * target_w / gray.width))))
    contrast = ImageStat.Stat(gray).stddev[0]
    laplacian = gray.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128))
    sharpness = ImageStat.Stat(laplacian).var[0] / max(contrast * contrast, 1.0)

    if effective_dpi is not None and effective_dpi < _LOW_DPI:
        issues.append(f"độ phân giải thấp (~{effective_dpi:.0f} dpi)")
    if contrast < _CONTRAST_FAINT:
        issues.append("chữ nhạt / thiếu tương phản")
    if contrast >= 3 and sharpness < _SHARPNESS_BLURRY:
        issues.append("ảnh mờ / nhòe")
    return issues


def _to_jpeg(image, max_side: int = 2600, quality: int = 88) -> bytes:
    img = image.convert("RGB")
    if max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Engine 1: Gemini
# ---------------------------------------------------------------------------
_GEMINI_SYSTEM = (
    "Bạn là công cụ nhận dạng chữ (OCR) cho tài liệu tố tụng tiếng Việt. Nhiệm vụ "
    "duy nhất của bạn là chép lại CHÍNH XÁC những chữ nhìn thấy trong ảnh."
)
_GEMINI_PROMPT = f"""Chép lại toàn bộ chữ trong ảnh trang tài liệu này.

QUY TẮC BẮT BUỘC:
1. Chép NGUYÊN VĂN từng chữ: đúng dấu tiếng Việt, đúng con số, ngày tháng, họ tên,
   địa danh, số tiền, số điều luật. KHÔNG sửa chính tả, KHÔNG diễn đạt lại, KHÔNG
   tóm tắt, KHÔNG thêm bớt, KHÔNG suy đoán nội dung.
2. Chỗ nào mờ, nhòe, bị che, bị con dấu đè hoặc bạn không chắc chắn: ghi
   {UNREADABLE_MARK} thay cho đúng phần đó. TUYỆT ĐỐI không đoán tên riêng hay con số.
3. Giữ thứ tự đọc từ trên xuống dưới, trái sang phải. Mỗi đoạn văn một dòng.
   Bảng: mỗi hàng một dòng, các ô cách nhau bằng " | ".
4. Chữ viết tay: chép nếu đọc được rõ, không thì ghi {UNREADABLE_MARK}.
   Con dấu ghi [con dấu], chữ ký ghi [chữ ký]. Không mô tả hình ảnh khác.
5. Chỉ trả về phần chữ chép lại — không lời dẫn, không giải thích, không markdown.
   Nếu trang không có chữ nào, trả về đúng: [TRANG TRỐNG]"""


# Thời gian chờ (giây) trước mỗi lần thử lại.
_RATE_LIMIT_WAITS = (5, 15, 30)
_OVERLOAD_WAITS = (2, 6)


class GeminiOcr:
    key = "gemini"
    name = "Gemini"
    parallel = True

    def __init__(self):
        self._client = None
        self._lock = threading.Lock()
        self._working_model = None

    @staticmethod
    def _api_key() -> str:
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        key = key.strip().strip('"').strip("'")
        if key in {"PASTE_YOUR_KEY_HERE", "dán_key_vào_đây"} or not key.isascii():
            return ""
        return key

    def available(self) -> tuple[bool, str]:
        try:
            from google import genai  # noqa: F401
        except ImportError:
            return False, "chưa cài google-genai"
        if not self._api_key():
            return False, "chưa có GOOGLE_API_KEY"
        return True, ""

    def _models(self) -> list[str]:
        from .. import config as cfg

        models = [cfg.DEFAULT_MODELS["gemini"], *getattr(cfg, "GEMINI_MODEL_FALLBACKS", ())]
        if self._working_model:
            models.insert(0, self._working_model)
        seen, ordered = set(), []
        for m in models:
            if m and m not in seen:
                seen.add(m)
                ordered.append(m)
        return ordered

    def read(self, jpeg: bytes) -> tuple[str, float | None, list[str]]:
        from google import genai
        from google.genai import types

        with self._lock:
            if self._client is None:
                self._client = genai.Client(api_key=self._api_key())
        config = types.GenerateContentConfig(
            system_instruction=_GEMINI_SYSTEM,
            temperature=0,
            max_output_tokens=16384,
        )
        contents = [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), _GEMINI_PROMPT]

        last_error = None
        for model in self._models():
            attempt = 0
            while True:
                try:
                    response = self._client.models.generate_content(
                        model=model, contents=contents, config=config
                    )
                except Exception as e:  # noqa: BLE001 - phân loại lỗi API bên dưới
                    last_error = e
                    code = getattr(e, "code", None)
                    message = str(e)
                    if code == 404 or "NOT_FOUND" in message or "is not found" in message:
                        break                      # model không tồn tại → thử model kế
                    # Quá giới hạn số lượt gọi/phút (hay gặp ở key miễn phí khi OCR
                    # nhiều trang liền nhau): chờ lâu dần rồi thử lại, đừng bỏ trang.
                    rate_limited = code == 429 or "RESOURCE_EXHAUSTED" in message
                    overloaded = code in (500, 502, 503, 504) or "UNAVAILABLE" in message
                    waits = _RATE_LIMIT_WAITS if rate_limited else _OVERLOAD_WAITS if overloaded else ()
                    if attempt < len(waits):
                        time.sleep(waits[attempt])
                        attempt += 1
                        continue
                    raise OcrError(f"Lỗi gọi Gemini: {message[:300]}") from e
                self._working_model = model
                return self._parse(response)
        raise OcrError(f"Không gọi được Gemini để OCR: {str(last_error)[:300]}")

    @staticmethod
    def _parse(response) -> tuple[str, float | None, list[str]]:
        issues = []
        try:
            text = response.text or ""
        except Exception:  # noqa: BLE001 - response bị chặn không có .text
            text = ""
        finish = ""
        try:
            finish = str(response.candidates[0].finish_reason or "")
        except Exception:  # noqa: BLE001
            pass
        if "MAX_TOKENS" in finish:
            issues.append("kết quả có thể bị cắt cụt ở cuối trang")
        if not text.strip():
            if finish and "STOP" not in finish:
                raise OcrError(f"Gemini không trả về nội dung (lý do: {finish}).")
            raise OcrError("Gemini không trả về nội dung cho trang này.")
        text = re.sub(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$", "", text.strip())
        if text.strip().upper().strip("[]. ") in ("TRANG TRỐNG", "TRANG TRONG"):
            text = ""
        return text, None, issues


# ---------------------------------------------------------------------------
# Engine 2: EasyOCR (ngoại tuyến)
# ---------------------------------------------------------------------------
class EasyOcr:
    key = "easyocr"
    name = "EasyOCR"
    parallel = False

    def __init__(self, langs: str = "vie+eng"):
        mapping = {"vie": "vi", "vi": "vi", "eng": "en", "en": "en"}
        self.langs = []
        for code in re.split(r"[+,\s]+", langs.lower()):
            if mapping.get(code) and mapping[code] not in self.langs:
                self.langs.append(mapping[code])
        self.langs = self.langs or ["vi", "en"]
        self._reader = None
        self._lock = threading.Lock()

    def available(self) -> tuple[bool, str]:
        try:
            import easyocr  # noqa: F401
        except Exception:  # noqa: BLE001 - thiếu easyocr hoặc torch hỏng
            return False, "chưa cài easyocr"
        return True, ""

    def read(self, jpeg: bytes) -> tuple[str, float | None, list[str]]:
        import easyocr
        import numpy as np
        from PIL import Image

        with self._lock:
            if self._reader is None:
                try:
                    self._reader = easyocr.Reader(self.langs, gpu=False, verbose=False)
                except Exception as e:  # noqa: BLE001
                    raise OcrError(
                        f"Không khởi tạo được EasyOCR (lần đầu cần mạng để tải model): {e}"
                    ) from e
            image = np.array(Image.open(io.BytesIO(jpeg)).convert("RGB"))
            try:
                boxes = self._reader.readtext(image, detail=1, paragraph=False)
            except Exception as e:  # noqa: BLE001
                raise OcrError(f"EasyOCR lỗi: {e}") from e

        # Gom các khung chữ thành dòng theo tọa độ dọc, rồi xếp trái → phải.
        items = []
        for box, text, conf in boxes:
            ys = [pt[1] for pt in box]
            xs = [pt[0] for pt in box]
            items.append((min(ys), max(ys), min(xs), str(text), float(conf)))
        items.sort(key=lambda it: (it[0] + it[1]) / 2)
        lines, current, current_mid = [], [], None
        for top, bottom, left, text, conf in items:
            mid, height = (top + bottom) / 2, max(1.0, bottom - top)
            if current_mid is not None and abs(mid - current_mid) > height * 0.6:
                lines.append(current)
                current = []
            current.append((left, text, conf))
            current_mid = mid if current_mid is None or not current[:-1] else (current_mid + mid) / 2
        if current:
            lines.append(current)
        out = "\n".join(" ".join(t for _, t, _ in sorted(line)) for line in lines)
        total = sum(len(t) for *_, t, _ in items)
        conf = sum(len(t) * c for *_, t, c in items) / total if total else None
        return out, conf, []


# ---------------------------------------------------------------------------
# Engine 3: Tesseract (ngoại tuyến)
# ---------------------------------------------------------------------------
_WINDOWS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _locate_tesseract():
    """Trả về module pytesseract đã trỏ đúng file chạy, hoặc None."""
    try:
        import pytesseract
    except ImportError:
        return None
    if not shutil.which(pytesseract.pytesseract.tesseract_cmd):
        for candidate in _WINDOWS_TESSERACT:
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                break
    try:
        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001
        return None
    return pytesseract


class TesseractOcr:
    key = "tesseract"
    name = "Tesseract"
    parallel = True

    def __init__(self, langs: str = "vie+eng"):
        self.requested = [c for c in re.split(r"[+,\s]+", langs.lower()) if c]
        self.lang = "+".join(self.requested) or "vie+eng"

    def available(self) -> tuple[bool, str]:
        tess = _locate_tesseract()
        if tess is None:
            return False, "chưa cài Tesseract"
        try:
            installed = set(tess.get_languages(config=""))
        except Exception:  # noqa: BLE001
            installed = set()
        if "vie" in self.requested and "vie" not in installed:
            return False, "Tesseract thiếu gói tiếng Việt (vie)"
        usable = [c for c in self.requested if c in installed]
        if not usable:
            return False, "Tesseract thiếu gói ngôn ngữ"
        self.lang = "+".join(usable)
        return True, ""

    def read(self, jpeg: bytes) -> tuple[str, float | None, list[str]]:
        from PIL import Image, ImageOps

        tess = _locate_tesseract()
        if tess is None:
            raise OcrError("Không tìm thấy Tesseract.")
        image = ImageOps.autocontrast(Image.open(io.BytesIO(jpeg)).convert("L"), cutoff=1)
        try:
            data = tess.image_to_data(
                image, lang=self.lang, config="--psm 3", output_type=tess.Output.DICT
            )
        except Exception as e:  # noqa: BLE001
            raise OcrError(f"Tesseract lỗi: {str(e)[:200]}") from e

        lines: dict[tuple, list[str]] = {}
        weight = total = 0.0
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            weight += conf * len(word)
            total += len(word)
        text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
        return text, (weight / total / 100.0 if total else None), []


# ---------------------------------------------------------------------------
# Chọn engine + chạy
# ---------------------------------------------------------------------------
_ENGINE_CACHE: dict[tuple[str, str], object] = {}


def _engine(key: str, langs: str):
    cache_key = (key, langs)
    if cache_key not in _ENGINE_CACHE:
        if key == "gemini":
            _ENGINE_CACHE[cache_key] = GeminiOcr()
        elif key == "easyocr":
            _ENGINE_CACHE[cache_key] = EasyOcr(langs)
        else:
            _ENGINE_CACHE[cache_key] = TesseractOcr(langs)
    return _ENGINE_CACHE[cache_key]


def engine_chain(options: OcrOptions) -> tuple[list, list[str]]:
    """Danh sách engine dùng được theo thứ tự ưu tiên + lý do các engine bị loại."""
    keys = ["gemini", "easyocr", "tesseract"] if options.engine == "auto" else [options.engine]
    chain, unavailable = [], []
    for key in keys:
        engine = _engine(key, options.langs)
        ok, reason = engine.available()
        if ok:
            chain.append(engine)
        else:
            unavailable.append(f"{engine.name}: {reason}")
    return chain, unavailable


def detect_ocr_capability(langs: str = "vie+eng") -> dict:
    """Engine OCR nào đang dùng được trên máy này (cho giao diện hiển thị)."""
    status = {}
    for key in ("gemini", "easyocr", "tesseract"):
        ok, reason = _engine(key, langs).available()
        status[key] = {"ok": ok, "reason": reason, "name": ENGINE_LABELS[key]}
    return status


def no_engine_message(unavailable: list[str]) -> str:
    return (
        "Không có công cụ nhận dạng chữ (OCR) nào dùng được ("
        + "; ".join(unavailable)
        + "). Cách đơn giản nhất: kiểm tra GOOGLE_API_KEY và kết nối mạng để dùng "
        "Gemini; hoặc cài OCR ngoại tuyến (xem README, mục OCR)."
    )


def _evaluate(page: OcrPage) -> None:
    """Bổ sung cảnh báo dựa trên chính kết quả OCR."""
    stats = text_stats(page.text)
    # Điểm tin cậy engine tự báo thường LẠC QUAN (Tesseract vẫn báo ~94% trên
    # trang mờ chỉ đúng 75% số từ), nên đặt ngưỡng cao và chỉ coi là tham khảo.
    threshold = 0.88 if page.engine == "Tesseract" else 0.75
    if page.confidence is not None and page.confidence < threshold and stats["chars"] > 20:
        page.issues.append(f"độ tin cậy OCR thấp ({page.confidence:.0%})")
    if stats["unreadable_marks"]:
        page.issues.append(f"{stats['unreadable_marks']} chỗ không đọc được")
    if stats["words"] >= 40 and stats["viet_ratio"] < 0.25:
        page.issues.append("chữ đọc ra ít dấu tiếng Việt bất thường (nghi nhận dạng sai)")
    if stats["bad_ratio"] > 0.03:
        page.issues.append("lẫn nhiều ký tự lạ")


def run_ocr(jobs, options: OcrOptions, total: int, progress=None) -> tuple[dict[int, OcrPage], list[str]]:
    """OCR một loạt trang.

    `jobs`: iterable các (số_trang, ảnh PIL, dpi_thực_tế | None). Ảnh được
    dựng LẦN LƯỢT (không giữ tất cả trong bộ nhớ) và nén JPEG ngay.
    Trả về ({số_trang: OcrPage}, cảnh báo chung)."""
    chain, unavailable = engine_chain(options)
    if not chain:
        raise OcrError(no_engine_message(unavailable))

    failures = {e.name: 0 for e in chain}
    successes = {e.name: 0 for e in chain}
    state_lock = threading.Lock()

    def work(jpeg: bytes) -> OcrPage:
        errors = []
        for engine in chain:
            with state_lock:
                # Engine hỏng hẳn (sai key, hết quota...) thì thôi không thử lại
                # cho các trang sau, khỏi chờ vô ích.
                if failures[engine.name] >= 3 and successes[engine.name] == 0:
                    continue
            try:
                text, confidence, issues = engine.read(jpeg)
            except OcrError as e:
                with state_lock:
                    failures[engine.name] += 1
                errors.append(f"{engine.name}: {e}")
                continue
            except Exception as e:  # noqa: BLE001 - engine ngoài lỗi bất ngờ, thử engine kế
                with state_lock:
                    failures[engine.name] += 1
                errors.append(f"{engine.name}: {e}")
                continue
            with state_lock:
                successes[engine.name] += 1
            page = OcrPage(text=clean_text(text), engine=engine.name, confidence=confidence, issues=list(issues))
            _evaluate(page)
            return page
        return OcrPage(error=" | ".join(errors) or "không có engine OCR nào chạy được")

    workers = max(1, options.workers) if all(e.parallel for e in chain) else 1
    slots = threading.BoundedSemaphore(workers * 2)
    results: dict[int, OcrPage] = {}
    image_issues: dict[int, list[str]] = {}
    done = 0

    def guarded(jpeg: bytes) -> OcrPage:
        try:
            return work(jpeg)
        finally:
            slots.release()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for number, image, effective_dpi in jobs:
            image_issues[number] = assess_image(image, effective_dpi)
            jpeg = _to_jpeg(image)
            del image
            slots.acquire()
            futures[pool.submit(guarded, jpeg)] = number
            finished = sum(1 for f in futures if f.done())
            if progress and finished != done:
                done = finished
                progress(done, total, f"Đang nhận dạng chữ (OCR): {done}/{total} trang")
        for future in as_completed(futures):
            number = futures[future]
            page = future.result()
            page.issues = image_issues.get(number, []) + page.issues
            results[number] = page
            if progress:
                progress(len(results), total, f"Đang nhận dạng chữ (OCR): {len(results)}/{total} trang")

    warnings = []
    used = {p.engine for p in results.values() if p.engine}
    for engine in chain:
        if failures[engine.name] and used and engine.name not in used:
            warnings.append(
                f"{engine.name} không chạy được ở {failures[engine.name]} trang nên đã chuyển sang "
                f"{' / '.join(sorted(used))}."
            )
    return results, warnings


def ocr_images(images: list, options: OcrOptions, progress=None):
    """OCR danh sách ảnh rời (ảnh nhúng trong .docx).
    Trả về (văn bản, [PageInfo], tên engine, cảnh báo)."""
    images = images[: options.max_pages]
    try:
        results, warnings = run_ocr(
            ((i + 1, img, None) for i, img in enumerate(images)), options, len(images), progress
        )
    except OcrError as e:
        return "", [], "", [str(e)]
    pages, texts, engines = [], [], []
    for number in sorted(results):
        page = results[number]
        if page.error:
            pages.append(PageInfo(number, "failed", issues=[page.error]))
            continue
        pages.append(PageInfo(number, "ocr", page.engine, len(page.text), page.confidence, page.issues))
        if page.text:
            texts.append(page.text)
        if page.engine not in engines:
            engines.append(page.engine)
    return "\n\n".join(texts), pages, " + ".join(engines), warnings
