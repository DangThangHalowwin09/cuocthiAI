"""
Lớp trừu tượng hóa việc gọi các mô hình AI khác nhau (Claude / OpenAI / Gemini)
qua CÙNG MỘT hàm call_model(). Nhờ vậy, muốn đổi model nền chỉ cần đổi
tham số `provider`, không cần sửa logic pipeline ở nơi khác.

Yêu cầu cài đặt (xem requirements.txt):
    pip install anthropic openai google-generativeai

API key được đọc từ biến môi trường:
    ANTHROPIC_API_KEY  - cho Claude
    OPENAI_API_KEY     - cho GPT (OpenAI)
    GOOGLE_API_KEY     - cho Gemini
"""

import os
from .config import DEFAULT_MODELS, MAX_TOKENS_DEFAULT


class ModelCallError(RuntimeError):
    """Lỗi khi gọi mô hình AI (thiếu key, hết quota, lỗi mạng, v.v.)"""


def call_claude(system_prompt: str, user_prompt: str, model: str = None,
                 max_tokens: int = MAX_TOKENS_DEFAULT) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise ModelCallError(
            "Chưa cài thư viện 'anthropic'. Chạy: pip install anthropic"
        ) from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ModelCallError("Thiếu ANTHROPIC_API_KEY trong biến môi trường.")

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model or DEFAULT_MODELS["claude"],
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:  # noqa: BLE001 - muốn bắt mọi lỗi API để báo rõ cho người dùng
        raise ModelCallError(f"Lỗi gọi Claude API: {e}") from e

    return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")


def call_openai(system_prompt: str, user_prompt: str, model: str = None,
                 max_tokens: int = MAX_TOKENS_DEFAULT) -> str:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ModelCallError(
            "Chưa cài thư viện 'openai'. Chạy: pip install openai"
        ) from e

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ModelCallError("Thiếu OPENAI_API_KEY trong biến môi trường.")

    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=model or DEFAULT_MODELS["openai"],
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:  # noqa: BLE001
        raise ModelCallError(f"Lỗi gọi OpenAI API: {e}") from e

    return resp.choices[0].message.content


def call_gemini(system_prompt: str, user_prompt: str, model: str = None,
                 max_tokens: int = MAX_TOKENS_DEFAULT) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise ModelCallError(
            "Chưa cài thư viện 'google-genai'. Chạy: pip install -U google-genai"
        ) from e

    api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise ModelCallError("Thiếu GOOGLE_API_KEY trong biến môi trường.")
    if api_key in {"PASTE_YOUR_KEY_HERE", "dán_key_vào_đây"} or not api_key.isascii():
        raise ModelCallError(
            "GOOGLE_API_KEY chưa phải key thật. Mở file .env, dán key từ "
            "Google AI Studio (thường bắt đầu bằng AIza), lưu file, rồi chạy lại."
        )

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model or DEFAULT_MODELS["gemini"],
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
            ),
        )
    except Exception as e:  # noqa: BLE001
        raise ModelCallError(f"Lỗi gọi Gemini API: {e}") from e

    return response.text


_PROVIDERS = {
    "claude": call_claude,
    "openai": call_openai,
    "gemini": call_gemini,
}


def call_model(provider: str, system_prompt: str, user_prompt: str, **kwargs) -> str:
    """Điểm vào DUY NHẤT mà pipeline.py sử dụng để gọi bất kỳ model nào."""
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Provider '{provider}' không được hỗ trợ. Chọn một trong: {list(_PROVIDERS)}"
        )
    return _PROVIDERS[provider](system_prompt, user_prompt, **kwargs)
