from typing import List, Optional

from pydantic import BaseModel


class GoalRow(BaseModel):
    id: str
    lastName: str = ""
    leaderId: Optional[str] = None
    goal: str = ""
    metricGoals: str = ""
    weightQ: str = ""
    weightYear: str = ""
    q1: str = ""
    q2: str = ""
    q3: str = ""
    q4: str = ""
    year: str = ""
    reportYear: str = ""


class GoalTable(BaseModel):
    rows: List[GoalRow]
