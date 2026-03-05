from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class GoalRowMixin:
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_name: Mapped[str] = mapped_column(String, default="", nullable=False)
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
