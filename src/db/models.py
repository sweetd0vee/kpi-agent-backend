from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class GoalRowMixin:
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_name: Mapped[str] = mapped_column(String, default="", nullable=False)
    leader_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("leaders.id"),
        nullable=True,
    )
    goal: Mapped[str] = mapped_column(String, default="", nullable=False)
    metric_goals: Mapped[str] = mapped_column(String, default="", nullable=False)
    weight_q: Mapped[str] = mapped_column(String, default="", nullable=False)
    weight_year: Mapped[str] = mapped_column(String, default="", nullable=False)
    q1: Mapped[str] = mapped_column(String, default="", nullable=False)
    q2: Mapped[str] = mapped_column(String, default="", nullable=False)
    q3: Mapped[str] = mapped_column(String, default="", nullable=False)
    q4: Mapped[str] = mapped_column(String, default="", nullable=False)
    year: Mapped[str] = mapped_column(String, default="", nullable=False)
    report_year: Mapped[str] = mapped_column(String, default="", nullable=False)


class KpiRow(GoalRowMixin, Base):
    __tablename__ = "kpi"


class PprRow(GoalRowMixin, Base):
    __tablename__ = "ppr"


class Leader(Base):
    __tablename__ = "leaders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class LeaderGoalRow(Base):
    """Таблица «Руководители» — цели руководителей по форме (шаблон lead_goals_template)."""

    __tablename__ = "leader_goals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_name: Mapped[str] = mapped_column(String, default="", nullable=False)
    goal_num: Mapped[str] = mapped_column(String, default="", nullable=False)
    name: Mapped[str] = mapped_column(String, default="", nullable=False)
    goal_type: Mapped[str] = mapped_column(String, default="", nullable=False)
    goal_kind: Mapped[str] = mapped_column(String, default="", nullable=False)
    unit: Mapped[str] = mapped_column(String, default="", nullable=False)
    q1_weight: Mapped[str] = mapped_column(String, default="", nullable=False)
    q1_value: Mapped[str] = mapped_column(String, default="", nullable=False)
    q2_weight: Mapped[str] = mapped_column(String, default="", nullable=False)
    q2_value: Mapped[str] = mapped_column(String, default="", nullable=False)
    q3_weight: Mapped[str] = mapped_column(String, default="", nullable=False)
    q3_value: Mapped[str] = mapped_column(String, default="", nullable=False)
    q4_weight: Mapped[str] = mapped_column(String, default="", nullable=False)
    q4_value: Mapped[str] = mapped_column(String, default="", nullable=False)
    year_weight: Mapped[str] = mapped_column(String, default="", nullable=False)
    year_value: Mapped[str] = mapped_column(String, default="", nullable=False)
    comments: Mapped[str] = mapped_column(String, default="", nullable=False)
    method_desc: Mapped[str] = mapped_column(String, default="", nullable=False)
    source_info: Mapped[str] = mapped_column(String, default="", nullable=False)
    report_year: Mapped[str] = mapped_column(String, default="", nullable=False)


class StrategyGoalRow(Base):
    """Таблица стратегических целей (strategy goals)."""

    __tablename__ = "strategy_goals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_unit: Mapped[str] = mapped_column(String, default="", nullable=False)
    segment: Mapped[str] = mapped_column(String, default="", nullable=False)
    strategic_priority: Mapped[str] = mapped_column(String, default="", nullable=False)
    goal_objective: Mapped[str] = mapped_column(String, default="", nullable=False)
    initiative: Mapped[str] = mapped_column(String, default="", nullable=False)
    initiative_type: Mapped[str] = mapped_column(String, default="", nullable=False)
    responsible_person_owner: Mapped[str] = mapped_column(String, default="", nullable=False)
    other_units_involved: Mapped[str] = mapped_column(String, default="", nullable=False)
    budget: Mapped[str] = mapped_column(String, default="", nullable=False)
    start_date: Mapped[str] = mapped_column(String, default="", nullable=False)
    end_date: Mapped[str] = mapped_column(String, default="", nullable=False)
    kpi: Mapped[str] = mapped_column(String, default="", nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String, default="", nullable=False)
    target_value_2025: Mapped[str] = mapped_column(String, default="", nullable=False)
    target_value_2026: Mapped[str] = mapped_column(String, default="", nullable=False)
    target_value_2027: Mapped[str] = mapped_column(String, default="", nullable=False)
    category: Mapped[str] = mapped_column(String, default="", nullable=False)
