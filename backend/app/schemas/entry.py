"""
Pydantic schemas for entry requests, responses, and validations.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EntryCategory(str, Enum):
    """
    The 6 supported behavioral time-series categories for entries.
    Note: Personal Goals is excluded (handled separately in Chunk 4).
    """
    INCOME_EXPENSE = "income_expense"
    SAVINGS = "savings"
    STUDY = "study"
    ACADEMIC = "academic"
    FITNESS = "fitness"
    HABITS = "habits"


def validate_occurred_date(v: Optional[date]) -> Optional[date]:
    """Validate that occurred_at is not beyond today + 1 day (timezone tolerance)."""
    if v is not None:
        max_allowed = date.today() + timedelta(days=1)
        if v > max_allowed:
            raise ValueError(
                f"occurred_at cannot be in the future beyond 1-day timezone tolerance (max allowed: {max_allowed})"
            )
    return v


def validate_finite_decimal(v: Optional[Decimal]) -> Optional[Decimal]:
    """Validate that Decimal value is finite and within Numeric(12, 2) bounds."""
    if v is not None:
        if v.is_nan() or v.is_infinite():
            raise ValueError("value must be a finite number")
        # Ensure it fits within 10 digits before decimal point
        if abs(v) >= Decimal("10000000000"):
            raise ValueError("value exceeds maximum allowable magnitude for Numeric(12, 2)")
    return v


def format_entry_value(category: str, value: Decimal) -> Decimal:
    """
    Apply category-specific rounding to entry values.

    - income_expense, savings: round to nearest whole integer (monetary amounts)
    - study, academic: round to 1 decimal place (preserve variation for regression)
    - fitness, habits: no transformation
    """
    cat = category.lower() if isinstance(category, str) else category
    if cat in ("income_expense", "savings"):
        return Decimal(str(round(float(value))))
    elif cat in ("study", "academic"):
        return value.quantize(Decimal("0.1"))
    return value


class EntryCreate(BaseModel):
    """Payload for creating a new entry."""
    category: EntryCategory
    subcategory: Optional[str] = Field(None, max_length=200, description="Category-specific subcategory or label")
    value: Decimal = Field(..., description="Numeric amount, duration, score, or count")
    unit: Optional[str] = Field(None, max_length=50, description="Unit of measurement (e.g. INR, hours, minutes)")
    max_value: Optional[Decimal] = Field(None, gt=0, description="Maximum attainable value (e.g. maximum marks for an assessment)")
    occurred_at: date = Field(..., description="Date of the entry (YYYY-MM-DD)")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes or context")

    @field_validator("occurred_at")
    @classmethod
    def check_date(cls, v: date) -> date:
        val = validate_occurred_date(v)
        assert val is not None
        return val

    @field_validator("value")
    @classmethod
    def check_value(cls, v: Decimal) -> Decimal:
        val = validate_finite_decimal(v)
        assert val is not None
        return val

    @field_validator("max_value")
    @classmethod
    def check_max_value(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return validate_finite_decimal(v)

    @field_validator("subcategory", "unit", "notes")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None

    @model_validator(mode="after")
    def apply_category_formatting(self) -> "EntryCreate":
        """Round value based on category: integers for monetary, 1 decimal for academic."""
        self.value = format_entry_value(self.category.value, self.value)
        return self



class EntryUpdate(BaseModel):
    """
    Payload for updating an existing entry.
    Note: 'category' stays immutable after creation. Supplying it is rejected with a
    422 error due to extra='forbid'. 'subcategory' IS editable: it carries the
    user-facing label (description, vault, course, activity, habit), and moving an
    entry to another series invalidates the old series' cached forecast (see router).
    """
    model_config = ConfigDict(extra="forbid")

    subcategory: Optional[str] = Field(None, max_length=200)
    value: Optional[Decimal] = None
    unit: Optional[str] = Field(None, max_length=50)
    max_value: Optional[Decimal] = Field(None, gt=0)
    occurred_at: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("occurred_at")
    @classmethod
    def check_date(cls, v: Optional[date]) -> Optional[date]:
        return validate_occurred_date(v)

    @field_validator("value")
    @classmethod
    def check_value(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return validate_finite_decimal(v)

    @field_validator("max_value")
    @classmethod
    def check_max_value(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return validate_finite_decimal(v)

    @field_validator("subcategory", "unit", "notes")
    @classmethod
    def trim_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class EntryResponse(BaseModel):
    """Public representation of an entry."""
    id: uuid.UUID
    category: str
    subcategory: Optional[str]
    value: Decimal
    unit: Optional[str]
    max_value: Optional[Decimal] = None
    occurred_at: date
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EntryListResponse(BaseModel):
    """Paginated list response of entries."""
    items: List[EntryResponse]
    total: int
    limit: int
    offset: int
