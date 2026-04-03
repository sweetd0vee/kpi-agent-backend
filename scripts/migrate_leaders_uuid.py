"""Drop old kpi/ppr tables and migrate leaders.id + board_goals.leader_id to UUID."""
import os
import sys

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from sqlalchemy import text
from src.db.database import engine

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS kpi CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS ppr CASCADE"))

    conn.execute(text("ALTER TABLE board_goals DROP CONSTRAINT IF EXISTS board_goals_leader_id_fkey"))
    conn.execute(text("ALTER TABLE board_goals ALTER COLUMN leader_id TYPE uuid USING leader_id::uuid"))
    conn.execute(text("ALTER TABLE leaders ALTER COLUMN id TYPE uuid USING id::uuid"))
    conn.execute(text(
        "ALTER TABLE board_goals ADD CONSTRAINT board_goals_leader_id_fkey "
        "FOREIGN KEY (leader_id) REFERENCES leaders (id)"
    ))
    conn.commit()

print("Migration done: kpi/ppr dropped, leaders.id and board_goals.leader_id -> uuid")
