"""
Настройки приложения: шаблонные документы (Бизнес-план, Стратегия, Регламент).
Загружаются один раз на вкладке «Настройки» и автоматически подставляются в каждую новую коллекцию.
"""
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from src.models.documents import DocumentMeta
from src.models.knowledge import DocumentType
from src.services.document_store import (
    TEMPLATE_COLLECTION_ID,
    TEMPLATE_DOCUMENT_TYPES,
    add_document,
    delete_document,
    generate_document_id,
    get_document,
    get_storage_path_for_upload,
    list_documents as store_list_documents,
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

    # Удалить предыдущий шаблон этого типа, если был
    existing = store_list_documents(collection_id=TEMPLATE_COLLECTION_ID)
    for ex in existing:
        if ex.get("document_type") == document_type:
            delete_document(ex["id"])
            break

    doc_id = generate_document_id()
    filename = file.filename or "file"
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
