"""Разбор xlsx для таблицы «Реестр процессов» (первая строка — заголовки).

Ожидаемые имена колонок (как в шаблоне): process_area, process_code, process, process_owner,
leader, business_unit, top_20 — также поддерживаются русские синонимы и старые имена.
"""

from __future__ import annotations

from src.models.process_registry_tables import ProcessRegistryRow
from src.services.xlsx_goals_import import (
    _build_header_field_lookup,
    _generate_row_id,
    _normalize_cell,
    _normalize_header_for_match,
    _read_first_sheet_matrix,
)

PROCESS_REGISTRY_HEADER_TO_FIELD: dict[str, str] = {
    "id": "id",
    # English (как в выгрузке / Excel)
    "process_area": "processArea",
    "process_code": "processCode",
    "process": "process",
    "process_owner": "processOwner",
    "leader": "leader",
    "business_unit": "businessUnit",
    "top_20": "top20",
    # Старые англ. имена
    "process_name": "process",
    "owner_full_name_ref": "leader",
    # Русские
    "Процессная область": "processArea",
    "Код процесса": "processCode",
    "Наименование процесса": "process",
    "Наименование": "process",
    "Владелец процесса": "processOwner",
    "Владелец": "processOwner",
    "Справочно ФИО": "leader",
    "Справочно (ФИО владельца процесса)": "leader",
    "ФИО владельца": "leader",
    "Бизнес/блок": "businessUnit",
    "Блок": "businessUnit",
    "ТОП 20": "top20",
    "Топ 20": "top20",
}

PROCESS_REGISTRY_HEADER_LOOKUP = _build_header_field_lookup(PROCESS_REGISTRY_HEADER_TO_FIELD)


def parse_process_registry_xlsx(content: bytes) -> list[ProcessRegistryRow]:
    matrix = _read_first_sheet_matrix(content)
    if len(matrix) < 2:
        return []
    col_to_field: dict[int, str] = {}
    for index, cell in enumerate(matrix[0]):
        field = PROCESS_REGISTRY_HEADER_LOOKUP.get(_normalize_header_for_match(cell))
        if field:
            col_to_field[index] = field
    if not col_to_field:
        raise ValueError(
            "Не найдено ни одной известной колонки. Ожидаются заголовки: "
            "process_area, process_code, process, process_owner, leader, business_unit, top_20 "
            "(или русские: «Процессная область», «Код процесса», …)."
        )

    empty = {
        "id": "",
        "processArea": "",
        "processCode": "",
        "process": "",
        "processOwner": "",
        "leader": "",
        "businessUnit": "",
        "top20": "",
    }
    out: list[ProcessRegistryRow] = []
    for raw in matrix[1:]:
        row = dict(empty)
        for col_index, field in col_to_field.items():
            cell = raw[col_index] if col_index < len(raw) else None
            row[field] = _normalize_cell(cell)
        if not any(str(v).strip() for v in row.values()):
            continue
        rid = (row.get("id") or "").strip()
        if not rid:
            rid = _generate_row_id()
        out.append(
            ProcessRegistryRow(
                id=rid,
                processArea=row["processArea"],
                processCode=row["processCode"],
                process=row["process"],
                processOwner=row["processOwner"],
                leader=row["leader"],
                businessUnit=row["businessUnit"],
                top20=row["top20"],
            )
        )
    return out
