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
from src.core.config import settings
from src.services.preprocess_prompts import (
    PREPROCESS_SYSTEM,
    get_department_regulation_extract_prompt,
    get_preprocess_prompt,
)


def _llm_json_error_message() -> str:
    if getattr(settings, "use_ollama_for_preprocess", True):
        model = getattr(settings, "ollama_preprocess_model", "qwen2.5:7b")
        return (
            f"LLM не вернул валидный JSON. Проверьте: Ollama запущен (ollama serve), "
            f"модель установлена (ollama pull {model}). Для быстрой обработки используйте модель 7B–8B; "
            f"при таймауте увеличьте OLLAMA_PREPROCESS_TIMEOUT в .env."
        )
    return (
        "LLM не вернул валидный JSON. Проверьте OPEN_WEBUI_URL и OPEN_WEBUI_API_KEY."
    )


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
            error=_llm_json_error_message(),
        )

    set_parsed_json(document_id, parsed)
    updated = get_document(document_id)
    return PreprocessResponse(
        document_id=document_id,
        preprocessed=True,
        parsed_json=parsed,
        parsed_json_path=updated.get("parsed_json_path") if updated else None,
    )


def run_department_regulation_extract(document_id: str) -> PreprocessResponse:
    """
    Извлечь из документа «Положение о департаменте» чеклист целей и задач через LLM.
    Не сохраняет результат в хранилище — только возвращает JSON для валидации пользователем.
    """
    doc = get_document(document_id)
    if not doc:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Документ не найден")

    if doc.get("document_type") != "department_goals_checklist":
        return PreprocessResponse(
            document_id=document_id,
            preprocessed=False,
            error="Обработка положений о департаменте доступна только для документов типа department_goals_checklist",
        )

    content = get_document_bytes(document_id)
    if not content:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Файл документа не найден в хранилище")

    path = get_document_path(document_id)
    path_name = path.name if path else doc.get("name") or "file"
    text = extract_text_from_bytes(content, path_name, None)
    if not text or len(text.strip()) < 10:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Не удалось извлечь текст из файла")

    prompt = get_department_regulation_extract_prompt()
    if not prompt:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Промпт для положения о департаменте не настроен")

    system = PREPROCESS_SYSTEM + "\n\n" + prompt
    # Ограничиваем объём текста для быстрой обработки (положение о департаменте обычно до 30–50 тыс. символов)
    parsed = preprocess_document_to_json(system, text, max_content_chars=50_000)
    if parsed is None:
        return PreprocessResponse(
            document_id=document_id,
            preprocessed=False,
            error=_llm_json_error_message(),
        )

    # Нормализуем структуру: goals и tasks — массивы с полями id, text, section, checked
    if "goals" not in parsed or not isinstance(parsed["goals"], list):
        parsed["goals"] = []
    if "tasks" not in parsed or not isinstance(parsed["tasks"], list):
        parsed["tasks"] = []
    for item in parsed["goals"] + parsed["tasks"]:
        if isinstance(item, dict):
            item.setdefault("checked", False)
            item.setdefault("section", "")
            item.setdefault("id", "")
            item.setdefault("text", "")

    return PreprocessResponse(
        document_id=document_id,
        preprocessed=False,
        parsed_json=parsed,
        parsed_json_path=None,
    )
