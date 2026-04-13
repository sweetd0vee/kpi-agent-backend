"""Детерминированное каскадирование KPI между manager -> deputy."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

from src.services.cascade_repository import CascadeSnapshot


def norm_text(value: object) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def normalize_name(value: object) -> str:
    text = norm_text(value)
    text = re.sub(r"[^a-zа-я0-9\s]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def names_match(left: object, right: object) -> bool:
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 6 and a in b:
        return True
    if len(b) >= 6 and b in a:
        return True
    return False


@dataclass
class CascadeComputationResult:
    report_year: str
    selected_managers: list[str]
    total_managers: int
    total_deputies: int
    warnings: list[str]
    unmatched: list[dict[str, str]]
    items: list[dict[str, object]]


class CascadeService:
    def __init__(self, snapshot: CascadeSnapshot) -> None:
        self.snapshot = snapshot

    def run(
        self,
        *,
        report_year: str = "",
        managers: Optional[list[str]] = None,
        max_items_per_deputy: int = 25,
    ) -> CascadeComputationResult:
        manager_to_deputies = self._build_manager_tree()
        selected = [m.strip() for m in (managers or []) if m and m.strip()]
        if not selected:
            selected = sorted(manager_to_deputies.keys())
        max_per_deputy = max(1, min(max_items_per_deputy, 200))

        all_deputies: set[str] = set()
        items: list[dict[str, object]] = []
        unmatched: list[dict[str, str]] = []
        warnings: list[str] = []

        for manager_name in selected:
            deputies = sorted(manager_to_deputies.get(manager_name, set()))
            if not deputies:
                unmatched.append(
                    {
                        "managerName": manager_name,
                        "reason": "В staff не найдены подчиненные по полю functionalBlockCurator.",
                        "reportYear": report_year,
                    }
                )
                continue
            source_goals = self._build_source_goals_for_manager(manager_name, report_year=report_year)
            if not source_goals:
                unmatched.append(
                    {
                        "managerName": manager_name,
                        "reason": "Не найдены цели в таблицах board/leader/strategy для выбранного руководителя.",
                        "reportYear": report_year,
                    }
                )
                continue

            for deputy_name in deputies:
                all_deputies.add(deputy_name)
                for source in source_goals[:max_per_deputy]:
                    items.append(
                        {
                            "id": str(uuid.uuid4()),
                            "managerName": manager_name,
                            "deputyName": deputy_name,
                            "sourceType": source["sourceType"],
                            "sourceRowId": source["sourceRowId"],
                            "sourceGoalTitle": source["sourceGoalTitle"],
                            "sourceMetric": source["sourceMetric"],
                            "businessUnit": source["businessUnit"],
                            "department": source["department"],
                            "reportYear": source["reportYear"] or report_year,
                            "traceRule": source["traceRule"],
                            "confidence": None,
                        }
                    )

        if not items:
            warnings.append("Каскадирование не дало назначений. Проверьте заполненность staff и целей.")

        return CascadeComputationResult(
            report_year=report_year,
            selected_managers=selected,
            total_managers=len(selected),
            total_deputies=len(all_deputies),
            warnings=warnings,
            unmatched=unmatched,
            items=items,
        )

    def _build_manager_tree(self) -> dict[str, set[str]]:
        tree: dict[str, set[str]] = {}
        for row in self.snapshot.staff_rows:
            manager = str(row.functional_block_curator or "").strip()
            deputy = str(row.head or "").strip()
            if not manager or not deputy:
                continue
            if names_match(manager, deputy):
                continue
            tree.setdefault(manager, set()).add(deputy)
        return tree

    def _build_source_goals_for_manager(self, manager_name: str, report_year: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        year = (report_year or "").strip()
        for row in self.snapshot.leader_rows:
            if year and str(row.report_year or "").strip() != year:
                continue
            if not names_match(row.last_name, manager_name):
                continue
            out.append(
                {
                    "sourceType": "leader",
                    "sourceRowId": row.id,
                    "sourceGoalTitle": str(row.name or ""),
                    "sourceMetric": str(row.year_value or ""),
                    "businessUnit": "",
                    "department": "",
                    "reportYear": str(row.report_year or ""),
                    "traceRule": "match: leader_goals.last_name == manager",
                }
            )

        for row in self.snapshot.board_rows:
            if year and str(row.report_year or "").strip() != year:
                continue
            if not names_match(row.last_name, manager_name):
                continue
            out.append(
                {
                    "sourceType": "board",
                    "sourceRowId": row.id,
                    "sourceGoalTitle": str(row.goal or ""),
                    "sourceMetric": str(row.metric_goals or ""),
                    "businessUnit": str(row.business_unit or ""),
                    "department": str(row.department or ""),
                    "reportYear": str(row.report_year or ""),
                    "traceRule": "match: board_goals.last_name == manager",
                }
            )

        for row in self.snapshot.strategy_rows:
            if not names_match(row.responsible_person_owner, manager_name):
                continue
            out.append(
                {
                    "sourceType": "strategy",
                    "sourceRowId": row.id,
                    "sourceGoalTitle": str(row.goal_objective or row.initiative or ""),
                    "sourceMetric": str(row.kpi or ""),
                    "businessUnit": str(row.business_unit or ""),
                    "department": str(row.segment or ""),
                    "reportYear": year,
                    "traceRule": "match: strategy_goals.responsible_person_owner == manager",
                }
            )

        return out
