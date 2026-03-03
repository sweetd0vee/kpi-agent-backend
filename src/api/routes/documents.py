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
from src.core.config import settings
from src.services import file_storage
from src.services.document_store import (
    add_document,
    delete_document as store_delete,
    generate_document_id,
    get_collection,
    get_document,
    get_document_path,
    get_storage_path_for_upload,
    list_documents as store_list,
)
from src.services.document_preprocess import run_preprocess
from src.services.open_webui_client import sync_file_to_knowledge

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
        parsed_json_path=d.get("parsed_json_path"),
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
    object_key = get_storage_path_for_upload(dt.value, doc_id, filename)
    bucket = file_storage.document_type_to_bucket(dt.value) if settings.use_minio else None
    file_storage.put_file(object_key, content, bucket=bucket, content_type=file.content_type)

    uploaded_at = datetime.now(timezone.utc).isoformat()
    add_document(doc_id, filename, dt.value, object_key, uploaded_at=uploaded_at, collection_id=collection_id)

    if collection_id:
        col = get_collection(collection_id)
        if col and col.get("open_webui_knowledge_id"):
            sync_file_to_knowledge(
                col["open_webui_knowledge_id"],
                content,
                filename,
                file.content_type,
            )

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
    result = run_preprocess(document_id)
    if not result.preprocessed and result.error and "не найден" in result.error.lower():
        raise HTTPException(status_code=404, detail=result.error)
    return result
