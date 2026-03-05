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
    parsed_json_path: Optional[str] = None  # путь/ключ JSON-файла (опционально)
    open_webui_synced: Optional[bool] = None  # при загрузке в коллекцию: удалось ли синхронизировать с OWU
    open_webui_error: Optional[str] = None  # при загрузке: ошибка синхронизации с Open Web UI


class CollectionMeta(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    department: Optional[str] = None
    period: Optional[str] = None
    responsibles: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None


class DocumentList(BaseModel):
    items: List[DocumentMeta]
    total: int


class PreprocessResponse(BaseModel):
    document_id: str
    preprocessed: bool
    parsed_json: Optional[dict[str, Any]] = None
    parsed_json_path: Optional[str] = None
    error: Optional[str] = None


class DepartmentChecklistItem(BaseModel):
    id: str = ""
    text: str = ""
    section: str = ""
    checked: bool = False


class DepartmentChecklistSubmit(BaseModel):
    """Тело запроса для сохранения проверенного пользователем чеклиста по положению о департаменте."""
    department: Optional[str] = None
    goals: List[DepartmentChecklistItem] = []
    tasks: List[DepartmentChecklistItem] = []


class TemplateChecklistSubmit(BaseModel):
    """Тело запроса для сохранения проверенного шаблонного чеклиста (БП/Стратегия/Регламент)."""
    parsed_json: dict[str, Any]


class ChecklistSubmit(BaseModel):
    """Тело запроса для сохранения проверенного чеклиста пользователя."""
    parsed_json: dict[str, Any]
