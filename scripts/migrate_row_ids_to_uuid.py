"""Перевод колонки id с VARCHAR на UUID (PostgreSQL 13+).

Таблицы: board_goals, leader_goals, strategy_goals, process_registry, staff.
Для каждой строки задаётся новый UUID (старые строковые id не сохраняются).

Запуск из каталога kpi-agent-backend:
  python scripts/migrate_row_ids_to_uuid.py

Остановите приложение на время миграции. После миграции обновите страницы в браузере.
"""
import os
import sys

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from sqlalchemy import text

from src.db.database import engine

TABLES = (
    "board_goals",
    "leader_goals",
    "strategy_goals",
    "process_registry",
    "staff",
)


def main() -> None:
    with engine.connect() as conn:
        for table in TABLES:
            conn.execute(
                text(
                    f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = '{table}'
      AND column_name = 'id'
      AND udt_name = 'varchar'
  ) THEN
    ALTER TABLE {table} ALTER COLUMN id TYPE uuid USING gen_random_uuid();
  END IF;
END $$;
"""
                )
            )
        conn.commit()
    print("Migration done: id -> uuid for", ", ".join(TABLES), "(where column was varchar)")


if __name__ == "__main__":
    main()
