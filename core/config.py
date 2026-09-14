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
