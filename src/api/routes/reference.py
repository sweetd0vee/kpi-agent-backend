from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import Leader
from src.models.reference import ResponsiblesList

router = APIRouter()


@router.get("/responsibles", response_model=ResponsiblesList)
def list_responsibles(db: Session = Depends(get_db)):
    rows = db.query(Leader.full_name).order_by(Leader.full_name).all()
    names = [r[0].strip() for r in rows if r and r[0]]
    return ResponsiblesList(items=names)
