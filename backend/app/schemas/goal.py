"""
Pydantic schemas for Personal Goals requests, responses, and computed progress.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


def compute_progress_percent(current_val: Decimal, target_val: Decimal) -> float:
    """
    Calculate progress percentage:
    progress_percent = min(100.0, round(current_value / target_value * 100, 1))
    Zero or negative target_value is invalid; guarded to prevent division by zero.
    """
    if target_val <= 0:
        return 0.0
    pct = float((current_val / target_val) * Decimal("100"))
    return min(100.0, max(0.0, round(pct, 1)))


def validate_target_value_decimal(v: Optional[Decimal]) -> Optional[Decimal]:
    """Ensure target_value is finite, strictly positive, and within column bounds."""
    if v is not None:
        if v.is_nan() or v.is_infinite():
            raise ValueError("target_value must be a finite number")
        if v <= 0:
            raise ValueError("target_value must be strictly positive (> 0)")
        if v >= Decimal("10000000000"):
            raise ValueError("target_value exceeds maximum allowable magnitude for Numeric(12, 2)")
    return v


def validate_current_value_decimal(v: Optional[Decimal]) -> Optional[Decimal]:
    """Ensure current_value is finite, non-negative, and within column bounds."""
    if v is not None:
        if v.is_nan() or v.is_infinite():
            raise ValueError("current_value must be a finite number")
        if v < 0:
            raise ValueError("current_value must be non-negative (>= 0)")
        if v >= Decimal("10000000000"):
            raise ValueError("current_value exceeds maximum allowable magnitude for Numeric(12, 2)")
    return v


class GoalCreate(BaseModel):
    """
    Payload for creating a new goal.
    current_value (or 'current') is optional and defaults to 0.00.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(
        ...,
        validation_alias=AliasChoices("name", "title"),
        min_length=1,
        max_length=200,
        description="Goal description or title",
    )
    target_value: Decimal = Field(
        ...,
        validation_alias=AliasChoices("target_value", "target"),
        description="Target numeric goal (must be positive > 0)",
    )
    current_value: Decimal = Field(
        Decimal("0.00"),
        validation_alias=AliasChoices("current_value", "current"),
        description="Starting progress value (optional, defaults to 0)",
    )
    unit: Optional[str] = Field(
        None,
        max_length=50,
        description="Unit of measurement (e.g. INR, hours, modules)",
    )
    deadline: Optional[date] = Field(
        None,
        description="Target completion date (optional)",
    )

    @field_validator("target_value")
    @classmethod
    def validate_target(cls, v: Decimal) -> Decimal:
        val = validate_target_value_decimal(v)
        assert val is not None
        return val

    @field_validator("current_value")
    @classmethod
    def validate_current(cls, v: Decimal) -> Decimal:
        val = validate_current_value_decimal(v)
        assert val is not None
        return val

    @field_validator("name", "unit")
    @classmethod
    def trim_text(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class GoalUpdate(BaseModel):
    """
    Payload for updating an existing goal.
    target_value and current_value are mutable here.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("name", "title"),
        min_length=1,
        max_length=200,
    )
    target_value: Optional[Decimal] = Field(
        None,
        validation_alias=AliasChoices("target_value", "target"),
    )
    current_value: Optional[Decimal] = Field(
        None,
        validation_alias=AliasChoices("current_value", "current"),
    )
    unit: Optional[str] = Field(None, max_length=50)
    deadline: Optional[date] = None

    @field_validator("target_value")
    @classmethod
    def validate_target(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return validate_target_value_decimal(v)

    @field_validator("current_value")
    @classmethod
    def validate_current(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return validate_current_value_decimal(v)

    @field_validator("name", "unit")
    @classmethod
    def trim_text(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class GoalResponse(BaseModel):
    """
    Public representation of a goal, including computed progress fields.
    Does NOT leak user_id or deleted_at.
    """
    id: uuid.UUID
    name: str
    target_value: Decimal
    current_value: Decimal
    unit: Optional[str]
    deadline: Optional[date]
    progress_percent: float
    is_completed: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_computed(cls, goal: object) -> "GoalResponse":
        """Factory method computing progress_percent and is_completed from ORM model."""
        target = getattr(goal, "target_value")
        current = getattr(goal, "current_value")
        pct = compute_progress_percent(current, target)
        completed = bool(current >= target)

        return cls(
            id=getattr(goal, "id"),
            name=getattr(goal, "name"),
            target_value=target,
            current_value=current,
            unit=getattr(goal, "unit"),
            deadline=getattr(goal, "deadline"),
            progress_percent=pct,
            is_completed=completed,
            created_at=getattr(goal, "created_at"),
            updated_at=getattr(goal, "updated_at"),
        )


class GoalListResponse(BaseModel):
    """Paginated list of goals."""
    items: List[GoalResponse]
    total: int
    limit: int
    offset: int
