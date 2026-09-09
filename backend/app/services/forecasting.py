"""
Forecasting service utilizing Prophet for classical statistical time-series forecasting,
reliability tiering, and graceful edge-case handling.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
from prophet import Prophet

from app.models.entry import Entry

logger = logging.getLogger(__name__)

# Suppress verbose logs from cmdstanpy and prophet
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)


def compute_forecast(
    entries: List[Entry],
    horizon_days: int = 14,
) -> Dict[str, Any]:
    """
    Given a list of historical Entry records for a series:
    1. Aggregates daily values into (ds, y) points.
    2. Evaluates reliability tiering:
       - < 14 points: 'insufficient'
       - 14-27 points: 'low_confidence'
       - >= 28 points: 'reliable'
    3. Fits Prophet and predicts `horizon_days` steps into the future.
    4. Handles degenerate series or fitting errors gracefully without raising 500s.
    """
    if not entries:
        return {
            "reliability": "insufficient",
            "data_point_count": 0,
            "message": "More data is required to generate a forecast",
            "forecast_points": [],
        }

    # Aggregate by date (sum daily points)
    raw_data = [{"ds": e.occurred_at, "y": float(e.value)} for e in entries]
    df_raw = pd.DataFrame(raw_data)
    df_daily = (
        df_raw.groupby("ds", as_index=False)["y"]
        .sum()
        .sort_values("ds")
        .reset_index(drop=True)
    )

    n_points = len(df_daily)

    # ── Tier 1: Insufficient Data (< 14 data points) ─────────────────
    if n_points < 14:
        return {
            "reliability": "insufficient",
            "data_point_count": n_points,
            "message": "More data is required to generate a forecast",
            "forecast_points": [],
        }

    # ── Tier 2 & 3: Low Confidence (14-27) or Reliable (>= 28) ──────
    reliability = "low_confidence" if n_points < 28 else "reliable"

    try:
        # Convert date objects to datetime format expected by Prophet
        df_daily["ds"] = pd.to_datetime(df_daily["ds"])

        # Check for constant/degenerate values
        is_constant = df_daily["y"].nunique() <= 1

        # Fit Prophet model
        model = Prophet(
            interval_width=0.80,
            daily_seasonality=False,
            weekly_seasonality=(n_points >= 14),
            yearly_seasonality=False,
        )
        model.fit(df_daily)

        # Make future dataframe strictly for future horizon
        future = model.make_future_dataframe(
            periods=horizon_days,
            freq="D",
            include_history=False,
        )
        forecast = model.predict(future)

        forecast_points: List[Dict[str, Any]] = []
        for _, row in forecast.iterrows():
            pred = round(float(row["yhat"]), 2)
            lower = round(float(row["yhat_lower"]), 2)
            upper = round(float(row["yhat_upper"]), 2)

            # Ensure lower <= pred <= upper sanity
            if lower > pred:
                lower = pred
            if upper < pred:
                upper = pred

            forecast_points.append(
                {
                    "date": pd.to_datetime(row["ds"]).strftime("%Y-%m-%d"),
                    "predicted": pred,
                    "lower": lower,
                    "upper": upper,
                }
            )

        message = (
            "Model fitted with constant variance."
            if is_constant
            else None
        )

        return {
            "reliability": reliability,
            "data_point_count": n_points,
            "message": message,
            "forecast_points": forecast_points,
        }

    except Exception as exc:
        logger.warning("Prophet fitting failed for series: %s", exc, exc_info=True)
        # Fallback projection without raising 500
        last_y = float(df_daily["y"].iloc[-1])
        last_date = pd.to_datetime(df_daily["ds"].iloc[-1])
        fallback_points = []
        for day_offset in range(1, horizon_days + 1):
            next_date = last_date + pd.Timedelta(days=day_offset)
            fallback_points.append(
                {
                    "date": next_date.strftime("%Y-%m-%d"),
                    "predicted": round(last_y, 2),
                    "lower": round(last_y * 0.9, 2),
                    "upper": round(last_y * 1.1, 2),
                }
            )

        return {
            "reliability": "low_confidence",
            "data_point_count": n_points,
            "message": "Forecast temporarily unavailable, using trend fallback",
            "forecast_points": fallback_points,
        }

