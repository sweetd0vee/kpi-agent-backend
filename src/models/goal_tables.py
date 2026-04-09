from typing import List

from pydantic import BaseModel


class GoalRow(BaseModel):
    id: str
    lastName: str = ""
    businessUnit: str = ""
    department: str = ""
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
