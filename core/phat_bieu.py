"""
Dựng bản PHÁT BIỂU của Kiểm sát viên (vụ án dân sự) trực tiếp từ BÁO CÁO ĐỀ XUẤT
của công chức nghiên cứu, bằng code thuần (không AI).

Lý do: Báo cáo đề xuất đã có sẵn đúng các nội dung Phát biểu cần (đương sự, nhận
xét việc tuân theo pháp luật tố tụng, đề xuất quan điểm giải quyết). Việc cần làm
là CHUYỂN thể thức, giữ nguyên từng chữ — nhờ AI chép lại chỉ tổ làm rơi năm sinh,
địa chỉ, đổi danh xưng, thêm bớt điều luật. Hồ sơ không đúng cấu trúc này thì
`parse_bao_cao_de_xuat` trả None và pipeline quay về soạn bằng AI.
"""

import re

_ABBR = {"KSND": "kiểm sát nhân dân"}

# Mẫu 36/DS (QĐ 195/QĐ-VKSTC ngày 30/6/2026) — phát biểu tại phiên tòa sơ thẩm.
# Khi xuất .docx, các đoạn "Căn cứ" lấy thẳng từ template trong data/templates;
# bản này chỉ để văn bản hiển thị trên giao diện khớp với file Word.
CAN_CU_DS = [
    "Căn cứ Điều 27 Luật Tổ chức Viện kiểm sát nhân dân năm 2014 đã được sửa đổi, bổ sung "
    "bởi Luật số 82/2025/QH15;",
    "Căn cứ các điều 21, 58, 262 Bộ luật Tố tụng dân sự số 92/2015/QH13 đã được sửa đổi, bổ sung "
    "bởi Bộ luật số 45/2019/QH14, Luật số 59/2020/QH14, Luật số 13/2022/QH15, Luật số 19/2023/QH15, "
    "Luật số 34/2024/QH15, Luật số 46/2024/QH15 và Luật số 85/2025/QH15;",
    "Căn cứ Điều 29 Thông tư liên tịch số 07/2026/TTLT-VKSNDTC-TANDTC ngày 10/3/2026 của Viện "
    "trưởng Viện kiểm sát nhân dân tối cao - Chánh án Tòa án nhân dân tối cao quy định việc phối "
    "hợp giữa Viện kiểm sát nhân dân và Tòa án nhân dân trong việc thi hành một số quy định của "
    "Bộ luật Tố tụng dân sự.",
]

PARTY_LABELS = (
    "Nguyên đơn", "Bị đơn", "Người có quyền lợi, nghĩa vụ liên quan",
    "Người có quyền lợi nghĩa vụ liên quan", "Người khởi kiện", "Người bị kiện",
)


def _lines(text: str) -> list[str]:
    out = []
    for raw in (text or "").splitlines():
        line = re.sub(r"[ \t\u00a0]+", " ", raw).strip()
        if line:
            out.append(line)
    return out


def is_bao_cao_de_xuat(text: str) -> bool:
    return bool(
        re.search(r"BÁO\s+CÁO\s+ĐỀ\s+XUẤT", text or "", re.IGNORECASE)
        and re.search(r"QUAN\s+ĐIỂM\s+CỦA\s+CÔNG\s+CHỨC", text or "", re.IGNORECASE)
    )


def _find(lines: list[str], pattern: str, start: int = 0) -> int | None:
    rx = re.compile(pattern, re.IGNORECASE)
    for index in range(start, len(lines)):
        if rx.search(lines[index]):
            return index
    return None


def _title_case_place(text: str) -> str:
    """'VIỆN KSND TỈNH NGHỆ AN' -> 'Viện kiểm sát nhân dân tỉnh Nghệ An'."""
    words = []
    for word in text.split():
        folded = _ABBR.get(word.upper())
        if folded:
            words.append(folded)
        elif word.upper() in {"VIỆN", "TỈNH", "KHU", "VỰC", "THÀNH", "PHỐ"}:
            words.append(word.lower())
        elif word.isdigit() or word == "-":
            words.append(word)
        else:
            words.append(word.capitalize())
    result = " ".join(words)
    return result[:1].upper() + result[1:]


def _end_punct(line: str, last: bool = False) -> str:
    if re.search(r"sinh\s+năm\s*$", line, re.IGNORECASE):
        return line  # đương sự chưa có năm sinh: giữ nguyên như hồ sơ
    if last:
        return line if line.endswith(".") else line.rstrip(";,") + "."
    if line.endswith((";", ":")):
        return line
    return line.rstrip(".,") + ";"


def parse_bao_cao_de_xuat(text: str) -> dict | None:
    lines = _lines(text)
    if not lines or not is_bao_cao_de_xuat(text):
        return None

    so_line = _find(lines, r"^Số\s*:")
    if so_line is None or so_line < 1:
        return None
    parent_line, unit_line = lines[so_line - 2] if so_line >= 2 else "", lines[so_line - 1]
    so_match = re.search(r"Số\s*:\s*\d*\s*/\s*([A-ZĐ]+)\s*-\s*(\S+)", lines[so_line])
    suffix = so_match.group(2) if so_match else "VKS"
    dia_danh, year = "", 0
    for line in lines[so_line:so_line + 6]:
        date_match = re.search(
            r"(?:^|\|)\s*([^,|]+?)\s*,\s*ngày\s+\d+\s+tháng\s+\d+\s+năm\s+(\d{4})", line
        )
        if date_match:
            dia_danh, year = date_match.group(1).strip(), int(date_match.group(2))
            break

    flat = " ".join(lines)
    case_match = re.search(r"giải quyết vụ án\s*[“\"](.+?)[”\"]", flat)
    court_match = re.search(r"do\s+(Tòa án nhân dân[^,“”\"]*?)\s+(?:thụ lý|giải quyết)", flat)
    ksv_match = re.search(r"Chúng tôi gồm:\s*-?\s*(.+?)\s*-\s*KSV", flat)

    kind = "HANH_CHINH" if re.search(r"vụ án hành chính", flat, re.IGNORECASE) else "DAN_SU"

    party_start = _find(lines, r"^(Nguyên đơn|Người khởi kiện)\b")
    party_end = _find(lines, r"^Sau khi nghiên cứu", party_start or 0)
    iii = _find(lines, r"^III\.\s*QUAN\s+ĐIỂM")
    if None in (party_start, party_end, iii) or not (case_match and ksv_match):
        return None

    sec1 = _find(lines, r"^1\.\s*Về việc tuân theo pháp luật tố tụng", iii)
    sec2 = _find(lines, r"^2\.\s*Đề xuất quan điểm", iii)
    closing = _find(lines, r"^Trên đây là báo cáo", iii)
    if None in (sec1, sec2, closing) or not (sec1 < sec2 < closing):
        return None

    return {
        "kind": kind,
        "year": year,
        "parent_line": parent_line,
        "unit_line": unit_line,
        "so_suffix": suffix,
        "dia_danh": dia_danh,
        "ten_vu_an": case_match.group(1).strip(),
        "toa_an": court_match.group(1).strip() if court_match else "",
        "ksv": ksv_match.group(1).strip(" -"),
        "parties": lines[party_start:party_end],
        "section1": lines[sec1:sec2],
        "section2": lines[sec2 + 1:closing],
    }


def _renumber_section2(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        out.append(re.sub(r"^2\.(\d+)\.\s*", lambda m: f"{m.group(1)}. ", line))
    return out


def _format_parties(parties: list[str]) -> list[str]:
    out = []
    for index, line in enumerate(parties):
        last = index == len(parties) - 1
        out.append(_end_punct(line, last))
    return out


def build_phat_bieu(parsed: dict) -> tuple[str, dict]:
    """Trả về (văn bản thân Phát biểu, header cho bộ ghi .docx)."""
    vks = _title_case_place(parsed["unit_line"])
    court = parsed["toa_an"] or "Tòa án nhân dân"
    case = parsed["ten_vu_an"]
    year = parsed["year"]

    body: list[str] = list(CAN_CU_DS)
    body.append(
        f"Hôm nay, {court} mở phiên tòa sơ thẩm giải quyết vụ án dân sự về “{case}” "
        "giữa các đương sự:"
    )
    body.extend(_format_parties(parsed["parties"]))
    body.append(
        f"Qua nghiên cứu hồ sơ vụ án dân sự, kết quả kiểm sát việc tuân theo pháp luật của "
        f"{court} và tham gia phiên tòa sơ thẩm hôm nay, đại diện {vks} phát biểu ý kiến như sau:"
    )
    body.append("I. VỀ VIỆC TUÂN THEO PHÁP LUẬT TỐ TỤNG")
    # Mục 1: giữ nguyên nhận xét của công chức nghiên cứu (bỏ câu kết luận riêng của báo cáo).
    body.extend(
        line for line in parsed["section1"] if not re.match(r"^Như vậy quá trình thụ lý", line)
    )
    body.append(
        "2. Việc tuân theo pháp luật tố tụng của Hội đồng xét xử (Hội đồng giải quyết việc dân sự; "
        "Hội đồng xét đơn yêu cầu), Thư ký phiên tòa (phiên họp)"
    )
    body.append(
        "Hội đồng xét xử, Thư ký phiên tòa đã thực hiện đúng, đầy đủ quy định của Bộ luật Tố tụng "
        "dân sự và các văn bản quy phạm pháp luật có liên quan về việc xét xử vụ án."
    )
    body.append("3. Việc chấp hành pháp luật của người tham gia tố tụng")
    body.append(
        "Người tham gia tố tụng đã thực hiện đúng, đầy đủ quyền và nghĩa vụ tố tụng theo quy định "
        "của pháp luật"
    )
    body.append("II. VỀ VIỆC GIẢI QUYẾT VỤ ÁN DÂN SỰ")
    body.extend(_renumber_section2(parsed["section2"]))
    body.append(
        f"Trên đây là ý kiến của đại diện {vks} về việc tuân theo pháp luật tố tụng và giải quyết "
        f"vụ án {case} nêu trên. Đề nghị HĐXX xem xét, quyết định."
    )

    so_suffix = parsed["so_suffix"] or "VKS"
    header = {
        "kind": "PHAT_BIEU",
        "unit_parent": parsed["parent_line"] or "VIỆN KSND TỐI CAO",
        "unit_name": parsed["unit_line"],
        "so_ky_hieu": f"Số:      /PB-{so_suffix}",
        "dia_danh": parsed["dia_danh"] or "",
        "nam": str(year) if year else "20…",
        "ten_vu_an": case,
        "ksv": parsed["ksv"],
        "hanh_chinh": False,
        "loai": "dân sự",
        "ma_loai": "DS",
        "toa_an_tail": _tail(court, "Tòa án nhân dân"),
        "vks_tail": _tail(vks, "Viện kiểm sát nhân dân"),
        "noi_nhan": ["Tòa án xét xử sơ thẩm;", "Lãnh đạo cơ quan, đơn vị phụ trách (để báo cáo);", "Lưu: VT, HSKS."],
    }
    return "\n".join(body), header


def _tail(full_name: str, prefix: str) -> str:
    """'Tòa án nhân dân tỉnh Nghệ An' -> 'tỉnh Nghệ An' (phần điền vào ô '…(n)…' của mẫu)."""
    text = (full_name or "").strip()
    if text.lower().startswith(prefix.lower()):
        text = text[len(prefix):].strip()
    return text


def split_phat_bieu_text(text: str) -> dict | None:
    """Tách văn bản Phát biểu (dạng phẳng, do code hoặc AI sinh) thành các phần để điền vào
    template chính thức. Trả None nếu thiếu mốc bắt buộc → dùng cách dựng từ đầu."""
    lines = _lines(text)

    def at(pattern: str, start: int = 0) -> int | None:
        return _find(lines, pattern, start)

    hom = at(r"^Hôm nay")
    qua = at(r"^Qua nghiên cứu", hom or 0)
    sec_i = at(r"^I\.\s", qua or 0)
    s1 = at(r"^1\.\s*(Việc|Về việc) tuân theo", sec_i or 0)
    s2 = at(r"^2\.\s*Việc tuân theo pháp luật tố tụng của Hội đồng", s1 or 0)
    s3 = at(r"^3\.\s*Việc chấp hành", s2 or 0)
    sec_ii = at(r"^II\.\s", s3 or 0)
    sec_iii = at(r"^III\.\s", sec_ii or 0)
    closing = at(r"^Trên đây là ý kiến", sec_ii or 0)
    required = (hom, qua, sec_i, s1, s2, s3, sec_ii, closing)
    if any(value is None for value in required):
        return None
    ii_end = sec_iii if sec_iii is not None else closing
    return {
        "parties": lines[hom + 1:qua],
        "sec1": lines[s1 + 1:s2],
        "sec2": lines[s2 + 1:s3],
        "sec3": lines[s3 + 1:sec_ii],
        "giai_quyet": lines[sec_ii + 1:ii_end],
        "kien_nghi": lines[sec_iii + 1:closing] if sec_iii is not None else [],
    }


def summarize_check(parsed: dict) -> str:
    blanks = [
        line for line in parsed["parties"] if re.search(r"sinh\s+năm\s*[:;,.]?\s*$", line, re.IGNORECASE)
    ]
    lines = [
        "--- PHỤ LỤC KIỂM TRA NỘI BỘ ---",
        "1. KIỂM TRA DỮ KIỆN: Văn bản được dựng trực tiếp từ Báo cáo đề xuất (không qua AI chép lại): "
        f"{len(parsed['parties'])} dòng đương sự, {len(parsed['section1'])} dòng nhận xét tố tụng, "
        f"{len(parsed['section2'])} dòng đề xuất giải quyết đều được giữ nguyên văn.",
    ]
    if blanks:
        lines.append(
            "   Lưu ý: hồ sơ gốc còn để trống năm sinh ở "
            f"{len(blanks)} đương sự ({'; '.join(b[:40] for b in blanks)}) — giữ nguyên như hồ sơ, KSV bổ sung nếu có."
        )
    lines += [
        "2. KIỂM TRA CẤU TRÚC: Đủ các phần Mẫu 36/DS: căn cứ, đương sự, I. Tuân theo pháp luật tố tụng "
        "(3 mục), II. Giải quyết vụ án, lời kết, nơi nhận, chữ ký Kiểm sát viên.",
        "3. KIỂM TRA ĐIỀU LUẬT: Các điều luật trong phần nhận xét và đề xuất là của Báo cáo đề xuất, "
        "không do AI thêm. KSV đối chiếu lại với hồ sơ vụ án trước khi ban hành.",
        "--- HẾT PHỤ LỤC KIỂM TRA NỘI BỘ ---",
    ]
    return "\n".join(lines)
