# Структура базы данных AI KPI

## Обзор

PostgreSQL, подключение через `DATABASE_URL` (по умолчанию `postgresql+psycopg://postgres:postgres@localhost:5434/ai-kpi`).

Таблицы создаются автоматически при старте приложения (`init_db`) или вызовом `POST /api/db/init`. После `create_all` `init_db` при необходимости применяет встроенные мини-миграции для уже существующих БД (см. `src/db/database.py`).

---

## ER-диаграмма (текстовая)

```
┌───────────────────────────────────────────────┐
│               board_goals                     │
│  Цели правления (объединённая таблица)        │
├───────────────────────────────────────────────┤
│ id             UUID           PK              │
│ last_name      STR            ФИО             │
│ business_unit  STR            Бизнес/блок    │
│ department     STR            Департамент     │
│ goal           STR            SCAI Цель       │
│ metric_goals   STR            Метрические цели│
│ weight_q       STR            Вес квартал     │
│ weight_year    STR            Вес год         │
│ q1..q4         STR            Кварталы 1–4    │
│ year           STR            Итог за год     │
│ report_year    STR            Отчётный год    │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│              leader_goals                      │
│  Цели руководителей (форма по шаблону)         │
├───────────────────────────────────────────────┤
│ id             UUID           PK              │
│ last_name      STR            ФИО             │
│ goal_num       STR            № цели          │
│ name           STR            Наименование КПЭ│
│ goal_type      STR            Тип цели        │
│ goal_kind      STR            Вид цели        │
│ unit           STR            Ед. измерения   │
│ q1_weight      STR            I кв. Вес %     │
│ q1_value       STR            I кв. План      │
│ q2_weight      STR            II кв. Вес %    │
│ q2_value       STR            II кв. План     │
│ q3_weight      STR            III кв. Вес %   │
│ q3_value       STR            III кв. План    │
│ q4_weight      STR            IV кв. Вес %    │
│ q4_value       STR            IV кв. План     │
│ year_weight    STR            Год Вес %       │
│ year_value     STR            Год План        │
│ comments       STR            Комментарии     │
│ method_desc    STR            Методика расчёта │
│ source_info    STR            Источник инфо   │
│ report_year    STR            Отчётный год    │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│            strategy_goals                      │
│  Цели стратегии                                │
├───────────────────────────────────────────────┤
│ id                      UUID         PK       │
│ business_unit           STR   Бизнес/блок     │
│ segment                 STR   Сегмент         │
│ strategic_priority      STR   Стратег. приор. │
│ goal_objective          STR   Цель            │
│ initiative              STR   Инициатива      │
│ initiative_type         STR   Тип инициативы  │
│ responsible_person_owner STR  Ответственный   │
│ other_units_involved    STR   Участие др. блок│
│ budget                  STR   Бюджет          │
│ start_date              STR   Начало          │
│ end_date                STR   Конец           │
│ kpi                     STR   КПЭ             │
│ unit_of_measure         STR   Ед. измерения   │
│ target_value_2025       STR   2025: целевое   │
│ target_value_2026       STR   2026: целевое   │
│ target_value_2027       STR   2027: целевое   │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│            process_registry                    │
│  Реестр процессов                             │
├───────────────────────────────────────────────┤
│ id                      UUID         PK       │
│ process_area            STR   Процессная область │
│ process_code            STR   Код процесса    │
│ process                 STR   Процесс / наименование │
│ process_owner           STR   Владелец        │
│ leader                  STR   Руководитель (ФИО) │
│ business_unit           STR   Бизнес/блок     │
│ top_20                  STR   ТОП 20           │
└───────────────────────────────────────────────┘

┌───────────────────────────────────────────────┐
│                 staff                          │
│  Оргструктура / штат                           │
├───────────────────────────────────────────────┤
│ id                      UUID         PK       │
│ org_structure_code      STR   Код оргструктуры │
│ unit_name               STR   Наименование    │
│ head                    STR   Руководитель    │
│ business_unit           STR   Бизнес/блок     │
│ functional_block_curator STR  Куратор блока    │
└───────────────────────────────────────────────┘
```

---

## Таблицы и их назначение

Отдельной таблицы справочника руководителей **нет**: ФИО в целях правления хранится только в поле `last_name`. Подсказки для полей «ответственные» в других модулях приложения формируются эндпоинтом `GET /api/reference/responsibles` (объединение уникальных ФИО из `board_goals`, `leader_goals` и руководителей из `staff.head`).

### 1. `board_goals` — Цели правления

Объединённая таблица (ранее были отдельные `kpi` и `ppr`).

| Колонка        | Тип         | Ограничения      | Описание                                        |
|----------------|-------------|-------------------|-------------------------------------------------|
| `id`           | UUID        | PK               | Уникальный идентификатор строки (UUID v4)       |
| `last_name`    | STRING      | NOT NULL         | ФИО руководителя                                |
| `business_unit`| STRING      | NOT NULL         | Бизнес/блок                                     |
| `department`   | STRING      | NOT NULL         | Департамент                                     |
| `goal`         | STRING      | NOT NULL         | SCAI Цель                                       |
| `metric_goals` | STRING      | NOT NULL         | Метрические цели                                |
| `weight_q`     | STRING      | NOT NULL         | Вес (квартал)                                   |
| `weight_year`  | STRING      | NOT NULL         | Вес (год)                                       |
| `q1`           | STRING      | NOT NULL         | Значение за 1 квартал                           |
| `q2`           | STRING      | NOT NULL         | Значение за 2 квартал                           |
| `q3`           | STRING      | NOT NULL         | Значение за 3 квартал                           |
| `q4`           | STRING      | NOT NULL         | Значение за 4 квартал                           |
| `year`         | STRING      | NOT NULL         | Итоговое значение за год                        |
| `report_year`  | STRING      | NOT NULL         | Отчётный год (например "2026")                  |

Если таблица уже существовала без новых колонок:

```sql
ALTER TABLE board_goals ADD COLUMN IF NOT EXISTS business_unit VARCHAR NOT NULL DEFAULT '';
ALTER TABLE board_goals ADD COLUMN IF NOT EXISTS department VARCHAR NOT NULL DEFAULT '';
```

### 2. `leader_goals` — Цели руководителей

Детализированная форма целей каждого руководителя по шаблону.

| Колонка       | Тип         | Ограничения | Описание                                |
|---------------|-------------|-------------|-----------------------------------------|
| `id`          | UUID        | PK          | Уникальный идентификатор строки (UUID v4) |
| `last_name`   | STRING      | NOT NULL    | ФИО руководителя                        |
| `goal_num`    | STRING      | NOT NULL    | Номер цели                              |
| `name`        | STRING      | NOT NULL    | Наименование КПЭ                        |
| `goal_type`   | STRING      | NOT NULL    | Тип цели (типовая/групповая/индивид.)   |
| `goal_kind`   | STRING      | NOT NULL    | Вид цели                                |
| `unit`        | STRING      | NOT NULL    | Единица измерения                       |
| `q1_weight`   | STRING      | NOT NULL    | I квартал — вес %                       |
| `q1_value`    | STRING      | NOT NULL    | I квартал — плановое значение / веха    |
| `q2_weight`   | STRING      | NOT NULL    | II квартал — вес %                      |
| `q2_value`    | STRING      | NOT NULL    | II квартал — плановое значение / веха   |
| `q3_weight`   | STRING      | NOT NULL    | III квартал — вес %                     |
| `q3_value`    | STRING      | NOT NULL    | III квартал — плановое значение / веха  |
| `q4_weight`   | STRING      | NOT NULL    | IV квартал — вес %                      |
| `q4_value`    | STRING      | NOT NULL    | IV квартал — плановое значение / веха   |
| `year_weight` | STRING      | NOT NULL    | Год — вес %                             |
| `year_value`  | STRING      | NOT NULL    | Год — плановое значение                 |
| `comments`    | STRING      | NOT NULL    | Комментарии                             |
| `method_desc` | STRING      | NOT NULL    | Методика расчёта / описание КПЭ         |
| `source_info` | STRING      | NOT NULL    | Источник информации о факт. выполнении  |
| `report_year` | STRING      | NOT NULL    | Отчётный год                            |

### 3. `strategy_goals` — Цели стратегии

Стратегические инициативы банка с целевыми показателями на 2025–2027.

| Колонка                    | Тип         | Ограничения | Описание                                   |
|----------------------------|-------------|-------------|---------------------------------------------|
| `id`                       | UUID        | PK          | Уникальный идентификатор строки (UUID v4)   |
| `business_unit`            | STRING      | NOT NULL    | Бизнес/блок                                 |
| `segment`                  | STRING      | NOT NULL    | Сегмент                                     |
| `strategic_priority`       | STRING      | NOT NULL    | Стратегический приоритет                    |
| `goal_objective`           | STRING      | NOT NULL    | Цель                                        |
| `initiative`               | STRING      | NOT NULL    | Инициатива                                  |
| `initiative_type`          | STRING      | NOT NULL    | Тип инициативы                              |
| `responsible_person_owner` | STRING      | NOT NULL    | Ответственный исполнитель                   |
| `other_units_involved`     | STRING      | NOT NULL    | Участие других блоков                       |
| `budget`                   | STRING      | NOT NULL    | Бюджет                                      |
| `start_date`               | STRING      | NOT NULL    | Дата начала                                 |
| `end_date`                 | STRING      | NOT NULL    | Дата окончания                              |
| `kpi`                      | STRING      | NOT NULL    | КПЭ (ключевой показатель эффективности)     |
| `unit_of_measure`          | STRING      | NOT NULL    | Единица измерения                           |
| `target_value_2025`        | STRING      | NOT NULL    | Целевое значение на 2025                    |
| `target_value_2026`        | STRING      | NOT NULL    | Целевое значение на 2026                    |
| `target_value_2027`        | STRING      | NOT NULL    | Целевое значение на 2027                    |

Если в таблице ещё есть колонка `category` (устарела), удалите:

```sql
ALTER TABLE strategy_goals DROP COLUMN IF EXISTS category;
```

### 4. `process_registry` — Реестр процессов

Справочник процессов (процессная область, код, наименование, владелец, блок, признак ТОП 20 и т.д.). FK к другим таблицам не используется.

| Колонка               | Тип         | Ограничения | Описание (как в шаблоне)                         |
|-----------------------|-------------|-------------|--------------------------------------------------|
| `id`                  | UUID        | PK          | Уникальный идентификатор строки (UUID v4)       |
| `process_area`        | STRING      | NOT NULL    | Процессная область                               |
| `process_code`        | STRING      | NOT NULL    | Код процесса                                     |
| `process`             | STRING      | NOT NULL    | Процесс / наименование                           |
| `process_owner`       | STRING      | NOT NULL    | Владелец процесса                                |
| `leader`              | STRING      | NOT NULL    | Руководитель (ФИО, справочно)                    |
| `business_unit`       | STRING      | NOT NULL    | Бизнес/блок                                      |
| `top_20`              | STRING      | NOT NULL    | ТОП 20 (текст/признак, например «Да»/«Нет»)      |

Загрузка из Excel: `POST /api/process-registry/upload` (см. раздел «API-эндпоинты»). Удобно использовать **английские** заголовки как в шаблоне: `process_area`, `process_code`, `process`, `process_owner`, `leader`, `business_unit`, `top_20` (поддерживаются русские синонимы и старые имена `process_name`, `owner_full_name_ref` — см. `xlsx_process_registry_import.py`).

Если таблица уже существует с колонками `process_name` и `owner_full_name_ref`, выполните `scripts/migrate_process_registry_process_and_leader.py` или вручную:

```sql
ALTER TABLE process_registry RENAME COLUMN process_name TO process;
ALTER TABLE process_registry RENAME COLUMN owner_full_name_ref TO leader;
```

Если таблица уже создана со старой колонкой `block`, переименуйте в PostgreSQL:

```sql
ALTER TABLE process_registry RENAME COLUMN block TO business_unit;
```

### 5. `staff` — Оргструктура (штат)

Справочник подразделений: код оргструктуры, наименование, руководитель, бизнес/блок и куратор. FK к другим таблицам не используется.

| Колонка                    | Тип         | Ограничения | Описание (как в шаблоне)              |
|----------------------------|-------------|-------------|----------------------------------------|
| `id`                       | UUID        | PK          | Уникальный идентификатор строки (UUID v4) |
| `org_structure_code`       | STRING      | NOT NULL    | Код оргструктуры                       |
| `unit_name`                | STRING      | NOT NULL    | Наименование                           |
| `head`                     | STRING      | NOT NULL    | Руководитель                           |
| `business_unit`            | STRING      | NOT NULL    | Бизнес/блок                            |
| `functional_block_curator` | STRING      | NOT NULL    | Куратор функционального блока          |

Если таблица уже существует с колонкой `functional_block`, переименуйте в PostgreSQL (или выполните `scripts/migrate_staff_functional_block_to_business_unit.py`):

```sql
ALTER TABLE staff RENAME COLUMN functional_block TO business_unit;
```

---

## Связи между таблицами

Все перечисленные таблицы **без FK** между собой: связи предметной области выражены текстовыми полями (ФИО, наименования блоков и т.д.).

```
board_goals ── независимая таблица
   │  Цели правления. ФИО — поле last_name.

leader_goals ── независимая таблица
   │  Хранит цели руководителей в формате шаблона.
   │  Привязка к руководителю — через текстовое поле last_name.

strategy_goals ── независимая таблица
   │  Стратегические цели и инициативы банка.
   │  Не имеет FK-связей с другими таблицами.
   │  Привязка к ответственному — через текстовое поле
   │  responsible_person_owner.

process_registry ── независимая таблица
   │  Реестр процессов (справочник). Без FK.

staff ── независимая таблица
   │  Оргструктура / штат. Без FK.
```

### Логическая связь данных (каскадирование)

```
strategy_goals                     Стратегия банка (верхний уровень)
    │                              Приоритеты, инициативы, КПЭ на 3 года
    │
    ▼  декомпозиция
board_goals                        Цели правления (средний уровень)
    │                              Конкретные цели председателя/зампредов
    │                              с весами и квартальными показателями
    │
    ▼  каскадирование
leader_goals                       Цели руководителей (нижний уровень)
                                   Детализация по каждому руководителю
                                   подразделения с формой оценки
```

---

## API-эндпоинты

| Таблица          | GET                    | PUT                    | Загрузка xlsx |
|------------------|------------------------|------------------------|---------------|
| `board_goals`    | `GET /api/board-goals` | `PUT /api/board-goals` | `POST /api/board-goals/upload` (multipart `file`) |
| `leader_goals`   | `GET /api/leader-goals`| `PUT /api/leader-goals`| `POST /api/leader-goals/upload` |
| `strategy_goals` | `GET /api/strategy-goals` | `PUT /api/strategy-goals` | `POST /api/strategy-goals/upload` |
| `process_registry` | `GET /api/process-registry` | `PUT /api/process-registry` | `POST /api/process-registry/upload` |
| `staff`          | `GET /api/staff`       | `PUT /api/staff`       | — |

**Справочные данные (не таблица):** `GET /api/reference/responsibles` — список строк ФИО для подсказок в UI (см. описание выше).

Все PUT-эндпоинты принимают `{ "rows": [...] }` и полностью заменяют содержимое таблицы (DELETE + INSERT).

**POST …/upload** — тело `multipart/form-data`, поле **`file`**: файл `.xlsx` с первой строкой заголовков (те же названия колонок, что при импорте во фронте). После разбора таблица **полностью заменяется**, как при PUT. Пример:

```bash
curl -X POST "http://localhost:8000/api/strategy-goals/upload" -F "file=@strategy.xlsx"
curl -X POST "http://localhost:8000/api/process-registry/upload" -F "file=@process_registry.xlsx"
```

Для **реестра процессов** первая строка листа — заголовки. Рекомендуемые имена (как в Excel-шаблоне): `process_area`, `process_code`, `process`, `process_owner`, `leader`, `business_unit`, `top_20`. Допускаются русские заголовки и варианты вроде `process_name` / `owner_full_name_ref`. Колонка `id` необязательна: если её нет, для каждой строки генерируется идентификатор как на фронте.

---

## Создание / пересоздание таблиц

```bash
# Автоматически при старте бэкенда:
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Принудительно через API:
curl -X POST http://localhost:8000/api/db/init
```

Таблицы создаются через `Base.metadata.create_all()` — если таблица уже существует, она не пересоздаётся (данные сохраняются).

Если в базе осталась устаревшая таблица `departments` (ранее использовалась как справочник), её можно удалить вручную:

```sql
DROP TABLE IF EXISTS departments;
```

---

## Соглашения

- **Все текстовые поля** хранятся как `STRING` (без ограничения длины). Пустые значения хранятся как `""` (не NULL).
- **id** в `board_goals`, `leader_goals`, `strategy_goals`, `process_registry`, `staff` — **UUID** (в API и на фронте — строка UUID v4, `generateId()` / импорт xlsx).

Существующая БД со старым типом `VARCHAR` для `id`: выполните `scripts/migrate_row_ids_to_uuid.py` (PostgreSQL; строкам будут назначены новые UUID).

При обновлении со старой схемы: таблица **`leaders`** и колонка **`board_goals.leader_id`** удаляются автоматически при старте приложения (`init_db` → см. `src/db/database.py`). При необходимости то же можно выполнить вручную: `python scripts/migrate_drop_leaders.py`.

---

## См. также

- [DATA_STORAGE_AND_MIGRATIONS.md](./DATA_STORAGE_AND_MIGRATIONS.md) — как хранить данные, нужны ли миграции при смене схемы, отличие `create_all` от миграций.
