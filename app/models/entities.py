"""
SQLAlchemy ORM models for KPI Platform:
- Department, Position
- FormulaTemplate
- User (Admin, Department Head, Employee)
- Period (Draft, Calculated, Locked)
- EmployeeTarget (Individual plans per period)
- CalculationResult (Historical snapshot of metrics, evaluated formula, bonus and payout)
"""

from datetime import datetime, timezone
import json
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)

    positions = relationship("Position", back_populates="department", cascade="all, delete-orphan")
    users = relationship("User", back_populates="department")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)

    department = relationship("Department", back_populates="positions")
    users = relationship("User", back_populates="position")
    formula_template = relationship("FormulaTemplate", back_populates="position", uselist=False, cascade="all, delete-orphan")


class FormulaTemplate(Base):
    __tablename__ = "formula_templates"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id", ondelete="CASCADE"), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    formula_expression = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    position = relationship("Position", back_populates="formula_template")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, index=True, nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(20), default="EMPLOYEE")  # ADMIN, HEAD, EMPLOYEE
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    position_id = Column(Integer, ForeignKey("positions.id", ondelete="SET NULL"), nullable=True)
    bitrix_user_id = Column(Integer, nullable=True, unique=True)
    avatar_url = Column(String(255), nullable=True)

    department = relationship("Department", back_populates="users")
    position = relationship("Position", back_populates="users")
    targets = relationship("EmployeeTarget", back_populates="user", cascade="all, delete-orphan")
    results = relationship("CalculationResult", back_populates="user", cascade="all, delete-orphan")


class Period(Base):
    __tablename__ = "periods"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # e.g., "Сентябрь 2026"
    start_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    end_date = Column(String(10), nullable=False)    # YYYY-MM-DD
    status = Column(String(20), default="DRAFT")    # DRAFT, CALCULATED, LOCKED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    locked_at = Column(DateTime, nullable=True)

    targets = relationship("EmployeeTarget", back_populates="period", cascade="all, delete-orphan")
    results = relationship("CalculationResult", back_populates="period", cascade="all, delete-orphan")


class EmployeeTarget(Base):
    __tablename__ = "employee_targets"

    id = Column(Integer, primary_key=True, index=True)
    period_id = Column(Integer, ForeignKey("periods.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Standard targets
    base_rate = Column(Float, default=50000.0)      # Base monthly salary
    plan_sales = Column(Float, default=300000.0)    # Revenue target
    plan_tasks = Column(Float, default=20.0)        # Task completion target
    target_calls = Column(Float, default=100.0)     # Telephony target
    quality_score = Column(Float, default=100.0)    # Quality assessment
    custom_targets_json = Column(Text, default="{}")

    period = relationship("Period", back_populates="targets")
    user = relationship("User", back_populates="targets")

    @property
    def custom_targets(self):
        try:
            return json.loads(self.custom_targets_json or "{}")
        except Exception:
            return {}

    @custom_targets.setter
    def custom_targets(self, val):
        self.custom_targets_json = json.dumps(val, ensure_ascii=False)


class CalculationResult(Base):
    __tablename__ = "calculation_results"

    id = Column(Integer, primary_key=True, index=True)
    period_id = Column(Integer, ForeignKey("periods.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    formula_template_id = Column(Integer, ForeignKey("formula_templates.id", ondelete="SET NULL"), nullable=True)
    
    formula_expression = Column(Text, nullable=False)
    raw_metrics_json = Column(Text, default="{}")        # Raw fact from Bitrix24
    computed_variables_json = Column(Text, default="{}") # Combined context (plan + fact)
    
    kpi_percent = Column(Float, default=0.0)             # Resulting KPI %
    bonus_amount = Column(Float, default=0.0)            # Computed bonus amount (₽)
    total_payout = Column(Float, default=0.0)            # Base + Bonus (₽)
    status = Column(String(20), default="CALCULATED")    # CALCULATED, APPROVED, LOCKED
    notes = Column(Text, nullable=True)
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    period = relationship("Period", back_populates="results")
    user = relationship("User", back_populates="results")

    @property
    def raw_metrics(self):
        try:
            return json.loads(self.raw_metrics_json or "{}")
        except Exception:
            return {}

    @raw_metrics.setter
    def raw_metrics(self, val):
        self.raw_metrics_json = json.dumps(val, ensure_ascii=False)

    @property
    def computed_variables(self):
        try:
            return json.loads(self.computed_variables_json or "{}")
        except Exception:
            return {}

    @computed_variables.setter
    def computed_variables(self, val):
        self.computed_variables_json = json.dumps(val, ensure_ascii=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="sessions")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=True)
