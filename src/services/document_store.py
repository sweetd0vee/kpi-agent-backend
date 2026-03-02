"""
Хранение метаданных и путей загруженных документов базы знаний.
Файлы лежат в upload_dir по типам; индекс — upload_dir/index.json.
Коллекции — upload_dir/collections.json (id, name, created_at, updated_at).
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


def get_upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


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
        "uploaded_at": uploaded_at or datetime.now(timezone.utc).isoformat(),
        "collection_id": collection_id,
    })
    _save_index(items)


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
    key = doc["relative_path"]
    bucket = file_storage.document_type_to_bucket(doc["document_type"]) if settings.use_minio else None
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
            _save_index(items)
            return True
    return False


def delete_document(document_id: str) -> bool:
    doc = get_document(document_id)
    if not doc:
        return False
    key = doc["relative_path"]
    bucket = file_storage.document_type_to_bucket(doc["document_type"]) if settings.use_minio else None
    file_storage.delete_file(key, bucket=bucket)
    items = [d for d in _load_index() if d.get("id") != document_id]
    _save_index(items)
    return True


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


def create_collection(name: str) -> dict[str, Any]:
    cid = generate_collection_id()
    now = datetime.now(timezone.utc).isoformat()
    col = {"id": cid, "name": name.strip() or "Без названия", "created_at": now, "updated_at": now}
    items = _load_collections()
    items.append(col)
    _save_collections(items)
    return col


def list_collections() -> list[dict[str, Any]]:
    return _load_collections()


def get_collection(collection_id: str) -> Optional[dict[str, Any]]:
    for c in _load_collections():
        if c.get("id") == collection_id:
            return c
    return None


def update_collection(collection_id: str, name: str) -> bool:
    items = _load_collections()
    for c in items:
        if c.get("id") == collection_id:
            c["name"] = name.strip() or c["name"]
            c["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_collections(items)
            return True
    return False


def delete_collection(collection_id: str) -> bool:
    items = [c for c in _load_collections() if c.get("id") != collection_id]
    if len(items) == len(_load_collections()):
        return False
    _save_collections(items)
    # Отвязать документы от коллекции (не удалять файлы)
    doc_items = _load_index()
    changed = False
    for d in doc_items:
        if d.get("collection_id") == collection_id:
            d["collection_id"] = None
            changed = True
    if changed:
        _save_index(doc_items)
    return True
