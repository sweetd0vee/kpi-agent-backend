"""Pydantic-модели для API «Реестр процессов»."""

from typing import List

from pydantic import BaseModel


class ProcessRegistryRow(BaseModel):
    id: str
    processArea: str = ""
    processCode: str = ""
    process: str = ""
    processOwner: str = ""
    leader: str = ""
    businessUnit: str = ""
    top20: str = ""


class ProcessRegistryTable(BaseModel):
    rows: List[ProcessRegistryRow]
