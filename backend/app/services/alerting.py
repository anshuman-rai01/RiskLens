"""
Alerting service for computing threshold-based and trend-based risk conditions.

Rules:
1. Threshold rules:
   - Evaluated on active (non-completed, non-deleted) goals with a deadline.
   - Pace gap = actual_progress_pct - expected_progress_pct
   - pace_gap >= -5.0: No alert (on pace or ahead)
   - -15.0 <= pace_gap < -5.0: Warning ("behind pace")
   - pace_gap < -15.0: Risk ("critically behind pace")
   - Open-ended goals (no deadline) are explicitly skipped as there is no fixed timeline.

2. Trend-based rules:
   - Requires a forecast with reliability 'low_confidence' or 'reliable'.
   - When reliability is 'insufficient', NO alert is fabricated (omitted entirely because
     an ungrounded model cannot reliably assess deviation).
   - Compares the most recent entry value against the closest forecast point confidence band.
   - Outside by <= 1.5 * band_width: Warning
   - Outside by > 1.5 * band_width: Risk
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Sequence, Tuple

from app.models.entry import Entry
from app.models.forecast import Forecast
from app.models.goal import Goal
from app.models.profile import Profile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertCondition:
    """Represents a computed active alert condition prior to DB reconciliation."""
    category: str
    subcategory: Optional[str]
    kind: str  # 'threshold' | 'trend'
    severity: str  # 'info' | 'warning' | 'risk'
    message: str


def compute_threshold_alerts(
    goals: Sequence[Goal],
    current_date: Optional[date] = None,
) -> List[AlertCondition]:
    """
    Evaluate threshold alert rules over active personal goals.
    
    Pace is computed as:
      expected_progress_pct = (days_elapsed / total_days) * 100 [clamped 0-100]
      actual_progress_pct = (current_value / target_value) * 100 [clamped 0-100]
      pace_gap = actual_progress_pct - expected_progress_pct
    """
    today = current_date or datetime.now(timezone.utc).date()
    conditions: List[AlertCondition] = []

    for goal in goals:
        # Exclude soft-deleted goals
        if goal.deleted_at is not None:
            continue

        # Open-ended goals with no deadline have no timeline/pace to compute against;
        # skipping them explicitly per specification.
        if goal.deadline is None:
            continue

        # Goals where target is non-positive or already reached/exceeded are completed/inactive
        if goal.target_value <= Decimal("0.00") or goal.current_value >= goal.target_value:
            continue

        created_date = goal.created_at.date()
        deadline_date = goal.deadline

        # Total duration from creation to deadline (guard against 0 or negative division)
        total_days = max(1, (deadline_date - created_date).days)
        # Days elapsed from creation to today (clamped between 0 and total_days)
        days_elapsed = max(0, min(total_days, (today - created_date).days))

        expected_progress_pct = (days_elapsed / total_days) * 100.0
        actual_progress_pct = float(
            (goal.current_value / goal.target_value) * Decimal("100.0")
        )
        actual_progress_pct = min(100.0, max(0.0, actual_progress_pct))

        pace_gap = actual_progress_pct - expected_progress_pct

        # Severity band evaluation:
        # pace_gap >= -5.0: On pace or ahead (no alert)
        # -15.0 <= pace_gap < -5.0: Warning
        # pace_gap < -15.0: Risk
        if pace_gap >= -5.0:
            continue

        if pace_gap >= -15.0:
            severity = "warning"
            message = (
                f"Goal '{goal.name}' is behind pace "
                f"({pace_gap:.1f}% vs expected {expected_progress_pct:.1f}%)"
            )
        else:
            severity = "risk"
            message = (
                f"Goal '{goal.name}' is critically behind pace "
                f"({pace_gap:.1f}% vs expected {expected_progress_pct:.1f}%)"
            )

        conditions.append(
            AlertCondition(
                category="goals",
                subcategory=str(goal.id),
                kind="threshold",
                severity=severity,
                message=message,
            )
        )

    return conditions


def compute_baseline_alerts(
    profile: Optional[Profile],
    month_spending: Decimal = Decimal("0.00"),
    month_savings: Decimal = Decimal("0.00"),
    week_study_hours: Decimal = Decimal("0.00"),
    week_fitness_minutes: int = 0,
    week_habit_completions: int = 0,
    current_date: Optional[date] = None,
) -> List[AlertCondition]:
    """
    Evaluate threshold alert rules over user profile baseline targets.

    Financial Baselines:
    - monthly_spending_cap: warning at >= 90%, risk at >= 100% of cap.
    - monthly_savings_target: warning at < 75%, risk at < 50% of prorated target.

    Time-Based Baselines:
    - weekly_study_hours: warning at < 75%, risk at < 50% of prorated target.
    - weekly_fitness_minutes: warning at < 75%, risk at < 50% of prorated target.
    - weekly_habit_completions: warning at < 75%, risk at < 50% of prorated target.
    """
    if profile is None:
        return []

    today = current_date or datetime.now(timezone.utc).date()
    conditions: List[AlertCondition] = []

    # 1. Monthly Spending Cap
    if profile.monthly_spending_cap is not None and profile.monthly_spending_cap > Decimal("0.00"):
        cap = profile.monthly_spending_cap
        if month_spending >= cap:
            conditions.append(
                AlertCondition(
                    category="income_expense",
                    subcategory="monthly_spending_cap",
                    kind="threshold",
                    severity="risk",
                    message=f"Monthly spending ({month_spending:.2f}) has reached or exceeded cap ({cap:.2f})",
                )
            )
        elif month_spending >= cap * Decimal("0.90"):
            conditions.append(
                AlertCondition(
                    category="income_expense",
                    subcategory="monthly_spending_cap",
                    kind="threshold",
                    severity="warning",
                    message=f"Monthly spending ({month_spending:.2f}) has reached 90% of cap ({cap:.2f})",
                )
            )

    # 2. Monthly Savings Target (prorated by elapsed days in month)
    if profile.monthly_savings_target is not None and profile.monthly_savings_target > Decimal("0.00"):
        target = profile.monthly_savings_target
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_elapsed = max(1, today.day)
        prorated_target = (target * Decimal(days_elapsed)) / Decimal(days_in_month)

        if prorated_target > Decimal("0.00"):
            if month_savings < prorated_target * Decimal("0.50"):
                conditions.append(
                    AlertCondition(
                        category="savings",
                        subcategory="monthly_savings_target",
                        kind="threshold",
                        severity="risk",
                        message=(
                            f"Month-to-date savings ({month_savings:.2f}) is critically behind target "
                            f"({target:.2f}, prorated: {prorated_target:.2f})"
                        ),
                    )
                )
            elif month_savings < prorated_target * Decimal("0.75"):
                conditions.append(
                    AlertCondition(
                        category="savings",
                        subcategory="monthly_savings_target",
                        kind="threshold",
                        severity="warning",
                        message=(
                            f"Month-to-date savings ({month_savings:.2f}) is behind target "
                            f"({target:.2f}, prorated: {prorated_target:.2f})"
                        ),
                    )
                )

    # Days elapsed in current week (Monday=1, Sunday=7)
    days_elapsed_week = today.weekday() + 1

    # 3. Weekly Study Hours (prorated by elapsed days in week)
    if profile.weekly_study_hours is not None and profile.weekly_study_hours > Decimal("0.00"):
        target_hours = profile.weekly_study_hours
        prorated_hours = (target_hours * Decimal(days_elapsed_week)) / Decimal(7)

        if prorated_hours > Decimal("0.00"):
            if week_study_hours < prorated_hours * Decimal("0.50"):
                conditions.append(
                    AlertCondition(
                        category="study",
                        subcategory="weekly_study_hours",
                        kind="threshold",
                        severity="risk",
                        message=(
                            f"Week-to-date study time ({week_study_hours:.1f}h) is critically behind target "
                            f"({target_hours:.1f}h, prorated: {prorated_hours:.1f}h)"
                        ),
                    )
                )
            elif week_study_hours < prorated_hours * Decimal("0.75"):
                conditions.append(
                    AlertCondition(
                        category="study",
                        subcategory="weekly_study_hours",
                        kind="threshold",
                        severity="warning",
                        message=(
                            f"Week-to-date study time ({week_study_hours:.1f}h) is behind target "
                            f"({target_hours:.1f}h, prorated: {prorated_hours:.1f}h)"
                        ),
                    )
                )

    # 4. Weekly Fitness Minutes (prorated by elapsed days in week)
    if profile.weekly_fitness_minutes is not None and profile.weekly_fitness_minutes > 0:
        target_mins = profile.weekly_fitness_minutes
        prorated_mins = (float(target_mins) * days_elapsed_week) / 7.0

        if prorated_mins > 0.0:
            actual_mins = float(week_fitness_minutes)
            if actual_mins < prorated_mins * 0.50:
                conditions.append(
                    AlertCondition(
                        category="fitness",
                        subcategory="weekly_fitness_minutes",
                        kind="threshold",
                        severity="risk",
                        message=(
                            f"Week-to-date fitness ({week_fitness_minutes}m) is critically behind target "
                            f"({target_mins}m, prorated: {int(prorated_mins)}m)"
                        ),
                    )
                )
            elif actual_mins < prorated_mins * 0.75:
                conditions.append(
                    AlertCondition(
                        category="fitness",
                        subcategory="weekly_fitness_minutes",
                        kind="threshold",
                        severity="warning",
                        message=(
                            f"Week-to-date fitness ({week_fitness_minutes}m) is behind target "
                            f"({target_mins}m, prorated: {int(prorated_mins)}m)"
                        ),
                    )
                )

    # 5. Weekly Habit Completions (prorated by elapsed days in week)
    if profile.weekly_habit_completions is not None and profile.weekly_habit_completions > 0:
        target_habits = profile.weekly_habit_completions
        prorated_habits = (float(target_habits) * days_elapsed_week) / 7.0

        if prorated_habits > 0.0:
            actual_habits = float(week_habit_completions)
            if actual_habits < prorated_habits * 0.50:
                conditions.append(
                    AlertCondition(
                        category="habits",
                        subcategory="weekly_habit_completions",
                        kind="threshold",
                        severity="risk",
                        message=(
                            f"Week-to-date habit completions ({week_habit_completions}) is critically behind target "
                            f"({target_habits}, prorated: {int(prorated_habits)})"
                        ),
                    )
                )
            elif actual_habits < prorated_habits * 0.75:
                conditions.append(
                    AlertCondition(
                        category="habits",
                        subcategory="weekly_habit_completions",
                        kind="threshold",
                        severity="warning",
                        message=(
                            f"Week-to-date habit completions ({week_habit_completions}) is behind target "
                            f"({target_habits}, prorated: {int(prorated_habits)})"
                        ),
                    )
                )

    return conditions


def compute_trend_alerts(
    forecasts: Sequence[Forecast],
    recent_entries: Dict[Tuple[str, Optional[str]], Entry],
) -> List[AlertCondition]:
    """
    Evaluate trend-based alert rules by checking whether recent actual entries
    deviate outside the confidence intervals of reliable series forecasts.
    
    Rules:
    - Only evaluates forecasts with reliability in ('low_confidence', 'reliable').
    - If reliability is 'insufficient', NO alert is fabricated.
    - If value is inside [lower, upper], no alert.
    - If value is outside by <= 1.5 * band_width: warning.
    - If value is outside by > 1.5 * band_width: risk.
    """
    conditions: List[AlertCondition] = []

    for forecast in forecasts:
        # Trend alerts strictly require meaningful statistical confidence.
        # Insufficient data means no valid predictive model exists, so this rule
        # intentionally does not fire (distinct from asserting the series is "on track").
        if forecast.reliability not in ("low_confidence", "reliable"):
            continue

        if not forecast.forecast_points:
            continue

        series_key = (forecast.category, forecast.subcategory)
        entry = recent_entries.get(series_key)
        if entry is None or entry.deleted_at is not None:
            continue

        entry_val = float(entry.value)
        entry_date = entry.occurred_at

        # Match with the nearest forecast point in time
        try:
            closest_point = min(
                forecast.forecast_points,
                key=lambda p: abs((date.fromisoformat(p["date"]) - entry_date).days),
            )
        except Exception:
            logger.warning("Malformed forecast points for series %s", series_key)
            continue

        lower = float(closest_point.get("lower", 0.0))
        upper = float(closest_point.get("upper", 0.0))
        band_width = max(0.01, upper - lower)

        if entry_val < lower:
            deviation = lower - entry_val
        elif entry_val > upper:
            deviation = entry_val - upper
        else:
            deviation = 0.0

        if deviation <= 0.0:
            # Within confidence band: on track
            continue

        series_label = (
            f"{forecast.category} ({forecast.subcategory})"
            if forecast.subcategory
            else forecast.category
        )

        if deviation <= 1.5 * band_width:
            severity = "warning"
            message = (
                f"Recent entry for '{series_label}' ({entry_val:.2f}) "
                f"is outside forecast confidence band [{lower:.2f}, {upper:.2f}]"
            )
        else:
            severity = "risk"
            message = (
                f"Recent entry for '{series_label}' ({entry_val:.2f}) "
                f"deviates significantly from forecast confidence band [{lower:.2f}, {upper:.2f}]"
            )

        conditions.append(
            AlertCondition(
                category=forecast.category,
                subcategory=forecast.subcategory,
                kind="trend",
                severity=severity,
                message=message,
            )
        )

    return conditions
