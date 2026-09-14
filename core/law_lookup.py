"""
Tra cứu điều luật liên quan trong dữ liệu đã tách sẵn (data/laws/*.json)
theo từ khóa — mặc định KHÔNG dùng AI, KHÔNG lên mạng (chế độ "offline").

Hỗ trợ 2 chế độ (cấu hình ở core/config.py, biến LAW_SEARCH_MODE):
  - "offline": CHỈ tra cứu trong dữ liệu luật đã nạp sẵn.
  - "hybrid" : tra cứu offline trước; nếu không tìm thấy điều nào đủ
               liên quan (điểm số quá thấp / rỗng), gọi thêm Gemini với
               công cụ Google Search để tìm bổ sung trên mạng. Kết quả
               tìm trên mạng sẽ được ĐÁNH DẤU RÕ nguồn khác với dữ liệu
               offline, để AI ở bước soạn thảo biết mà thận trọng hơn.
"""

import json
import re
import unicodedata
from pathlib import Path

from . import config as cfg

BASE_DIR = Path(__file__).resolve().parent.parent
LAWS_DIR = BASE_DIR / "data" / "laws"

_STOPWORDS = {
    "và", "hoặc", "của", "cho", "là", "các", "một", "những", "người",
    "khi", "để", "theo", "về", "trong", "có", "không", "bị", "đã",
    "này", "đó", "với", "từ", "được", "thì", "nào",
}


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").lower()


def _tokenize(text: str) -> set:
    text = _normalize(text)
    words = re.findall(r"[a-zà-ỹ0-9]+", text)
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


_all_laws_cache = None


def _load_all_laws() -> list:
    """Nạp TẤT CẢ file .json trong data/laws/ (mỗi file là 1 bộ luật đã
    tách sẵn), gộp thành 1 danh sách để tra cứu chung — không cần biết
    trước đề thi thuộc lĩnh vực nào, cứ để điểm số từ khóa tự quyết định
    điều nào liên quan nhất, bất kể thuộc bộ luật nào."""
    global _all_laws_cache
    if _all_laws_cache is None:
        _all_laws_cache = []
        json_files = sorted(LAWS_DIR.glob("*.json"))
        if not json_files:
            raise FileNotFoundError(
                f"Không tìm thấy file luật nào trong {LAWS_DIR}. Chạy trước: "
                f"python scripts/build_law_database.py"
            )
        for jf in json_files:
            with open(jf, encoding="utf-8") as f:
                _all_laws_cache.extend(json.load(f))
    return _all_laws_cache


def _score_articles(query_text: str, articles: list, top_n: int) -> list:
    query_tokens = _tokenize(query_text)
    if not query_tokens:
        return []

    scored = []
    for art in articles:
        haystack = art["tieu_de"] + " " + art["noi_dung"][:300]
        art_tokens = _tokenize(haystack)
        overlap = len(query_tokens & art_tokens)
        title_overlap = len(query_tokens & _tokenize(art["tieu_de"]))
        score = overlap + title_overlap * 3
        if score > 0:
            scored.append((score, art))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [art for _, art in scored[:top_n]]


def find_relevant_articles_offline(query_text: str, top_n: int = 10) -> list:
    """Tra cứu THUẦN CODE trong dữ liệu đã nạp sẵn — không AI, không mạng."""
    articles = _load_all_laws()
    return _score_articles(query_text, articles, top_n)


def _search_online_via_gemini(query_text: str, top_n: int = 5) -> str:
    """Chế độ hybrid: khi offline không tìm đủ, nhờ Gemini tự tra cứu
    Google Search để tìm điều luật liên quan. CHỈ dùng khi
    LAW_SEARCH_MODE = "hybrid". Kết quả trả về dạng text thô kèm cảnh
    báo rõ ràng đây là nguồn từ internet, chưa được kiểm chứng offline."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "[LỖI: chưa cài google-genai, không thể tra cứu online]"

    import os
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return "[LỖI: thiếu GOOGLE_API_KEY, không thể tra cứu online]"

    client = genai.Client(api_key=api_key)
    prompt = (
        f"Tìm các điều luật liên quan nhất tới nội dung sau, CHỈ trong "
        f"phạm vi Bộ luật Hình sự, Bộ luật Tố tụng hình sự, Bộ luật Dân "
        f"sự, Bộ luật Tố tụng dân sự, Luật Tố tụng hành chính của Việt "
        f"Nam (bản hiện hành, đã cập nhật sửa đổi mới nhất). Với mỗi "
        f"điều tìm được, trích dẫn NGUYÊN VĂN đầy đủ nội dung điều đó, "
        f"không tóm tắt, không diễn giải lại. Ghi rõ nguồn (link) đã "
        f"tham khảo. Trả về tối đa {top_n} điều liên quan nhất.\n\n"
        f"Nội dung cần tra cứu: {query_text}"
    )
    try:
        response = client.models.generate_content(
            model=cfg.DEFAULT_MODELS["gemini"],
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        return response.text
    except Exception as e:  # noqa: BLE001
        return f"[LỖI khi tra cứu online: {e}]"


def find_relevant_articles(query_text: str, top_n: int = 10) -> dict:
    """Điểm vào chính — trả về dict gồm kết quả offline (luôn có) và
    online (chỉ có nếu chế độ hybrid VÀ offline không tìm đủ)."""
    offline_results = find_relevant_articles_offline(query_text, top_n)

    result = {"offline": offline_results, "online_text": None}

    is_weak = (not offline_results) or (len(offline_results) < 2)
    if cfg.LAW_SEARCH_MODE == "hybrid" and is_weak:
        result["online_text"] = _search_online_via_gemini(query_text)

    return result


def format_articles_for_prompt(result: dict) -> str:
    """Định dạng kết quả tra cứu (offline + online nếu có) thành text
    để đưa vào prompt, có ghi rõ nguồn của từng phần."""
    parts = []

    offline = result.get("offline") or []
    if offline:
        parts.append(
            "### NGUỒN: DỮ LIỆU LUẬT ĐÃ NẠP SẴN (đáng tin cậy, đã tách "
            "từ văn bản chính thức)\n"
        )
        for art in offline:
            chuong = f" ({art['chuong']})" if art.get("chuong") else ""
            parts.append(
                f"[{art.get('luat', '')}] Điều {art['dieu_so']}{chuong}\n{art['noi_dung']}"
            )
    else:
        parts.append(
            "[KHÔNG TÌM THẤY ĐIỀU LUẬT LIÊN QUAN TRONG DỮ LIỆU CÓ SẴN]"
        )

    online_text = result.get("online_text")
    if online_text:
        parts.append(
            "\n### NGUỒN: TRA CỨU BỔ SUNG TRÊN INTERNET (CHƯA được kiểm "
            "chứng offline — CHỈ dùng nếu không có lựa chọn nào từ dữ "
            "liệu có sẵn ở trên, và PHẢI đánh dấu [CẦN KIỂM TRA LẠI ĐIỀU "
            "LUẬT] khi dùng nguồn này)\n"
        )
        parts.append(online_text)

    return "\n\n---\n\n".join(parts)
