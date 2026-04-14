"""Репозиторий данных для табличного каскадирования целей."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models import (
    BoardGoalRow,
    CascadeRun,
    CascadeRunItem,
    LeaderGoalRow,
    ProcessRegistryRow,
    StaffRow,
    StrategyGoalRow,
)


@dataclass
class CascadeSnapshot:
    board_rows: list[BoardGoalRow]
    leader_rows: list[LeaderGoalRow]
    strategy_rows: list[StrategyGoalRow]
    staff_rows: list[StaffRow]
    process_rows: list[ProcessRegistryRow]


class CascadeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def load_snapshot(self, report_year: str = "") -> CascadeSnapshot:
        year = (report_year or "").strip()
        board_q = self.db.query(BoardGoalRow)
        leader_q = self.db.query(LeaderGoalRow)
        if year:
            board_q = board_q.filter(BoardGoalRow.report_year == year)
            leader_q = leader_q.filter(LeaderGoalRow.report_year == year)
        return CascadeSnapshot(
            board_rows=board_q.order_by(BoardGoalRow.id).all(),
            leader_rows=leader_q.order_by(LeaderGoalRow.id).all(),
            strategy_rows=self.db.query(StrategyGoalRow).order_by(StrategyGoalRow.id).all(),
            staff_rows=self.db.query(StaffRow).order_by(StaffRow.id).all(),
            process_rows=self.db.query(ProcessRegistryRow).order_by(ProcessRegistryRow.id).all(),
        )

    def save_run(
        self,
        *,
        report_year: str,
        managers: list[str],
        status: str,
        warnings: list[str],
        unmatched: list[dict[str, str]],
        items: list[dict[str, object]],
        total_managers: int,
        total_deputies: int,
    ) -> str:
        run_id = str(uuid.uuid4())
        row = CascadeRun(
            id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            report_year=report_year,
            managers_filter=json.dumps(managers, ensure_ascii=False),
            total_managers=total_managers,
            total_deputies=total_deputies,
            total_items=len(items),
            unmatched_count=len(unmatched),
            warnings_json=json.dumps(warnings, ensure_ascii=False),
            unmatched_json=json.dumps(unmatched, ensure_ascii=False),
        )
        self.db.add(row)
        for item in items:
            self.db.add(
                CascadeRunItem(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    manager_name=str(item.get("managerName") or ""),
                    deputy_name=str(item.get("deputyName") or ""),
                    source_type=str(item.get("sourceType") or ""),
                    source_row_id=str(item.get("sourceRowId") or ""),
                    source_goal_title=str(item.get("sourceGoalTitle") or ""),
                    source_metric=str(item.get("sourceMetric") or ""),
                    business_unit=str(item.get("businessUnit") or ""),
                    department=str(item.get("department") or ""),
                    report_year=str(item.get("reportYear") or ""),
                    trace_rule=str(item.get("traceRule") or ""),
                    confidence=(
                        ""
                        if item.get("confidence") is None
                        else str(item.get("confidence"))
                    ),
                )
            )
        self.db.commit()
        return run_id

    def list_runs(self, limit: int = 20) -> list[CascadeRun]:
        size = max(1, min(limit, 200))
        return self.db.query(CascadeRun).order_by(CascadeRun.created_at.desc()).limit(size).all()

    def get_run(self, run_id: str) -> Optional[CascadeRun]:
        return self.db.query(CascadeRun).filter(CascadeRun.id == run_id).first()

    def get_run_items(self, run_id: str) -> list[CascadeRunItem]:
        return self.db.query(CascadeRunItem).filter(CascadeRunItem.run_id == run_id).order_by(CascadeRunItem.id).all()
