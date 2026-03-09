"""Pydantic-модели для API таблицы «Руководители» (leader goals)."""

from typing import List

from pydantic import BaseModel


class LeaderGoalRow(BaseModel):
    """Строка таблицы целей руководителя (форма по шаблону)."""

    id: str
    lastName: str = ""
    goalNum: str = ""
    name: str = ""
    goalType: str = ""
    goalKind: str = ""
    unit: str = ""
    q1Weight: str = ""
    q1Value: str = ""
    q2Weight: str = ""
    q2Value: str = ""
    q3Weight: str = ""
    q3Value: str = ""
    q4Weight: str = ""
    q4Value: str = ""
    yearWeight: str = ""
    yearValue: str = ""
    comments: str = ""
    methodDesc: str = ""
    sourceInfo: str = ""
    reportYear: str = ""


class LeaderGoalTable(BaseModel):
    """Тело ответа/запроса: список строк таблицы «Руководители»."""

    rows: List[LeaderGoalRow]
