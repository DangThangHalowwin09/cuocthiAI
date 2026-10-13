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

import hashlib
import os
import random
import time
from pathlib import Path

from .config import (
    CACHE_DIR,
    DEFAULT_MODELS,
    FALLBACK_PROVIDERS,
    GEMINI_BACKUP_MODEL,
    GEMINI_CALL_BUDGET_SECONDS,
    GEMINI_MODEL_FALLBACKS,
    GEMINI_REQUEST_TIMEOUT_MS,
    GEMINI_RETRY_ROUNDS,
    LLM_CACHE_ENABLED,
    MAX_TOKENS_DEFAULT,
)


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

    # Có hạn chờ cho MỖI lần gọi: một lần treo không được làm cả buổi thi đứng.
    client = genai.Client(
        api_key=api_key, http_options=types.HttpOptions(timeout=GEMINI_REQUEST_TIMEOUT_MS)
    )
    primary = model or DEFAULT_MODELS["gemini"]
    # Chuỗi model: model chính, rồi các model khác. Khi một model quá tải (503/429),
    # CHUYỂN NGAY sang model khác (mỗi model có năng lực phục vụ riêng) thay vì chờ;
    # hết một vòng mà vẫn lỗi thì nghỉ (tăng dần) rồi lặp lại vòng mới.
    chain = [primary]
    for name in (GEMINI_BACKUP_MODEL, *GEMINI_MODEL_FALLBACKS):
        if name and name not in chain:
            chain.append(name)

    deadline = time.monotonic() + GEMINI_CALL_BUDGET_SECONDS
    last_error: Exception | None = None
    for round_index in range(GEMINI_RETRY_ROUNDS):
        for name in chain:
            if time.monotonic() > deadline:
                break
            try:
                response = client.models.generate_content(
                    model=name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=max_tokens,
                    ),
                )
                if response.text:
                    return response.text
                last_error = RuntimeError("Model trả về nội dung rỗng")
            except Exception as e:  # noqa: BLE001
                last_error = e
                if not _is_retryable(e):
                    raise ModelCallError(f"Lỗi gọi Gemini API: {e}") from e
        if round_index < GEMINI_RETRY_ROUNDS - 1 and time.monotonic() < deadline:
            time.sleep(min(4 * (2 ** round_index) + random.uniform(0, 2), 20))
    raise ModelCallError(
        f"Lỗi gọi Gemini API (đã thử {len(chain)} model, {GEMINI_RETRY_ROUNDS} vòng): {last_error}"
    ) from last_error


def _is_retryable(error: Exception) -> bool:
    """Lỗi quá tải / quota / model không tồn tại → đáng thử lại hoặc đổi model."""
    text = f"{type(error).__name__} {error}".lower()
    return any(
        marker in text
        for marker in ("503", "429", "404", "500", "unavailable", "overload",
                       "resource_exhausted", "quota", "not found", "deadline", "timeout")
    )


_PROVIDERS = {
    "claude": call_claude,
    "openai": call_openai,
    "gemini": call_gemini,
}


_KEY_ENV = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GOOGLE_API_KEY"}


def _cache_file(provider: str, system_prompt: str, user_prompt: str, kwargs: dict) -> Path:
    raw = "\x1f".join(
        (provider, str(kwargs.get("model") or ""), str(kwargs.get("max_tokens") or ""),
         system_prompt, user_prompt)
    )
    return CACHE_DIR / (hashlib.sha256(raw.encode("utf-8")).hexdigest() + ".txt")


def call_model(provider: str, system_prompt: str, user_prompt: str, **kwargs) -> str:
    """Điểm vào DUY NHẤT mà pipeline.py sử dụng để gọi bất kỳ model nào.

    - Bộ nhớ đệm trên đĩa: cùng một lời gọi (cùng model + prompt) trả kết quả đã có ngay.
      Nhờ đó nếu một bước giữa chừng lỗi, bấm chạy lại chỉ gọi lại các bước chưa xong.
    - Dự phòng chéo nhà cung cấp: Gemini lỗi hẳn thì thử Claude/OpenAI nếu có API key.
    """
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Provider '{provider}' không được hỗ trợ. Chọn một trong: {list(_PROVIDERS)}"
        )
    cache_file = _cache_file(provider, system_prompt, user_prompt, kwargs) if LLM_CACHE_ENABLED else None
    if cache_file is not None:
        try:
            if cache_file.is_file():
                return cache_file.read_text(encoding="utf-8")
        except OSError:
            pass

    try:
        result = _PROVIDERS[provider](system_prompt, user_prompt, **kwargs)
    except ModelCallError as primary_error:
        result = None
        for alternative in FALLBACK_PROVIDERS:
            if alternative == provider or not os.environ.get(_KEY_ENV[alternative]):
                continue
            alt_kwargs = {k: v for k, v in kwargs.items() if k != "model"}  # tên model riêng từng nhà
            try:
                result = _PROVIDERS[alternative](system_prompt, user_prompt, **alt_kwargs)
                break
            except ModelCallError:
                continue
        if result is None:
            raise primary_error

    if cache_file is not None and result:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(result, encoding="utf-8")
        except OSError:
            pass
    return result
