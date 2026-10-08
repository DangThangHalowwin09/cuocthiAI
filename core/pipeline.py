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
import re
import unicodedata

from . import model_clients as mc
from . import prompts as pr
from . import law_lookup
from .config import GEMINI_STEP_MODELS, MAX_TOKENS_LONG


def _step_kwargs(step: str, provider: str) -> dict:
    model = GEMINI_STEP_MODELS.get(step) if provider == "gemini" else None
    return {"model": model} if model else {}


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


def split_internal_check(text: str) -> tuple[str, str | None]:
    """Tách phụ lục kiểm tra khỏi thân văn bản để đặt sau phần ký tên."""
    marker_index = text.find(_INTERNAL_CHECK_MARKER)
    if marker_index < 0:
        return text, None

    end_index = text.find(_INTERNAL_CHECK_END_MARKER, marker_index)
    if end_index < 0:
        return text[:marker_index].rstrip(), text[marker_index:].strip()

    appendix_end = end_index + len(_INTERNAL_CHECK_END_MARKER)
    document = (text[:marker_index] + text[appendix_end:]).strip()
    appendix = text[marker_index:appendix_end].strip()
    return document, appendix


def _normalize_legal_terms(text: str) -> str:
    patterns = (
        r"phòng\s+thi\s+hành\s+án(?:\s+dân\s+sự)?(?:\s+khu\s+vực\s*\d+)?(?:\s*[–-]\s*[^,;.\n]+)?",
        r"thi\s+hành\s+án\s+khu\s+vực\s*\d+(?:\s*[–-]\s*[^,;.\n]+)?",
    )
    normalized = text
    for pattern in patterns:
        normalized = re.sub(
            pattern,
            "Cơ quan Thi hành án dân sự có thẩm quyền",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


_AI_SUGGESTION_PATTERN = re.compile(
    r"\[(?:GỢI Ý PHÁP LÝ\s*-\s*KSV XÁC NHẬN|GỢI Ý CỦA AI,?\s*KSV CẦN XÁC NHẬN LẠI):\s*([^\]]+)\]",
    flags=re.IGNORECASE,
)


def _preserve_ai_suggestions(document: str, draft: str) -> str:
    suggestions = _AI_SUGGESTION_PATTERN.findall(draft)
    if not suggestions:
        return document

    normalized_suggestions = [
        f"[GỢI Ý CỦA AI, KSV CẦN XÁC NHẬN LẠI: {suggestion.strip()}]"
        for suggestion in suggestions
    ]
    missing = [suggestion for suggestion in normalized_suggestions if suggestion not in document]
    if not missing:
        return document

    block = "\n".join(missing)
    decision_match = re.search(r"(?m)^\s*QUYẾT ĐỊNH\s*$", document)
    if decision_match:
        position = decision_match.start()
        return f"{document[:position].rstrip()}\n\n{block}\n\n{document[position:]}".strip()
    return f"{document.rstrip()}\n\n{block}".strip()


def classify_case(input_text: str, provider: str = "gemini") -> str:
    raw = mc.call_model(
        provider, pr.SYSTEM_BASE, pr.CLASSIFY_PROMPT.format(input_text=input_text),
        **_step_kwargs("classify", provider),
    )
    raw_upper = raw.strip().upper()
    if "HINH_SU" in raw_upper or "HÌNH SỰ" in raw_upper:
        return "HINH_SU"
    return "DAN_SU_HANH_CHINH"


def _clean_json_text(raw: str) -> str:
    """Bỏ rào ```json và chữ thừa quanh JSON; nếu không parse được thì trả nguyên văn."""
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.dumps(json.loads(candidate), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return candidate
    return text


def extract_facts(input_text: str, case_type: str, provider: str = "gemini") -> str:
    template = pr.EXTRACT_PROMPT_HS if case_type == "HINH_SU" else pr.EXTRACT_PROMPT_DS
    raw = mc.call_model(
        provider, pr.SYSTEM_BASE, template.format(input_text=input_text),
        max_tokens=MAX_TOKENS_LONG, **_step_kwargs("extract", provider),
    )
    return _clean_json_text(raw)


def _fold(text: str) -> str:
    """Bỏ dấu + chữ thường để so khớp tên (OCR hay lẫn 'Thủy'/'Thuỷ')."""
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", stripped.replace("đ", "d").replace("Đ", "D")).strip().lower()


_NARRATIVE_PLACEHOLDER = "[[DIEN_BIEN_VU_AN]]"
_HO_SO_LINE = "- Hồ sơ vụ án gồm: … tập, bằng … tờ; đánh số thứ tự từ 01 đến hết."

# Các mục có thể là tiêu đề của phần KHÁC trong đề thi — dùng để cắt phần diễn biến.
_NARRATIVE_START = re.compile(
    r"(?im)^\W*(?:\d+\.\s*)?(?:Diễn\s*biến(?:\s*(?:của\s*)?(?:vụ\s*án|hành\s*vi[^\n:]*))?|Nội\s*dung\s*vụ\s*án|Tình\s*huống)\s*:?[^\n]*\n"
)
_NARRATIVE_END = re.compile(
    r"(?im)^\W*(?:\d+\.\s*)?(?:Tình\s*tiết\s*(?:tăng|giảm)|Phân\s*tích|Vật\s*chứng|Việc\s*thu\s*giữ|"
    r"Phần\s*dân\s*sự|Trách\s*nhiệm\s*dân\s*sự|Kết\s*luận(?!\s*giám)|Lý\s*lịch|Nhân\s*thân|"
    r"Bị\s*can\s*:|Họ\s*tên\s*:|Căn\s*cứ\s*(?:vào|các))"
)


def extract_case_narrative(input_text: str) -> str:
    """Lấy NGUYÊN VĂN phần diễn biến vụ án từ đề thi bằng quy tắc (không qua
    mô hình) để không bị mô hình nhỏ rút gọn. Trả '' nếu không nhận ra mục."""
    start = _NARRATIVE_START.search(input_text or "")
    if not start:
        return ""
    rest = input_text[start.end():]
    end = _NARRATIVE_END.search(rest)
    narrative = (rest[: end.start()] if end else rest).strip()
    return narrative if len(narrative) >= 200 else ""


def apply_default_values(facts_json: str, input_text: str = "") -> str:
    """Điền giá trị mặc định theo quy ước của Viện kiểm sát:
    - nhân thân / tiền án / tiền sự / biện pháp ngăn chặn không có dữ liệu → "Không";
    - hồ sơ không nêu số tập, số tờ → để "…" cho Kiểm sát viên điền tay;
    - diễn biến vụ án: ưu tiên bản chép nguyên văn bằng quy tắc từ đề thi,
      nếu không nhận ra thì dùng bản mô hình trích xuất, cuối cùng ghép từ hành vi từng bị can.
    Nhân thân (bản án, xử phạt hành chính) KHÔNG bị đổi thành tiền án/tiền sự."""
    try:
        facts = json.loads(facts_json)
        if not isinstance(facts, dict):
            return facts_json
    except json.JSONDecodeError:
        return facts_json

    for suspect in facts.get("bi_can") or []:
        if not isinstance(suspect, dict):
            continue
        for key in ("nhan_than", "tien_an", "tien_su", "bien_phap_ngan_chan"):
            value = suspect.get(key)
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            if not _is_filled(value):
                suspect[key] = "Không"

    ho_so = facts.get("ho_so") if isinstance(facts.get("ho_so"), dict) else {}
    for key in ("so_tap", "so_to"):
        if not _is_filled(ho_so.get(key)):
            ho_so[key] = "…"
    facts["ho_so"] = ho_so

    narrative = extract_case_narrative(input_text)
    if not narrative:
        narrative = str(facts.get("dien_bien_vu_an_nguyen_van") or "").strip()
    if not _is_filled(narrative):
        parts = [str(facts.get("hanh_vi_pham_toi_tom_tat") or "")]
        for item in facts.get("hanh_vi_tung_bi_can") or []:
            if isinstance(item, dict):
                parts.append(f"{item.get('bi_can', '')}: {item.get('hanh_vi_cu_the', '')}")
        narrative = "\n".join(x for x in parts if _is_filled(x))
    facts["dien_bien_vu_an_nguyen_van"] = narrative
    return json.dumps(facts, ensure_ascii=False, indent=2)


def insert_narrative(document: str, facts_json: str) -> str:
    """Thay dấu [[DIEN_BIEN_VU_AN]] bằng diễn biến vụ án đầy đủ. Nếu mô hình
    làm mất dấu thì chèn ngay sau dòng 'Trên cơ sở kết quả điều tra...'."""
    try:
        narrative = str(json.loads(facts_json).get("dien_bien_vu_an_nguyen_van") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        narrative = ""
    if not narrative:
        return document.replace(_NARRATIVE_PLACEHOLDER, "").strip()
    narrative = "\n".join(line.strip() for line in narrative.splitlines() if line.strip())
    if _NARRATIVE_PLACEHOLDER in document:
        return document.replace(_NARRATIVE_PLACEHOLDER, narrative)
    lead = re.search(r"(?im)^.*Trên cơ sở kết quả điều tra[^\n]*\n?", document)
    if lead:
        return f"{document[:lead.end()].rstrip()}\n{narrative}\n{document[lead.end():].lstrip()}"
    return document


_MISSING_TAG = r"\[THIẾU DỮ LIỆU[^\]]*\]"


def apply_default_text_rules(document: str) -> str:
    """Lưới an toàn sau cùng, không phụ thuộc mô hình có tuân thủ prompt hay không."""
    document = re.sub(
        rf"(?im)^(\s*-?\s*(?:Nhân thân|Tiền án, tiền sự|Biện pháp ngăn chặn[^:\n]*)\s*:\s*){_MISSING_TAG}\s*$",
        r"\1Không", document,
    )
    document = re.sub(rf"(?i)(Tiền án\s*:\s*){_MISSING_TAG}", r"\1Không", document)
    document = re.sub(rf"(?i)(Tiền sự\s*:\s*){_MISSING_TAG}", r"\1Không", document)
    document = re.sub(r"(?im)^\s*-?\s*Hồ sơ vụ án gồm[^\n]*$", _HO_SO_LINE, document)
    return document


_BODY_END_PATTERN = re.compile(
    r"(?im)^\W*Danh sách những người Viện kiểm sát đề nghị Tòa án triệu tập[^\n]*\n?"
)


def trim_to_body(text: str) -> str:
    """Chỉ giữ phần từ 'Căn cứ...' đến hết mục QUYẾT ĐỊNH. Mô hình đôi khi vẫn
    chèn lại quốc hiệu/tên cơ quan ở đầu và Nơi nhận/chữ ký ở cuối, trong khi
    template mẫu 156 đã có sẵn các phần đó."""
    document, appendix = split_internal_check(text)
    start = re.search(r"(?m)^\s*Căn cứ", document)
    if start:
        document = document[start.start():]
    end = None
    for end in _BODY_END_PATTERN.finditer(document):
        pass
    if end is not None:
        document = document[: end.end()]
    document = document.strip()
    return f"{document}\n\n{appendix}".strip() if appendix else document


def _is_filled(value) -> bool:
    text = str(value or "").strip()
    return bool(text) and "THIẾU DỮ LIỆU" not in text.upper()


def build_header_info(facts_json: str) -> dict | None:
    """Dựng phần đầu Cáo trạng (tên cơ quan, số ký hiệu, địa danh, dòng
    'VIỆN TRƯỞNG VIỆN KIỂM SÁT ...') từ trường vks_truy_to đã trích xuất.
    Trả None nếu chưa xác định được thẩm quyền (khi đó giữ nguyên chỗ trống
    trong mẫu để Kiểm sát viên tự điền)."""
    try:
        vks = json.loads(facts_json).get("vks_truy_to") or {}
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(vks, dict):
        return None

    ten_day_du = str(vks.get("ten_day_du") or "")
    cap = str(vks.get("cap") or "").lower()
    so_kv = str(vks.get("so_khu_vuc") or "").strip()
    tinh = str(vks.get("tinh_thanh") or "").strip()

    if not _is_filled(ten_day_du) and not _is_filled(tinh):
        return None
    if not so_kv:
        match = re.search(r"khu\s*vực\s*(\d+)", ten_day_du, flags=re.IGNORECASE)
        so_kv = match.group(1) if match else ""
    if not _is_filled(tinh):
        match = re.search(r"(?:tỉnh|thành phố)\s+(.+)$", ten_day_du, flags=re.IGNORECASE)
        tinh = match.group(1).strip() if match else ""
    if not tinh:
        return None
    if "khu vực" not in cap and "tỉnh" not in cap:
        cap = "khu vực" if (so_kv or "khu vực" in ten_day_du.lower()) else "tỉnh"

    tinh_hoa = tinh.upper()
    if "khu vực" in cap:
        unit_name = f"VIỆN KIỂM SÁT NHÂN DÂN KHU VỰC {so_kv} - {tinh_hoa}".replace("  ", " ")
        unit_parent = f"VIỆN KIỂM SÁT NHÂN DÂN TỈNH {tinh_hoa}"
        so_ky_hieu = f"Số: …/CT-VKSKV{so_kv}-…" if so_kv else "Số: …/CT-VKS…-…"
    else:
        unit_name = f"VIỆN KIỂM SÁT NHÂN DÂN TỈNH {tinh_hoa}"
        unit_parent = "VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO"
        so_ky_hieu = "Số: …/CT-VKS…-…"
    return {
        "unit_name": unit_name,
        "unit_parent": unit_parent,
        "so_ky_hieu": so_ky_hieu,
        "dia_danh": tinh,
        "vien_truong": f"VIỆN TRƯỞNG {unit_name}",
    }


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

    result = law_lookup.find_relevant_articles(
        query,
        top_n=max(top_n, 20) if case_type == "HINH_SU" else top_n,
    )
    if case_type == "HINH_SU":
        # Ghim ĐÚNG các điều BLHS mà hồ sơ đã nêu (tội danh trong quyết định khởi
        # tố / kết luận điều tra) + Điều 51, 52 (tình tiết giảm nhẹ/tăng nặng),
        # để bản thảo trích dẫn chính xác thay vì phụ thuộc điểm số từ khóa.
        try:
            cited = json.loads(facts_json).get("dieu_luat_blhs_duoc_nhac_toi") or []
        except (json.JSONDecodeError, AttributeError):
            cited = []
        if isinstance(cited, str):
            cited = re.findall(r"\d+[a-zđ]?", cited)
        cited = [re.sub(r"\D*(\d+[a-zđ]?).*", r"\1", str(c)) for c in cited]
        pinned = law_lookup.get_articles_by_numbers("blhs", [*cited, "51", "52"])
        pinned_keys = {(a["ma_luat"], str(a["dieu_so"])) for a in pinned}
        result["offline"] = pinned + [
            a for a in result["offline"]
            if (a["ma_luat"], str(a["dieu_so"])) not in pinned_keys
        ]
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
    return mc.call_model(
        provider, pr.SYSTEM_BASE, prompt, max_tokens=MAX_TOKENS_LONG,
        **_step_kwargs("draft", provider),
    )


def self_check(
    draft_text: str,
    facts_json: str,
    case_type: str,
    dieu_luat_lien_quan: str,
    provider: str = "gemini",
    ) -> tuple[str, str | None]:
    prompt = pr.SELF_CHECK_PROMPT.format(
        draft_text=draft_text,
        facts_json=facts_json,
        case_type=case_type,
        dieu_luat_lien_quan=dieu_luat_lien_quan,
    )
    checked_text = mc.call_model(
        provider, pr.SYSTEM_BASE, prompt, max_tokens=MAX_TOKENS_LONG,
        **_step_kwargs("self_check", provider),
    )
    document, appendix = split_internal_check(checked_text)
    document = _normalize_legal_terms(document)
    document = _preserve_ai_suggestions(document, draft_text)
    if case_type == "HINH_SU":
        document = trim_to_body(document)
        document = insert_narrative(document, facts_json)
        document = apply_default_text_rules(document)
    return document, appendix


def run_pipeline(
    input_text: str,
    provider: str = "gemini",
    case_type_override: str | None = None,
    progress_callback=None,
    input_note: str | None = None,
) -> dict:
    """
    progress_callback(step_name: str, content: str) được gọi sau MỖI bước,
    dùng để Streamlit hiển thị tiến trình theo thời gian thực.

    input_note: ghi chú của hệ thống đặt TRƯỚC nội dung hồ sơ khi đưa cho mô
    hình (ví dụ pr.OCR_INPUT_NOTE khi hồ sơ được đọc bằng OCR từ bản scan).
    """
    if input_note:
        input_text = f"{input_note}\n\n{input_text}"

    def notify(step_name, content):
        if progress_callback:
            progress_callback(step_name, content)

    case_type = case_type_override or classify_case(input_text, provider)
    notify("classify", case_type)

    facts = extract_facts(input_text, case_type, provider)
    if case_type == "HINH_SU":
        facts = apply_default_values(facts, input_text)
    notify("extract", facts)

    is_hc = case_type == "DAN_SU_HANH_CHINH" and _is_hanh_chinh(facts)

    dieu_luat_lien_quan = lookup_laws(facts, case_type)
    notify("lookup_laws", dieu_luat_lien_quan)

    draft = draft_document(facts, dieu_luat_lien_quan, case_type, provider)
    notify("draft", draft)

    final, internal_check = self_check(
        draft, facts, case_type, dieu_luat_lien_quan, provider
    )
    notify("self_check", final)

    return {
        "case_type": case_type,
        "is_hanh_chinh": is_hc,
        "header": build_header_info(facts) if case_type == "HINH_SU" else None,
        "facts": facts,
        "dieu_luat_lien_quan": dieu_luat_lien_quan,
        "draft": draft,
        "final": final,
        "internal_check": internal_check or "Chưa có báo cáo kiểm tra nội bộ.",
    }
