"""
Pydantic schemas for simulation requests, responses, and debug output.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScenarioType(str, Enum):
    """Supported simulation scenario types."""
    INCREASE_SAVINGS_RATE = "increase_savings_rate"
    FITNESS_PLAN = "fitness_plan"
    REDUCE_STUDY_HOURS = "reduce_study_hours"
    BUY_VS_RENT = "buy_vs_rent"
    PROGRAM_OUTCOME = "program_outcome"


class SimulationRequest(BaseModel):
    """Payload for running a simulation scenario."""
    scenario_type: ScenarioType
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scenario-specific parameters (e.g., target_rate, target_weekly_minutes)",
    )


class SimulationPoint(BaseModel):
    """A single data point in a simulation line."""
    date: str = Field(description="Date string (YYYY-MM-DD or YYYY-MM)")
    value: float = Field(description="Projected value at this date")


class SimulationLine(BaseModel):
    """A named projection line in the simulation chart."""
    label: str = Field(description="Line label (e.g., 'current_path_expected', 'best_case')")
    points: List[SimulationPoint] = Field(default_factory=list)


class SimulationResponse(BaseModel):
    """Response payload for POST /simulations."""
    id: str = Field(description="UUID of the cached simulation result")
    scenario_type: str
    reliability: str = Field(
        description="Reliability tier: 'insufficient' | 'low_confidence' | 'reliable' | 'assumption_based'",
    )
    data_point_count: Optional[int] = Field(
        None,
        description="Number of real data points used (None for assumption-based scenarios)",
    )
    message: Optional[str] = None
    lines: List[SimulationLine] = Field(default_factory=list)
    generated_at: datetime
    correlation_r_squared: Optional[float] = Field(
        None,
        description="R² of the regression (only for reduce_study_hours)",
    )
    derived_values: Optional[Dict[str, Any]] = Field(
        None,
        description="Scenario-specific intermediate values (e.g., current_rate, current_avg_minutes)",
    )
    # ── Chunk 11: AI Recommendations ──────────────────────────────
    recommendations: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="AI-generated recommendations (null while pending or unavailable)",
    )
    recommendations_status: str = Field(
        "pending",
        description="Status of AI recommendations: 'pending' | 'ready' | 'unavailable'",
    )
    recommendation_disclaimer: Optional[str] = Field(
        None,
        description="Disclaimer text (present for savings_rate scenario)",
    )

    model_config = ConfigDict(from_attributes=True)


class SimulationDebugResponse(BaseModel):
    """Debug/inspection response for GET /simulations/{id}/debug."""
    id: str
    scenario_type: str
    generated_at: datetime
    params_hash: str
    input_params: Dict[str, Any]
    data_point_count: Optional[int] = None
    reliability: str
    derived_values: Optional[Dict[str, Any]] = None
    # ── Chunk 11: AI Recommendations debug ────────────────────────
    recommendations_status: Optional[str] = Field(
        None,
        description="Status of AI recommendations: 'pending' | 'ready' | 'unavailable'",
    )
    recommendation_outcome: Optional[str] = Field(
        None,
        description="Sanitized outcome of last generation attempt (never raw exception text)",
    )

    model_config = ConfigDict(from_attributes=True)


# ── Assumption-Based Scenario Param Validation Schemas ───────────────


class BuyVsRentParams(BaseModel):
    """Validated input parameters for Buy vs Rent scenario."""
    home_price: float = Field(..., gt=0, description="Total home purchase price")
    mortgage_rate_pct: float = Field(..., gt=0, description="Annual mortgage interest rate (%)")
    loan_term_years: int = Field(..., gt=0, description="Mortgage loan term in years")
    current_monthly_rent: float = Field(..., gt=0, description="Current monthly rent amount")
    expected_rent_increase_pct_per_year: float = Field(
        ..., gt=0, description="Expected annual rent increase (%)",
    )
    expected_home_appreciation_pct_per_year: float = Field(
        ..., gt=0, description="Expected annual home value appreciation (%)",
    )
    expected_investment_return_pct_per_year: float = Field(
        ..., gt=0, description="Expected annual investment return (%) for rent path",
    )


class ProgramOutcomeParams(BaseModel):
    """Validated input parameters for Program Outcome scenario."""
    current_annual_salary: float = Field(..., gt=0, description="Current annual salary before program")
    program_tuition_cost: float = Field(..., gt=0, description="Total tuition cost of the program")
    program_duration_years: float = Field(
        ..., ge=0.5, le=10.0, description="Program duration in years (0.5 to 10.0)",
    )
    expected_salary_post_program: float = Field(
        ..., gt=0, description="Expected annual salary after completing the program",
    )
    opportunity_cost_income_during_program: float = Field(
        ..., ge=0, description="Annual income forgone during program (can be 0 if studying part-time)",
    )
