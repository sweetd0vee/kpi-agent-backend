# Файловое хранилище на MinIO

## Запуск MinIO (Docker)

Сообщение **"Unable to find image 'minio/minio:latest' locally"** означает, что образ в кэше отсутствует и Docker пытается скачать его из Docker Hub. Если загрузка не начинается или падает:

1. **Скачать образ вручную:**
   ```bash
   docker pull minio/minio:latest
   ```
2. **Запустить контейнер:**
   ```bash
   docker run -p 9000:9000 -p 9001:9001 --name minio-server ^
     -e "MINIO_ROOT_USER=minioadmin" -e "MINIO_ROOT_PASSWORD=minioadmin" ^
     -v minio-data:/data minio/minio server /data --console-address ":9001"
   ```
   На Windows лучше использовать **именованный том** `minio-data` (как выше), а не `/mnt/data` (путь Linux). Консоль MinIO: http://localhost:9001

3. **Включить MinIO в бэкенде:** в `.env` задать:
   ```
   USE_MINIO=true
   MINIO_ENDPOINT=localhost:9000
   MINIO_ACCESS_KEY=minioadmin
   MINIO_SECRET_KEY=minioadmin
   ```

Загружаемые файлы попадают в MinIO **каждый тип документа в свой бакет**: `goals`, `strategy`, `regulation`, `department-regulation`, `business-plan` (см. `DOCUMENT_TYPE_TO_BUCKET` в `src/core/config.py`).

---

## Текущее состояние (локальная ФС и MinIO)

- **Хранение:** локальная ФС в каталоге `upload_dir` (по умолчанию `uploads/`).
- **Структура:** `uploads/{document_type}/{document_id}_{filename}`; индекс документов — `uploads/index.json`.
- **Использование:** загрузка документов (API `/api/documents/upload`), чтение файла при предобработке (preprocess), удаление документа (удаление файла с диска и записи из индекса).
- **Ключевые места:** `src/services/document_store.py` (пути, индекс, удаление файла), `src/api/routes/documents.py` (запись `path.write_bytes(content)` и чтение через `get_document_path()`).

## Цель

Перевести хранение файлов на **MinIO** (S3-совместимое хранилище), сохранив текущий API и логику индекса (метаданные документов и коллекций можно по-прежнему хранить в JSON на диске или в БД).

---

## 1. Конфигурация MinIO

Добавить в `src/core/config.py` (или `.env`) параметры:

| Переменная | Описание | Пример |
|------------|----------|--------|
| `MINIO_ENDPOINT` | Хост MinIO (без протокола) | `localhost:9000` |
| `MINIO_ACCESS_KEY` | Access Key | `minioadmin` |
| `MINIO_SECRET_KEY` | Secret Key | `minioadmin` |
| `MINIO_BUCKET` | Имя бакета для документов | `kpi-documents` |
| `MINIO_USE_SSL` | Использовать HTTPS | `false` (для локального MinIO) |
| `USE_MINIO` | Включить MinIO вместо локальной ФС | `true` |

При `USE_MINIO=false` оставить текущее поведение (локальный `upload_dir`).

---

## 2. Сервис доступа к MinIO (новый модуль)

**Файл:** `src/services/file_storage.py` (или `minio_storage.py`).

Реализовать абстракцию хранилища файлов (интерфейс), чтобы роуты и `document_store` не зависели от «диск или MinIO»:

### 2.1. Интерфейс (абстрактные функции или класс)

- **`put_file(object_key: str, data: bytes, content_type: str | None = None) -> None`**  
  Сохранить файл в хранилище.  
  - Локальная ФС: `object_key` — относительный путь, запись в `upload_dir / object_key`.  
  - MinIO: загрузка в бакет с ключом `object_key`.

- **`get_file(object_key: str) -> bytes`**  
  Прочитать файл по ключу.  
  - Локальная ФС: чтение из `upload_dir / object_key`.  
  - MinIO: `get_object()` и чтение потока в `bytes`.

- **`delete_file(object_key: str) -> bool`**  
  Удалить файл.  
  - Локальная ФС: `Path.unlink()`.  
  - MinIO: `remove_object()`.

- **`file_exists(object_key: str) -> bool`**  
  Проверка существования (для совместимости и отладки).

Для MinIO использовать клиент `minio` (пакет `minio` в `requirements.txt`).  
Структура ключей в бакете может совпадать с текущей: `{document_type}/{document_id}_{safe_filename}`.

### 2.2. Создание бакета при старте (опционально)

В `main.py` или при первом обращении к MinIO вызывать `client.bucket_exists(bucket)` и при отсутствии — `client.make_bucket(bucket)`.

---

## 3. Изменения в document_store

- **`get_storage_path_for_upload`**  
  Вместо возврата `Path` возвращать **строку object key** (например `chairman_goals/uuid_filename.xlsx`), общую для ФС и MinIO.  
  Для локальной ФС: формировать путь так же, как сейчас, но сохранять в индекс именно `relative_path` как ключ (уже так и есть).

- **Запись файла**  
  Вынести из роута в `document_store` или в общий сервис: «сохранить файл по object_key».  
  В `documents.upload`: после генерации `doc_id` и `object_key` вызывать `put_file(object_key, content)` вместо `path.write_bytes(content)`.

- **`get_document_path(document_id)`**  
  Сейчас возвращает `Path` для чтения с диска. Варианты:
  - **Вариант A:** переименовать/расширить в «получить содержимое файла»: `get_document_bytes(document_id) -> bytes`, внутри вызывать `get_file(doc["relative_path"])`. Тогда предобработка и скачивание работают через байты, без временных файлов.
  - **Вариант B:** оставить семантику «путь к файлу» только для локальной ФС; для MinIO при preprocess скачивать объект во временный файл и возвращать `Path` к нему (нужно не забывать удалять temp-файл после использования).

Рекомендуется **вариант A**: единый метод `get_document_bytes(document_id) -> bytes`, а в роуте preprocess и при отдаче файла клиенту (если будет) использовать эти байты. Для локальной ФС внутри `get_file` читать с диска по `upload_dir / object_key`.

- **`delete_document(document_id)`**  
  Вместо удаления по `Path` вызывать `delete_file(doc["relative_path"])`. Для MinIO — удаление объекта по ключу; индекс обновлять как сейчас.

---

## 4. Изменения в API документов

- **POST /upload**  
  После `file.read()` вызывать `put_file(object_key, content)` (object_key из `get_storage_path_for_upload` в виде строки). Не писать напрямую в `Path`. Метаданные по-прежнему в `add_document(..., relative_path=object_key)`.

- **GET /{document_id}** (метаданные)  
  Без изменений.

- **POST /{document_id}/preprocess**  
  Вместо `path.read_bytes()` использовать `get_document_bytes(document_id)` (или временный файл из MinIO, если выбран вариант B). Дальше передавать байты в `extract_text_from_bytes(...)` — это уже поддерживается.

- **DELETE /{document_id}**  
  Логика в `document_store.delete_document`: удаление через `delete_file(relative_path)` и обновление индекса — без изменений в сигнатуре роута.

---

## 5. Зависимости

В `requirements.txt` добавить:

```
minio
```

Использовать официальный клиент [minio-py](https://github.com/minio/minio-py): `from minio import Minio`.

---

## 6. Инициализация и выбор бэкенда

- По конфигу `USE_MINIO` выбирать реализацию `put_file` / `get_file` / `delete_file` (локальная ФС или MinIO).
- Либо фабрика в `file_storage.py`: `get_storage() -> FileStorage`, возвращающая нужную реализацию. Роуты и `document_store` вызывают только методы этого интерфейса.

---

## 7. Безопасность и политики MinIO

- Настроить бакет и политики доступа по необходимости (доступ только с бэкенда по ключам, без публичного чтения).
- Не отдавать наружу `MINIO_SECRET_KEY` и не логировать ключи.

---

## 8. Краткий чек-лист реализации

| Задача | Где |
|--------|-----|
| Добавить настройки MinIO в config | `src/core/config.py` |
| Реализовать MinIO-клиент и функции put/get/delete по object_key | `src/services/file_storage.py` |
| Реализовать локальную реализацию того же интерфейса (текущая логика с Path) | `src/services/file_storage.py` |
| Выбор реализации по USE_MINIO | `src/services/file_storage.py` или конфиг |
| Заменить запись файла в upload на put_file(object_key, content) | `src/api/routes/documents.py` |
| Ввести get_document_bytes(document_id) и использовать в preprocess | `document_store` + `documents.py` |
| В delete_document вызывать delete_file(relative_path) вместо Path.unlink | `src/services/document_store.py` |
| get_storage_path_for_upload возвращать строку (object key) | `document_store` |
| Создание бакета при старте при USE_MINIO | `main.py` или при первом put_file |
| Добавить minio в requirements.txt | корень бэкенда |

После этого бэкенд будет поддерживать и локальное хранилище, и MinIO; переключение — через переменную окружения `USE_MINIO`.
