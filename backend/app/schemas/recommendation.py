"""
Pydantic schemas for AI recommendation validation.

Strict schemas with extra="forbid" and real Enums — any hallucinated fields
or off-schema output from the LLM causes a validation failure that the
grounded_llm service catches and translates to None.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ImpactLevel(str, Enum):
    """Impact level for a recommendation."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class EffortLevel(str, Enum):
    """Effort level for a recommendation."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class RecommendationItem(BaseModel):
    """A single grounded recommendation item.

    extra="forbid" ensures any hallucinated fields from the LLM
    cause a hard validation failure rather than silently passing.
    """
    title: str = Field(description="Concise, actionable summary (max 10 words)")
    impact: ImpactLevel = Field(description="Impact level: High, Medium, or Low")
    effort: EffortLevel = Field(description="Effort level: High, Medium, or Low")
    description: str = Field(
        description="1-3 sentences explaining the recommendation, citing only numbers from the context",
    )

    model_config = ConfigDict(extra="forbid")


class RecommendationResponse(BaseModel):
    """Schema for the full LLM recommendation output.

    The LLM is instructed to return a JSON object matching this schema.
    min_length=2, max_length=4 enforces the 2-4 recommendation constraint.
    """
    recommendations: List[RecommendationItem] = Field(
        ...,
        min_length=2,
        max_length=4,
    )
    disclaimer: Optional[str] = Field(
        None,
        description="Disclaimer text (required for savings_rate, optional otherwise)",
    )

    model_config = ConfigDict(extra="forbid")
