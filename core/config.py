"""
Cấu hình chung cho hệ thống.
Chỉnh sửa tên model ở đây nếu nhà cung cấp cập nhật phiên bản mới.

Phạm vi hệ thống: Hình sự (Cáo trạng) + Dân sự/Hành chính (Phát biểu
của Kiểm sát viên tại phiên tòa sơ thẩm).
"""

DEFAULT_MODELS = {
    "claude": "claude-sonnet-5-5",
    "openai": "gpt-4o",
    "gemini": "gemini-3.5-flash-lite",
}

# Nếu model mặc định bị Google gỡ (404), thử lần lượt các tên còn lại.
GEMINI_MODEL_FALLBACKS = (
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
)

# ---------------------------------------------------------------------------
# CHẾ ĐỘ TRA CỨU LUẬT — đổi giá trị này để chuyển chế độ (KHÔNG hiển thị
# cho người dùng cuối chọn, chỉ đội kỹ thuật cấu hình trước khi deploy):
#
#   "offline" — CHỈ tra cứu trong dữ liệu luật đã nạp sẵn (data/laws/).
#               Nhanh, miễn phí, không phụ thuộc mạng lúc BTC chấm thi.
#               KHUYẾN NGHỊ dùng chế độ này cho buổi thi chính thức.
#
#   "hybrid"  — Tra cứu offline trước; nếu không tìm đủ điều liên quan,
#               tự động nhờ Gemini tra cứu thêm trên Google Search.
#               Tiện khi đề thi đụng tội danh/quan hệ pháp luật ngoài
#               phạm vi 8 bộ luật đã nạp — nhưng phụ thuộc mạng và độ
#               chính xác thấp hơn (cần tự kiểm tra kỹ hơn ở bước sau).
# ---------------------------------------------------------------------------
LAW_SEARCH_MODE = "offline"

MAX_TOKENS_DEFAULT = 4000

# Các bước trích xuất / soạn thảo / tự kiểm tra sinh văn bản dài (JSON lý lịch
# nhiều bị can, cả bản cáo trạng) — 4000 token sẽ làm văn bản bị cắt giữa chừng.
MAX_TOKENS_LONG = 16000


# Mô hình theo từng bước (chỉ áp dụng cho Gemini). Phân loại là việc dễ nên
# dùng bản lite cho rẻ/nhanh; trích xuất, soạn thảo và tự kiểm tra phải bám
# sát nhiều quy tắc cùng lúc trên văn bản dài — bản lite hay bỏ sót/rút gọn,
# nên dùng bản flash đầy đủ. Đặt cả hai bằng nhau nếu muốn dùng một model.
GEMINI_STEP_MODELS = {
    "classify": "gemini-3.5-flash-lite",
    "extract": "gemini-3.5-flash",
    "draft": "gemini-3.5-flash",
    "self_check": "gemini-3.5-flash",
}

# Model dự phòng: khi model chính báo quá tải (503/429), hết quota hoặc bị gỡ
# (404), hệ thống tự gọi lại bằng model này để không gián đoạn buổi thi.
GEMINI_BACKUP_MODEL = "gemini-3.5-flash-lite"

# ---------------------------------------------------------------------------
# ĐỘ BỀN KHI GỌI MODEL (quá tải / chậm lúc thi)
# ---------------------------------------------------------------------------
# Mỗi lần gọi Gemini: tối đa N vòng, mỗi vòng thử lần lượt các model trong chuỗi
# (model chính -> GEMINI_BACKUP_MODEL -> GEMINI_MODEL_FALLBACKS); nghỉ tăng dần giữa các vòng.
GEMINI_RETRY_ROUNDS = 3
GEMINI_REQUEST_TIMEOUT_MS = 90_000      # một lần gọi treo quá 90 giây thì bỏ, chuyển model khác
GEMINI_CALL_BUDGET_SECONDS = 240        # tổng thời gian tối đa cho MỘT lời gọi (kể cả thử lại)

# Nếu Gemini lỗi hẳn: tự gọi nhà cung cấp khác NẾU có API key tương ứng trong môi trường
# (ANTHROPIC_API_KEY / OPENAI_API_KEY). Không có key thì bỏ qua.
FALLBACK_PROVIDERS = ("claude", "openai")

# Bộ nhớ đệm kết quả gọi model trên đĩa (cùng prompt = trả ngay, không gọi lại).
LLM_CACHE_ENABLED = True
CACHE_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / ".cache" / "llm"

# Bước 5 "AI tự kiểm tra" là lượt gọi dài nhất (đọc lại cả bản thảo + dữ kiện + điều luật) và ít
# bắt được lỗi thật. True = giữ như cũ. False = bỏ lượt này, thay bằng kiểm tra bằng code
# (nhanh hơn ~1/4 thời gian, bớt một điểm có thể bị quá tải).
SELF_CHECK_WITH_AI = True
