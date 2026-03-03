"""
Общая логика предобработки документа (извлечение текста + LLM → JSON).
Используется в API одного документа и при массовой генерации JSON для коллекции.
"""
from src.models.documents import PreprocessResponse
from src.models.knowledge import DocumentType
from src.services.document_store import (
    get_document,
    get_document_bytes,
    get_document_path,
    set_parsed_json,
)
from src.services.extract_text import extract_text_from_bytes
from src.services.llm import preprocess_document_to_json
from src.services.preprocess_prompts import PREPROCESS_SYSTEM, get_preprocess_prompt


def run_preprocess(document_id: str) -> PreprocessResponse:
    """
    Предобработать документ: извлечь текст, преобразовать в JSON по типу документа.
    Возвращает PreprocessResponse (успех/ошибка, parsed_json при успехе).
    """
    doc = get_document(document_id)
    if not doc:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Документ не найден")

    content = get_document_bytes(document_id)
    if not content:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Файл документа не найден в хранилище")

    doc_type_str = doc.get("document_type", "")
    try:
        dt = DocumentType(doc_type_str)
    except ValueError:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error=f"Неизвестный тип: {doc_type_str}")

    path = get_document_path(document_id)
    path_name = path.name if path else doc.get("name") or "file"
    text = extract_text_from_bytes(content, path_name, None)
    if not text or len(text.strip()) < 10:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Не удалось извлечь текст из файла")

    system = PREPROCESS_SYSTEM + "\n\n" + get_preprocess_prompt(dt)
    parsed = preprocess_document_to_json(system, text)
    if parsed is None:
        return PreprocessResponse(
            document_id=document_id,
            preprocessed=False,
            error="LLM не вернул валидный JSON. Проверьте OPEN_WEBUI_URL и OPEN_WEBUI_API_KEY.",
        )

    set_parsed_json(document_id, parsed)
    updated = get_document(document_id)
    return PreprocessResponse(
        document_id=document_id,
        preprocessed=True,
        parsed_json=parsed,
        parsed_json_path=updated.get("parsed_json_path") if updated else None,
    )
