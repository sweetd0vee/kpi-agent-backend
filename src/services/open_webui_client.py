"""
Клиент Open Web UI API для синхронизации коллекций базы знаний.
Создание Knowledge, загрузка файлов и привязка к коллекции.
"""
import time
from typing import Optional

import httpx

from src.core.config import settings


def _base_url() -> str:
    return (settings.open_webui_url or "").rstrip("/")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.open_webui_api_key or ''}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def create_knowledge(name: str) -> tuple[Optional[str], str]:
    """
    Найти коллекцию знаний в Open Web UI по имени (Open Web UI не поддерживает создание через API).
    Возвращает (knowledge_id или None, сообщение_об_ошибке).
    Коллекцию с таким именем нужно заранее создать в Open Web UI: Workspace → Knowledge.
    """
    base = _base_url()
    if not base:
        return None, "OPEN_WEBUI_URL не задан в настройках бэкенда (.env)"
    if not (settings.open_webui_api_key or "").strip():
        return None, "OPEN_WEBUI_API_KEY не задан в настройках бэкенда (.env)"
    title = (name[:255] if name else "Коллекция").strip()
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{base}/api/v1/knowledge/", headers=_headers())
            if r.status_code != 200:
                try:
                    body = r.text[:200] if r.text else ""
                except Exception:
                    body = ""
                return None, f"Open Web UI ответил {r.status_code}: {body or r.reason_phrase or 'нет тела ответа'}"
            try:
                raw = r.json()
            except Exception:
                return None, "Ответ Open Web UI не JSON"
            items = raw if isinstance(raw, list) else (raw.get("items") or raw.get("data") or [])
            for k in items:
                n = (k.get("name") or k.get("title") or "").strip()
                if n == title:
                    kid = k.get("id") or k.get("knowledge_id")
                    if kid:
                        return str(kid), ""
            return (
                None,
                f'Создайте в Open Web UI коллекцию с именем «{title}»: откройте {base}/ → Workspace → Knowledge → новая коллекция (имя: «{title}»). Затем снова нажмите «В Open Web UI». К сожалению, Open Web UI не даёт создавать коллекции через API — поэтому нужен этот один шаг.',
            )
    except httpx.ConnectError as e:
        return None, f"Не удалось подключиться к Open Web UI по адресу {base}. Проверьте OPEN_WEBUI_URL и что сервер запущен. Ошибка: {e!s}"
    except httpx.TimeoutException:
        return None, "Таймаут при обращении к Open Web UI"
    except Exception as e:
        return None, f"Ошибка при обращении к Open Web UI: {e!s}"


def upload_file(content: bytes, filename: str, content_type: Optional[str] = None) -> Optional[str]:
    """Загрузить файл в Open Web UI. Возвращает file_id или None."""
    base = _base_url()
    if not base or not settings.open_webui_api_key:
        return None
    try:
        headers = {"Authorization": f"Bearer {settings.open_webui_api_key}", "Accept": "application/json"}
        with httpx.Client(timeout=60.0) as client:
            files = {"file": (filename or "file", content, content_type or "application/octet-stream")}
            r = client.post(f"{base}/api/v1/files/", headers=headers, files=files)
            if r.status_code != 200:
                return None
            data = r.json()
            return str(data.get("id") or data.get("file_id") or "")
    except Exception:
        return None


def wait_for_file_ready(file_id: str, timeout_sec: int = 120, poll_interval: float = 2.0) -> bool:
    """Дождаться завершения обработки файла в Open Web UI."""
    base = _base_url()
    if not base or not settings.open_webui_api_key:
        return False
    start = time.monotonic()
    while (time.monotonic() - start) < timeout_sec:
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(
                    f"{base}/api/v1/files/{file_id}/process/status",
                    headers=_headers(),
                )
                if r.status_code != 200:
                    time.sleep(poll_interval)
                    continue
                data = r.json()
                status = data.get("status")
                if status == "completed":
                    return True
                if status == "failed":
                    return False
        except Exception:
            pass
        time.sleep(poll_interval)
    return False


def add_file_to_knowledge(knowledge_id: str, file_id: str) -> bool:
    """Привязать файл к коллекции знаний в Open Web UI."""
    base = _base_url()
    if not base or not settings.open_webui_api_key:
        return False
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{base}/api/v1/knowledge/{knowledge_id}/file/add",
                headers=_headers(),
                json={"file_id": file_id},
            )
            return r.status_code == 200
    except Exception:
        return False


def sync_file_to_knowledge(
    knowledge_id: str,
    content: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> bool:
    """Загрузить файл в OWU, дождаться обработки и добавить в коллекцию. Возвращает True при успехе."""
    file_id = upload_file(content, filename, content_type)
    if not file_id:
        return False
    if not wait_for_file_ready(file_id):
        return False
    return add_file_to_knowledge(knowledge_id, file_id)
