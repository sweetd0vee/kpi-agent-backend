"""API таблицы «Руководители» (leader goals): GET/PUT по аналогии с KPI и PPR."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import LeaderGoalRow as LeaderGoalRowDb
from src.models.leader_goal_tables import LeaderGoalRow, LeaderGoalTable
from src.services.xlsx_goals_import import parse_leader_goals_xlsx

router = APIRouter()


def _db_to_schema(row: LeaderGoalRowDb) -> LeaderGoalRow:
    return LeaderGoalRow(
        id=row.id,
        lastName=row.last_name or "",
        goalNum=row.goal_num or "",
        name=row.name or "",
        goalType=row.goal_type or "",
        goalKind=row.goal_kind or "",
        unit=row.unit or "",
        q1Weight=row.q1_weight or "",
        q1Value=row.q1_value or "",
        q2Weight=row.q2_weight or "",
        q2Value=row.q2_value or "",
        q3Weight=row.q3_weight or "",
        q3Value=row.q3_value or "",
        q4Weight=row.q4_weight or "",
        q4Value=row.q4_value or "",
        yearWeight=row.year_weight or "",
        yearValue=row.year_value or "",
        comments=row.comments or "",
        methodDesc=row.method_desc or "",
        sourceInfo=row.source_info or "",
        reportYear=row.report_year or "",
    )


def _schema_to_db(row: LeaderGoalRow) -> LeaderGoalRowDb:
    return LeaderGoalRowDb(
        id=row.id,
        last_name=row.lastName or "",
        goal_num=row.goalNum or "",
        name=row.name or "",
        goal_type=row.goalType or "",
        goal_kind=row.goalKind or "",
        unit=row.unit or "",
        q1_weight=row.q1Weight or "",
        q1_value=row.q1Value or "",
        q2_weight=row.q2Weight or "",
        q2_value=row.q2Value or "",
        q3_weight=row.q3Weight or "",
        q3_value=row.q3Value or "",
        q4_weight=row.q4Weight or "",
        q4_value=row.q4Value or "",
        year_weight=row.yearWeight or "",
        year_value=row.yearValue or "",
        comments=row.comments or "",
        method_desc=row.methodDesc or "",
        source_info=row.sourceInfo or "",
        report_year=row.reportYear or "",
    )


def _dedupe_rows(rows: list[LeaderGoalRow]) -> list[LeaderGoalRow]:
    unique_rows: list[LeaderGoalRow] = []
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


@router.get("", response_model=LeaderGoalTable)
def get_leader_goals_table(db: Session = Depends(get_db)):
    """Вернуть все строки таблицы «Руководители»."""
    rows = db.query(LeaderGoalRowDb).order_by(LeaderGoalRowDb.id).all()
    return LeaderGoalTable(rows=[_db_to_schema(row) for row in rows])


@router.put("", response_model=LeaderGoalTable)
def replace_leader_goals_table(payload: LeaderGoalTable, db: Session = Depends(get_db)):
    """Полностью заменить таблицу «Руководители» переданными строками."""
    unique_rows = _dedupe_rows(payload.rows)
    try:
        db.query(LeaderGoalRowDb).delete()
        if unique_rows:
            for obj in (_schema_to_db(row) for row in unique_rows):
                db.add(obj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return LeaderGoalTable(rows=unique_rows)


@router.post("/upload", response_model=LeaderGoalTable)
async def upload_leader_goals_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Загрузить таблицу целей руководителей из .xlsx. Полностью заменяет данные, как PUT."""
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Ожидается файл с расширением .xlsx")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")
    try:
        rows = parse_leader_goals_xlsx(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать xlsx: {e}") from e
    return replace_leader_goals_table(LeaderGoalTable(rows=rows), db)
