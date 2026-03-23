"""Эндпоинт для принудительного создания таблиц БД (если не создались при старте)."""
import logging

from fastapi import APIRouter
from sqlalchemy import inspect

from src.db.database import engine, init_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/init")
def create_tables():
    """Создать все таблицы (kpi, ppr, leader_goals, strategy_goals, leaders, departments)."""
    init_db()
    with engine.connect() as conn:
        tables = inspect(conn).get_table_names()
    return {"ok": True, "tables": tables}
