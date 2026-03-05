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
- **Layout** — боковое меню (КПЭ, ППР, База знаний, Чат, Дашборды).
- **Страницы:**
  - **КПЭ** (`/kpi`) — работа с KPI.
  - **ППР** (`/goals`) — цели (План профессионального развития / цели подразделений).
  - **База знаний** (`/knowledge`) — импорт документов: загрузка в коллекции, типы документов (цели председателя, чеклисты стратегии/регламента/бизнес-плана и т.д.).
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
- **Чат и каскадирование** — API `/api/chat/completions` и `/api/chat/cascade` зарезервированы под вызов LLM и сценарий каскадирования (LangGraph) — в разработке.
- **Дашборд** — `/api/dashboard/goals` (иерархия целей), `/api/dashboard/metrics` (метрики KPI) — заглушки, данные планируются из разбора документов и результата каскада.

### API (кратко)
| Группа | Эндпоинты |
|--------|------------|
| **documents** | `POST /upload`, `GET /`, `GET /types`, `GET /{id}`, `DELETE /{id}`, `POST /{id}/preprocess` |
| **collections** | `GET/POST /`, `GET/PATCH/DELETE /{id}`, `GET /{id}/context` (возвращает `content`, `document_count`, `included_count`), `POST /{id}/generate-json`, `POST /{id}/sync-openwebui` |
| **chat** | `POST /completions`, `POST /cascade` |
| **dashboard** | `GET /goals`, `GET /metrics` |

### Запуск
```bash
cd kpi-agent-backend
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn src.main:app uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
--reload --host 0.0.0.0 --port 8000
```
- API: http://localhost:8000  
- Swagger: http://localhost:8000/docs  
- Health: http://localhost:8000/health  

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

**Финальная генерация (каскад/итоговая таблица)** должна выполняться **сильной моделью**:

- По умолчанию используется Open Web UI / OpenAI с моделью `LLM_CASCADE_MODEL` (например, через Open Web UI).
- Если хотите сильную **локальную** модель в Ollama: `USE_OLLAMA_FOR_CASCADE=true`, указать `OLLAMA_CASCADE_MODEL`, и установить модель командой `ollama pull <model>`.
- Рекомендуемые сильные модели (примерный список): `qwen2.5:32b`, `llama3.1:70b` (выберите подходящую под ресурсы).

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
