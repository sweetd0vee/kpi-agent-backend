"""
Дашборды: иерархия целей, метрики KPI.
По ТЗ: данные из разбора файла целей и/или из ответа LangGraph (каскадирование).
"""
from typing import Optional

from fastapi import APIRouter, Query

from src.models.goals import GoalsHierarchy

router = APIRouter()


@router.get("/goals", response_model=GoalsHierarchy)
async def get_goals_hierarchy(
    period: Optional[str] = Query(None, description="Период: год/квартал"),
    level: Optional[str] = Query(None, description="Уровень: общие / по подразделениям"),
    subdivision_id: Optional[str] = Query(None, description="ID подразделения (опционально)"),
):
    """
    Иерархия целей для визуализации (дерево, sunburst).
    Корень — цели руководства, ветви — цели подразделений.
    """
    # TODO: выборка из хранилища/результатов каскадирования, фильтры
    return GoalsHierarchy(nodes=[], edges=[])


@router.get("/metrics")
async def get_metrics(
    period: Optional[str] = Query(None),
    subdivision_id: Optional[str] = Query(None),
):
    """Метрики достижения KPI по целям (прогресс, %) для графиков."""
    # TODO: агрегация по целям/подразделениям
    return {"items": []}
