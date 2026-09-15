"""
Điều phối luồng xử lý 5 bước (Hình sự + Dân sự/Hành chính):
  1. Phân loại vụ việc (HINH_SU / DAN_SU_HANH_CHINH)
  2. Trích xuất dữ kiện có cấu trúc (JSON) — đúng nhánh theo loại vụ việc
  3. Tra cứu điều luật liên quan (offline, hoặc offline+online nếu hybrid)
  4. Soạn bản thảo (Cáo trạng / Phát biểu của Kiểm sát viên)
  5. Tự kiểm tra (chống bịa đặt, thiếu mục, xử lý ngoại lệ)

Đổi model nền chỉ cần đổi tham số `provider`.
"""

import json

from . import model_clients as mc
from . import prompts as pr
from . import law_lookup


_INTERNAL_CHECK_MARKER = "--- PHỤ LỤC KIỂM TRA NỘI BỘ"
_INTERNAL_CHECK_END_MARKER = "--- HẾT PHỤ LỤC KIỂM TRA NỘI BỘ ---"


def _move_internal_check_to_end(text: str) -> str:
    """Giữ phụ lục kiểm tra ở cuối cáo trạng dù model đặt sai vị trí."""
    marker_index = text.find(_INTERNAL_CHECK_MARKER)
    if marker_index < 0:
        return text

    end_index = text.find(_INTERNAL_CHECK_END_MARKER, marker_index)
    if end_index >= 0:
        appendix_end = end_index + len(_INTERNAL_CHECK_END_MARKER)
        appendix = text[marker_index:appendix_end].strip()
        document = (text[:marker_index] + text[appendix_end:]).strip()
    else:
        document = text[:marker_index].rstrip()
        appendix = text[marker_index:].strip()
    return f"{document}\n\n{appendix}".strip()


def classify_case(input_text: str, provider: str = "gemini") -> str:
    raw = mc.call_model(
        provider, pr.SYSTEM_BASE, pr.CLASSIFY_PROMPT.format(input_text=input_text)
    )
    raw_upper = raw.strip().upper()
    if "HINH_SU" in raw_upper or "HÌNH SỰ" in raw_upper:
        return "HINH_SU"
    return "DAN_SU_HANH_CHINH"


def extract_facts(input_text: str, case_type: str, provider: str = "gemini") -> str:
    template = pr.EXTRACT_PROMPT_HS if case_type == "HINH_SU" else pr.EXTRACT_PROMPT_DS
    return mc.call_model(provider, pr.SYSTEM_BASE, template.format(input_text=input_text))


def lookup_laws(facts_json: str, case_type: str, top_n: int = 10) -> str:
    """Tra cứu điều luật liên quan — dùng tội danh/quan hệ pháp luật
    tranh chấp trong JSON dữ kiện làm truy vấn. Tự động tìm trên TOÀN BỘ
    8 bộ luật đã nạp (không cần biết trước case_type thuộc bộ luật nào),
    điểm số từ khóa tự quyết định điều nào liên quan nhất."""
    try:
        facts = json.loads(facts_json)
        if case_type == "HINH_SU":
            query = " ".join(
                str(facts.get(k, ""))
                for k in (
                    "toi_danh_nghi_van",
                    "hanh_vi_pham_toi_tom_tat",
                    "tuoi_tai_thoi_diem_pham_toi",
                    "la_nguoi_duoi_18_tuoi",
                    "tinh_tiet_tang_nang",
                    "tinh_tiet_giam_nhe",
                )
            )
        else:
            query = " ".join(
                str(facts.get(k, ""))
                for k in ("quan_he_phap_luat_tranh_chap", "yeu_cau_khoi_kien", "loai_vu_viec")
            )
    except (json.JSONDecodeError, AttributeError):
        query = facts_json

    result = law_lookup.find_relevant_articles(query, top_n=top_n)
    return law_lookup.format_articles_for_prompt(result)


def _is_hanh_chinh(facts_json: str) -> bool:
    """Xác định vụ việc dân sự/hành chính có phải HÀNH CHÍNH cụ thể hay
    không (để chọn đúng Mẫu 35/HC thay vì Mẫu 36/DS), dựa vào trường
    loai_vu_viec đã trích xuất ở Bước 2."""
    try:
        facts = json.loads(facts_json)
        loai = str(facts.get("loai_vu_viec", "")).strip().lower()
        return "hành chính" in loai or "hanh chinh" in loai
    except (json.JSONDecodeError, AttributeError):
        return False


def draft_document(facts_json: str, dieu_luat_lien_quan: str, case_type: str, provider: str = "gemini") -> str:
    if case_type == "HINH_SU":
        template = pr.DRAFT_PROMPT_HS
        mau = pr.MAU_CAO_TRANG_THAM_CHIEU
    elif _is_hanh_chinh(facts_json):
        template = pr.DRAFT_PROMPT_DS
        mau = pr.MAU_PHAT_BIEU_HANH_CHINH_THAM_CHIEU  # Mẫu 35/HC
    else:
        template = pr.DRAFT_PROMPT_DS
        mau = pr.MAU_BAI_PHAT_BIEU_THAM_CHIEU  # Mẫu 36/DS

    prompt = template.format(
        facts_json=facts_json,
        mau_tham_chieu=mau,
        dieu_luat_lien_quan=dieu_luat_lien_quan,
    )
    return mc.call_model(provider, pr.SYSTEM_BASE, prompt)


def self_check(
    draft_text: str,
    facts_json: str,
    case_type: str,
    dieu_luat_lien_quan: str,
    provider: str = "gemini",
) -> str:
    prompt = pr.SELF_CHECK_PROMPT.format(
        draft_text=draft_text,
        facts_json=facts_json,
        case_type=case_type,
        dieu_luat_lien_quan=dieu_luat_lien_quan,
    )
    checked_text = mc.call_model(provider, pr.SYSTEM_BASE, prompt)
    return _move_internal_check_to_end(checked_text)


def run_pipeline(
    input_text: str,
    provider: str = "gemini",
    case_type_override: str | None = None,
    progress_callback=None,
) -> dict:
    """
    progress_callback(step_name: str, content: str) được gọi sau MỖI bước,
    dùng để Streamlit hiển thị tiến trình theo thời gian thực.
    """

    def notify(step_name, content):
        if progress_callback:
            progress_callback(step_name, content)

    case_type = case_type_override or classify_case(input_text, provider)
    notify("classify", case_type)

    facts = extract_facts(input_text, case_type, provider)
    notify("extract", facts)

    is_hc = case_type == "DAN_SU_HANH_CHINH" and _is_hanh_chinh(facts)

    dieu_luat_lien_quan = lookup_laws(facts, case_type)
    notify("lookup_laws", dieu_luat_lien_quan)

    draft = draft_document(facts, dieu_luat_lien_quan, case_type, provider)
    notify("draft", draft)

    final = self_check(draft, facts, case_type, dieu_luat_lien_quan, provider)
    notify("self_check", final)

    return {
        "case_type": case_type,
        "is_hanh_chinh": is_hc,
        "facts": facts,
        "dieu_luat_lien_quan": dieu_luat_lien_quan,
        "draft": draft,
        "final": final,
    }
