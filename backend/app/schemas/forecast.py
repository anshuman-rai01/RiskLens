"""
Pydantic schemas for series forecasts, confidence bands, and reliability metrics.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ForecastPoint(BaseModel):
    """A single forecasted point with confidence interval."""
    date: str = Field(description="Forecast date (YYYY-MM-DD)")
    predicted: float = Field(description="Point prediction (yhat)")
    lower: float = Field(description="Lower bound of 80% confidence interval (yhat_lower)")
    upper: float = Field(description="Upper bound of 80% confidence interval (yhat_upper)")

    model_config = ConfigDict(from_attributes=True)


class ForecastResponse(BaseModel):
    """
    Response payload for GET /forecast.
    Provides reliability tiering, sample count, generation timestamp,
    and confidence-band projections.
    """
    category: str
    subcategory: Optional[str] = None
    reliability: str = Field(
        ...,
        description="Reliability tier: 'insufficient' | 'low_confidence' | 'reliable'",
    )
    data_point_count: int = Field(
        ...,
        description="Number of historical daily data points fed into the model",
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this forecast was generated/cached",
    )
    message: Optional[str] = Field(
        None,
        description="Explanation when reliability is insufficient or fitting Degenerate",
    )
    forecast_points: List[ForecastPoint] = Field(
        default_factory=list,
        description="Projected forecast points (empty when reliability is insufficient)",
    )

    model_config = ConfigDict(from_attributes=True)
