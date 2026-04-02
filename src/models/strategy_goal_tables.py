"""Pydantic-модели для API таблицы стратегических целей (strategy goals)."""

from typing import List

from pydantic import BaseModel


class StrategyGoalRow(BaseModel):
    id: str
    businessUnit: str = ""
    segment: str = ""
    strategicPriority: str = ""
    goalObjective: str = ""
    initiative: str = ""
    initiativeType: str = ""
    responsiblePersonOwner: str = ""
    otherUnitsInvolved: str = ""
    budget: str = ""
    startDate: str = ""
    endDate: str = ""
    kpi: str = ""
    unitOfMeasure: str = ""
    targetValue2025: str = ""
    targetValue2026: str = ""
    targetValue2027: str = ""


class StrategyGoalTable(BaseModel):
    rows: List[StrategyGoalRow]
