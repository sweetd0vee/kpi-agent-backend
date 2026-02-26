"""
Типы документов базы знаний и схемы JSON для предобработки LLM.
Используются для каскадирования целей: от целей председателя → к целям директоров департаментов.
"""
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Типы загружаемых документов (коллекции по типу)."""
    CHAIRMAN_GOALS = "chairman_goals"           # Цели председателя банка
    STRATEGY_CHECKLIST = "strategy_checklist"   # Чеклист по стратегии банка
    REGLAMENT_CHECKLIST = "reglament_checklist" # Чеклист по регламенту банка
    DEPARTMENT_GOALS_CHECKLIST = "department_goals_checklist"  # Чеклист по целям департамента
    BUSINESS_PLAN_CHECKLIST = "business_plan_checklist"        # Чеклист по бизнес-плану
    GOALS_TABLE = "goals_table"                 # Таблица целей (форма) — результат LLM


# --- Схемы JSON (примеры структуры после предобработки) ---

class QuarterlyValue(BaseModel):
    q1: Optional[str] = None
    q2: Optional[str] = None
    q3: Optional[str] = None
    q4: Optional[str] = None
    year: Optional[str] = None


class ChairmanGoalItem(BaseModel):
    id: str
    title: str
    weight_percent: Optional[float] = None
    quarters: Optional[QuarterlyValue] = None
    unit: Optional[str] = None
    category: Optional[str] = None  # financial, ppr, etc.


class ChairmanGoalsJson(BaseModel):
    """JSON после предобработки целей председателя."""
    period: Optional[str] = None
    subdivision: Optional[str] = None
    position: Optional[str] = None
    goals: List[ChairmanGoalItem] = Field(default_factory=list)
    total_weight_kpe: Optional[float] = None
    total_weight_ppr: Optional[float] = None


class ChecklistItem(BaseModel):
    id: str
    text: str
    section: Optional[str] = None
    checked: bool = False


class StrategyChecklistJson(BaseModel):
    items: List[ChecklistItem] = Field(default_factory=list)
    sections: List[str] = Field(default_factory=list)


class ReglamentChecklistJson(BaseModel):
    rules: List[ChecklistItem] = Field(default_factory=list)


class DepartmentGoalsChecklistJson(BaseModel):
    department: Optional[str] = None
    goals: List[ChecklistItem] = Field(default_factory=list)
    tasks: List[ChecklistItem] = Field(default_factory=list)


class BusinessPlanChecklistJson(BaseModel):
    items: List[ChecklistItem] = Field(default_factory=list)
    sections: List[str] = Field(default_factory=list)


class GoalsTableRow(BaseModel):
    goal_number: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None  # типовая/групповая/индивидуальная
    kind: Optional[str] = None  # вид цели
    unit: Optional[str] = None
    q1_weight: Optional[str] = None
    q1_value: Optional[str] = None
    q2_weight: Optional[str] = None
    q2_value: Optional[str] = None
    q3_weight: Optional[str] = None
    q3_value: Optional[str] = None
    q4_weight: Optional[str] = None
    q4_value: Optional[str] = None
    year_weight: Optional[str] = None
    year_value: Optional[str] = None
    comments: Optional[str] = None
    methodology: Optional[str] = None
    source: Optional[str] = None


class GoalsTableJson(BaseModel):
    """Таблица целей (форма) — по шаблону lead_goals_template."""
    subdivision: Optional[str] = None
    position: Optional[str] = None
    period: Optional[str] = None
    rows: List[GoalsTableRow] = Field(default_factory=list)


# Для хранения произвольного JSON от LLM (если схема не совпадает)
ParsedKnowledgeDoc = dict[str, Any]
