"""API табличного каскадирования целей (strategy/board/leader/staff)."""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.models.cascade import (
    CascadeFallbackGoal,
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
logger = logging.getLogger(__name__)


def _make_summary(
    *,
    run_id: str,
    created_at: str,
    status: str,
    report_year: str,
    managers: list[str],
    use_llm: bool,
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
        managers=managers,
        useLlm=use_llm,
        totalManagers=total_managers,
        totalDeputies=total_deputies,
        totalItems=total_items,
        unmatchedManagers=unmatched_count,
        warnings=warnings,
    )


def _parse_managers_filter(raw: str) -> tuple[list[str], bool]:
    try:
        parsed = json.loads(raw or "")
    except json.JSONDecodeError:
        return [], False
    if isinstance(parsed, list):
        return [str(x) for x in parsed if str(x).strip()], False
    if isinstance(parsed, dict):
        managers_raw = parsed.get("managers")
        managers = [str(x) for x in managers_raw] if isinstance(managers_raw, list) else []
        use_llm = bool(parsed.get("useLlm"))
        return [m for m in managers if m.strip()], use_llm
    return [], False


@router.post("/run", response_model=CascadeRunResponse)
def run_table_cascade(payload: CascadeRunRequest, db: Session = Depends(get_db)):
    started_at = time.perf_counter()
    logger.info(
        "API /api/cascade/run start: managers=%s useLlm=%s reportYear=%s maxItemsPerDeputy=%s persist=%s",
        len(payload.managers or []),
        payload.useLlm,
        payload.reportYear or "-",
        payload.maxItemsPerDeputy,
        payload.persist,
    )
    repo = CascadeRepository(db)
    snapshot = repo.load_snapshot(report_year=payload.reportYear or "")
    logger.info(
        "Cascade snapshot loaded: board=%s leader=%s strategy=%s staff=%s process_registry=%s",
        len(snapshot.board_rows),
        len(snapshot.leader_rows),
        len(snapshot.strategy_rows),
        len(snapshot.staff_rows),
        len(snapshot.process_rows),
    )
    service = CascadeService(snapshot)
    result = service.run(
        report_year=payload.reportYear or "",
        managers=payload.managers,
        max_items_per_deputy=payload.maxItemsPerDeputy,
        use_llm=payload.useLlm,
    )
    run_id = str(uuid.uuid4())
    created_at = ""
    if payload.persist:
        run_id = repo.save_run(
            report_year=result.report_year,
            managers=result.selected_managers,
            use_llm=payload.useLlm,
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

    response = CascadeRunResponse(
        run=_make_summary(
            run_id=run_id,
            created_at=created_at,
            status="success",
            report_year=result.report_year,
            managers=result.selected_managers,
            use_llm=payload.useLlm,
            total_managers=result.total_managers,
            total_deputies=result.total_deputies,
            total_items=len(result.items),
            unmatched_count=len(result.unmatched),
            warnings=result.warnings,
        ),
        items=[CascadeGoalItem.model_validate(item) for item in result.items],
        unmatched=[CascadeUnmatchedManager.model_validate(item) for item in result.unmatched],
        fallbackGoals=[CascadeFallbackGoal.model_validate(item) for item in result.fallback_goals],
    )
    logger.info(
        "API /api/cascade/run finished in %.2fs: items=%s unmatched=%s totalManagers=%s",
        time.perf_counter() - started_at,
        len(response.items),
        len(response.unmatched),
        response.run.totalManagers,
    )
    return response


@router.get("/runs", response_model=CascadeRunListResponse)
def list_cascade_runs(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(get_db)):
    repo = CascadeRepository(db)
    runs = repo.list_runs(limit=limit)
    out = []
    for row in runs:
        managers, use_llm = _parse_managers_filter(row.managers_filter or "")
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
                managers=managers,
                use_llm=use_llm,
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
    managers, use_llm = _parse_managers_filter(row.managers_filter or "")

    return CascadeRunResponse(
        run=_make_summary(
            run_id=row.id,
            created_at=row.created_at,
            status=row.status,
            report_year=row.report_year,
            managers=managers,
            use_llm=use_llm,
            total_managers=row.total_managers,
            total_deputies=row.total_deputies,
            total_items=row.total_items,
            unmatched_count=row.unmatched_count,
            warnings=[str(w) for w in warnings],
        ),
        items=items,
        unmatched=unmatched,
        fallbackGoals=[],
    )


@router.delete("/runs/{run_id}")
def delete_cascade_run(run_id: str, db: Session = Depends(get_db)):
    repo = CascadeRepository(db)
    deleted = repo.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Запуск каскадирования не найден.")
    return {"ok": True, "runId": run_id}


@router.post("/runs/{run_id}/delete")
def delete_cascade_run_via_post(run_id: str, db: Session = Depends(get_db)):
    """Совместимость для окружений, где DELETE может быть запрещен прокси/шлюзом."""
    repo = CascadeRepository(db)
    deleted = repo.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Запуск каскадирования не найден.")
    return {"ok": True, "runId": run_id}
