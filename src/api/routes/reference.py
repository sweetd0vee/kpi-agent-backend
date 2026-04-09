from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import BoardGoalRow, LeaderGoalRow, StaffRow
from src.models.reference import ResponsiblesList

router = APIRouter()


@router.get("/responsibles", response_model=ResponsiblesList)
def list_responsibles(db: Session = Depends(get_db)):
    """Список ФИО для подсказок: из целей правления, целей руководителей и штата (без отдельной таблицы leaders)."""
    names: set[str] = set()
    for (ln,) in db.query(BoardGoalRow.last_name).distinct().all():
        if ln and str(ln).strip():
            names.add(str(ln).strip())
    for (ln,) in db.query(LeaderGoalRow.last_name).distinct().all():
        if ln and str(ln).strip():
            names.add(str(ln).strip())
    for (head,) in db.query(StaffRow.head).distinct().all():
        h = str(head or "").strip()
        if h:
            names.add(h)
    return ResponsiblesList(items=sorted(names, key=lambda x: x.lower()))
