from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import KpiRow, PprRow
from src.models.reference import ResponsiblesList

router = APIRouter()


@router.get("/responsibles", response_model=ResponsiblesList)
def list_responsibles(db: Session = Depends(get_db)):
    kpi_rows = db.query(KpiRow.last_name).distinct().all()
    ppr_rows = db.query(PprRow.last_name).distinct().all()
    names = {r[0].strip() for r in kpi_rows + ppr_rows if r and r[0]}
    return ResponsiblesList(items=sorted(names))
