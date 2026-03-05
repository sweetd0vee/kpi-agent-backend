import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import Department
from src.models.departments import DepartmentCreate, DepartmentItem, DepartmentList

router = APIRouter()


@router.get("", response_model=DepartmentList)
def list_departments(db: Session = Depends(get_db)):
    items = db.query(Department).order_by(Department.name).all()
    return DepartmentList(items=[DepartmentItem(id=d.id, name=d.name) for d in items])


@router.post("", response_model=DepartmentItem)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название подразделения обязательно")
    existing = db.query(Department).filter(Department.name == name).first()
    if existing:
        return DepartmentItem(id=existing.id, name=existing.name)
    dep = Department(id=str(uuid.uuid4()), name=name)
    db.add(dep)
    db.commit()
    return DepartmentItem(id=dep.id, name=dep.name)
