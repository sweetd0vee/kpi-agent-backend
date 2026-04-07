import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.core.config import settings

logger = logging.getLogger(__name__)

# Одноразовое выравнивание схемы: старые БД имели staff.functional_block вместо business_unit.
_STAFF_RENAME_FUNCTIONAL_BLOCK_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'staff' AND column_name = 'functional_block'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'staff' AND column_name = 'business_unit'
  ) THEN
    ALTER TABLE staff RENAME COLUMN functional_block TO business_unit;
  END IF;
END $$;
"""


def _ensure_staff_business_unit_column(engine: Engine) -> None:
    """Переименовать staff.functional_block → business_unit (старые БД)."""
    try:
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                conn.execute(text(_STAFF_RENAME_FUNCTIONAL_BLOCK_SQL))
            logger.info("staff: проверка колонки business_unit (PostgreSQL) выполнена")
            return
        if engine.dialect.name == "sqlite":
            with engine.connect() as conn:
                rows = conn.execute(text("PRAGMA table_info(staff)")).fetchall()
                if not rows:
                    return
                names = {r[1] for r in rows}
                if "functional_block" in names and "business_unit" not in names:
                    conn.execute(text("ALTER TABLE staff RENAME COLUMN functional_block TO business_unit"))
                    conn.commit()
                    logger.info("staff: колонка functional_block переименована в business_unit (SQLite)")
    except Exception as e:
        logger.warning("staff: не удалось применить миграцию колонки business_unit: %s", e)


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
    # Импорт всех моделей регистрирует таблицы в Base.metadata.
    from .models import (  # noqa: F401
        BoardGoalRow,
        Leader,
        LeaderGoalRow,
        ProcessRegistryRow,
        StaffRow,
        StrategyGoalRow,
    )

    table_names = list(Base.metadata.tables.keys())
    logger.info("Creating tables: %s", table_names)
    Base.metadata.create_all(bind=engine)
    _ensure_staff_business_unit_column(engine)
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
