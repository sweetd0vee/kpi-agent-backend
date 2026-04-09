"""API таблицы «Цели правления» (board goals): GET/PUT."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import BoardGoalRow
from src.models.goal_tables import GoalRow, GoalTable
from src.services.xlsx_goals_import import parse_board_goals_xlsx

router = APIRouter()


def _db_to_schema(row: BoardGoalRow) -> GoalRow:
    return GoalRow(
        id=row.id,
        lastName=row.last_name,
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


def _schema_to_db(row: GoalRow) -> BoardGoalRow:
    return BoardGoalRow(
        id=row.id,
        last_name=row.lastName or "",
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


@router.get("", response_model=GoalTable)
def get_board_goals_table(db: Session = Depends(get_db)):
    rows = db.query(BoardGoalRow).order_by(BoardGoalRow.id).all()
    return GoalTable(rows=[_db_to_schema(r) for r in rows])


@router.put("", response_model=GoalTable)
def replace_board_goals_table(payload: GoalTable, db: Session = Depends(get_db)):
    unique_rows = _dedupe_rows(payload.rows)
    try:
        db.query(BoardGoalRow).delete()
        if unique_rows:
            for obj in (_schema_to_db(r) for r in unique_rows):
                db.add(obj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return GoalTable(rows=unique_rows)


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
