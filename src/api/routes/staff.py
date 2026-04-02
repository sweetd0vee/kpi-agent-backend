"""API таблицы «staff» (оргструктура): GET/PUT по аналогии с реестром процессов."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import StaffRow as StaffRowDb
from src.models.staff_tables import StaffRow, StaffTable

router = APIRouter()


def _db_to_schema(row: StaffRowDb) -> StaffRow:
    return StaffRow(
        id=row.id,
        orgStructureCode=row.org_structure_code or "",
        unitName=row.unit_name or "",
        head=row.head or "",
        functionalBlock=row.functional_block or "",
        functionalBlockCurator=row.functional_block_curator or "",
    )


def _schema_to_db(row: StaffRow) -> StaffRowDb:
    return StaffRowDb(
        id=row.id,
        org_structure_code=row.orgStructureCode or "",
        unit_name=row.unitName or "",
        head=row.head or "",
        functional_block=row.functionalBlock or "",
        functional_block_curator=row.functionalBlockCurator or "",
    )


def _dedupe_rows(rows: list[StaffRow]) -> list[StaffRow]:
    unique_rows: list[StaffRow] = []
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


@router.get("", response_model=StaffTable)
def get_staff_table(db: Session = Depends(get_db)):
    rows = db.query(StaffRowDb).order_by(StaffRowDb.id).all()
    return StaffTable(rows=[_db_to_schema(row) for row in rows])


@router.put("", response_model=StaffTable)
def replace_staff_table(payload: StaffTable, db: Session = Depends(get_db)):
    unique_rows = _dedupe_rows(payload.rows)
    try:
        db.query(StaffRowDb).delete()
        if unique_rows:
            for obj in (_schema_to_db(row) for row in unique_rows):
                db.add(obj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return StaffTable(rows=unique_rows)
