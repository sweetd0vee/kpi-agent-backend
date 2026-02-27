"""
Загрузка и список документов базы знаний по типам.
Предобработка (LLM) для преобразования в JSON.
Форматы: PDF, DOCX, XLSX, TXT.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from src.models.documents import DocumentList, DocumentMeta, PreprocessResponse
from src.models.knowledge import DocumentType
from src.services.document_store import (
    add_document,
    delete_document as store_delete,
    generate_document_id,
    get_document,
    get_document_path,
    get_storage_path_for_upload,
    list_documents as store_list,
    set_parsed_json,
)
from src.services.extract_text import extract_text_from_bytes
from src.services.llm import preprocess_document_to_json
from src.services.preprocess_prompts import PREPROCESS_SYSTEM, get_preprocess_prompt

router = APIRouter()


def _doc_to_meta(d: dict, include_json: bool = False) -> DocumentMeta:
    return DocumentMeta(
        id=d["id"],
        name=d["name"],
        document_type=d["document_type"],
        collection_id=d.get("collection_id"),
        size=None,
        content_type=None,
        uploaded_at=d.get("uploaded_at"),
        preprocessed=d.get("preprocessed", False),
        parsed_json=d.get("parsed_json") if include_json else None,
    )


def _get_upload_root():
    from src.services.document_store import get_upload_root
    return get_upload_root()


@router.post("/upload", response_model=DocumentMeta)
async def upload_document(
    document_type: str = Query(..., description="Тип документа: chairman_goals, strategy_checklist, ..."),
    collection_id: Optional[str] = Query(None, description="ID коллекции, в которую добавить документ"),
    file: UploadFile = File(...),
):
    """Загрузить документ заданного типа, опционально в коллекцию."""
    try:
        dt = DocumentType(document_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип документа: {document_type}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")

    doc_id = generate_document_id()
    filename = file.filename or "file"
    path = get_storage_path_for_upload(dt.value, doc_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    root = _get_upload_root()
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(dt.value) / path.name
    uploaded_at = datetime.now(timezone.utc).isoformat()
    add_document(doc_id, filename, dt.value, str(relative), uploaded_at=uploaded_at, collection_id=collection_id)

    doc = get_document(doc_id)
    return _doc_to_meta(doc)


@router.get("/", response_model=DocumentList)
async def list_documents(
    document_type: Optional[str] = Query(None, description="Фильтр по типу документа"),
    collection_id: Optional[str] = Query(None, description="Фильтр по коллекции"),
    include_json: bool = Query(False, description="Включать ли parsed_json в ответ"),
):
    """Список загруженных документов, опционально по типу и/или коллекции."""
    items = store_list(document_type=document_type, collection_id=collection_id)
    root = _get_upload_root()
    out = []
    for d in items:
        rel = d.get("relative_path", "")
        full = root / rel
        if not full.is_absolute():
            full = root / rel
        d["uploaded_at"] = d.get("uploaded_at")
        out.append(_doc_to_meta(d, include_json=include_json))
    return DocumentList(items=out, total=len(out))


@router.get("/types")
async def list_document_types():
    """Список типов документов для UI."""
    return [
        {"id": t.value, "label": _document_type_label(t) }
        for t in DocumentType
    ]


def _document_type_label(t: DocumentType) -> str:
    labels = {
        DocumentType.CHAIRMAN_GOALS: "Цели председателя банка",
        DocumentType.STRATEGY_CHECKLIST: "Чеклист по стратегии банка",
        DocumentType.REGLAMENT_CHECKLIST: "Чеклист по регламенту банка",
        DocumentType.DEPARTMENT_GOALS_CHECKLIST: "Чеклист по целям департамента",
        DocumentType.BUSINESS_PLAN_CHECKLIST: "Чеклист по бизнес-плану",
        DocumentType.GOALS_TABLE: "Таблица целей (форма)",
    }
    return labels.get(t, t.value)


@router.get("/{document_id}", response_model=DocumentMeta)
async def get_document_by_id(document_id: str, include_json: bool = Query(True)):
    """Получить документ по id, с parsed_json если есть."""
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return _doc_to_meta(doc, include_json=include_json)


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """Удалить документ по id."""
    if not store_delete(document_id):
        raise HTTPException(status_code=404, detail="Документ не найден")
    return {"status": "ok"}


@router.post("/{document_id}/preprocess", response_model=PreprocessResponse)
async def preprocess_document(document_id: str):
    """
    Предобработать документ с помощью LLM: извлечь текст, преобразовать в JSON по типу документа.
    Требует настроенный OPEN_WEBUI_URL и OPEN_WEBUI_API_KEY (или OpenAI).
    """
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    path = get_document_path(document_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Файл документа не найден на диске")

    doc_type_str = doc.get("document_type", "")
    try:
        dt = DocumentType(doc_type_str)
    except ValueError:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error=f"Неизвестный тип: {doc_type_str}")

    content = path.read_bytes()
    text = extract_text_from_bytes(content, path.name, None)
    if not text or len(text.strip()) < 10:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="Не удалось извлечь текст из файла")

    system = PREPROCESS_SYSTEM + "\n\n" + get_preprocess_prompt(dt)
    parsed = preprocess_document_to_json(system, text)
    if parsed is None:
        return PreprocessResponse(document_id=document_id, preprocessed=False, error="LLM не вернул валидный JSON. Проверьте OPEN_WEBUI_URL и OPEN_WEBUI_API_KEY.")

    set_parsed_json(document_id, parsed)
    return PreprocessResponse(document_id=document_id, preprocessed=True, parsed_json=parsed)
