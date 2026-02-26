"""
Интеграция с LLM: Open Web UI API (OpenAI-совместимый) или прямой OpenAI.
Используется в чате и для предобработки документов базы знаний.
"""
import json
import re
from typing import Any

from openai import OpenAI

from src.core.config import settings


def get_openai_client() -> OpenAI | None:
    """Клиент для Open Web UI (OpenAI-совместимый) или OpenAI."""
    base = (settings.open_webui_url or "").strip().rstrip("/")
    key = (settings.open_webui_api_key or "").strip()
    if not key:
        return None
    # Open Web UI: base + /api/v1, api_key как Bearer
    if base:
        return OpenAI(base_url=f"{base}/api/v1", api_key=key)
    return OpenAI(api_key=key)


def chat_completion(
    messages: list[dict[str, str]],
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
) -> str | None:
    """
    Один запрос к LLM. Возвращает текст ответа или None при ошибке.
    """
    client = get_openai_client()
    if not client:
        return None
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        if resp.choices and len(resp.choices) > 0:
            msg = resp.choices[0].message
            return (msg.content or "").strip() if msg else None
    except Exception:
        pass
    return None


def preprocess_document_to_json(system_prompt: str, user_content: str, model: str = "gpt-4o-mini") -> dict[str, Any] | None:
    """
    Передаёт текст документа в LLM с промптом на вывод JSON.
    Возвращает распарсенный JSON или None.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content[:120000]},  # лимит контекста
    ]
    raw = chat_completion(messages, model=model, temperature=0.1)
    if not raw:
        return None
    # Убрать обёртку ```json ... ```
    cleaned = raw.strip()
    for pattern in (r"^```(?:json)?\s*", r"\s*```\s*$"):
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Попробовать вытащить первый JSON-объект из ответа
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None
