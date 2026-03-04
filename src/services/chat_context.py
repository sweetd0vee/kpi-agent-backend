"""
Получение текстового контента документов по id для чата и каскада.
"""
from __future__ import annotations

import json

from src.services.document_store import get_document, get_document_bytes
from src.services.extract_text import extract_text_from_bytes

_MAX_CHARS_PER_DOC = 35000


def _filename_for_extract(d: dict) -> str:
    name = (d.get("name") or "").strip() or "file"
    if "." in name:
        return name
    rel = (d.get("relative_path") or "").strip()
    if rel:
        return rel.split("/")[-1] if "/" in rel else rel
    return name


def get_document_text_content(document_id: str, max_chars: int = _MAX_CHARS_PER_DOC) -> str | None:
    """
    Вернуть текстовое представление документа: parsed_json (как JSON-строка) или извлечённый текст.
    """
    doc = get_document(document_id)
    if not doc:
        return None
    parsed = doc.get("parsed_json")
    if parsed is not None:
        raw = json.dumps(parsed, ensure_ascii=False, indent=2)
        return raw[:max_chars] + ("..." if len(raw) > max_chars else "")
    raw_content = get_document_bytes(document_id)
    if not raw_content:
        return None
    try:
        text = extract_text_from_bytes(
            raw_content,
            _filename_for_extract(doc),
            None,
        )
        if text and text.strip():
            return text[:max_chars] + ("\n\n[... обрезано ...]" if len(text) > max_chars else "")
    except Exception:
        pass
    return None


def get_documents_combined_text(
    document_ids: list[str],
    max_per_doc: int = _MAX_CHARS_PER_DOC,
    separator: str = "\n\n---\n\n",
) -> str:
    """Объединить контент нескольких документов в один текст."""
    parts = []
    for doc_id in document_ids:
        content = get_document_text_content(doc_id, max_chars=max_per_doc)
        if content:
            parts.append(content)
    return separator.join(parts) if parts else ""
