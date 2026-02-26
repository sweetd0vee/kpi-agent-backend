from typing import List, Optional

from pydantic import BaseModel


class GoalNode(BaseModel):
    id: str
    title: str
    level: Optional[str] = None  # root | subdivision
    subdivision_id: Optional[str] = None
    progress: Optional[float] = None
    status: Optional[str] = None


class GoalEdge(BaseModel):
    source_id: str
    target_id: str


class GoalsHierarchy(BaseModel):
    """Иерархия целей для дерева/sunburst: узлы и рёбра."""
    nodes: List[GoalNode]
    edges: List[GoalEdge]


class DashboardFilters(BaseModel):
    period: Optional[str] = None
    level: Optional[str] = None
    subdivision_id: Optional[str] = None
