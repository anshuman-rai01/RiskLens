"""
FastAPI router for statistical time-series forecasting with caching and on-demand recomputation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.entry import Entry
from app.models.forecast import Forecast
from app.models.user import User
from app.schemas.forecast import ForecastResponse
from app.services.forecasting import compute_forecast

logger = logging.getLogger(__name__)

router = APIRouter(tags=["forecasts"])


# ==============================================================================
# ISOLATION & ON-DEMAND CACHING:
#
# Forecasts are strictly scoped by current_user.id.
# If a cached forecast exists and no entries have been created, modified,
# or deleted since `generated_at`, the cached forecast is returned directly.
# Otherwise, Prophet refits on-demand and updates the cache.
# ==============================================================================


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    summary="Get or recompute series forecast with confidence intervals",
)
async def get_forecast(
    category: str = Query(..., description="Category identifier (e.g. income_expense, study)"),
    subcategory: Optional[str] = Query(None, description="Subcategory identifier"),
    horizon_days: int = Query(14, ge=1, le=90, description="Number of days to forecast into future"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastResponse:
    """
    Retrieve forecasted values and confidence intervals for a time-series.
    Employs reliability tiering:
      - < 14 points: 'insufficient'
      - 14-27 points: 'low_confidence'
      - >= 28 points: 'reliable'
    """
    sub_val = subcategory.strip() if subcategory else None
    entry_filters = [
        Entry.user_id == current_user.id,
        Entry.category == category,
    ]
    if sub_val is not None:
        entry_filters.append(Entry.subcategory == sub_val)

    # 1. Check for existing cached forecast
    forecast_stmt = select(Forecast).where(
        Forecast.user_id == current_user.id,
        Forecast.category == category,
        Forecast.subcategory == sub_val if sub_val is not None else Forecast.subcategory.is_(None),
    )
    cached_forecast = (await db.execute(forecast_stmt)).scalar_one_or_none()

    # 2. Universal Threshold Enforcement: Query actual active database records
    entries_stmt = (
        select(Entry)
        .where(
            *entry_filters,
            Entry.deleted_at.is_(None),
        )
        .order_by(Entry.occurred_at.asc())
    )
    entries = list((await db.execute(entries_stmt)).scalars().all())
    actual_records_count = len(entries)

    # Enforce strict dynamic threshold: len(actual_db_records) < 14 is universally insufficient
    if actual_records_count < 14:
        logger.info(
            "Insufficient data for user=%s, series=(%s, %s): %d records (requires >= 14)",
            current_user.id,
            category,
            sub_val,
            actual_records_count,
        )
        now_utc = datetime.now(timezone.utc)
        if cached_forecast is not None:
            cached_forecast.generated_at = now_utc
            cached_forecast.horizon_days = horizon_days
            cached_forecast.forecast_points = []
            cached_forecast.data_point_count = actual_records_count
            cached_forecast.reliability = "insufficient"
            cached_forecast.message = "More data is required to generate a forecast"
        else:
            cached_forecast = Forecast(
                user_id=current_user.id,
                category=category,
                subcategory=sub_val,
                generated_at=now_utc,
                horizon_days=horizon_days,
                forecast_points=[],
                data_point_count=actual_records_count,
                reliability="insufficient",
                message="More data is required to generate a forecast",
            )
            db.add(cached_forecast)

        await db.commit()
        await db.refresh(cached_forecast)
        return ForecastResponse.model_validate(cached_forecast)

    # 3. Check if cached forecast is fresh (matching horizon, record count, and no newer modifications)
    if (
        cached_forecast is not None
        and cached_forecast.horizon_days == horizon_days
        and cached_forecast.data_point_count == actual_records_count
        and cached_forecast.reliability != "insufficient"
    ):
        stale_check = select(func.count()).select_from(Entry).where(
            *entry_filters,
            (
                (Entry.created_at > cached_forecast.generated_at)
                | (Entry.updated_at > cached_forecast.generated_at)
                | (Entry.deleted_at > cached_forecast.generated_at)
            ),
        )
        stale_count = (await db.execute(stale_check)).scalar_one()

        if stale_count == 0:
            logger.info(
                "Cache HIT: Returning cached forecast for user=%s, series=(%s, %s), horizon=%s",
                current_user.id,
                category,
                sub_val,
                horizon_days,
            )
            return ForecastResponse.model_validate(cached_forecast)

    # 4. Cache MISS or STALE: Recompute forecast with actual records using Prophet
    logger.info(
        "Cache MISS: Recomputing forecast for user=%s, series=(%s, %s)",
        current_user.id,
        category,
        sub_val,
    )
    result = compute_forecast(entries, horizon_days=horizon_days)
    now_utc = datetime.now(timezone.utc)

    if cached_forecast is not None:
        cached_forecast.generated_at = now_utc
        cached_forecast.horizon_days = horizon_days
        cached_forecast.forecast_points = result["forecast_points"]
        cached_forecast.data_point_count = result["data_point_count"]
        cached_forecast.reliability = result["reliability"]
        cached_forecast.message = result["message"]
    else:
        cached_forecast = Forecast(
            user_id=current_user.id,
            category=category,
            subcategory=sub_val,
            generated_at=now_utc,
            horizon_days=horizon_days,
            forecast_points=result["forecast_points"],
            data_point_count=result["data_point_count"],
            reliability=result["reliability"],
            message=result["message"],
        )
        db.add(cached_forecast)

    await db.commit()
    await db.refresh(cached_forecast)

    return ForecastResponse.model_validate(cached_forecast)
