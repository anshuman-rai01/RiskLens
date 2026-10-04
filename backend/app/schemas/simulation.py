"""
Pydantic schemas for simulation requests, responses, and debug output.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    x: Optional[float] = Field(default=None, description="Numeric x-axis value (months, days, hours, years)")


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
    # Purchase
    home_price: float = Field(..., gt=0, description="Total home purchase price")
    down_payment_pct: float = Field(20.0, ge=0, le=100.0, description="Down payment percentage (0-100)")
    expected_home_appreciation_pct_per_year: float = Field(
        ..., ge=-10.0, le=30.0, description="Expected annual home appreciation (%)"
    )
    maintenance_pct_per_year: float = Field(1.0, ge=0, le=20.0, description="Annual maintenance (% of home price)")
    property_tax_pct_per_year: float = Field(1.0, ge=0, le=20.0, description="Annual property tax (% of home price)")
    selling_costs_pct: float = Field(6.0, ge=0, le=30.0, description="Selling costs upon exit (% of home value)")

    # Mortgage
    mortgage_rate_pct: float = Field(..., ge=0, le=30.0, description="Annual mortgage interest rate (%)")
    loan_term_years: int = Field(..., ge=1, le=40, description="Mortgage loan term in years (1-40)")
    closing_costs_pct: float = Field(3.0, ge=0, le=20.0, description="Closing costs paid at purchase (% of home price)")

    # Rental
    current_monthly_rent: float = Field(..., gt=0, description="Initial monthly rent amount")
    expected_rent_increase_pct_per_year: float = Field(
        ..., ge=0, le=30.0, description="Expected annual rent increase (%)"
    )
    security_deposit_months: float = Field(2.0, ge=0, le=24.0, description="Security deposit in months of rent (refundable)")

    # Investment & Tax
    expected_investment_return_pct_per_year: float = Field(
        ..., ge=0, le=40.0, description="Expected annual investment return (%)"
    )
    inflation_pct_per_year: float = Field(5.0, ge=-5.0, le=30.0, description="Annual inflation rate (%)")
    output_basis: str = Field("nominal", description="Output basis: 'nominal' or 'real'")
    portfolio_gains_tax_pct: float = Field(0.0, ge=0, le=60.0, description="Tax on investment portfolio gains (%)")
    property_gains_tax_pct: float = Field(0.0, ge=0, le=60.0, description="Tax on property appreciation gains (%)")

    # Horizon
    horizon_years: Optional[int] = Field(None, ge=1, le=40, description="Projection horizon in years (1-40)")

    @model_validator(mode="after")
    def validate_deposit_and_horizon(self) -> "BuyVsRentParams":
        if self.horizon_years is None:
            self.horizon_years = self.loan_term_years

        k = (self.down_payment_pct / 100.0 * self.home_price) + (self.closing_costs_pct / 100.0 * self.home_price)
        d0 = self.security_deposit_months * self.current_monthly_rent
        if d0 > k:
            raise ValueError(f"Security deposit ({d0:,.2f}) exceeds initial required capital ({k:,.2f})")

        if self.output_basis not in ("nominal", "real"):
            raise ValueError("output_basis must be 'nominal' or 'real'")
        return self


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


class IncreaseSavingsRateParams(BaseModel):
    """Validated input parameters for Increase Savings Rate scenario."""
    target_rate: float = Field(..., gt=0, le=1.0, description="Target savings rate as a fraction (0 < x <= 1)")
    horizon_months: int = Field(60, ge=1, le=120, description="Projection horizon in months (1-120)")
    window_start: Optional[str] = Field(None, description="Window start ISO date (YYYY-MM-DD)")
    window_end: Optional[str] = Field(None, description="Window end ISO date (YYYY-MM-DD)")

    @field_validator("window_start", "window_end")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError("Must be a valid ISO date (YYYY-MM-DD)")
        return v

    @model_validator(mode="after")
    def validate_window(self) -> "IncreaseSavingsRateParams":
        if self.window_start and self.window_end:
            d_start = date.fromisoformat(self.window_start)
            d_end = date.fromisoformat(self.window_end)
            if d_start >= d_end:
                raise ValueError("window_start must be strictly before window_end")
            if d_end > date.today():
                raise ValueError("window_end cannot be in the future")
        elif (self.window_start and not self.window_end) or (self.window_end and not self.window_start):
            raise ValueError("Both window_start and window_end must be provided together")
        return self


class FitnessPlanParams(BaseModel):
    """Validated input parameters for Fitness Plan scenario."""
    target_weekly_minutes: float = Field(..., gt=0, description="Target weekly workout minutes (> 0)")
    horizon_days: int = Field(90, ge=7, le=365, description="Projection horizon in days (7-365)")
    history_days: Optional[int] = Field(None, ge=14, le=365, description="History window in days (14-365, or None for all-time)")


class StudyHoursParams(BaseModel):
    """Validated input parameters for Study Hours What-If scenario."""
    window_days: int = Field(14, description="Study aggregation window in days (7 or 14)")
    subject: Optional[str] = Field(None, description="Optional academic course / study subject filter")
    assessment_type: Optional[str] = Field(None, description="Optional assessment type filter")
    current_daily_hours: Optional[float] = Field(None, ge=0.0, le=8.0, description="Baseline daily study hours (0-8)")
    simulated_daily_hours: Optional[float] = Field(None, ge=0.0, le=8.0, description="Simulated daily study hours (0-8)")

    @field_validator("window_days")
    @classmethod
    def validate_window_days(cls, v: int) -> int:
        if v not in (7, 14):
            raise ValueError("window_days must be 7 or 14")
        return v


