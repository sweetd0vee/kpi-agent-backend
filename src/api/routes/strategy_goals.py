"""API таблицы «Цели стратегии»: GET/PUT по аналогии с KPI и PPR."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import StrategyGoalRow as StrategyGoalRowDb
from src.models.strategy_goal_tables import StrategyGoalRow, StrategyGoalTable
from src.services.xlsx_goals_import import parse_strategy_goals_xlsx

router = APIRouter()


def _db_to_schema(row: StrategyGoalRowDb) -> StrategyGoalRow:
    return StrategyGoalRow(
        id=row.id,
        businessUnit=row.business_unit or "",
        segment=row.segment or "",
        strategicPriority=row.strategic_priority or "",
        goalObjective=row.goal_objective or "",
        initiative=row.initiative or "",
        initiativeType=row.initiative_type or "",
        responsiblePersonOwner=row.responsible_person_owner or "",
        otherUnitsInvolved=row.other_units_involved or "",
        budget=row.budget or "",
        startDate=row.start_date or "",
        endDate=row.end_date or "",
        kpi=row.kpi or "",
        unitOfMeasure=row.unit_of_measure or "",
        targetValue2025=row.target_value_2025 or "",
        targetValue2026=row.target_value_2026 or "",
        targetValue2027=row.target_value_2027 or "",
    )


def _schema_to_db(row: StrategyGoalRow) -> StrategyGoalRowDb:
    return StrategyGoalRowDb(
        id=row.id,
        business_unit=row.businessUnit or "",
        segment=row.segment or "",
        strategic_priority=row.strategicPriority or "",
        goal_objective=row.goalObjective or "",
        initiative=row.initiative or "",
        initiative_type=row.initiativeType or "",
        responsible_person_owner=row.responsiblePersonOwner or "",
        other_units_involved=row.otherUnitsInvolved or "",
        budget=row.budget or "",
        start_date=row.startDate or "",
        end_date=row.endDate or "",
        kpi=row.kpi or "",
        unit_of_measure=row.unitOfMeasure or "",
        target_value_2025=row.targetValue2025 or "",
        target_value_2026=row.targetValue2026 or "",
        target_value_2027=row.targetValue2027 or "",
    )


def _dedupe_rows(rows: list[StrategyGoalRow]) -> list[StrategyGoalRow]:
    unique_rows: list[StrategyGoalRow] = []
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


@router.get("", response_model=StrategyGoalTable)
def get_strategy_goals_table(db: Session = Depends(get_db)):
    rows = db.query(StrategyGoalRowDb).order_by(StrategyGoalRowDb.id).all()
    return StrategyGoalTable(rows=[_db_to_schema(row) for row in rows])


@router.put("", response_model=StrategyGoalTable)
def replace_strategy_goals_table(payload: StrategyGoalTable, db: Session = Depends(get_db)):
    unique_rows = _dedupe_rows(payload.rows)
    try:
        db.query(StrategyGoalRowDb).delete()
        if unique_rows:
            for obj in (_schema_to_db(row) for row in unique_rows):
                db.add(obj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return StrategyGoalTable(rows=unique_rows)


@router.post("/upload", response_model=StrategyGoalTable)
async def upload_strategy_goals_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Загрузить таблицу «Цели стратегии» из .xlsx. Полностью заменяет данные, как PUT."""
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Ожидается файл с расширением .xlsx")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")
    try:
        rows = parse_strategy_goals_xlsx(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать xlsx: {e}") from e
    return replace_strategy_goals_table(StrategyGoalTable(rows=rows), db)
