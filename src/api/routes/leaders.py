import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import Leader
from src.models.leaders import LeaderCreate, LeaderItem, LeaderList

router = APIRouter()


@router.get("", response_model=LeaderList)
def list_leaders(db: Session = Depends(get_db)):
    items = db.query(Leader).order_by(Leader.full_name).all()
    return LeaderList(items=[LeaderItem(id=item.id, name=item.full_name) for item in items])


@router.post("", response_model=LeaderItem)
def create_leader(payload: LeaderCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="ФИО руководителя обязательно")
    existing = db.query(Leader).filter(Leader.full_name == name).first()
    if existing:
        return LeaderItem(id=existing.id, name=existing.full_name)
    leader = Leader(id=str(uuid.uuid4()), full_name=name)
    db.add(leader)
    db.commit()
    return LeaderItem(id=leader.id, name=leader.full_name)
