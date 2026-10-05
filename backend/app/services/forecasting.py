"""
Forecasting service utilizing Prophet for classical statistical time-series forecasting,
reliability tiering, and graceful edge-case handling.

This is the SINGLE source of truth for Prophet-based forecasting. All simulation
scenarios call this function — no independent forecasting code exists elsewhere.
The signature is extended with freq, growth, and threshold parameters so scenarios
can customize behavior without forking the logic.
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
    freq: str = "D",
    growth: str = "linear",
    min_points_low: int = 14,
    min_points_reliable: int = 28,
    include_history: bool = False,
    zero_fill: bool = False,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Given a list of historical Entry records for a series:
    1. Aggregates values by the given frequency into (ds, y) points.
    2. Evaluates reliability tiering:
       - < min_points_low:     'insufficient'
       - min_points_low to min_points_reliable-1: 'low_confidence'
       - >= min_points_reliable: 'reliable'
    3. Fits Prophet and predicts `horizon_days` steps into the future.
    4. Handles degenerate series or fitting errors gracefully without raising 500s.

    When `zero_fill` is True and `freq == "D"`:
        Missing days between the first entry date and max(last_entry_date, as_of)
        are reindexed and filled with 0.0.
        Assumption: days without a logged entry are treated as zero.
        `n_points` (used for reliability tiering and data_point_count) reflects
        only days with actual logged entries, preventing synthetic zeros from
        inflating reliability.

    Parameters:
        entries: Historical Entry records
        horizon_days: Number of periods to forecast (days if freq="D", months if freq="MS")
        freq: Aggregation frequency ("D" for daily, "MS" for month-start, "W" for weekly)
        growth: Prophet growth mode ("linear" or "flat")
        min_points_low: Minimum aggregated points for low_confidence tier
        min_points_reliable: Minimum aggregated points for reliable tier
        include_history: If True, include historical fitted values in output
        zero_fill: If True (and freq="D"), fill missing calendar days with 0
        as_of: Reference date to anchor the horizon. If provided and after the last
               entry, missing days up to as_of are zero-filled so forecast starts tomorrow.
    """
    if not entries:
        return {
            "reliability": "insufficient",
            "data_point_count": 0,
            "message": "More data is required to generate a forecast",
            "forecast_points": [],
        }

    # Build raw dataframe
    raw_data = [{"ds": e.occurred_at, "y": float(e.value)} for e in entries]
    df_raw = pd.DataFrame(raw_data)
    df_raw["ds"] = pd.to_datetime(df_raw["ds"])

    # Aggregate by frequency
    if freq == "D":
        df_agg = (
            df_raw.groupby("ds", as_index=False)["y"]
            .sum()
            .sort_values("ds")
            .reset_index(drop=True)
        )
    elif freq == "MS":
        # Monthly aggregation: sum values within each calendar month
        df_raw["month"] = df_raw["ds"].dt.to_period("M").dt.to_timestamp()
        df_agg = (
            df_raw.groupby("month", as_index=False)["y"]
            .sum()
            .rename(columns={"month": "ds"})
            .sort_values("ds")
            .reset_index(drop=True)
        )
    elif freq == "W":
        # Weekly aggregation
        df_raw["week"] = df_raw["ds"].dt.to_period("W").dt.to_timestamp()
        df_agg = (
            df_raw.groupby("week", as_index=False)["y"]
            .sum()
            .rename(columns={"week": "ds"})
            .sort_values("ds")
            .reset_index(drop=True)
        )
    else:
        raise ValueError(f"Unsupported frequency: {freq}")

    n_points = len(df_agg)

    # ── Tier 1: Insufficient Data ─────────────────────────────────
    if n_points < min_points_low:
        return {
            "reliability": "insufficient",
            "data_point_count": n_points,
            "message": "More data is required to generate a forecast",
            "forecast_points": [],
        }

    # ── Tier 2 & 3: Low Confidence or Reliable ───────────────────
    reliability = "low_confidence" if n_points < min_points_reliable else "reliable"

    # ── Zero-fill handling (when enabled for daily frequency) ────
    if zero_fill and freq == "D":
        first_date = df_agg["ds"].min()
        last_entry_date = df_agg["ds"].max()
        if as_of is not None:
            as_of_dt = pd.to_datetime(as_of)
            end_date = max(last_entry_date, as_of_dt)
        else:
            end_date = last_entry_date
        full_index = pd.date_range(start=first_date, end=end_date, freq="D", name="ds")
        fit_df = (
            df_agg.set_index("ds")
            .reindex(full_index, fill_value=0.0)
            .reset_index()
        )
    else:
        fit_df = df_agg

    try:
        # Check for constant/degenerate values
        is_constant = fit_df["y"].nunique() <= 1

        # Configure seasonality based on frequency and data volume
        if freq == "D":
            weekly_seasonality = len(fit_df) >= 14
            yearly_seasonality = False
            daily_seasonality = False
        elif freq == "MS":
            weekly_seasonality = False
            yearly_seasonality = len(fit_df) >= 24
            daily_seasonality = False
        else:
            weekly_seasonality = len(fit_df) >= 4
            yearly_seasonality = False
            daily_seasonality = False

        # Fit Prophet model
        model = Prophet(
            growth=growth,
            interval_width=0.80,
            daily_seasonality=daily_seasonality,
            weekly_seasonality=weekly_seasonality,
            yearly_seasonality=yearly_seasonality,
        )
        model.fit(fit_df)

        # Make future dataframe strictly for future horizon
        future = model.make_future_dataframe(
            periods=horizon_days,
            freq=freq,
            include_history=include_history,
        )
        if not include_history:
            # Ensure we only get future points
            last_date = fit_df["ds"].max()
            future = future[future["ds"] > last_date]

        forecast = model.predict(future)

        forecast_points: List[Dict[str, Any]] = []
        date_format = "%Y-%m-%d" if freq == "D" else "%Y-%m"
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
                    "date": pd.to_datetime(row["ds"]).strftime(date_format),
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
        if zero_fill and freq == "D":
            last_y = float(fit_df["y"].mean())
            last_date = pd.to_datetime(fit_df["ds"].iloc[-1])
        else:
            last_y = float(df_agg["y"].iloc[-1])
            last_date = pd.to_datetime(df_agg["ds"].iloc[-1])

        if freq == "D":
            delta_fn = lambda i: pd.Timedelta(days=i)
            date_format = "%Y-%m-%d"
        elif freq == "MS":
            delta_fn = lambda i: pd.DateOffset(months=i)
            date_format = "%Y-%m"
        else:
            delta_fn = lambda i: pd.Timedelta(weeks=i)
            date_format = "%Y-%m-%d"

        fallback_points = []
        for offset in range(1, horizon_days + 1):
            next_date = last_date + delta_fn(offset)
            fallback_points.append(
                {
                    "date": next_date.strftime(date_format),
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
