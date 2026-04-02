"""Pydantic-модели для API таблицы «staff» (оргструктура)."""

from typing import List

from pydantic import BaseModel


class StaffRow(BaseModel):
    id: str
    orgStructureCode: str = ""
    unitName: str = ""
    head: str = ""
    functionalBlock: str = ""
    functionalBlockCurator: str = ""


class StaffTable(BaseModel):
    rows: List[StaffRow]
