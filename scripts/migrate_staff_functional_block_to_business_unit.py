"""Переименование колонки staff.functional_block -> business_unit (PostgreSQL).

Выполнить один раз на БД, где таблица staff уже создана со старым именем колонки.
На пустой БД, созданной заново через create_all, скрипт не нужен.

Запуск из каталога kpi-agent-backend:
  python scripts/migrate_staff_functional_block_to_business_unit.py
"""
import os
import sys

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from sqlalchemy import text

from src.db.database import engine

RENAME_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'staff' AND column_name = 'functional_block'
  ) THEN
    ALTER TABLE staff RENAME COLUMN functional_block TO business_unit;
  END IF;
END $$;
"""

with engine.connect() as conn:
    conn.execute(text(RENAME_SQL))
    conn.commit()

print("Migration done: staff.functional_block -> business_unit (if column existed)")
