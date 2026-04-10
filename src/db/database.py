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


def _migrate_drop_leaders_and_board_goals_leader_id(engine: Engine) -> None:
    """Удалить таблицу leaders и колонку board_goals.leader_id (устаревшая схема)."""
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                if "board_goals" in table_names:
                    conn.execute(
                        text(
                            "ALTER TABLE board_goals DROP CONSTRAINT IF EXISTS board_goals_leader_id_fkey"
                        )
                    )
                    cols = {c["name"] for c in inspector.get_columns("board_goals")}
                    if "leader_id" in cols:
                        conn.execute(text("ALTER TABLE board_goals DROP COLUMN leader_id"))
                if "leaders" in table_names:
                    conn.execute(text("DROP TABLE IF EXISTS leaders"))
            logger.info("Схема: таблица leaders и колонка leader_id в board_goals убраны (PostgreSQL)")
            return
        if engine.dialect.name == "sqlite":
            with engine.begin() as conn:
                if "board_goals" in table_names:
                    cols = {c["name"] for c in inspector.get_columns("board_goals")}
                    if "leader_id" in cols:
                        conn.execute(text("ALTER TABLE board_goals DROP COLUMN leader_id"))
                if "leaders" in table_names:
                    conn.execute(text("DROP TABLE IF EXISTS leaders"))
            logger.info("Схема: таблица leaders и колонка leader_id в board_goals убраны (SQLite)")
    except Exception as e:
        logger.warning("Не удалось применить миграцию leaders/leader_id: %s", e)


def _ensure_strategy_goals_schema(engine: Engine) -> None:
    """Добавить недостающие колонки в strategy_goals (старые БД до полей target_value_* и т.п.)."""
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if "strategy_goals" not in tables:
            return
        cols = {c["name"] for c in inspector.get_columns("strategy_goals")}
        expected = {
            "business_unit",
            "segment",
            "strategic_priority",
            "goal_objective",
            "initiative",
            "initiative_type",
            "responsible_person_owner",
            "other_units_involved",
            "budget",
            "start_date",
            "end_date",
            "kpi",
            "unit_of_measure",
            "target_value_2025",
            "target_value_2026",
            "target_value_2027",
        }
        missing = sorted(expected - cols)
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                if "category" in cols:
                    conn.execute(text("ALTER TABLE strategy_goals DROP COLUMN IF EXISTS category"))
                for col in missing:
                    conn.execute(
                        text(
                            f"ALTER TABLE strategy_goals ADD COLUMN IF NOT EXISTS {col} VARCHAR NOT NULL DEFAULT ''"
                        )
                    )
            if missing or "category" in cols:
                logger.info(
                    "strategy_goals: выровнена схема (PostgreSQL), добавлено колонок: %s",
                    len(missing),
                )
            return
        if engine.dialect.name == "sqlite":
            with engine.begin() as conn:
                for col in missing:
                    conn.execute(
                        text(f"ALTER TABLE strategy_goals ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
                    )
            if missing:
                logger.info(
                    "strategy_goals: добавлены колонки (SQLite): %s",
                    ", ".join(missing),
                )
    except Exception as e:
        logger.warning("strategy_goals: не удалось выровнять схему: %s", e)


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
        LeaderGoalRow,
        ProcessRegistryRow,
        StaffRow,
        StrategyGoalRow,
    )

    table_names = list(Base.metadata.tables.keys())
    logger.info("Creating tables: %s", table_names)
    Base.metadata.create_all(bind=engine)
    _migrate_drop_leaders_and_board_goals_leader_id(engine)
    _ensure_staff_business_unit_column(engine)
    _ensure_strategy_goals_schema(engine)
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
