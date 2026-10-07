"""
Giao diện Streamlit — Hệ thống AI hỗ trợ soạn thảo văn bản tố tụng.
Chỉ dùng Google Gemini. API key đọc từ biến môi trường GOOGLE_API_KEY
đã cấu hình sẵn trên server hoặc trong Streamlit Secrets — người dùng cuối
(Ban Tổ chức) KHÔNG cần nhập bất kỳ key nào.

Luồng sử dụng:
    1. Tải file đề (.docx / .doc / .rtf / .pdf — kể cả PDF scan).
    2. Hệ thống đọc file, hiện NỘI DUNG ĐÃ ĐỌC kèm cảnh báo (nếu là bản scan).
       Người dùng đọc soát, sửa trực tiếp nếu cần.
    3. Bấm "Chạy xử lý".

Chạy local để test:
    export GOOGLE_API_KEY="..."
    streamlit run app.py
"""

import hashlib
import os
import sys
import tempfile

import streamlit as st

# 1. Nạp file .env an toàn nếu chạy local (bỏ qua nếu thiếu thư viện trên Cloud)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


# 2. Đồng bộ lấy API Key từ Streamlit Secrets hoặc Biến môi trường hệ thống (.env)
def _secret(name: str) -> str:
    try:
        return st.secrets.get(name) or ""
    except Exception:  # noqa: BLE001 - chạy local không có secrets.toml
        return ""


api_key = (
    _secret("GOOGLE_API_KEY")
    or _secret("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
    or ""
).strip().strip('"').strip("'")

# Gán ngược lại vào môi trường hệ thống để các SDK tự động sử dụng
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ["GEMINI_API_KEY"] = api_key

from core import prompts as pr  # noqa: E402
from core.docx_writer import write_result_docx  # noqa: E402
from core.file_parser import (  # noqa: E402
    PDF_NOTICE,
    SUPPORTED_EXTENSIONS,
    OcrOptions,
    detect_ocr_capability,
    extract_input_file,
)
from core.model_clients import ModelCallError  # noqa: E402
from core.pipeline import run_pipeline  # noqa: E402

PROVIDER = "gemini"  # Cố định — không cho người dùng cuối chọn model

st.set_page_config(
    page_title="AI hỗ trợ soạn thảo Cáo trạng",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ Hệ thống AI hỗ trợ soạn thảo văn bản tố tụng")
st.caption("VKSND tỉnh Nghệ An — Cuộc thi ứng dụng AI vào công tác chuyên môn, nghiệp vụ năm 2026")

# ---------------------------------------------------------------------------
# Kiểm tra cấu hình server — nếu quên cấu hình Key thì báo rõ cho người vận hành
# ---------------------------------------------------------------------------
if (
    not api_key
    or not api_key.isascii()
    or api_key in {"PASTE_YOUR_KEY_HERE", "dán_key_vào_đây"}
):
    st.error(
        "Chưa gắn API key Gemini hợp lệ. "
        "Vui lòng cấu hình `GOOGLE_API_KEY` trong mục **Secrets** trên Streamlit Cloud "
        "hoặc mở file `.env` trong thư mục project nếu chạy local, sửa dòng `GOOGLE_API_KEY=` "
        "thành key lấy từ https://aistudio.google.com/apikey (thường bắt đầu bằng `AIza`), "
        "**Ctrl+S lưu file**, rồi khởi chạy lại ứng dụng."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Thanh bên: thông tin + cài đặt đọc PDF scan
# ---------------------------------------------------------------------------
if "ocr_status" not in st.session_state:
    st.session_state["ocr_status"] = detect_ocr_capability()
ocr_cap = st.session_state["ocr_status"]

OCR_MODES = {
    "Tự động (khuyến nghị)": "auto",
    "Luôn OCR lại mọi trang": "always",
    "Không OCR": "never",
}
OCR_ENGINES = {
    "Tự động chọn": "auto",
    "Gemini (cần mạng)": "gemini",
    "EasyOCR (ngoại tuyến)": "easyocr",
    "Tesseract (ngoại tuyến)": "tesseract",
}

with st.sidebar:
    st.header("ℹ️ Thông tin hệ thống")
    st.markdown(
        "- **Mô hình AI:** Google Gemini\n"
        "- **Nguồn luật:** 10 văn bản đã nạp sẵn — BLHS, BLTTHS, BLDS, BLTTDS, "
        "Luật sửa đổi BLTTDS/LTTHC 2025, LTTHC, Luật Đất đai, Bộ luật Lao động, "
        "Luật Tư pháp người chưa thành niên, Nghị quyết 04/2025/NQ-HĐTP "
        "(tra cứu tự động, không lên mạng)\n"
        "- **Định dạng file:** .docx, .doc, .rtf, .pdf (kể cả PDF scan)\n"
        "- **Phạm vi:** Cáo trạng (Hình sự) + Phát biểu của KSV (Dân sự/Hành chính)"
    )
    st.divider()

    st.subheader("🔍 Đọc PDF scan / ảnh (OCR)")
    ocr_mode_label = st.radio(
        "Khi nào nhận dạng chữ từ ảnh",
        options=list(OCR_MODES),
        index=0,
        help=(
            "Tự động: trang nào đã có lớp chữ thì đọc trực tiếp, chỉ trang scan/ảnh mới OCR. "
            "Luôn OCR lại: dùng khi lớp chữ có sẵn của file bị sai. "
            "Không OCR: chỉ đọc lớp chữ có sẵn."
        ),
    )
    ocr_engine_label = st.selectbox(
        "Công cụ OCR",
        options=list(OCR_ENGINES),
        index=0,
        help=(
            "Tự động chọn: thử Gemini trước (đọc tiếng Việt tốt nhất, không cần cài thêm), "
            "nếu không được thì dùng công cụ ngoại tuyến có trên máy. "
            "Với Gemini, ảnh trang tài liệu được gửi tới dịch vụ Google Gemini — cùng "
            "dịch vụ đang nhận nội dung hồ sơ để soạn văn bản."
        ),
    )
    with st.expander("Tùy chỉnh nâng cao"):
        ocr_dpi = st.slider(
            "Độ phân giải dựng ảnh (DPI)",
            min_value=150, max_value=400, value=220, step=10,
            help="Cao hơn thì rõ hơn nhưng chậm hơn. 200–250 là đủ cho văn bản in thông thường.",
        )
        ocr_max_pages = st.slider(
            "Số trang OCR tối đa",
            min_value=1, max_value=200, value=60, step=1,
            help="Trang scan vượt quá số này sẽ KHÔNG được đọc (có cảnh báo).",
        )

    st.markdown("**Công cụ OCR trên máy này:**")
    st.caption("\n\n".join(
        ("✅ " if info["ok"] else "❌ ") + info["name"] + ("" if info["ok"] else f" — {info['reason']}")
        for info in ocr_cap.values()
    ))
    if not any(info["ok"] for info in ocr_cap.values()):
        st.error(
            "Chưa có công cụ OCR nào dùng được: PDF scan sẽ không đọc được. "
            "Kiểm tra GOOGLE_API_KEY để dùng Gemini (xem README, mục OCR)."
        )

    st.divider()
    st.caption(
        "Kết quả do AI hỗ trợ soạn. Kiểm sát viên có trách nhiệm kiểm "
        "tra, chỉnh sửa trước khi ban hành chính thức."
    )

ocr_options = OcrOptions(
    mode=OCR_MODES[ocr_mode_label],
    engine=OCR_ENGINES[ocr_engine_label],
    dpi=ocr_dpi,
    max_pages=ocr_max_pages,
)

# ---------------------------------------------------------------------------
# BƯỚC 1: tải file
# ---------------------------------------------------------------------------
uploaded_file = st.file_uploader(
    "📄 Tải lên file đề thi (.docx, .doc, .rtf hoặc .pdf — kể cả PDF scan)",
    type=list(SUPPORTED_EXTENSIONS),
)

with st.expander("📌 Lưu ý khi dùng file PDF / bản scan — nên đọc trước khi tải lên"):
    st.markdown(PDF_NOTICE)

if uploaded_file is None:
    st.info("Tải lên file đề thi ở trên. Hệ thống sẽ đọc file và hiện nội dung để bạn kiểm tra trước khi chạy.")
    st.stop()

# ---------------------------------------------------------------------------
# BƯỚC 2: đọc file (chỉ đọc lại khi đổi file hoặc đổi cài đặt OCR)
# ---------------------------------------------------------------------------
file_bytes = uploaded_file.getvalue()
is_pdf = b"%PDF-" in file_bytes[:1024]
# Cài đặt OCR chỉ ảnh hưởng tới PDF (và .docx toàn ảnh) — với file chữ thường,
# đổi cài đặt không được làm mất phần người dùng đã sửa tay.
settings_tag = repr((ocr_options.mode, ocr_options.engine, ocr_options.dpi, ocr_options.max_pages)) if is_pdf else ""
file_key = hashlib.sha1(file_bytes + uploaded_file.name.encode("utf-8") + settings_tag.encode()).hexdigest()

if st.session_state.get("file_key") != file_key:
    suffix = os.path.splitext(uploaded_file.name)[1] or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    progress_bar = st.progress(0.0, text="Đang đọc nội dung file...")

    def _on_progress(done: int, total: int, message: str) -> None:
        progress_bar.progress(min(1.0, done / total) if total else 0.0, text=message)

    extraction, read_error = None, ""
    try:
        extraction = extract_input_file(tmp_path, ocr=ocr_options, progress=_on_progress)
    except ValueError as e:
        read_error = str(e)
    except Exception as e:  # noqa: BLE001 - lỗi bất ngờ của thư viện đọc file
        read_error = f"Lỗi không mong muốn khi đọc file ({type(e).__name__}): {e}"
    finally:
        progress_bar.empty()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    st.session_state["file_key"] = file_key
    st.session_state["extraction"] = extraction
    st.session_state["read_error"] = read_error
    st.session_state.pop("result", None)

extraction = st.session_state.get("extraction")
if extraction is None:
    st.error(f"Không đọc được file: {st.session_state.get('read_error', '')}")
    st.stop()

# ---------------------------------------------------------------------------
# BƯỚC 3: cho người dùng xem / sửa nội dung đã đọc
# ---------------------------------------------------------------------------
char_count = f"{len(extraction.text):,}".replace(",", ".")
summary = f"**Đã đọc file** `{uploaded_file.name}` — {extraction.method} · {char_count} ký tự"
if extraction.pages:
    summary += f" · {len(extraction.pages)} trang"

if extraction.needs_review:
    st.warning(summary, icon="⚠️")
    if extraction.used_ocr:
        st.error(
            "**Nội dung dưới đây được nhận dạng từ ảnh (OCR) nên có thể KHÔNG chính xác.** "
            "Hãy đọc soát và so với bản gốc — nhất là họ tên, ngày tháng, số tiền, số điều "
            "luật — rồi sửa trực tiếp trong ô bên dưới trước khi bấm Chạy xử lý.",
            icon="📷",
        )
    for warning in extraction.warnings:
        st.warning(warning)
else:
    st.success(summary, icon="✅")

if extraction.file_type == "pdf" and extraction.pages:
    method_labels = {
        "text": "Lớp chữ có sẵn", "ocr": "OCR (nhận dạng từ ảnh)", "blank": "Trang trắng / không có chữ",
        "skipped": "CHƯA ĐỌC (vượt giới hạn)", "failed": "KHÔNG ĐỌC ĐƯỢC",
    }
    flagged = len(extraction.problem_pages)
    label = "📑 Chi tiết từng trang" + (f" — {flagged} trang cần xem kỹ" if flagged else "")
    with st.expander(label, expanded=bool(flagged) and len(extraction.pages) <= 30):
        st.dataframe(
            [
                {
                    "Trang": page.number,
                    "Cách đọc": method_labels.get(page.method, page.method),
                    "Công cụ": page.engine or "—",
                    "Số ký tự": page.chars,
                    "Độ tin cậy": "—" if page.confidence is None else f"{page.confidence:.0%}",
                    "Vấn đề": "; ".join(page.issues) or "—",
                }
                for page in extraction.pages
            ],
            hide_index=True,
        )
        st.caption(
            "Cột Độ tin cậy do công cụ OCR tự báo (chỉ có với OCR ngoại tuyến) và thường lạc "
            "quan hơn thực tế — không thay cho việc đối chiếu bản gốc."
        )

input_text = st.text_area(
    "📖 Nội dung đã đọc từ file — có thể sửa trực tiếp trước khi chạy",
    value=extraction.text,
    height=320 if extraction.needs_review else 220,
    key=f"input_text_{file_key}",
)

run_clicked = st.button("🚀 Chạy xử lý", type="primary")

# ---------------------------------------------------------------------------
# BƯỚC 4: chạy 5 bước xử lý
# ---------------------------------------------------------------------------
if run_clicked:
    if len(input_text.strip()) < 50:
        st.error("Nội dung hồ sơ quá ngắn (dưới 50 ký tự) — chưa đủ để soạn văn bản.")
        st.stop()

    status_box = st.status("Đang xử lý qua các bước...", expanded=True)
    step_labels = {
        "classify": "Bước 1 — Phân loại vụ việc (Hình sự / Dân sự-Hành chính)",
        "extract": "Bước 2 — Trích xuất dữ kiện có cấu trúc",
        "lookup_laws": "Bước 3 — Tra cứu điều luật liên quan",
        "draft": "Bước 4 — Soạn bản thảo",
        "self_check": "Bước 5 — Tự kiểm tra & xử lý ngoại lệ",
    }

    def progress_callback(step_name, content):
        status_box.write(f"✅ {step_labels.get(step_name, step_name)} — hoàn thành")

    try:
        with status_box:
            result = run_pipeline(
                input_text,
                provider=PROVIDER,
                progress_callback=progress_callback,
                input_note=pr.OCR_INPUT_NOTE if extraction.used_ocr else None,
            )
        status_box.update(label="Đã xử lý xong toàn bộ 5 bước", state="complete")
    except ModelCallError as e:
        status_box.update(label="Lỗi khi gọi mô hình AI", state="error")
        st.error(str(e))
        st.stop()
    except Exception as e:  # noqa: BLE001
        status_box.update(label="Lỗi không xác định", state="error")
        st.error(f"Lỗi: {e}")
        st.stop()

    # Xuất .docx ngay và giữ trong phiên, để bấm Tải về không làm mất kết quả.
    docx_bytes, docx_error = None, ""
    out_fd, out_path = tempfile.mkstemp(suffix="_ket_qua.docx")
    os.close(out_fd)
    try:
        write_result_docx(
            result["final"],
            result["case_type"],
            out_path,
            is_hanh_chinh=result.get("is_hanh_chinh", False),
            header=result.get("header"),
        )
        with open(out_path, "rb") as f:
            docx_bytes = f.read()
    except (FileNotFoundError, ValueError) as e:
        docx_error = str(e)
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    st.session_state["result"] = {
        "file_key": file_key,
        "data": result,
        "docx": docx_bytes,
        "docx_error": docx_error,
        "source": extraction.method,
        "used_ocr": extraction.used_ocr,
        "input_warnings": list(extraction.warnings),
    }

# ---------------------------------------------------------------------------
# Kết quả (giữ lại giữa các lần tương tác, cho tới khi đổi file hoặc chạy lại)
# ---------------------------------------------------------------------------
saved = st.session_state.get("result")
if saved and saved["file_key"] == file_key:
    result = saved["data"]
    loai_hien_thi = (
        "Hình sự" if result["case_type"] == "HINH_SU"
        else ("Hành chính" if result.get("is_hanh_chinh") else "Dân sự / HNGĐ / KDTM / Lao động")
    )
    st.success(f"Đã soạn xong bản thảo — loại vụ việc: **{loai_hien_thi}**")

    internal_check = result["internal_check"]
    if saved["used_ocr"] or saved["input_warnings"]:
        lines = [f"0. NGUỒN ĐẦU VÀO: {saved['source']}."]
        if saved["used_ocr"]:
            lines.append(
                "   ⚠ Hồ sơ được nhận dạng bằng OCR từ bản scan/ảnh — mọi họ tên, ngày tháng, "
                "số tiền, số điều luật trong bản thảo cần đối chiếu lại với bản gốc."
            )
        lines.extend(f"   - {w}" for w in saved["input_warnings"])
        internal_check = "\n".join(lines) + "\n\n" + internal_check

    tab_final, tab_check, tab_facts, tab_laws, tab_draft = st.tabs(
        ["📌 Kết quả cuối", "✅ Kiểm tra nội bộ", "🔍 Dữ kiện đã trích xuất", "⚖️ Điều luật tìm được", "📝 Bản thảo (trước kiểm tra)"]
    )
    with tab_final:
        st.text_area("Văn bản cáo trạng (không kèm phụ lục nội bộ)", result["final"], height=500)
    with tab_check:
        st.text_area("Phụ lục kiểm tra nội bộ (chỉ hiển thị trên ứng dụng)", internal_check, height=350)
    with tab_facts:
        st.text_area("Dữ kiện trích xuất (JSON)", result["facts"], height=400)
    with tab_laws:
        st.text_area("Điều luật liên quan (tra cứu tự động)", result["dieu_luat_lien_quan"], height=400)
    with tab_draft:
        st.text_area("Bản thảo ban đầu", result["draft"], height=400)

    if saved["docx"]:
        st.download_button(
            "📥 Tải kết quả (.docx)",
            data=saved["docx"],
            file_name="ket_qua_ai.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        st.error(f"Chưa thể xuất văn bản theo mẫu: {saved['docx_error']}")

    st.warning(
        "Đây là bản thảo do AI hỗ trợ soạn. Vui lòng kiểm tra kỹ trước khi "
        "sử dụng, đặc biệt các đoạn được đánh dấu [THIẾU DỮ LIỆU], "
        "[CẦN KIỂM TRA LẠI ĐIỀU LUẬT], [TÌNH TIẾT MÂU THUẪN]."
        + (
            " Hồ sơ đầu vào là bản scan đọc bằng OCR nên cần đối chiếu thêm với bản gốc."
            if saved["used_ocr"] else ""
        )
    )
