"""
Pydantic schemas for API requests and responses.
"""

from datetime import datetime
import re
from typing import Dict, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class LoginRequest(BaseModel):
    user_id: int


class BitrixSettingsUpdate(BaseModel):
    webhook_url: Optional[str] = None
    mock_mode: Optional[bool] = None
    clear_webhook: Optional[bool] = False

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            val = v.strip()
            if val == "":
                return None
            if "****" in val:
                raise ValueError("Нельзя сохранять маску вместо реального URL вебхука")
            if not (val.startswith("https://") and "/rest/" in val):
                raise ValueError("URL вебхука должен начинаться с https:// и содержать /rest/")
            return val
        return v


class FormulaTestRequest(BaseModel):
    expression: str
    custom_variables: Optional[Dict[str, float]] = None


class FormulaTemplateCreate(BaseModel):
    position_id: int
    name: str
    formula_expression: str
    description: Optional[str] = None


class FormulaTemplateUpdate(BaseModel):
    name: Optional[str] = None
    formula_expression: Optional[str] = None
    description: Optional[str] = None


class PeriodCreate(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Октябрь 2026"})
    start_date: str = Field(..., json_schema_extra={"example": "2026-10-01"})
    end_date: str = Field(..., json_schema_extra={"example": "2026-10-31"})

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError("Дата должна быть в формате YYYY-MM-DD")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Некорректная дата")
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> "PeriodCreate":
        if self.start_date > self.end_date:
            raise ValueError("Дата начала периода (start_date) не может быть позже даты окончания (end_date)")
        return self


class TargetUpdate(BaseModel):
    base_rate: float = Field(default=50000.0, ge=0.0)
    plan_sales: float = Field(default=300000.0, ge=0.0)
    plan_tasks: float = Field(default=20.0, ge=0.0)
    target_calls: float = Field(default=100.0, ge=0.0)
    quality_score: float = Field(default=100.0, ge=1.0, le=100.0)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    department_id: Optional[int]
    position_id: Optional[int]
    department_name: Optional[str] = None
    position_name: Optional[str] = None
    avatar_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
