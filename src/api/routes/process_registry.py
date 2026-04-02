"""API таблицы «Реестр процессов»: GET/PUT по аналогии с целями стратегии."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.db.database import get_db
from src.db.models import ProcessRegistryRow as ProcessRegistryRowDb
from src.models.process_registry_tables import ProcessRegistryRow, ProcessRegistryTable
from src.services.xlsx_process_registry_import import parse_process_registry_xlsx

router = APIRouter()


def _db_to_schema(row: ProcessRegistryRowDb) -> ProcessRegistryRow:
    return ProcessRegistryRow(
        id=row.id,
        processArea=row.process_area or "",
        processCode=row.process_code or "",
        processName=row.process_name or "",
        processOwner=row.process_owner or "",
        ownerFullNameRef=row.owner_full_name_ref or "",
        businessUnit=row.business_unit or "",
        top20=row.top_20 or "",
    )


def _schema_to_db(row: ProcessRegistryRow) -> ProcessRegistryRowDb:
    return ProcessRegistryRowDb(
        id=row.id,
        process_area=row.processArea or "",
        process_code=row.processCode or "",
        process_name=row.processName or "",
        process_owner=row.processOwner or "",
        owner_full_name_ref=row.ownerFullNameRef or "",
        business_unit=row.businessUnit or "",
        top_20=row.top20 or "",
    )


def _dedupe_rows(rows: list[ProcessRegistryRow]) -> list[ProcessRegistryRow]:
    unique_rows: list[ProcessRegistryRow] = []
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


@router.get("", response_model=ProcessRegistryTable)
def get_process_registry_table(db: Session = Depends(get_db)):
    rows = db.query(ProcessRegistryRowDb).order_by(ProcessRegistryRowDb.id).all()
    return ProcessRegistryTable(rows=[_db_to_schema(row) for row in rows])


@router.put("", response_model=ProcessRegistryTable)
def replace_process_registry_table(payload: ProcessRegistryTable, db: Session = Depends(get_db)):
    unique_rows = _dedupe_rows(payload.rows)
    try:
        db.query(ProcessRegistryRowDb).delete()
        if unique_rows:
            for obj in (_schema_to_db(row) for row in unique_rows):
                db.add(obj)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ProcessRegistryTable(rows=unique_rows)


@router.post("/upload", response_model=ProcessRegistryTable)
async def upload_process_registry_xlsx(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Загрузить «Реестр процессов» из .xlsx. Полностью заменяет данные, как PUT."""
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Ожидается файл с расширением .xlsx")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")
    try:
        rows = parse_process_registry_xlsx(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать xlsx: {e}") from e
    return replace_process_registry_table(ProcessRegistryTable(rows=rows), db)
