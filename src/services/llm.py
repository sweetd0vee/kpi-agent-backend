"""
Интеграция с LLM: Open Web UI API (OpenAI-совместимый), OpenAI или Ollama.
Используется в чате и для предобработки документов базы знаний.
"""
import json
import re
from typing import Any, Optional

from openai import OpenAI

from src.core.config import settings


def get_openai_client() -> Optional[OpenAI]:
    """Клиент для Open Web UI (OpenAI-совместимый) или OpenAI."""
    base = (settings.open_webui_url or "").strip().rstrip("/")
    key = (settings.open_webui_api_key or "").strip()
    if not key:
        return None
    # Open Web UI: base + /api/v1, api_key как Bearer
    if base:
        return OpenAI(base_url=f"{base}/api/v1", api_key=key)
    return OpenAI(api_key=key)


def get_ollama_client(timeout: Optional[float] = None) -> OpenAI:
    """Клиент для Ollama (OpenAI-совместимый API на /v1). API key не проверяется Ollama."""
    base = (settings.ollama_base_url or "http://localhost:11434").strip().rstrip("/")
    t = timeout if timeout is not None else getattr(settings, "ollama_preprocess_timeout", 180.0)
    return OpenAI(base_url=f"{base}/v1", api_key="ollama", timeout=t)


def chat_completion(
    messages: list[dict[str, str]],
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
) -> Optional[str]:
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


def _extract_json_from_text(raw: str) -> Optional[dict[str, Any]]:
    """
    Извлекает JSON-объект из текста ответа LLM (может быть обёрнут в ```json, с пояснениями до/после).
    """
    cleaned = raw.strip()
    # Убрать обёртку ```json ... ``` или ``` ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    # Найти первый { и извлечь объект по скобкам
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    end = -1
    in_string = False
    escape = False
    quote = None
    for i in range(start, len(cleaned)):
        c = cleaned[i]
        if escape:
            escape = False
            continue
        if in_string and c == "\\":
            escape = True
            continue
        if not in_string:
            if c in ('"', "'"):
                in_string = True
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        else:
            if c == quote:
                in_string = False
    if end == -1:
        end = len(cleaned)
    json_str = cleaned[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    # Fallback: одна строка с \n в строках может быть экранирована
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    return None


def preprocess_document_to_json(
    system_prompt: str,
    user_content: str,
    model: Optional[str] = None,
    max_content_chars: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """
    Передаёт текст документа в LLM с промптом на вывод JSON.
    При use_ollama_for_preprocess=True используется Ollama (модель из ollama_preprocess_model),
    иначе — Open Web UI / OpenAI. Возвращает распарсенный JSON или None.
    max_content_chars — лимит символов текста документа (по умолчанию 120000; для положения о департаменте лучше 50000).
    """
    limit = max_content_chars if max_content_chars is not None else 120000
    content = user_content[:limit]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]
    use_ollama = getattr(settings, "use_ollama_for_preprocess", True)
    ollama_model = getattr(settings, "ollama_preprocess_model", "qwen2.5:7b")
    if use_ollama:
        client = get_ollama_client()
        model = model or ollama_model
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
            )
            if resp.choices and len(resp.choices) > 0:
                msg = resp.choices[0].message
                raw = (msg.content or "").strip() if msg else ""
            else:
                raw = ""
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Ollama preprocess failed: %s", e)
            raw = ""
    else:
        raw = chat_completion(messages, model=model or "gpt-4o-mini", temperature=0.1) or ""
    if not raw:
        return None
    return _extract_json_from_text(raw)
