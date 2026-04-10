"""
Хранение метаданных и путей загруженных документов базы знаний.
Файлы лежат в upload_dir по типам; индекс — upload_dir/index.json.
Коллекции — upload_dir/collections.json (id, name, created_at, updated_at, карточка).
Документ может принадлежать коллекции (collection_id).
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.core.config import settings
from src.models.knowledge import DocumentType
from src.services import file_storage


# Коллекция-шаблон: документы, загружаемые один раз в настройках (Стратегия, Регламент).
# При создании новой коллекции они автоматически копируются в неё.
TEMPLATE_COLLECTION_ID = "__template__"

# Типы документов, хранящиеся как шаблон (загружаются на вкладке «Настройки»).
TEMPLATE_DOCUMENT_TYPES = ("strategy_checklist", "reglament_checklist")


def get_upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _bucket_for_doc_type(document_type: str) -> Optional[str]:
    return file_storage.document_type_to_bucket(document_type) if settings.use_minio else None


def get_collections_path() -> Path:
    return get_upload_root() / "collections.json"


def get_index_path() -> Path:
    return get_upload_root() / "index.json"


def _load_index() -> list[dict[str, Any]]:
    path = get_index_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_index(items: list[dict[str, Any]]) -> None:
    get_index_path().write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_document_id() -> str:
    return str(uuid.uuid4())


def add_document(
    document_id: str,
    name: str,
    document_type: str,
    relative_path: str,
    uploaded_at: Optional[str] = None,
    collection_id: Optional[str] = None,
) -> None:
    items = _load_index()
    items.append({
        "id": document_id,
        "name": name,
        "document_type": document_type,
        "relative_path": relative_path,
        "preprocessed": False,
        "parsed_json": None,
        "parsed_json_path": None,
        "uploaded_at": uploaded_at or datetime.now(timezone.utc).isoformat(),
        "collection_id": collection_id,
    })
    _save_index(items)


def add_document_from_parsed(
    collection_id: str,
    document_type: str,
    name: str,
    parsed_json: dict[str, Any],
) -> str:
    """
    Создать документ в коллекции из уже полученного parsed_json (JSON сохраняется в хранилище).
    Возвращает id нового документа.
    """
    doc_id = generate_document_id()
    json_path = get_parsed_json_storage_key(document_type, doc_id)
    bucket = _bucket_for_doc_type(document_type)
    payload = json.dumps(parsed_json, ensure_ascii=False, indent=2).encode("utf-8")
    file_storage.put_file(json_path, payload, bucket=bucket, content_type="application/json")
    uploaded_at = datetime.now(timezone.utc).isoformat()
    items = _load_index()
    items.append({
        "id": doc_id,
        "name": name,
        "document_type": document_type,
        "relative_path": json_path,
        "preprocessed": True,
        "parsed_json": parsed_json,
        "parsed_json_path": json_path,
        "uploaded_at": uploaded_at,
        "collection_id": collection_id,
    })
    _save_index(items)
    return doc_id


def get_document(document_id: str) -> Optional[dict[str, Any]]:
    for d in _load_index():
        if d.get("id") == document_id:
            return d
    return None


def list_documents(
    document_type: Optional[str] = None,
    collection_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    items = _load_index()
    if document_type:
        items = [d for d in items if d.get("document_type") == document_type]
    if collection_id is not None:
        items = [d for d in items if d.get("collection_id") == collection_id]
    return items


def get_document_path(document_id: str) -> Optional[Path]:
    """Путь к файлу на диске (только для USE_MINIO=false). Для MinIO используйте get_document_bytes."""
    if settings.use_minio:
        return None
    doc = get_document(document_id)
    if not doc:
        return None
    return get_upload_root() / doc["relative_path"]


def get_document_bytes(document_id: str) -> Optional[bytes]:
    """Содержимое файла документа (работает и для локальной ФС, и для MinIO)."""
    doc = get_document(document_id)
    if not doc:
        return None
    key = doc.get("relative_path") or ""
    doc_type = doc.get("document_type") or ""
    if not key or not doc_type:
        return None
    bucket = _bucket_for_doc_type(doc_type)
    try:
        return file_storage.get_file(key, bucket=bucket)
    except Exception:
        return None


def set_parsed_json(document_id: str, parsed_json: dict[str, Any]) -> bool:
    items = _load_index()
    for d in items:
        if d.get("id") == document_id:
            d["preprocessed"] = True
            d["parsed_json"] = parsed_json
            doc_type = d.get("document_type") or ""
            existing_path = d.get("parsed_json_path")
            json_path = existing_path
            if doc_type:
                try:
                    json_path = get_parsed_json_storage_key(doc_type, document_id)
                    bucket = _bucket_for_doc_type(doc_type)
                    payload = json.dumps(parsed_json, ensure_ascii=False, indent=2).encode("utf-8")
                    file_storage.put_file(json_path, payload, bucket=bucket, content_type="application/json")
                except Exception:
                    json_path = existing_path
            d["parsed_json_path"] = json_path
            _save_index(items)
            return True
    return False


def delete_document(document_id: str) -> bool:
    doc = get_document(document_id)
    if not doc:
        return False
    key = doc.get("relative_path") or ""
    doc_type = doc.get("document_type") or ""
    if key and doc_type:
        bucket = _bucket_for_doc_type(doc_type)
        try:
            file_storage.delete_file(key, bucket=bucket)
        except Exception:
            pass  # удаляем запись из индекса даже если файл в хранилище не найден
        parsed_path = doc.get("parsed_json_path")
        if parsed_path and parsed_path != key:
            try:
                file_storage.delete_file(parsed_path, bucket=bucket)
            except Exception:
                pass
    items = [d for d in _load_index() if d.get("id") != document_id]
    _save_index(items)
    return True


def copy_document_to_collection(document_id: str, collection_id: str) -> Optional[str]:
    """
    Скопировать документ (файл) в другую коллекцию. Возвращает id нового документа или None.
    """
    doc = get_document(document_id)
    if not doc:
        return None
    content = get_document_bytes(document_id)
    if not content:
        return None
    new_id = generate_document_id()
    name = doc.get("name") or "file"
    doc_type = doc.get("document_type") or ""
    object_key = get_storage_path_for_upload(doc_type, new_id, name)
    bucket = _bucket_for_doc_type(doc_type)
    try:
        file_storage.put_file(object_key, content, bucket=bucket, content_type=None)
    except Exception:
        return None
    uploaded_at = datetime.now(timezone.utc).isoformat()
    add_document(new_id, name, doc_type, object_key, uploaded_at=uploaded_at, collection_id=collection_id)
    parsed = doc.get("parsed_json")
    if isinstance(parsed, dict) and parsed:
        try:
            set_parsed_json(new_id, parsed)
        except Exception:
            pass
    return new_id


def _safe_filename(filename: str) -> str:
    return "".join(c for c in filename if c.isalnum() or c in "._- ") or "file"


def get_storage_path_for_upload(document_type: str, document_id: str, filename: str) -> str:
    """
    Object key для сохранения загруженного файла.
    - Локальная ФС: {type}/{id}_{filename} (относительный путь).
    - MinIO: {id}_{filename} (ключ внутри бакета по типу).
    """
    safe_name = _safe_filename(filename)
    if settings.use_minio:
        return f"{document_id}_{safe_name}"
    root = get_upload_root()
    folder = root / document_type
    folder.mkdir(parents=True, exist_ok=True)
    return f"{document_type}/{document_id}_{safe_name}"


def get_parsed_json_storage_key(document_type: str, document_id: str) -> str:
    """
    Object key для JSON после предобработки.
    - Локальная ФС: {type}/parsed/{id}.json (относительный путь).
    - MinIO: parsed/{id}.json (ключ внутри бакета по типу).
    """
    if settings.use_minio:
        return f"parsed/{document_id}.json"
    root = get_upload_root()
    folder = root / document_type / "parsed"
    folder.mkdir(parents=True, exist_ok=True)
    return f"{document_type}/parsed/{document_id}.json"


# --- Коллекции ---

def _load_collections() -> list[dict[str, Any]]:
    path = get_collections_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_collections(items: list[dict[str, Any]]) -> None:
    get_upload_root().mkdir(parents=True, exist_ok=True)
    get_collections_path().write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_collection_id() -> str:
    return str(uuid.uuid4())


def create_collection(
    name: str,
    department: Optional[str] = None,
    period: Optional[str] = None,
    responsibles: Optional[str] = None,
    summary: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    cid = generate_collection_id()
    now = datetime.now(timezone.utc).isoformat()
    col = {
        "id": cid,
        "name": name.strip() or "Без названия",
        "created_at": now,
        "updated_at": now,
        "open_webui_knowledge_id": None,
        "department": department or "",
        "period": period or "",
        "responsibles": responsibles or "",
        "summary": summary or "",
        "status": status or "",
    }
    items = _load_collections()
    items.append(col)
    _save_collections(items)
    return col


def set_collection_open_webui_knowledge_id(collection_id: str, knowledge_id: str) -> bool:
    """Сохранить id коллекции знаний Open Web UI для синхронизации."""
    items = _load_collections()
    for c in items:
        if c.get("id") == collection_id:
            c["open_webui_knowledge_id"] = knowledge_id
            c["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_collections(items)
            return True
    return False


def list_collections() -> list[dict[str, Any]]:
    return _load_collections()


def get_collection(collection_id: str) -> Optional[dict[str, Any]]:
    for c in _load_collections():
        if c.get("id") == collection_id:
            return c
    return None


def update_collection(
    collection_id: str,
    name: Optional[str] = None,
    department: Optional[str] = None,
    period: Optional[str] = None,
    responsibles: Optional[str] = None,
    summary: Optional[str] = None,
    status: Optional[str] = None,
) -> bool:
    items = _load_collections()
    for c in items:
        if c.get("id") == collection_id:
            updated = False
            if name is not None:
                c["name"] = name.strip() or c["name"]
                updated = True
            if department is not None:
                c["department"] = department
                updated = True
            if period is not None:
                c["period"] = period
                updated = True
            if responsibles is not None:
                c["responsibles"] = responsibles
                updated = True
            if summary is not None:
                c["summary"] = summary
                updated = True
            if status is not None:
                c["status"] = status
                updated = True
            if updated:
                c["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_collections(items)
            return True
    return False


def delete_collection(collection_id: str) -> bool:
    items = [c for c in _load_collections() if c.get("id") != collection_id]
    if len(items) == len(_load_collections()):
        return False
    # Удалить все файлы документов коллекции (локальная ФС и/или MinIO по бакетам)
    docs_in_collection = list_documents(collection_id=collection_id)
    for doc in docs_in_collection:
        doc_type = doc.get("document_type") or ""
        bucket = _bucket_for_doc_type(doc_type)
        # основной файл (загруженный или parsed JSON)
        file_storage.delete_file(doc["relative_path"], bucket=bucket)
        # отдельный parsed JSON, если отличается от relative_path
        parsed_path = doc.get("parsed_json_path")
        if parsed_path and parsed_path != doc.get("relative_path"):
            file_storage.delete_file(parsed_path, bucket=bucket)
    # Удалить документы из индекса
    doc_items = _load_index()
    doc_items = [d for d in doc_items if d.get("collection_id") != collection_id]
    _save_index(doc_items)
    # Удалить коллекцию
    _save_collections(items)
    return True
