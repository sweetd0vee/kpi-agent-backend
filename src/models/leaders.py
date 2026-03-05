from typing import List

from pydantic import BaseModel


class LeaderItem(BaseModel):
    id: str
    name: str


class LeaderCreate(BaseModel):
    name: str


class LeaderList(BaseModel):
    items: List[LeaderItem]
