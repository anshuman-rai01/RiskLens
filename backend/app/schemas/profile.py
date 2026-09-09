"""
Pydantic schemas for User Profile and compliance baselines.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileResponse(BaseModel):
    """Public representation of a user profile."""
    user_id: uuid.UUID
    name: str = ""
    age: Optional[int] = None
    role: str = "student"
    currency: str = "INR"
    monthly_spending_cap: Optional[Decimal] = None
    monthly_savings_target: Optional[Decimal] = None
    weekly_study_hours: Optional[Decimal] = None
    weekly_fitness_minutes: Optional[int] = None
    weekly_habit_completions: Optional[int] = None
    onboarded: bool = False
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    """Payload for updating user profile and compliance baselines."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, max_length=100)
    age: Optional[int] = Field(None, ge=1, le=150)
    role: Optional[str] = Field(None, max_length=50)
    currency: Optional[str] = Field(None, max_length=10)
    monthly_spending_cap: Optional[Decimal] = None
    monthly_savings_target: Optional[Decimal] = None
    weekly_study_hours: Optional[Decimal] = None
    weekly_fitness_minutes: Optional[int] = Field(None, ge=0)
    weekly_habit_completions: Optional[int] = Field(None, ge=0)
    onboarded: Optional[bool] = None

    @field_validator(
        "monthly_spending_cap",
        "monthly_savings_target",
        "weekly_study_hours",
    )
    @classmethod
    def validate_decimals(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if v.is_nan() or v.is_infinite():
                raise ValueError("Limit must be a finite number")
            if v < 0:
                raise ValueError("Limit must be non-negative (>= 0)")
            if v >= Decimal("10000000000"):
                raise ValueError("Value exceeds maximum allowable magnitude")
        return v

    @field_validator("name", "role", "currency")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None
