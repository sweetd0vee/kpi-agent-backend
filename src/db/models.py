from sqlalchemy import Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class GoalRowMixin:
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    last_name: Mapped[str] = mapped_column(String, default="", nullable=False)
    business_unit: Mapped[str] = mapped_column(String, default="", nullable=False)
    department: Mapped[str] = mapped_column(String, default="", nullable=False)
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


class BoardGoalRow(GoalRowMixin, Base):
    """Объединённая таблица целей правления (вместо отдельных kpi и ppr)."""
    __tablename__ = "board_goals"


class LeaderGoalRow(Base):
    """Таблица «Руководители» — цели руководителей по форме (шаблон lead_goals_template)."""

    __tablename__ = "leader_goals"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
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

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
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


class ProcessRegistryRow(Base):
    """Реестр процессов (справочник)."""

    __tablename__ = "process_registry"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    process_area: Mapped[str] = mapped_column(String, default="", nullable=False)  # Процессная область
    process_code: Mapped[str] = mapped_column(String, default="", nullable=False)  # Код процесса
    process: Mapped[str] = mapped_column(String, default="", nullable=False)  # Наименование / процесс
    process_owner: Mapped[str] = mapped_column(String, default="", nullable=False)  # Владелец процесса
    leader: Mapped[str] = mapped_column(String, default="", nullable=False)  # Руководитель / ФИО (справочно)
    business_unit: Mapped[str] = mapped_column(String, default="", nullable=False)  # Бизнес/блок
    top_20: Mapped[str] = mapped_column(String, default="", nullable=False)  # ТОП 20


class StaffRow(Base):
    """Штат / оргструктура (справочник)."""

    __tablename__ = "staff"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    org_structure_code: Mapped[str] = mapped_column(String, default="", nullable=False)  # Код оргструктуры
    unit_name: Mapped[str] = mapped_column(String, default="", nullable=False)  # Наименование
    head: Mapped[str] = mapped_column(String, default="", nullable=False)  # Руководитель
    business_unit: Mapped[str] = mapped_column(String, default="", nullable=False)  # Бизнес/блок
    functional_block_curator: Mapped[str] = mapped_column(
        String, default="", nullable=False
    )  # Куратор функционального блока


class CascadeRun(Base):
    """История запусков табличного каскадирования."""

    __tablename__ = "cascade_runs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    created_at: Mapped[str] = mapped_column(String, default="", nullable=False)
    status: Mapped[str] = mapped_column(String, default="success", nullable=False)
    report_year: Mapped[str] = mapped_column(String, default="", nullable=False)
    managers_filter: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    total_managers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_deputies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    unmatched_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class CascadeRunItem(Base):
    """Назначения KPI в рамках конкретного запуска каскада."""

    __tablename__ = "cascade_run_items"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    manager_name: Mapped[str] = mapped_column(String, default="", nullable=False)
    deputy_name: Mapped[str] = mapped_column(String, default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String, default="", nullable=False)
    source_row_id: Mapped[str] = mapped_column(String, default="", nullable=False)
    source_goal_title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_metric: Mapped[str] = mapped_column(Text, default="", nullable=False)
    business_unit: Mapped[str] = mapped_column(String, default="", nullable=False)
    department: Mapped[str] = mapped_column(String, default="", nullable=False)
    report_year: Mapped[str] = mapped_column(String, default="", nullable=False)
    trace_rule: Mapped[str] = mapped_column(String, default="", nullable=False)
    confidence: Mapped[str] = mapped_column(String, default="", nullable=False)
