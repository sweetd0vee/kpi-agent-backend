from typing import Any, List, Optional

from pydantic import BaseModel


class DocumentMeta(BaseModel):
    id: str
    name: str
    document_type: str  # chairman_goals, strategy_checklist, ...
    collection_id: Optional[str] = None
    size: Optional[int] = None
    content_type: Optional[str] = None
    uploaded_at: Optional[str] = None
    preprocessed: bool = False  # есть ли сохранённый JSON после LLM
    parsed_json: Optional[dict[str, Any]] = None  # при GET по id или в списке (опционально)


class CollectionMeta(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentList(BaseModel):
    items: List[DocumentMeta]
    total: int


class PreprocessResponse(BaseModel):
    document_id: str
    preprocessed: bool
    parsed_json: Optional[dict[str, Any]] = None
    error: Optional[str] = None
