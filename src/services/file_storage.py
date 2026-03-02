"""
Абстракция хранилища файлов: локальная ФС или MinIO (каждый тип документа — свой бакет).
"""
from pathlib import Path
from typing import Optional

from src.core.config import DOCUMENT_TYPE_TO_BUCKET, settings


def document_type_to_bucket(document_type: str) -> str:
    """Имя бакета MinIO для данного типа документа."""
    return DOCUMENT_TYPE_TO_BUCKET.get(document_type, document_type.replace("_", "-"))


def _fs_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def put_file(
    object_key: str,
    data: bytes,
    bucket: Optional[str] = None,
    content_type: Optional[str] = None,
) -> None:
    """
    Сохранить файл.
    - Локальная ФС: bucket игнорируется, object_key — относительный путь (type/id_name).
    - MinIO: bucket — имя бакета, object_key — ключ объекта внутри бакета.
    """
    if not settings.use_minio:
        path = _fs_root() / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return

    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
    )
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    client.put_object(bucket, object_key, data=data, length=len(data), content_type=content_type or "application/octet-stream")


def get_file(object_key: str, bucket: Optional[str] = None) -> bytes:
    """
    Прочитать файл.
    - Локальная ФС: чтение из upload_dir / object_key.
    - MinIO: get_object(bucket, object_key).
    """
    if not settings.use_minio:
        path = _fs_root() / object_key
        return path.read_bytes()

    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
    )
    response = client.get_object(bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(object_key: str, bucket: Optional[str] = None) -> bool:
    """
    Удалить файл.
    - Локальная ФС: Path.unlink().
    - MinIO: remove_object().
    """
    if not settings.use_minio:
        path = _fs_root() / object_key
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return True

    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
    )
    try:
        client.remove_object(bucket, object_key)
        return True
    except Exception:
        return False


def ensure_buckets_exist() -> None:
    """Создать все бакеты MinIO при старте (если USE_MINIO=true)."""
    if not settings.use_minio:
        return
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_use_ssl,
    )
    for bucket in set(DOCUMENT_TYPE_TO_BUCKET.values()):
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
