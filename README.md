# Backend (AI KPI API)

## Запуск

Из каталога **backend**:

```bash
# Активировать виртуальное окружение (Windows)
venv\Scripts\activate

# Установить зависимости (если ещё не установлены)
pip install -r requirements.txt

# Запустить сервер на порту 8000
# --host 0.0.0.0 значит «принимать подключения с любых интерфейсов»; в браузере открывайте localhost, не 0.0.0.0
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

После запуска **открывайте в браузере именно эти адреса** (не `0.0.0.0` — он даёт ERR_ADDRESS_INVALID):
- API: http://localhost:8000
- Документация Swagger: http://localhost:8000/docs
- Проверка: http://localhost:8000/health

## Переменные окружения (опционально)

Создайте файл `.env` в каталоге `backend` или задайте переменные в системе:

- `OPEN_WEBUI_URL` — URL Open Web UI (или другого OpenAI-совместимого API) для предобработки документов
- `OPEN_WEBUI_API_KEY` — API-ключ
- `UPLOAD_DIR` — каталог для загрузок (по умолчанию `uploads`)
- **`USE_MINIO`** — **должно быть `true`**, чтобы загружаемые файлы попадали в бакеты MinIO. Если `false` или не задано — файлы сохраняются только в папку `uploads/` на диске (коллекции при этом создаются, но бакеты остаются пустыми).
- `MINIO_ENDPOINT` — адрес MinIO (например `localhost:9000`)
- `MINIO_ACCESS_KEY` — ключ доступа (по умолчанию `minioadmin`)
- `MINIO_SECRET_KEY` — секрет (по умолчанию `minioadmin`)
- `MINIO_USE_SSL` — `true/false` для https

После изменения `USE_MINIO` нужно **перезапустить бэкенд**.
