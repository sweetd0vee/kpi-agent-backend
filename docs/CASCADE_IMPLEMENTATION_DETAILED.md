# CASCADE: Актуальная реализация (backend)

Документ описывает **текущую** (актуальную) реализацию каскадирования в backend:

- как формируется итоговая таблица;
- какие данные используются;
- какие правила и fallback срабатывают;
- какие LLM-промпты применяются.

Основные файлы реализации:

- `src/services/cascade_service.py`
- `src/services/cascade_repository.py`
- `src/services/cascade_llm.py`
- `src/api/routes/cascade.py`
- `src/models/cascade.py`

---

## 1) Что является источником целей

В текущей логике базовый источник каскадируемых целей:

- **`board_goals`** (строки конкретного `report_year` и конкретного manager по `last_name`).

Таблица `strategy_goals` используется не как базовый пул board-целей, а как:

1. источник direct-целей для конкретного заместителя (match по `responsible_person_owner`);
2. дополнительный сигнал релевантности для назначения целей заместителю (direct strategy goals).

Таблица `leader_goals` в snapshot загружается, но в текущей версии каскадирования как источник `items` не используется.

---

## 2) Какие таблицы участвуют в расчете

`CascadeRepository.load_snapshot(report_year)` загружает:

- `board_goals` (с фильтром по `report_year`);
- `leader_goals` (с фильтром по `report_year`, сейчас не используется в каскаде);
- `strategy_goals` (целиком);
- `staff` (целиком);
- `process_registry` (целиком).

---

## 3) Выходные блоки результата

`POST /api/cascade/run` возвращает `CascadeRunResponse`:

- `items` — итоговые каскадированные строки;
- `unmatched` — строго ограниченные несопоставленные кейсы (см. раздел 7);
- `fallbackGoals` — резервные цели (отдельный набор).

История запусков хранится в:

- `cascade_runs`;
- `cascade_run_items`.

---

## 4) Основной алгоритм `CascadeService.run(...)`

## 4.1 Подготовка

Перед циклом:

- строится `manager_to_deputies` из `staff`:
  - `manager = functional_block_curator`,
  - `deputy = head`;
- строится `person_to_processes` из `process_registry`:
  - `leader -> [process, ...]`;
- строится `person_to_business_units` из `staff`:
  - `head -> [business_unit, unit_name, ...]`.

## 4.2 Для каждого manager

1. `source_goals = _build_source_goals_for_manager(manager, report_year)`  
   Сейчас это только `board_goals` по manager+year.

2. Берется список его `deputies`.

3. Для каждого deputy:
   - собираются процессы (`_get_processes_for_person`);
   - собираются блоки/подразделения (`_get_business_units_for_person`);
   - собираются direct strategy goals (`_build_strategy_goals_for_deputy`).

4. Проверка “жесткого unmatched”:
   - если **нет процессов** И **нет strategy goals**, тогда запись уходит в `unmatched`
     с причиной:
     - `Не найдены процессы в реестре процессов и цели в стратегии.`

5. Иначе:
   - board-кандидаты проходят `_filter_goals_by_process_relevance(...)`;
   - при `use_llm=true` strategy direct-goals также проходят эту фильтрацию;
   - два набора объединяются через `_merge_goal_candidates(...)`;
   - результат добавляется в `items`.

6. После обработки всех deputy:
   - если часть board-целей никому не назначилась, они добавляются в итоговую таблицу
     как неназначенные строки с пустым `deputyName` (в UI отображается `—`).

## 4.3 Как обрабатываются нераспределенные board-цели

Текущая логика:

- сначала цель пытается назначиться через основной фильтр (process_registry + strategy);
- если не назначилась никому, она все равно попадает в `items` как неназначенная строка;
- в такой строке `deputyName` пустой (в UI это `—`).

---

## 5) Фильтрация релевантности (`_filter_goals_by_process_relevance`)

## 5.1 Rule-based score

Для кандидата считаются:

- `keyword_score` — пересечение токенов goal/metric с токенами процессов;
- `business_score` — совпадение business/dept цели с блоком deputy;
- `source_score` — приоритет источника (`strategy > board > leader`).

Формула:

`rule_score = 0.6 * keyword_score + 0.3 * business_score + 0.1 * source_score`

## 5.2 LLM rerank (top-N)

Если `useLlm=true`:

- в LLM уходит top-N кандидатов (`cascade_llm_max_candidates_per_deputy`);
- LLM возвращает `relevant`, `confidence`, `reason`;
- пересчитывается `final_score`.

Важное правило:

- если `llm_relevant=false`, кандидат исключается из `items`.

## 5.3 Trace

`traceRule` включает:

- score-компоненты;
- process/business/source объяснение;
- классификацию;
- LLM-флаги и reason (если были).

Также сверху добавляется человекочитаемая префикс-фраза:

- `Назначено от руководителя '<manager>' заместителю '<deputy>'. Источник цели: '<source>'.`

---

## 6) Стратегия: как deputy сопоставляется с `responsible_person_owner`

`_strategy_executor_matches_deputy(...)`:

1. direct name match;
2. parsed name match (разбор из скобок/фрагментов);
3. cache;
4. если LLM включен — LLM match (`assess_responsible_executor_match`).

Если match успешен, строка стратегии добавляется в direct-goals deputy.

---

## 7) Что попадает в `unmatched` (текущее правило)

В `unmatched` попадает **только** deputy-кейс:

- у заместителя одновременно:
  - нет процессов в `process_registry`;
  - нет strategy direct-goals.

Поля записи:

- `managerName`
- `deputyName`
- `reason = "Не найдены процессы в реестре процессов и цели в стратегии."`
- `reportYear`

Manager-level причины (`нет source_goals`, `нет deputies`) в текущем поведении в `unmatched` не добавляются.

---

## 8) Нераспределенные board-цели

Если board-цель не получила назначения на основном этапе:

- она добавляется в `items` отдельной строкой;
- `deputyName` остается пустым;
- `traceRule` содержит пояснение, что цель не была сопоставлена ни одному заместителю.

---

## 9) Дедупликация

Используются dedup-ключи (нормализованные):

- manager/deputy;
- sourceType/sourceRowId;
- sourceGoalTitle/sourceMetric.

Дубли режутся как при основном назначении, так и при добавлении неназначенных строк.

---

## 10) Актуальные LLM-промпты

Ниже — шаблоны промптов из `src/services/cascade_llm.py`.

## 10.1 Bulk relevance prompt (`assess_goals_relevance_bulk`)

```text
Ты эксперт по каскадированию KPI и процессному управлению.
Для каждого кандидата цели оцени релевантность процессам сотрудника.
Верни строго JSON:
{"items":[{"idx":0,"relevant":true,"confidence":0.0,"reason":""}]}

Сотрудник: {subject_name}
Процессы сотрудника:
{process_text}

Кандидаты целей:
{goals_text}
```

Где:

- `process_text` — список процессов deputy;
- `goals_text` — список вида `idx=...; goal=...; metric=...`.

## 10.2 Responsible executor match prompt (`assess_responsible_executor_match`)

```text
Ты эксперт по оргструктуре и каскадированию целей.
Определи, соответствует ли строка 'Ответственный исполнитель' конкретному заместителю.
В строке могут быть сокращения и ФИО в скобках, например: 'ДЦР (Пинчук Ю.В.)'.
Верни строго JSON без пояснений:
{"match": true|false, "confidence": 0..1, "reason": "кратко"}

Заместитель (эталон): {deputy_name}
Ответственный исполнитель (из стратегии): {responsible_executor}
Цель: {goal_title}
Инициатива: {initiative}
```

## 10.3 Одиночный relevance prompt (`assess_goal_relevance`)

```text
Ты эксперт по каскадированию KPI и процессному управлению.
Оцени, релевантна ли цель руководителя процессам сотрудника из реестра процессов.
Верни строго JSON без пояснений:
{"relevant": true|false, "confidence": 0..1, "reason": "кратко"}

Сотрудник (получатель цели): {subject_name}
Процессы сотрудника:
{process_text}

Цель руководителя: {goal_title}
Метрика цели: {goal_metric}
```

---

## 11) Ключевые настройки (`src/core/config.py`)

- `enable_cascade_llm`
- `cascade_llm_judge_model`
- `cascade_llm_fallback_model`
- `cascade_llm_timeout_sec`
- `cascade_llm_max_candidates_per_deputy`

---

## 12) Что проверять при отладке

1. Есть ли у manager board-цели в выбранном `report_year`.
2. Есть ли связка manager -> deputy в `staff`.
3. Есть ли процессы deputy в `process_registry`.
4. Есть ли strategy direct-goals deputy.
5. Что написано в `traceRule` (rule/llm/fallback пояснения).
6. Что попало в `unmatched` (должны быть только deputy без процессов и без стратегии).

