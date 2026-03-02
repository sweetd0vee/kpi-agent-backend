# Backend (AI KPI API)

## Запуск

Из каталога **backend**:

```bash
# Активировать виртуальное окружение (Windows)
venv\Scripts\activate

# Установить зависимости (если ещё не установлены)
pip install -r requirements.txt

# Запустить сервер на порту 8000
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

После запуска:
- API: http://localhost:8000
- Документация Swagger: http://localhost:8000/docs
- Проверка: http://localhost:8000/health

## Переменные окружения (опционально)

Создайте файл `.env` в каталоге `backend` или задайте переменные в системе:

- `OPEN_WEBUI_URL` — URL Open Web UI (или другого OpenAI-совместимого API) для предобработки документов
- `OPEN_WEBUI_API_KEY` — API-ключ
- `UPLOAD_DIR` — каталог для загрузок (по умолчанию `uploads`)
- `USE_MINIO` — `true/false`, сохранять файлы в MinIO вместо локальной папки
- `MINIO_ENDPOINT` — адрес MinIO (например `localhost:9000`)
- `MINIO_ACCESS_KEY` — ключ доступа
- `MINIO_SECRET_KEY` — секрет
- `MINIO_USE_SSL` — `true/false` для https

Если `USE_MINIO=true`, загруженные файлы и результаты предобработки JSON сохраняются в MinIO.
