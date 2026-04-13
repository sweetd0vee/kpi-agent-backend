"""API табличного каскадирования целей (strategy/board/leader/staff)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.models.cascade import (
    CascadeGoalItem,
    CascadeRunListResponse,
    CascadeRunRequest,
    CascadeRunResponse,
    CascadeRunSummary,
    CascadeUnmatchedManager,
)
from src.services.cascade_repository import CascadeRepository
from src.services.cascade_service import CascadeService

router = APIRouter()


def _make_summary(
    *,
    run_id: str,
    created_at: str,
    status: str,
    report_year: str,
    total_managers: int,
    total_deputies: int,
    total_items: int,
    unmatched_count: int,
    warnings: list[str],
) -> CascadeRunSummary:
    return CascadeRunSummary(
        runId=run_id,
        createdAt=created_at,
        status=status,
        reportYear=report_year,
        totalManagers=total_managers,
        totalDeputies=total_deputies,
        totalItems=total_items,
        unmatchedManagers=unmatched_count,
        warnings=warnings,
    )


@router.post("/run", response_model=CascadeRunResponse)
def run_table_cascade(payload: CascadeRunRequest, db: Session = Depends(get_db)):
    repo = CascadeRepository(db)
    snapshot = repo.load_snapshot(report_year=payload.reportYear or "")
    service = CascadeService(snapshot)
    result = service.run(
        report_year=payload.reportYear or "",
        managers=payload.managers,
        max_items_per_deputy=payload.maxItemsPerDeputy,
    )
    run_id = str(uuid.uuid4())
    created_at = ""
    if payload.persist:
        run_id = repo.save_run(
            report_year=result.report_year,
            managers=result.selected_managers,
            status="success",
            warnings=result.warnings,
            unmatched=result.unmatched,
            items=result.items,
            total_managers=result.total_managers,
            total_deputies=result.total_deputies,
        )
        saved = repo.get_run(run_id)
        created_at = saved.created_at if saved else ""

    if not created_at:
        from datetime import datetime, timezone

        created_at = datetime.now(timezone.utc).isoformat()

    return CascadeRunResponse(
        run=_make_summary(
            run_id=run_id,
            created_at=created_at,
            status="success",
            report_year=result.report_year,
            total_managers=result.total_managers,
            total_deputies=result.total_deputies,
            total_items=len(result.items),
            unmatched_count=len(result.unmatched),
            warnings=result.warnings,
        ),
        items=[CascadeGoalItem.model_validate(item) for item in result.items],
        unmatched=[CascadeUnmatchedManager.model_validate(item) for item in result.unmatched],
    )


@router.get("/runs", response_model=CascadeRunListResponse)
def list_cascade_runs(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(get_db)):
    repo = CascadeRepository(db)
    runs = repo.list_runs(limit=limit)
    out = []
    for row in runs:
        try:
            warnings = json.loads(row.warnings_json or "[]")
            if not isinstance(warnings, list):
                warnings = []
        except json.JSONDecodeError:
            warnings = []
        out.append(
            _make_summary(
                run_id=row.id,
                created_at=row.created_at,
                status=row.status,
                report_year=row.report_year,
                total_managers=row.total_managers,
                total_deputies=row.total_deputies,
                total_items=row.total_items,
                unmatched_count=row.unmatched_count,
                warnings=[str(w) for w in warnings],
            )
        )
    return CascadeRunListResponse(runs=out)


@router.get("/runs/{run_id}", response_model=CascadeRunResponse)
def get_cascade_run(run_id: str, db: Session = Depends(get_db)):
    repo = CascadeRepository(db)
    row = repo.get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Запуск каскадирования не найден.")

    try:
        warnings = json.loads(row.warnings_json or "[]")
        if not isinstance(warnings, list):
            warnings = []
    except json.JSONDecodeError:
        warnings = []
    try:
        unmatched_raw = json.loads(row.unmatched_json or "[]")
        if not isinstance(unmatched_raw, list):
            unmatched_raw = []
    except json.JSONDecodeError:
        unmatched_raw = []

    items = [
        CascadeGoalItem(
            id=item.id,
            managerName=item.manager_name,
            deputyName=item.deputy_name,
            sourceType=item.source_type,
            sourceRowId=item.source_row_id,
            sourceGoalTitle=item.source_goal_title,
            sourceMetric=item.source_metric,
            businessUnit=item.business_unit,
            department=item.department,
            reportYear=item.report_year,
            traceRule=item.trace_rule,
            confidence=float(item.confidence) if item.confidence else None,
        )
        for item in repo.get_run_items(run_id)
    ]
    unmatched = [CascadeUnmatchedManager.model_validate(x) for x in unmatched_raw]

    return CascadeRunResponse(
        run=_make_summary(
            run_id=row.id,
            created_at=row.created_at,
            status=row.status,
            report_year=row.report_year,
            total_managers=row.total_managers,
            total_deputies=row.total_deputies,
            total_items=row.total_items,
            unmatched_count=row.unmatched_count,
            warnings=[str(w) for w in warnings],
        ),
        items=items,
        unmatched=unmatched,
    )
