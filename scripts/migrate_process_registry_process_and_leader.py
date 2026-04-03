"""Переименование колонок process_registry: process_name -> process, owner_full_name_ref -> leader.

Один раз для PostgreSQL, где таблица уже создана со старыми именами.
На новой БД через create_all колонки уже будут process и leader — скрипт ничего не сделает.

Запуск из каталога kpi-agent-backend:
  python scripts/migrate_process_registry_process_and_leader.py
"""
import os
import sys

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from sqlalchemy import text

from src.db.database import engine

SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'process_registry' AND column_name = 'process_name'
  ) THEN
    ALTER TABLE process_registry RENAME COLUMN process_name TO process;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'process_registry' AND column_name = 'owner_full_name_ref'
  ) THEN
    ALTER TABLE process_registry RENAME COLUMN owner_full_name_ref TO leader;
  END IF;
END $$;
"""

with engine.connect() as conn:
    conn.execute(text(SQL))
    conn.commit()

print("Migration done: process_registry process_name -> process, owner_full_name_ref -> leader (if needed)")
