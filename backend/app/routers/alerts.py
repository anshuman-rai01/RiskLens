"""
FastAPI router for on-demand alert computation and state reconciliation.

Alert rules evaluated:
1. Threshold rules: Evaluates active goals against expected pace to deadline.
2. Trend rules: Evaluates recent series data points against Prophet forecast bands.

Reconciliation discipline:
- Evaluated on-demand on every GET /alerts call.
- Active conditions matching existing unresolved alerts are updated in-place (severity/message
  updated if changed, triggered_at preserved as the origin timestamp of the condition).
- Newly appeared conditions produce new alert rows with triggered_at = now().
- Conditions that are no longer true have resolved_at set to now().
- Strict user-isolation and response sanitization enforced across all paths.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.alert import Alert
from app.models.entry import Entry
from app.models.forecast import Forecast
from app.models.goal import Goal
from app.models.profile import Profile
from app.models.user import User
from app.schemas.alert import AlertListResponse, AlertResponse
from app.services.alerting import (
    AlertCondition,
    compute_baseline_alerts,
    compute_threshold_alerts,
    compute_trend_alerts,
)
from app.services.forecasting import compute_forecast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=AlertListResponse,
    summary="Retrieve and reconcile active or historical risk alerts",
)
async def get_alerts(
    status_filter: str = Query(
        "active",
        alias="status",
        pattern="^(active|all)$",
        description="Filter alerts: 'active' (unresolved only, default) or 'all' (history)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """
    On-demand risk alert evaluation and DB reconciliation:
    1. Recomputes goal threshold pacing alerts.
    2. Reads cached forecasts directly (or computes initial forecast if none exists),
       and compares recent entries against the confidence intervals.
    3. Reconciles computed active conditions with existing DB alert rows.
    4. Returns active alerts (resolved_at IS NULL) or all alerts based on status query parameter.
    """
    try:
        now_utc = datetime.now(timezone.utc)

        # ── 1. Threshold Alerts (Goals) ──────────────────────────────────
        goals_stmt = select(Goal).where(
            Goal.user_id == current_user.id,
            Goal.deleted_at.is_(None),
        )
        goals = list((await db.execute(goals_stmt)).scalars().all())
        threshold_conditions = compute_threshold_alerts(goals, current_date=now_utc.date())

        # ── 1b. Baseline Alerts (Profile) ────────────────────────────────
        profile_stmt = select(Profile).where(Profile.user_id == current_user.id)
        profile = (await db.execute(profile_stmt)).scalar_one_or_none()

        today_date = now_utc.date()
        start_of_month = date(today_date.year, today_date.month, 1)
        start_of_week = today_date - timedelta(days=today_date.weekday())
        window_start = min(start_of_month, start_of_week)

        recent_entries_stmt = select(Entry).where(
            Entry.user_id == current_user.id,
            Entry.deleted_at.is_(None),
            Entry.occurred_at >= window_start,
            Entry.occurred_at <= today_date + timedelta(days=1),
        )
        recent_baseline_entries = list((await db.execute(recent_entries_stmt)).scalars().all())

        month_spending = Decimal("0.00")
        month_savings = Decimal("0.00")
        week_study_hours = Decimal("0.00")
        week_fitness_minutes = 0
        week_habit_completions = 0

        for entry in recent_baseline_entries:
            if entry.occurred_at >= start_of_month:
                if entry.category == "income_expense":
                    if entry.notes != "income" and entry.unit != "income":
                        month_spending += entry.value
                elif entry.category == "savings":
                    month_savings += entry.value

            if entry.occurred_at >= start_of_week:
                if entry.category == "study":
                    week_study_hours += entry.value
                elif entry.category == "fitness":
                    week_fitness_minutes += int(entry.value)
                elif entry.category == "habits":
                    week_habit_completions += int(entry.value)

        baseline_conditions = compute_baseline_alerts(
            profile=profile,
            month_spending=month_spending,
            month_savings=month_savings,
            week_study_hours=week_study_hours,
            week_fitness_minutes=week_fitness_minutes,
            week_habit_completions=week_habit_completions,
            current_date=today_date,
        )

        # ── 2. Trend Alerts (Forecasts & Recent Entries) ─────────────────
        # Fetch existing cached forecasts for this user
        cached_stmt = select(Forecast).where(
            Forecast.user_id == current_user.id,
        )
        cached_forecasts = list((await db.execute(cached_stmt)).scalars().all())
        forecasts_by_series: Dict[Tuple[str, Optional[str]], Forecast] = {
            (f.category, f.subcategory): f for f in cached_forecasts
        }

        # Query distinct series owned by this user
        series_stmt = (
            select(Entry.category, Entry.subcategory)
            .where(
                Entry.user_id == current_user.id,
                Entry.deleted_at.is_(None),
            )
            .distinct()
        )
        user_series = list((await db.execute(series_stmt)).all())

        # For any series that does not yet have a cached forecast, compute initial forecast
        for cat, sub in user_series:
            series_key = (cat, sub)
            if series_key not in forecasts_by_series:
                entries_stmt = (
                    select(Entry)
                    .where(
                        Entry.user_id == current_user.id,
                        Entry.category == cat,
                        Entry.subcategory == sub if sub is not None else Entry.subcategory.is_(None),
                        Entry.deleted_at.is_(None),
                    )
                    .order_by(Entry.occurred_at.asc())
                )
                series_entries = list((await db.execute(entries_stmt)).scalars().all())

                # compute_forecast instantly returns 'insufficient' for < 14 points
                forecast_result = compute_forecast(series_entries, horizon_days=14)
                new_forecast = Forecast(
                    user_id=current_user.id,
                    category=cat,
                    subcategory=sub,
                    generated_at=now_utc,
                    horizon_days=14,
                    forecast_points=forecast_result["forecast_points"],
                    data_point_count=forecast_result["data_point_count"],
                    reliability=forecast_result["reliability"],
                    message=forecast_result["message"],
                )
                db.add(new_forecast)
                forecasts_by_series[series_key] = new_forecast

        # Get latest entry per series for trend comparison
        recent_entries: Dict[Tuple[str, Optional[str]], Entry] = {}
        for cat, sub in user_series:
            series_key = (cat, sub)
            latest_entry_stmt = (
                select(Entry)
                .where(
                    Entry.user_id == current_user.id,
                    Entry.category == cat,
                    Entry.subcategory == sub if sub is not None else Entry.subcategory.is_(None),
                    Entry.deleted_at.is_(None),
                )
                .order_by(Entry.occurred_at.desc(), Entry.created_at.desc())
                .limit(1)
            )
            latest_entry = (await db.execute(latest_entry_stmt)).scalar_one_or_none()
            if latest_entry is not None:
                recent_entries[series_key] = latest_entry

        trend_conditions = compute_trend_alerts(
            list(forecasts_by_series.values()),
            recent_entries,
        )

        # ── 3. Combine & Reconcile Active Conditions ─────────────────────
        active_conditions: List[AlertCondition] = (
            threshold_conditions + baseline_conditions + trend_conditions
        )
        active_cond_map: Dict[Tuple[str, Optional[str], str], AlertCondition] = {
            (c.category, c.subcategory, c.kind): c for c in active_conditions
        }

        # Query existing unresolved alerts for this user
        existing_unresolved_stmt = select(Alert).where(
            Alert.user_id == current_user.id,
            Alert.resolved_at.is_(None),
        )
        existing_unresolved = list((await db.execute(existing_unresolved_stmt)).scalars().all())
        unresolved_map: Dict[Tuple[str, Optional[str], str], Alert] = {
            (a.category, a.subcategory, a.kind): a for a in existing_unresolved
        }

        # 3a. Update in-place or Insert active conditions
        for cond_key, cond in active_cond_map.items():
            if cond_key in unresolved_map:
                existing_alert = unresolved_map[cond_key]
                # Condition still active: update in-place if severity or message changed
                if (
                    existing_alert.severity != cond.severity
                    or existing_alert.message != cond.message
                ):
                    existing_alert.severity = cond.severity
                    existing_alert.message = cond.message
                    # triggered_at is strictly preserved as when the condition first emerged
            else:
                # Newly appeared condition
                new_alert = Alert(
                    user_id=current_user.id,
                    category=cond.category,
                    subcategory=cond.subcategory,
                    kind=cond.kind,
                    severity=cond.severity,
                    message=cond.message,
                    triggered_at=now_utc,
                )
                db.add(new_alert)

        # 3b. Resolve alerts whose condition is no longer active
        for alert_key, existing_alert in unresolved_map.items():
            if alert_key not in active_cond_map:
                existing_alert.resolved_at = now_utc

        await db.commit()

        # ── 4. Retrieve and Format Result ────────────────────────────────
        result_stmt = select(Alert).where(Alert.user_id == current_user.id)
        if status_filter == "active":
            result_stmt = result_stmt.where(Alert.resolved_at.is_(None))
        result_stmt = result_stmt.order_by(Alert.triggered_at.desc())

        alerts = list((await db.execute(result_stmt)).scalars().all())

        return AlertListResponse(
            items=[AlertResponse.model_validate(a) for a in alerts],
            total=len(alerts),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to retrieve/reconcile alerts for user %s: %s",
            getattr(current_user, "id", "unknown"),
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process alerts at this time",
        )
