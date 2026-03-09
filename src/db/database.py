import logging

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.core.config import settings

logger = logging.getLogger(__name__)


def _build_engine() -> Engine:
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        future=True,
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Импорт всех моделей регистрирует таблицы в Base.metadata (kpi, ppr, leaders, departments)
    from .models import Department, KpiRow, Leader, LeaderGoalRow, PprRow  # noqa: F401

    table_names = list(Base.metadata.tables.keys())
    logger.info("Creating tables: %s", table_names)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        inspector = inspect(conn)
        existing = inspector.get_table_names()
    logger.info("Tables in DB after create_all: %s", existing)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
