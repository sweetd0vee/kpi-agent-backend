from typing import List

from pydantic import BaseModel


class DepartmentItem(BaseModel):
    id: str
    name: str


class DepartmentCreate(BaseModel):
    name: str


class DepartmentList(BaseModel):
    items: List[DepartmentItem]
