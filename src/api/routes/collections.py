"""API коллекций документов базы знаний: создание, переименование, удаление, генерация JSON."""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.config import settings
from src.models.documents import CollectionMeta
from src.services.document_preprocess import run_preprocess
from src.services.document_store import (
    TEMPLATE_COLLECTION_ID,
    TEMPLATE_DOCUMENT_TYPES,
    add_document_from_parsed,
    copy_document_to_collection,
    create_collection as store_create,
    delete_collection as store_delete,
    get_collection,
    get_document,
    get_document_bytes,
    list_collections as store_list,
    list_documents as store_list_documents,
    set_collection_open_webui_knowledge_id,
    update_collection as store_update,
)
from src.services.extract_text import extract_text_from_bytes
from src.services.open_webui_client import create_knowledge, sync_file_to_knowledge

router = APIRouter()


class CreateCollectionBody(BaseModel):
    name: str = "Новая коллекция"


class UpdateCollectionBody(BaseModel):
    name: str


@router.get("", response_model=list[CollectionMeta])
async def list_collections():
    """Список всех коллекций."""
    return store_list()


@router.post("", response_model=CollectionMeta)
async def create_collection(body: Optional[CreateCollectionBody] = None):
    """Создать коллекцию в базе знаний и дублировать её в Open Web UI (Knowledge).
    Документы из шаблона (Бизнес-план, Стратегия, Регламент из Настроек) автоматически копируются в новую коллекцию."""
    name = (body.name if body else "").strip() or "Новая коллекция"
    col = store_create(name)
    # Скопировать шаблонные документы (загруженные в Настройках) в новую коллекцию (в т.ч. из MinIO)
    template_docs = store_list_documents(collection_id=TEMPLATE_COLLECTION_ID)
    for td in template_docs:
        try:
            copy_document_to_collection(td["id"], col["id"])
        except Exception:
            pass  # не ломаем создание коллекции, если один шаблон не скопировался
    owu_id, _ = create_knowledge(name)
    if owu_id:
        set_collection_open_webui_knowledge_id(col["id"], owu_id)
        col = get_collection(col["id"]) or col
    return col


@router.get("/{collection_id}", response_model=CollectionMeta)
async def get_collection_by_id(collection_id: str):
    """Получить коллекцию по id."""
    col = get_collection(collection_id)
    if not col:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    return col


class CollectionContextResponse(BaseModel):
    """Текстовый контекст коллекции для подстановки в промпт (содержимое документов)."""
    content: str
    document_count: int = 0
    """Всего документов в коллекции."""
    included_count: int = 0
    """Документов с успешно загруженным содержимым (для остальных — заглушка)."""


# Максимум символов сырого текста на документ (чтобы контекст не раздувался)
_MAX_RAW_TEXT_PER_DOC = 35000


def _filename_for_extract(d: dict) -> str:
    """Имя файла с расширением для extract_text (по name или relative_path)."""
    name = (d.get("name") or "").strip() or "file"
    if "." in name:
        return name
    rel = (d.get("relative_path") or "").strip()
    if rel:
        return rel.split("/")[-1] if "/" in rel else rel
    return name


@router.get("/{collection_id}/context", response_model=CollectionContextResponse)
async def get_collection_context(collection_id: str):
    """
    Вернуть содержимое всех документов коллекции в виде одного текста.
    Для обработанных документов — parsed_json; для остальных — извлечённый из файла текст,
    чтобы модель могла работать и с необработанными коллекциями.
    """
    col = get_collection(collection_id)
    if not col:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    docs = store_list_documents(collection_id=collection_id)
    parts = []
    included_count = 0
    for d in docs:
        name = d.get("name") or d.get("id") or "документ"
        parsed = d.get("parsed_json")
        if not parsed and d.get("id"):
            full = get_document(d["id"])
            parsed = full.get("parsed_json") if full else None
        if parsed:
            parts.append(f"## {name}\n{json.dumps(parsed, ensure_ascii=False, indent=2)}")
            included_count += 1
        else:
            raw_content = get_document_bytes(d["id"]) if d.get("id") else None
            if raw_content:
                try:
                    raw_text = extract_text_from_bytes(
                        raw_content,
                        _filename_for_extract(d),
                        None,
                    )
                    if raw_text and len(raw_text.strip()) > 0:
                        if len(raw_text) > _MAX_RAW_TEXT_PER_DOC:
                            raw_text = raw_text[:_MAX_RAW_TEXT_PER_DOC] + "\n\n[... текст обрезан ...]"
                        parts.append(f"## {name}\n(исходный текст документа)\n\n{raw_text}")
                        included_count += 1
                    else:
                        parts.append(f"## {name}\n(не удалось извлечь текст из файла)")
                except Exception:
                    parts.append(f"## {name}\n(ошибка извлечения текста)")
            else:
                parts.append(f"## {name}\n(файл не найден)")
    content = "\n\n".join(parts) if parts else "(В коллекции нет документов.)"
    return CollectionContextResponse(
        content=content,
        document_count=len(docs),
        included_count=included_count,
    )


@router.patch("/{collection_id}", response_model=CollectionMeta)
async def update_collection(collection_id: str, body: UpdateCollectionBody):
    """Переименовать коллекцию."""
    if not store_update(collection_id, body.name):
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    col = get_collection(collection_id)
    return col


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str):
    """Удалить коллекцию и все файлы её документов (в т.ч. в MinIO по бакетам)."""
    if not store_delete(collection_id):
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    return {"status": "ok"}


class GenerateJsonResponse(BaseModel):
    collection: CollectionMeta
    documents_processed: int
    errors: list[str] = []


@router.post("/{collection_id}/generate-json", response_model=GenerateJsonResponse)
async def generate_collection_json(collection_id: str):
    """
    Для всех документов коллекции выполнить преобразование и извлечение через LLM в JSON,
    создать новую коллекцию «{название} (JSON)» с документами в формате JSON.
    Новую коллекцию можно прикреплять к чату с моделью.
    """
    col = get_collection(collection_id)
    if not col:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")

    docs = store_list_documents(collection_id=collection_id)
    if not docs:
        raise HTTPException(status_code=400, detail="В коллекции нет документов")

    new_name = (col.get("name") or "Коллекция").strip() + " (JSON)"
    new_col = store_create(new_name)
    processed = 0
    errors: list[str] = []

    for d in docs:
        doc_id = d.get("id")
        if not doc_id:
            continue
        doc_type = d.get("document_type") or ""
        # Бизнес-план, Стратегия и Регламент из настроек не обрабатываем через LLM — они уже проверены
        if doc_type in TEMPLATE_DOCUMENT_TYPES:
            if copy_document_to_collection(doc_id, new_col["id"]):
                processed += 1
            continue
        # Предобработать, если ещё не обработан
        if not d.get("preprocessed"):
            result = run_preprocess(doc_id)
            if not result.preprocessed:
                errors.append(f"{d.get('name', doc_id)}: {result.error or 'Ошибка предобработки'}")
                continue
        # Взять актуальный документ с parsed_json
        updated = get_document(doc_id)
        if not updated or not updated.get("parsed_json"):
            errors.append(f"{d.get('name', doc_id)}: нет JSON после предобработки")
            continue
        name_suffix = " (JSON)" if not (d.get("name") or "").endswith(" (JSON)") else ""
        add_document_from_parsed(
            new_col["id"],
            updated["document_type"],
            (updated.get("name") or "document") + name_suffix,
            updated["parsed_json"],
        )
        processed += 1

    return GenerateJsonResponse(
        collection=new_col,
        documents_processed=processed,
        errors=errors,
    )


class SyncOpenWebUIResponse(BaseModel):
    open_webui_knowledge_id: Optional[str] = None
    files_synced: int = 0
    errors: list[str] = []
    open_webui_url: Optional[str] = None


@router.post("/{collection_id}/sync-openwebui", response_model=SyncOpenWebUIResponse)
async def sync_collection_to_open_webui(collection_id: str):
    """
    Создать коллекцию знаний в Open Web UI (если ещё нет) и загрузить в неё все файлы коллекции.
    После синхронизации коллекция будет видна в чате при выборе «Прикрепить коллекцию».
    """
    col = get_collection(collection_id)
    if not col:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")

    kid = col.get("open_webui_knowledge_id")
    if not kid:
        kid, err = create_knowledge(col.get("name") or "Коллекция")
        if kid:
            set_collection_open_webui_knowledge_id(collection_id, kid)
        else:
            return SyncOpenWebUIResponse(
                errors=[err or "Не удалось создать коллекцию в Open Web UI."],
                open_webui_url=(settings.open_webui_url or "").strip() or None,
            )

    docs = store_list_documents(collection_id=collection_id)
    files_synced = 0
    errors: list[str] = []
    for d in docs:
        doc_id = d.get("id")
        if not doc_id:
            continue
        content = get_document_bytes(doc_id)
        if not content:
            errors.append(f"{d.get('name', doc_id)}: файл не найден")
            continue
        name = d.get("name") or doc_id
        if sync_file_to_knowledge(kid, content, name, None):
            files_synced += 1
        else:
            errors.append(f"{name}: не удалось загрузить в Open Web UI")

    return SyncOpenWebUIResponse(
        open_webui_knowledge_id=kid,
        files_synced=files_synced,
        errors=errors,
        open_webui_url=(settings.open_webui_url or "").strip() or None,
    )
