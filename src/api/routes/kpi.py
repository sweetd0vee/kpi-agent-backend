from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import KpiRow
from src.models.goal_tables import GoalRow, GoalTable

router = APIRouter()


def _db_to_schema(row: KpiRow) -> GoalRow:
    return GoalRow(
        id=row.id,
        lastName=row.last_name,
        goal=row.goal,
        metricGoals=row.metric_goals,
        weightQ=row.weight_q,
        weightYear=row.weight_year,
        q1=row.q1,
        q2=row.q2,
        q3=row.q3,
        q4=row.q4,
        year=row.year,
        reportYear=row.report_year,
    )


def _schema_to_db(row: GoalRow) -> KpiRow:
    return KpiRow(
        id=row.id,
        last_name=row.lastName or "",
        goal=row.goal or "",
        metric_goals=row.metricGoals or "",
        weight_q=row.weightQ or "",
        weight_year=row.weightYear or "",
        q1=row.q1 or "",
        q2=row.q2 or "",
        q3=row.q3 or "",
        q4=row.q4 or "",
        year=row.year or "",
        report_year=row.reportYear or "",
    )


def _dedupe_rows(rows: list[GoalRow]) -> list[GoalRow]:
    unique_rows: list[GoalRow] = []
    seen: set[str] = set()
    for row in reversed(rows):
        row_id = row.id.strip() if isinstance(row.id, str) else ""
        if not row_id:
            raise HTTPException(status_code=400, detail="Поле id обязательно для всех строк")
        if row_id in seen:
            continue
        seen.add(row_id)
        unique_rows.append(row)
    unique_rows.reverse()
    return unique_rows


@router.get("", response_model=GoalTable)
def get_kpi_table(db: Session = Depends(get_db)):
    rows = db.query(KpiRow).order_by(KpiRow.id).all()
    return GoalTable(rows=[_db_to_schema(row) for row in rows])


@router.put("", response_model=GoalTable)
def replace_kpi_table(payload: GoalTable, db: Session = Depends(get_db)):
    unique_rows = _dedupe_rows(payload.rows)
    try:
        db.query(KpiRow).delete()
        if unique_rows:
            db.bulk_save_objects([_schema_to_db(row) for row in unique_rows])
        db.commit()
    except Exception:
        db.rollback()
        raise
    return GoalTable(rows=unique_rows)
