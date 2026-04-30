# AI KPI — краткая документация проекта

Инструмент каскадирования KPI: база знаний (документы, коллекции), чат с LLM, дашборды целей. Цели руководства → цели подразделений с опорой на чеклисты и регламенты.

---

## Frontend (`kpi-agent-front`)

### Стек
- **React 18** + **TypeScript**
- **Vite** — сборка и dev-сервер
- **React Router 6** — маршрутизация
- **docx**, **jspdf**, **jspdf-autotable**, **xlsx** — работа с документами (чтение/экспорт)

### Структура и функционал
- **Layout** — боковое меню (КПЭ, ППР, База знаний, Каскадирование, Чат, Дашборды).
- **Страницы:**
  - **КПЭ** (`/kpi`) — работа с KPI.
  - **ППР** (`/goals`) — цели (План профессионального развития / цели подразделений).
  - **База знаний** (`/knowledge`) — импорт документов: загрузка в коллекции, типы документов (цели председателя, чеклисты стратегии/регламента/бизнес-плана и т.д.).
  - **Каскадирование** (`/cascade`) — запуск каскадирования manager -> deputy, история запусков, экспорт `Каскадированных целей` и `Резервных целей для несопоставленных`.
    - Опция: **«Использовать LLM-фильтрацию целей по реестру процессов и стратегии»**.
  - **Чат с моделью** (`/chat`) — диалог с LLM, прикрепление документов из базы знаний.
  - **Дашборды** (`/dashboards`) — визуализация целей и метрик.

Фронт ходит к бэкенду по `VITE_API_URL` (в Docker задаётся как `http://localhost:8000`).

### Запуск
```bash
cd kpi-agent-front
npm install
npm run dev   # http://localhost:5173
```

---

## Backend (`kpi-agent-backend`)

### Стек
- **Python 3**
- **FastAPI** + **uvicorn** — API
- **pydantic-settings** — конфиг из `.env`
- **pypdf**, **python-docx**, **openpyxl** — извлечение текста из PDF/DOCX/XLSX
- **minio** — S3-совместимое хранилище (опционально)
- **httpx**, **openai** — клиенты к внешним API (Open Web UI и др.)

### Алгоритм и модули
- **Документы и коллекции** — загрузка файлов, индекс в `uploads/index.json`, коллекции в `uploads/collections.json`. При `USE_MINIO=true` файлы хранятся в бакетах MinIO по типу документа (goals, strategy, regulation, department-regulation, business-plan). При удалении коллекции удаляются и все её файлы (в т.ч. в MinIO).
- **Предобработка** — извлечение текста из файла, отправка в LLM (Open Web UI), сохранение результата как JSON в хранилище.
- **Каскадирование целей** — рабочий backend-сервис (`src/services/cascade_service.py`), источники `leader/board/strategy/staff/process_registry`, двухэтапная фильтрация (rule-based + LLM rerank), сохранение истории запусков.
  - При `llm_relevant=false` цель не попадает в `items`, а причина сохраняется в `unmatched`.
  - Если не найдено, кому каскадировать цель, такая цель возвращается в `items` с пустым `deputyName`.
- **Чат** — `POST /api/chat/completions`.
- **Дашборды** — визуализации строятся из табличных данных целей.

### API (кратко)
| Группа | Эндпоинты |
|--------|------------|
| **documents** | `POST /upload`, `GET /`, `GET /types`, `GET /{id}`, `DELETE /{id}`, `POST /{id}/preprocess` |
| **collections** | `GET/POST /`, `GET/PATCH/DELETE /{id}`, `GET /{id}/context` (возвращает `content`, `document_count`, `included_count`), `POST /{id}/generate-json`, `POST /{id}/sync-openwebui` |
| **chat** | `POST /completions` |
| **cascade** | `POST /run`, `GET /runs`, `GET /runs/{run_id}`, `DELETE /runs/{run_id}`, `POST /runs/{run_id}/delete` |
| **dashboard** | `GET /goals`, `GET /metrics` |

### База данных
При старте приложения создаются таблицы в PostgreSQL: `board_goals`, `leader_goals`, `strategy_goals`, `process_registry`, `staff`. Подключение задаётся через `DATABASE_URL` в `.env` (по умолчанию `postgresql+psycopg://postgres:postgres@localhost:5434/ai-kpi` при маппинге порта 5434 в docker-compose). Данные «Целей правления» сохраняются через `PUT /api/board-goals`.

Если таблицы не появились (БД была недоступна при старте), создайте их вручную:
- **Через API (удобнее всего):** запустите бэкенд, затем откройте http://localhost:8000/docs → раздел **db** → **POST /api/db/init** → Execute (или `curl -X POST http://localhost:8000/api/db/init`).
- **Скрипт (тот же Python, что и приложение):** из каталога `kpi-agent-backend` выполните `scripts\init_db.bat` — он сам поставит зависимости и создаст таблицы. Либо: `python -m pip install -r requirements.txt`, затем `python scripts/init_db.py`.

### Запуск
```bash
cd kpi-agent-backend
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```
- API: http://localhost:8000  
- Swagger: http://localhost:8000/docs  
- Health: http://localhost:8000/health  

**Если `/docs` не загружается:** убедитесь, что в терминале видно `Uvicorn running on http://0.0.0.0:8000` (или `127.0.0.1:8000`). Если процесса нет — бэкенд не запущен или упал с ошибкой до старта. При недоступной PostgreSQL приложение теперь всё равно стартует, в логе будет предупреждение; поднимите БД (docker-compose с `db`, порт как в `DATABASE_URL`, по умолчанию **5434**) и выполните `POST /api/db/init` из `/docs` или `python scripts/init_db.py`.

### LLM модели: предобработка и финальная генерация

**Предобработка (чеклисты целей/задач → JSON)** по умолчанию выполняется локально через **Ollama** (`USE_OLLAMA_FOR_PREPROCESS=true`). Это должна быть **маленькая, но качественная** модель:

1. **Модель по умолчанию** — `qwen3:8b` (быстрая, хорошо даёт JSON). Установка: `ollama pull qwen3:8b`.
2. **Рекомендуемые локальные модели для предобработки (установить в Ollama):**
   - `qwen3:8b` — дефолт и основной вариант.
   - `llama3.2` — альтернативная небольшая модель (укажите точный тег в `OLLAMA_PREPROCESS_MODEL`).
3. В `.env` при необходимости:
   - `OLLAMA_PREPROCESS_MODEL=qwen3:8b` (или другая 7B–8B модель).
   - `OLLAMA_PREPROCESS_TIMEOUT=180` — таймаут запроса в секундах (для больших моделей 70B можно 300–600).
4. Запуск Ollama: `ollama serve` (обычно уже запущен при установке).

Если использовать Open Web UI вместо Ollama: `USE_OLLAMA_FOR_PREPROCESS=false`, задать `OPEN_WEBUI_URL` и `OPEN_WEBUI_API_KEY`.

**Каскадирование (LLM judge в табличном каскаде)**:

- Основная judge-модель: `CASCADE_LLM_JUDGE_MODEL` (текущий дефолт: `qwen3:8b`).
- Резервная модель: `CASCADE_LLM_FALLBACK_MODEL` (используется при ошибке/таймауте основной).
- Таймаут LLM проверки: `CASCADE_LLM_TIMEOUT_SEC`.
- Ограничение LLM top-N на заместителя: `CASCADE_LLM_MAX_CANDIDATES_PER_DEPUTY`.
- Включение этапа LLM: `ENABLE_CASCADE_LLM` (в UI это переключатель `useLlm`).

Подробная документация по алгоритму каскадирования: `../BACKEND_CASCADE_GUIDE.md`.

---

## Что запускать в Docker

Для полного сценария с хранением файлов в MinIO и (опционально) фронтом в контейнере:

### 1. Сеть (один раз)
```bash
docker network create ai-kpi
```

### 2. MinIO (обязательно, если в `.env` бэкенда `USE_MINIO=true`)
```bash
docker run -p 9000:9000 -p 9001:9001 --name minio-server ^
  -e "MINIO_ROOT_USER=minioadmin" -e "MINIO_ROOT_PASSWORD=minioadmin" ^
  -v minio-data:/data minio/minio server /data --console-address ":9001"
```
- API: `localhost:9000`, консоль: http://localhost:9001  

В `.env` бэкенда:
```env
USE_MINIO=true
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

### 3. Frontend (опционально)
Из каталога `kpi-agent-front/docker`:
```bash
docker-compose up -d
```
Поднимает образ `sber/ai-kpi-fe:master` на порту **5173** с `VITE_API_URL=http://localhost:8000`. Сеть `ai-kpi` должна существовать.

### 4. Backend и Open Web UI
- **Backend** — по умолчанию запускается локально (uvicorn), отдельного образа в репозитории нет.
- **Open Web UI** (для предобработки документов и чата) — запускается отдельно (например, свой Docker/хост); в `.env` задаются `OPEN_WEBUI_URL` и `OPEN_WEBUI_API_KEY`.

---

## Итог: что должно быть запущено

| Компонент        | Где запускать        | Порт   |
|------------------|----------------------|--------|
| **MinIO**        | Docker               | 9000, 9001 |
| **Backend (API)**| Локально (uvicorn)   | 8000   |
| **Frontend**     | Локально (`npm run dev`) или Docker | 5173   |
| **Open Web UI**  | Отдельно (по инструкции продукта)   | например 3000 |

После запуска: фронт — http://localhost:5173, API — http://localhost:8000, при `USE_MINIO=true` файлы документов хранятся в MinIO, при удалении коллекции удаляются и все её файлы в бакетах.

---

## База знаний: почему модель «видит» не все файлы

- **Чат в нашем приложении**  
  Контекст коллекции берётся из бэкенда: `GET /api/collections/{id}/context`. В ответе есть `document_count` (всего документов) и `included_count` (сколько передано с содержимым). Если `included_count` меньше `document_count`, для части файлов не удалось прочитать файл или извлечь текст (файл не найден, ошибка формата). В таком случае в чате показывается подсказка: «в контекст передано N из M документов».

- **Open Web UI (Knowledge)**  
  При загрузке файлов в коллекцию каждый файл по возможности синхронизируется в Open Web UI. Если синхронизация не удалась (таймаут, ошибка API), после загрузки показывается предупреждение. В чате Open Web UI тогда могут быть видны не все файлы; в чате нашего приложения контекст по-прежнему строится из всех документов бэкенда.

- **Что проверить**  
  1) В интерфейсе «База знаний» — все ли 5 файлов отображаются в карточке коллекции.  
  2) Ответ `GET /api/collections/{id}/context`: значения `document_count` и `included_count`.  
  3) При создании коллекции — не было ли сообщения об ошибке синхронизации с Open Web UI.
