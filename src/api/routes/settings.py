"""
Настройки приложения: шаблонные документы (Бизнес-план, Стратегия, Регламент).
Загружаются один раз на вкладке «Настройки» и автоматически подставляются в каждую новую коллекцию.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from src.models.documents import DocumentMeta, PreprocessResponse, TemplateChecklistSubmit
from src.models.knowledge import DocumentType
from src.services.document_preprocess import run_preprocess
from src.services.checklist_normalize import normalize_checklist_json
from src.services.document_store import (
    TEMPLATE_COLLECTION_ID,
    TEMPLATE_DOCUMENT_TYPES,
    add_document,
    delete_document,
    generate_document_id,
    get_document,
    get_storage_path_for_upload,
    list_documents as store_list_documents,
    set_parsed_json,
)
from src.core.config import settings
from src.services import file_storage

router = APIRouter()


def _doc_to_meta(d: dict) -> DocumentMeta:
    return DocumentMeta(
        id=d["id"],
        name=d["name"],
        document_type=d["document_type"],
        collection_id=d.get("collection_id"),
        size=None,
        content_type=None,
        uploaded_at=d.get("uploaded_at"),
        preprocessed=d.get("preprocessed", False),
        parsed_json=None,
        parsed_json_path=d.get("parsed_json_path"),
    )


@router.get("/template-documents")
async def get_template_documents():
    """
    Список шаблонных документов (по одному на тип: Бизнес-план, Стратегия, Регламент).
    Ключ — document_type, значение — мета документа или null, если ещё не загружен.
    """
    docs = store_list_documents(collection_id=TEMPLATE_COLLECTION_ID)
    by_type: dict[str, Optional[DocumentMeta]] = {
        t: None for t in TEMPLATE_DOCUMENT_TYPES
    }
    for d in docs:
        dt = d.get("document_type")
        if dt in by_type:
            by_type[dt] = _doc_to_meta(d)
    return by_type


@router.post("/template-documents/upload", response_model=DocumentMeta)
async def upload_template_document(
    document_type: str = Query(..., description="business_plan_checklist, strategy_checklist или reglament_checklist"),
    file: UploadFile = File(...),
):
    """
    Загрузить или заменить шаблонный документ одного из типов.
    При USE_MINIO=true файл сохраняется в MinIO в бакет по типу (business-plan, strategy, regulation).
    Шаблоны загружаются один раз и автоматически копируются в каждую новую коллекцию и используются в контексте для LLM.
    """
    if document_type not in TEMPLATE_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Тип должен быть один из: {', '.join(TEMPLATE_DOCUMENT_TYPES)}",
        )
    try:
        DocumentType(document_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип документа: {document_type}")

    filename = file.filename or "file"
    ext = Path(filename).suffix.lower()
    if ext not in {".docx", ".txt"}:
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .docx или .txt")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")

    # При MinIO — убедиться, что бакеты существуют (на случай если при старте MinIO был недоступен)
    if settings.use_minio:
        try:
            from src.services.file_storage import ensure_buckets_exist
            ensure_buckets_exist()
        except Exception:
            pass

    # Удалить все предыдущие шаблоны этого типа (на случай дубликатов)
    existing = store_list_documents(collection_id=TEMPLATE_COLLECTION_ID)
    for ex in existing:
        if ex.get("document_type") == document_type:
            delete_document(ex["id"])

    doc_id = generate_document_id()
    object_key = get_storage_path_for_upload(document_type, doc_id, filename)
    bucket = file_storage.document_type_to_bucket(document_type) if settings.use_minio else None
    try:
        file_storage.put_file(object_key, content, bucket=bucket, content_type=file.content_type)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Не удалось сохранить файл в хранилище (MinIO/FS): {e!s}",
        )

    from datetime import datetime, timezone
    uploaded_at = datetime.now(timezone.utc).isoformat()
    add_document(
        doc_id,
        filename,
        document_type,
        object_key,
        uploaded_at=uploaded_at,
        collection_id=TEMPLATE_COLLECTION_ID,
    )

    doc = get_document(doc_id)
    return _doc_to_meta(doc)


@router.post("/template-documents/{document_id}/preprocess", response_model=PreprocessResponse)
async def preprocess_template_document(document_id: str):
    """Обработать шаблонный документ через LLM и сохранить JSON."""
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    if doc.get("collection_id") != TEMPLATE_COLLECTION_ID:
        raise HTTPException(status_code=400, detail="Документ не является шаблонным")
    if doc.get("document_type") not in TEMPLATE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Документ не относится к шаблонам")
    return run_preprocess(document_id)


@router.post("/template-documents/{document_id}/submit", response_model=DocumentMeta)
async def submit_template_document(document_id: str, body: TemplateChecklistSubmit):
    """Сохранить проверенный пользователем JSON для шаблонного документа."""
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    if doc.get("collection_id") != TEMPLATE_COLLECTION_ID:
        raise HTTPException(status_code=400, detail="Документ не является шаблонным")
    doc_type = doc.get("document_type") or ""
    if doc_type not in TEMPLATE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Документ не относится к шаблонам")
    normalized = normalize_checklist_json(doc_type, body.parsed_json or {})
    if doc_type in ("strategy_checklist", "business_plan_checklist") and not isinstance(normalized.get("items"), list):
        raise HTTPException(status_code=400, detail="Ожидается JSON с полем items")
    if doc_type == "reglament_checklist" and not isinstance(normalized.get("rules"), list):
        raise HTTPException(status_code=400, detail="Ожидается JSON с полем rules")
    if not set_parsed_json(document_id, normalized):
        raise HTTPException(status_code=500, detail="Не удалось сохранить JSON")
    updated = get_document(document_id)
    return _doc_to_meta(updated)
