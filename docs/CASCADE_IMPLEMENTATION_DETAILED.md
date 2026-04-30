# Подробная реализация каскадирования (backend)

Документ описывает, как устроено каскадирование целей в `kpi-agent-backend`, на уровне сервисов и таблиц БД:

- `src/services/cascade_service.py`
- `src/services/cascade_repository.py`
- `src/services/cascade_llm.py`
- `src/db/models.py`

---

## 1. Общая идея алгоритма

Цель алгоритма: для выбранного руководителя(ей) и отчетного года найти релевантные KPI/цели для его заместителей.

Входные данные берутся из пяти таблиц:

1. `board_goals` — основной пул целей для каскадирования в выбранный отчетный год.
2. `strategy_goals` — стратегический контекст и direct-цели по ответственному исполнителю.
3. `staff` — оргструктура (кто чей куратор/руководитель).
4. `process_registry` — реестр процессов, к которым привязан сотрудник/руководитель.
5. `leader_goals` — присутствует в snapshot, но в текущей логике каскада не используется как источник целей.

Результат разделен на три массива:

- `items` — каскадированные строки (включая специальные строки "не найдено").
- `unmatched` — причины, почему не удалось сопоставить/распределить.
- `fallback_goals` — резервные цели для несопоставленных случаев.

---

## 2. Какие сервисы за что отвечают

## `CascadeRepository` (`src/services/cascade_repository.py`)

Задача репозитория:

- загрузить срез данных для расчета (`load_snapshot`);
- сохранить и читать историю запусков (`save_run`, `list_runs`, `get_run`, `get_run_items`);
- удалить запуск истории (`delete_run`).

`load_snapshot(report_year)`:

- фильтрует по году `board_goals` и `leader_goals` (leader сейчас не участвует в каскаде, но остается в snapshot);
- `strategy_goals`, `staff`, `process_registry` загружаются целиком;
- возвращает `CascadeSnapshot`.

## `CascadeService` (`src/services/cascade_service.py`)

Главная бизнес-логика:

- строит дерево manager -> deputy из `staff`;
- собирает пул целей руководителя;
- фильтрует цели по процессам/бизнес-блоку;
- выполняет LLM rerank (если включено);
- добавляет цели стратегии для заместителя;
- выполняет merge + dedup;
- формирует `items`, `unmatched`, `fallback_goals`.

## `CascadeLlmAdapter` (`src/services/cascade_llm.py`)

Изолированный адаптер LLM:

- `assess_goals_relevance_bulk` — bulk judge релевантности целей процессам;
- `assess_goal_relevance` — одиночная версия (в текущем пайплайне почти не используется);
- `assess_responsible_executor_match` — сопоставление ФИО зама с полем `responsible_executor` стратегии.

Поддерживает:

- primary model (`cascade_llm_judge_model`);
- fallback model (`cascade_llm_fallback_model`);
- timeout (`cascade_llm_timeout_sec`);
- жесткий JSON-parsing ответа.

---

## 3. Нормализация имен и текстов

Ключевые утилиты в `cascade_service.py`:

- `norm_text(...)`:
  - lowercase;
  - `ё -> е`;
  - схлопывание пробелов.
- `normalize_name(...)`:
  - `norm_text`;
  - удаление пунктуации/символов;
  - оставляет буквы/цифры/пробел.
- `names_match(left, right)`:
  - exact normalized match;
  - либо включение длинной строки в другую (>= 6 символов), чтобы переживать форматы вроде `Иванов И.И.` vs `Иванов`.

Зачем это важно:

- в исходных таблицах ФИО часто в разных форматах;
- без нормализации резко растет количество ложных unmatched.

---

## 4. Колонки таблиц и как они используются в каскадировании

Ниже перечислены поля именно с точки зрения алгоритма каскадирования.

## 4.1 `leader_goals` (`LeaderGoalRow`)

Ключевые колонки:

- `id` — первичный ключ строки.
- `last_name` — ФИО/фамилия руководителя; используется для матчинга с выбранным manager.
- `name` — текст цели.
- `year_value` — годовая метрика цели.
- `report_year` — фильтр по отчетному году.

Как используется:

- в текущей версии каскадирования **не используется** как источник `source_goals`;
- хранится в БД и snapshot для совместимости и возможного будущего расширения.

## 4.2 `board_goals` (`BoardGoalRow`)

Ключевые колонки:

- `id`
- `last_name` — ФИО/фамилия руководителя.
- `goal` — цель правления.
- `metric_goals` — метрика.
- `business_unit`
- `department`
- `report_year`

Как используется (основной источник):

- в пул `source_goals` руководителя (только строки выбранного `report_year` и manager):
  - `sourceType = board`
  - `sourceGoalTitle = goal`
  - `sourceMetric = metric_goals`
  - `businessUnit = business_unit`
  - `department = department`
  - `traceRule = match: board_goals.last_name == manager`

## 4.3 `strategy_goals` (`StrategyGoalRow`)

Ключевые колонки:

- `id`
- `business_unit`
- `segment`
- `goal_objective`
- `initiative`
- `responsible_person_owner`
- `kpi`
- `target_value_2025/2026/2027`
- `start_date`, `end_date` (для дашбордов, не для match в каскаде).

Как используется:

### A) как direct цели заместителя:

- `_build_strategy_goals_for_deputy(...)` проверяет соответствие `responsible_person_owner` и `deputy_name`;
- сначала rule-based сопоставление ФИО, затем (опционально) LLM.

### B) как контекст для fallback-назначения board-целей:

- при невозможности назначить board-цель обычным способом для замов,
  стратегия используется в `_pick_candidate_deputies_for_goal(...)`;
- считается `strategy_score` — схожесть board-цели с direct strategy goals заместителя;
- итоговый fallback-score учитывает `process + business + strategy`.

## 4.4 `staff` (`StaffRow`)

Ключевые колонки:

- `head` — руководитель подразделения (в текущей логике трактуется как кандидат deputy).
- `functional_block_curator` — куратор функционального блока (manager).
- `business_unit`
- `unit_name`

Как используется:

- строится граф `manager -> deputies` из пары:
  - `manager = functional_block_curator`
  - `deputy = head`
- из `head` собирается карта бизнес-блоков сотрудника:
  - `business_unit`, `unit_name`.

## 4.5 `process_registry` (`ProcessRegistryRow`)

Ключевые колонки:

- `leader` — ФИО сотрудника/руководителя для связки;
- `process` — название процесса;
- `business_unit` — справочно.

Как используется:

- для каждого deputy ищутся процессы через `leader ~= deputy`;
- эти процессы участвуют в keyword-score и в LLM judge prompt.

## 4.6 История запусков: `cascade_runs`, `cascade_run_items`

### `cascade_runs` (`CascadeRun`)

- `id` — run id;
- `created_at`, `status`;
- `report_year`;
- `managers_filter` (JSON: managers + useLlm);
- `total_managers`, `total_deputies`, `total_items`, `unmatched_count`;
- `warnings_json`, `unmatched_json`.

### `cascade_run_items` (`CascadeRunItem`)

Снимок итоговой таблицы `items`:

- `manager_name`, `deputy_name`;
- `source_type`, `source_row_id`;
- `source_goal_title`, `source_metric`;
- `business_unit`, `department`, `report_year`;
- `trace_rule`, `confidence`.

---

## 5. Пошаговый flow `CascadeService.run(...)`

## Шаг 1: подготовка словарей

Создаются:

- `manager_to_deputies` из `staff`;
- `person_to_processes` из `process_registry`;
- `person_to_business_units` из `staff`.

## Шаг 2: выбор менеджеров

- если `managers` передан в запросе — берется этот список;
- иначе берутся все ключи из `manager_to_deputies`.

## Шаг 3: обработка каждого manager

1. `source_goals = _build_source_goals_for_manager(...)`.
2. `deputies = manager_to_deputies[manager]`.

Ветки:

- если нет заместителей:
  - запись в `unmatched`;
  - формирование `fallback_goals`;
  - переход к следующему manager.
- если нет source_goals:
  - запись в `unmatched`;
  - переход к следующему manager.

## Шаг 4: обработка каждого deputy

Для каждого зама:

1. Ищутся процессы (`_get_processes_for_person`) и бизнес-блоки (`_get_business_units_for_person`).
2. Если процессов нет:
   - `unmatched` + спец-строка `not_found` в `items` + fallback.
3. Иначе:
   - фильтрация `source_goals` через `_filter_goals_by_process_relevance`.
   - сбор direct strategy goals (`_build_strategy_goals_for_deputy`).
   - если `use_llm=true`, direct strategy goals тоже проходят `_filter_goals_by_process_relevance`.
   - merge двух наборов (`_merge_goal_candidates`).
4. Если итог пустой:
   - `unmatched` + спец-строка `not_found` + fallback.
5. Иначе:
   - добавление строк в `items` с dedup по стабильному ключу.

## Шаг 5: fallback-назначение каждой board-цели

После прохода всех замов для manager:

- берутся `source_goals` (board), которые еще не были назначены никому;
- для каждой такой цели вызывается `_pick_candidate_deputies_for_goal(...)`;
- цель назначается одному или нескольким заместителям:
  - всем кандидатам с положительным score и не ниже 85% от лучшего;
  - если у всех score нулевой — назначается один лучший fallback-кандидат.

Итог: каждая цель правления за выбранный год получает хотя бы одного заместителя.

---

## 6. Как работает фильтрация релевантности

Функция: `_filter_goals_by_process_relevance(...)`.

## 6.1 Rule-based этап

Для каждой цели считаются:

- `keyword_score` — overlap токенов goal/metric и process name;
- `business_score` — совпадение business/dept источника с блоком deputy;
- `source_score` — вес источника (`strategy=1.0`, `board=0.75`, `leader=0.65`, иначе `0.5`).

Формула:

`rule_score = 0.6 * keyword + 0.3 * business + 0.1 * source`.

Слабые кандидаты отбрасываются по порогу, но для `strategy` при `use_llm=true` действует послабление: цель не отбрасывается до LLM только из-за слабого rule-score.

## 6.2 LLM этап (rerank)

Для top-N (`cascade_llm_max_candidates_per_deputy`) вызывается:

- `assess_goals_relevance_bulk(...)`, результат по `idx`.

На кандидате:

- если есть `confidence`, рассчитывается `final_score = clamp(rule_score +/- confidence*0.35)`.
- если `llm_relevant=false`, кандидат исключается из `items`, а причина сохраняется через `llm_rejections_out` и далее в `unmatched`.

## 6.3 Trace

В `traceRule` пишется:

- `rule/final/keyword/business/source` scores;
- тип релевантности (`llm_rerank+process_registry` или `rule_based+process_registry`);
- `process_match`, `business_match`, `source_reason`;
- `classification`.

---

## 7. Стратегия: сопоставление `responsible_person_owner` и deputy

Функция: `_strategy_executor_matches_deputy(...)`.

Порядок:

1. direct `names_match`.
2. разбор ФИО из строки (включая скобки, списки, сокращения) через `_extract_possible_person_names`.
3. cache check (ключ: normalized executor + normalized deputy).
4. если `use_llm=false` -> no match.
5. token prefilter.
6. LLM `assess_responsible_executor_match(...)`.

Результат:

- `(match: bool, trace: str)`.

---

## 8. Дедупликация

Используются два набора ключей:

- `item_seen` для `items`;
- `fallback_seen` для `fallback_goals`.

Ключ построен из нормализованных:

- manager/deputy,
- sourceType/sourceRowId,
- sourceGoalTitle/sourceMetric.

Отдельно в `_merge_goal_candidates` merge по key `(sourceType, sourceRowId, goal, metric)` + подъем `classification` до `strategy+process_registry`, если цель пришла из обоих каналов.

---

## 9. Специальные типы строк в `items`

Кроме обычных `board/strategy`, сейчас возможны:

- `sourceType = not_found`:
  - когда по конкретному deputy не найдено релевантных целей;
  - обычно `sourceGoalTitle = "KPI не найдено"`.
- тип `unassigned` в текущей версии не используется, т.к. нераспределенные board-цели
  дополнительно назначаются через fallback-кандидатов.

---

## 10. Конфигурация LLM (из `src/core/config.py`)

Ключевые настройки:

- `enable_cascade_llm`
- `cascade_llm_judge_model` (default `qwen3:8b`)
- `cascade_llm_fallback_model`
- `cascade_llm_timeout_sec`
- `cascade_llm_max_candidates_per_deputy`

Транспорт:

- через `chat_completion(..., use_ollama=True)`;
- JSON extraction с fallback на вторую модель.

---

## 11. Почему в выдаче могут быть пустые `managerName` или `deputyName`

Это не ошибка парсинга, а часть правил:

- `managerName=""` в `not_found`-строках добавляется специально (по бизнес-требованию).
- `deputyName=""` в текущем алгоритме для board-целей больше не целевой сценарий:
  такие цели дораспределяются fallback-механизмом по заместителям.

---

## 12. Практическая интерпретация результата

В UI полезно воспринимать результат в 3 слоя:

1. `items` — итоговые назначения (включая технические `not_found` для случаев без процессов/релевантности).
2. `unmatched` — почему не удалось сопоставить (человекочитаемые причины).
3. `fallback_goals` — резервный пул, который можно рассматривать отдельно от целевых назначений.

Для аналитики качества алгоритма используйте:

- долю `items` с `sourceType=not_found`;
- количество `llm_relevant=false` в `unmatched`;
- долю fallback к total items;
- распределение `classification` в `traceRule`.

