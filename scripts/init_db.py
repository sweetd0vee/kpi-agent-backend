"""
Создание таблиц БД (board_goals, leader_goals, strategy_goals, process_registry, staff, leaders).
Запуск из каталога kpi-agent-backend:
  python scripts/init_db.py
Или из любого места:
  python C:\path\to\kpi-agent-backend\scripts\init_db.py
"""
import os
import sys

# Корень backend (где лежит src/) — чтобы импорт src.db работал при запуске из любого места
_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

def main():
    from src.db.database import init_db
    init_db()
    print("Таблицы созданы: board_goals, leader_goals, strategy_goals, process_registry, staff, leaders")

if __name__ == "__main__":
    main()
