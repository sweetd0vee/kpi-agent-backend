"""Удалить таблицу leaders и колонку board_goals.leader_id.

То же действие выполняется при старте приложения в init_db().
Скрипт удобен для ручного запуска против существующей БД.

Запуск из каталога kpi-agent-backend:
  python scripts/migrate_drop_leaders.py
"""

import os
import sys

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from sqlalchemy import create_engine, inspect, text

from src.core.config import settings


def main() -> None:
    engine = create_engine(settings.database_url, future=True)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    dialect = engine.dialect.name

    if dialect == "postgresql":
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
        print("OK: PostgreSQL — leaders и leader_id удалены.")
        return

    if dialect == "sqlite":
        with engine.begin() as conn:
            if "board_goals" in table_names:
                cols = {c["name"] for c in inspector.get_columns("board_goals")}
                if "leader_id" in cols:
                    conn.execute(text("ALTER TABLE board_goals DROP COLUMN leader_id"))
            if "leaders" in table_names:
                conn.execute(text("DROP TABLE IF EXISTS leaders"))
        print("OK: SQLite — leaders и leader_id удалены.")
        return

    print(f"Пропуск: неизвестный dialect {dialect}")


if __name__ == "__main__":
    main()
