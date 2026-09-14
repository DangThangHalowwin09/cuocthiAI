"""
Giao diện Streamlit — Hệ thống AI hỗ trợ soạn thảo Cáo trạng (Hình sự).
Chỉ dùng Google Gemini. API key đọc từ biến môi trường GOOGLE_API_KEY
đã cấu hình sẵn trên server hoặc trong Streamlit Secrets — người dùng cuối 
(Ban Tổ chức) KHÔNG cần nhập bất kỳ key nào, chỉ cần tải đề lên và bấm chạy.

Chạy local để test:
    export GOOGLE_API_KEY="..."
    streamlit run app.py
"""

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
api_key = (
    st.secrets.get("GOOGLE_API_KEY")
    or st.secrets.get("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
    or ""
).strip().strip('"').strip("'")

# Gán ngược lại vào môi trường hệ thống để các SDK tự động sử dụng
if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
    os.environ["GEMINI_API_KEY"] = api_key

from core.file_parser import read_input_file  # noqa: E402
from core.pipeline import run_pipeline  # noqa: E402
from core.docx_writer import write_result_docx  # noqa: E402
from core.model_clients import ModelCallError  # noqa: E402

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

with st.sidebar:
    st.header("ℹ️ Thông tin hệ thống")
    st.markdown(
        "- **Mô hình AI:** Google Gemini\n"
        "- **Nguồn luật:** 8 bộ luật đã nạp sẵn — BLHS, BLTTHS, BLDS, "
        "BLTTDS, Luật sửa đổi BLTTDS/LTTHC 2025, LTTHC, Luật Đất đai, "
        "Bộ luật Lao động (tra cứu tự động, không lên mạng)\n"
        "- **Phạm vi:** Cáo trạng (Hình sự) + Phát biểu của KSV (Dân sự/Hành chính)"
    )
    st.divider()
    st.caption(
        "Kết quả do AI hỗ trợ soạn. Kiểm sát viên có trách nhiệm kiểm "
        "tra, chỉnh sửa trước khi ban hành chính thức."
    )

# ---------------------------------------------------------------------------
# MAIN: tải đề thi & chạy xử lý
# ---------------------------------------------------------------------------
uploaded_file = st.file_uploader("📄 Tải lên file đề thi (.docx hoặc .pdf)", type=["docx", "pdf"])

run_clicked = st.button("🚀 Chạy xử lý", type="primary", disabled=uploaded_file is None)

if run_clicked and uploaded_file is not None:
    suffix = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    with st.spinner("Đang đọc nội dung đề thi..."):
        try:
            input_text = read_input_file(tmp_path)
        except Exception as e:
            st.error(f"Không đọc được file: {e}")
            st.stop()

    with st.expander("📖 Xem nội dung đề đã trích xuất từ file"):
        st.text(input_text)

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

    st.success(f"Đã soạn xong bản thảo — loại vụ việc: **{('Hình sự' if result['case_type']=='HINH_SU' else 'Dân sự / Hành chính')}**")

    tab_final, tab_facts, tab_laws, tab_draft = st.tabs(
        ["📌 Kết quả cuối", "🔍 Dữ kiện đã trích xuất", "⚖️ Điều luật tìm được", "📝 Bản thảo (trước kiểm tra)"]
    )
    with tab_final:
        st.text_area("Văn bản kết quả (đã qua bước tự kiểm tra)", result["final"], height=500)
    with tab_facts:
        st.text_area("Dữ kiện trích xuất (JSON)", result["facts"], height=400)
    with tab_laws:
        st.text_area("Điều luật liên quan (tra cứu tự động)", result["dieu_luat_lien_quan"], height=400)
    with tab_draft:
        st.text_area("Bản thảo ban đầu", result["draft"], height=400)

    out_path = tmp_path + "_ket_qua.docx"
    write_result_docx(result["final"], result["case_type"], out_path)
    with open(out_path, "rb") as f:
        st.download_button(
            "📥 Tải kết quả (.docx)",
            data=f,
            file_name="ket_qua_ai.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    st.warning(
        "Đây là bản thảo do AI hỗ trợ soạn. Vui lòng kiểm tra kỹ trước khi "
        "sử dụng, đặc biệt các đoạn được đánh dấu [THIẾU DỮ LIỆU], "
        "[CẦN KIỂM TRA LẠI ĐIỀU LUẬT], [TÌNH TIẾT MÂU THUẪN]."
    )
else:
    st.info("Tải lên file đề thi hình sự (.docx hoặc .pdf) ở trên rồi bấm **Chạy xử lý**.")