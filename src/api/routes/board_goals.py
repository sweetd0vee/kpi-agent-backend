"""API таблицы «Цели правления» (board goals): GET/PUT."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import BoardGoalRow, Leader
from src.models.goal_tables import GoalRow, GoalTable
from src.services.xlsx_goals_import import parse_board_goals_xlsx

router = APIRouter()


def _normalize_fio(s: str) -> str:
    return " ".join((s or "").split()).lower()


def _resolve_leader_id(db: Session, last_name: str) -> Optional[str]:
    """Сопоставляет ФИО строки с `leaders.full_name` (точное и без учёта регистра)."""
    ln = (last_name or "").strip()
    if not ln:
        return None
    leader = db.query(Leader).filter(Leader.full_name == ln).first()
    if leader:
        return str(leader.id)
    leader = (
        db.query(Leader)
        .filter(func.lower(Leader.full_name) == _normalize_fio(ln))
        .first()
    )
    if leader:
        return str(leader.id)
    return None


def _apply_leader_id(row: GoalRow, db: Session) -> GoalRow:
    resolved = _resolve_leader_id(db, row.lastName or "")
    return row.model_copy(update={"leaderId": resolved})


def _db_to_schema(row: BoardGoalRow) -> GoalRow:
    lid = str(row.leader_id) if row.leader_id is not None else None
    return GoalRow(
        id=row.id,
        lastName=row.last_name,
        leaderId=lid,
        businessUnit=row.business_unit or "",
        department=row.department or "",
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


def _sanitize_leader_id(value: Optional[str]) -> Optional[str]:
    """Невалидный UUID ломает INSERT в PostgreSQL; из Excel/ручного ввода часто приходит мусор."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        UUID(s)
    except ValueError:
        return None
    return s


def _schema_to_db(row: GoalRow) -> BoardGoalRow:
    return BoardGoalRow(
        id=row.id,
        last_name=row.lastName or "",
        leader_id=_sanitize_leader_id(row.leaderId),
        business_unit=row.businessUnit or "",
        department=row.department or "",
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


def _enrich_leader_for_response(db: Session, row: GoalRow) -> GoalRow:
    """Если в БД нет leader_id, подставляем по ФИО для ответа API (UI)."""
    if row.leaderId:
        return row
    resolved = _resolve_leader_id(db, row.lastName or "")
    if resolved:
        return row.model_copy(update={"leaderId": resolved})
    return row


@router.get("", response_model=GoalTable)
def get_board_goals_table(db: Session = Depends(get_db)):
    rows = db.query(BoardGoalRow).order_by(BoardGoalRow.id).all()
    out: list[GoalRow] = []
    for r in rows:
        schema = _db_to_schema(r)
        out.append(_enrich_leader_for_response(db, schema))
    return GoalTable(rows=out)


@router.put("", response_model=GoalTable)
def replace_board_goals_table(payload: GoalTable, db: Session = Depends(get_db)):
    unique_rows = _dedupe_rows(payload.rows)
    resolved_rows = [_apply_leader_id(r, db) for r in unique_rows]
    try:
        db.query(BoardGoalRow).delete()
        if resolved_rows:
            for obj in (_schema_to_db(r) for r in resolved_rows):
                db.add(obj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return GoalTable(rows=resolved_rows)


@router.post("/upload", response_model=GoalTable)
async def upload_board_goals_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Загрузить таблицу из .xlsx (первая строка — заголовки, как при импорте во фронте). Полностью заменяет данные, как PUT."""
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Ожидается файл с расширением .xlsx")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")
    try:
        rows = parse_board_goals_xlsx(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать xlsx: {e}") from e
    return replace_board_goals_table(GoalTable(rows=rows), db)
