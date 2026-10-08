"""
Cấu hình chung cho hệ thống.
Chỉnh sửa tên model ở đây nếu nhà cung cấp cập nhật phiên bản mới.

Phạm vi hệ thống: Hình sự (Cáo trạng) + Dân sự/Hành chính (Phát biểu
của Kiểm sát viên tại phiên tòa sơ thẩm).
"""

DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
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
