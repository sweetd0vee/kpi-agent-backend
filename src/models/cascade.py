"""Pydantic-модели API для табличного каскадирования целей."""

from typing import List, Optional

from pydantic import BaseModel, Field


class CascadeRunRequest(BaseModel):
    reportYear: Optional[str] = ""
    managers: List[str] = Field(default_factory=list)
    persist: bool = True
    useLlm: bool = True
    maxItemsPerDeputy: int = 25


class CascadeGoalItem(BaseModel):
    id: str
    managerName: str
    deputyName: str
    sourceType: str
    sourceRowId: str
    sourceGoalTitle: str = ""
    sourceMetric: str = ""
    businessUnit: str = ""
    department: str = ""
    reportYear: str = ""
    traceRule: str = ""
    confidence: Optional[float] = None


class CascadeUnmatchedManager(BaseModel):
    managerName: str
    reason: str
    reportYear: str = ""


class CascadeFallbackGoal(BaseModel):
    id: str
    managerName: str
    deputyName: str = ""
    sourceType: str
    sourceRowId: str
    sourceGoalTitle: str = ""
    sourceMetric: str = ""
    businessUnit: str = ""
    department: str = ""
    reportYear: str = ""
    reason: str = ""


class CascadeRunSummary(BaseModel):
    runId: str
    createdAt: str
    status: str
    reportYear: str = ""
    totalManagers: int
    totalDeputies: int
    totalItems: int
    unmatchedManagers: int
    warnings: List[str] = Field(default_factory=list)


class CascadeRunResponse(BaseModel):
    run: CascadeRunSummary
    items: List[CascadeGoalItem]
    unmatched: List[CascadeUnmatchedManager]
    fallbackGoals: List[CascadeFallbackGoal] = Field(default_factory=list)


class CascadeRunListResponse(BaseModel):
    runs: List[CascadeRunSummary]
