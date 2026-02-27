"""API коллекций документов базы знаний: создание, переименование, удаление."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.documents import CollectionMeta
from src.services.document_store import (
    create_collection as store_create,
    delete_collection as store_delete,
    get_collection,
    list_collections as store_list,
    update_collection as store_update,
)

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
    """Создать коллекцию."""
    name = (body.name if body else "").strip() or "Новая коллекция"
    return store_create(name)


@router.get("/{collection_id}", response_model=CollectionMeta)
async def get_collection_by_id(collection_id: str):
    """Получить коллекцию по id."""
    col = get_collection(collection_id)
    if not col:
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    return col


@router.patch("/{collection_id}", response_model=CollectionMeta)
async def update_collection(collection_id: str, body: UpdateCollectionBody):
    """Переименовать коллекцию."""
    if not store_update(collection_id, body.name):
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    col = get_collection(collection_id)
    return col


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str):
    """Удалить коллекцию (документы отвязываются, не удаляются)."""
    if not store_delete(collection_id):
        raise HTTPException(status_code=404, detail="Коллекция не найдена")
    return {"status": "ok"}
