"""Разбор xlsx для таблицы «Штатное расписание» (первая строка — заголовки)."""

from __future__ import annotations

from src.models.staff_tables import StaffRow
from src.services.xlsx_goals_import import (
    _build_header_field_lookup,
    _generate_row_id,
    _normalize_cell,
    _normalize_header_for_match,
    _read_first_sheet_matrix,
)

STAFF_HEADER_TO_FIELD: dict[str, str] = {
    "id": "id",
    "org_structure_code": "orgStructureCode",
    "unit_name": "unitName",
    "head": "head",
    "business_unit": "businessUnit",
    "functional_block_curator": "functionalBlockCurator",
    # Русские (как в UI)
    "Код оргструктуры": "orgStructureCode",
    "Наименование": "unitName",
    "Руководитель": "head",
    "Бизнес юнит": "businessUnit",
    "Бизнес/блок": "businessUnit",
    "Куратор ф. блока": "functionalBlockCurator",
    "Куратор функционального блока": "functionalBlockCurator",
}

STAFF_HEADER_LOOKUP = _build_header_field_lookup(STAFF_HEADER_TO_FIELD)


def parse_staff_xlsx(content: bytes) -> list[StaffRow]:
    matrix = _read_first_sheet_matrix(content)
    if len(matrix) < 2:
        return []
    col_to_field: dict[int, str] = {}
    for index, cell in enumerate(matrix[0]):
        field = STAFF_HEADER_LOOKUP.get(_normalize_header_for_match(cell))
        if field:
            col_to_field[index] = field
    if not col_to_field:
        raise ValueError(
            "Не найдено ни одной известной колонки. Ожидаются заголовки: "
            "org_structure_code, unit_name, head, business_unit, functional_block_curator "
            "(или русские: «Код оргструктуры», «Наименование», …)."
        )

    empty = {
        "id": "",
        "orgStructureCode": "",
        "unitName": "",
        "head": "",
        "businessUnit": "",
        "functionalBlockCurator": "",
    }
    out: list[StaffRow] = []
    for raw in matrix[1:]:
        row = dict(empty)
        for col_index, field in col_to_field.items():
            cell = raw[col_index] if col_index < len(raw) else None
            row[field] = _normalize_cell(cell)
        if not any(str(v).strip() for k, v in row.items() if k != "id"):
            continue
        rid = (row.get("id") or "").strip()
        if not rid:
            rid = _generate_row_id()
        out.append(
            StaffRow(
                id=rid,
                orgStructureCode=row["orgStructureCode"],
                unitName=row["unitName"],
                head=row["head"],
                businessUnit=row["businessUnit"],
                functionalBlockCurator=row["functionalBlockCurator"],
            )
        )
    return out
