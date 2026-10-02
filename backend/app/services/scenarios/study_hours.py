"""
Reduce Study Hours scenario — data-driven simulation.

Aggregates study and academic entries by week, runs OLS linear regression
of academic score ~ study hours, and provides a prediction interval for
a target study-hours reduction.

Uses statsmodels for regression (not Prophet), but the reliability semantics
and response shape match the other scenarios for consistency.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from app.models.entry import Entry
from app.services.scenarios import DataDrivenScenario

logger = logging.getLogger(__name__)

MIN_PAIRED_WEEKS = 14  # Minimum weekly observations before attempting regression
WEAK_R_SQUARED_THRESHOLD = 0.3
PREDICTION_INTERVAL_ALPHA = 0.20  # 80% prediction interval (matching Prophet convention)


class ReduceStudyHours(DataDrivenScenario):
    """
    Scenario: If I reduce study hours to X hours/week, what happens to
    my academic performance?

    - Pairing: aggregate study + academic entries by ISO week
    - Minimum: 14+ paired weekly observations
    - Method: OLS linear regression (statsmodels), 80% prediction interval
    - R² < 0.3 → low_confidence
    - Language: "correlation observed in your own historical data" — never causal
    """

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_hours = float(params.get("target_weekly_hours", 10.0))

        # Separate entries by category
        study_entries = [e for e in entries if e.category == "study"]
        academic_entries = [e for e in entries if e.category == "academic"]

        if not study_entries or not academic_entries:
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": 0,
                "message": "Both study and academic entries are required for this analysis.",
                "derived_values": {"target_weekly_hours": target_hours},
                "correlation_r_squared": None,
            }

        # ── Aggregate by ISO week ─────────────────────────────────────
        study_df = pd.DataFrame([
            {"ds": e.occurred_at, "y": float(e.value)} for e in study_entries
        ])
        study_df["ds"] = pd.to_datetime(study_df["ds"])
        study_df["week"] = study_df["ds"].dt.isocalendar().week.astype(int)
        study_df["year"] = study_df["ds"].dt.isocalendar().year.astype(int)
        study_weekly = (
            study_df.groupby(["year", "week"], as_index=False)["y"]
            .sum()
            .rename(columns={"y": "study_hours"})
        )

        academic_df = pd.DataFrame([
            {"ds": e.occurred_at, "y": float(e.value)} for e in academic_entries
        ])
        academic_df["ds"] = pd.to_datetime(academic_df["ds"])
        academic_df["week"] = academic_df["ds"].dt.isocalendar().week.astype(int)
        academic_df["year"] = academic_df["ds"].dt.isocalendar().year.astype(int)
        academic_weekly = (
            academic_df.groupby(["year", "week"], as_index=False)["y"]
            .mean()  # Average academic score per week
            .rename(columns={"y": "academic_score"})
        )

        # Pair weeks where both study hours and academic score exist
        paired = pd.merge(study_weekly, academic_weekly, on=["year", "week"], how="inner")
        n_paired = len(paired)

        if n_paired < MIN_PAIRED_WEEKS:
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": n_paired,
                "message": (
                    f"At least {MIN_PAIRED_WEEKS} paired weekly observations of both study hours "
                    f"and academic scores are required. Currently have {n_paired}."
                ),
                "derived_values": {
                    "target_weekly_hours": target_hours,
                    "paired_weeks": n_paired,
                },
                "correlation_r_squared": None,
            }

        # ── OLS Regression ────────────────────────────────────────────
        import statsmodels.api as sm

        X = sm.add_constant(paired["study_hours"].values)
        y = paired["academic_score"].values

        model = sm.OLS(y, X).fit()
        r_squared = round(float(model.rsquared), 4)

        # Determine reliability based on R²
        if r_squared < WEAK_R_SQUARED_THRESHOLD:
            reliability = "low_confidence"
        else:
            reliability = "reliable"

        # ── Prediction at target hours ────────────────────────────────
        # Get prediction with 80% prediction interval
        target_X = np.array([[1.0, target_hours]])
        prediction = model.get_prediction(target_X)
        pred_summary = prediction.summary_frame(alpha=PREDICTION_INTERVAL_ALPHA)

        predicted_score = round(float(pred_summary["mean"].iloc[0]), 2)
        lower_score = round(float(pred_summary["obs_ci_lower"].iloc[0]), 2)
        upper_score = round(float(pred_summary["obs_ci_upper"].iloc[0]), 2)

        # Also compute prediction at current average study hours for comparison
        current_avg_hours = round(float(paired["study_hours"].mean()), 1)
        current_X = np.array([[1.0, current_avg_hours]])
        current_prediction = model.get_prediction(current_X)
        current_summary = current_prediction.summary_frame(alpha=PREDICTION_INTERVAL_ALPHA)
        current_predicted = round(float(current_summary["mean"].iloc[0]), 2)

        # ── Build chart lines ─────────────────────────────────────────
        # Since this is a regression (not a time series), we present the
        # results as a comparison at two points: current and target
        lines = [
            {
                "label": "current_baseline",
                "points": [{"date": "current", "value": current_predicted}],
            },
            {
                "label": "best_case",
                "points": [{"date": "target", "value": upper_score}],
            },
            {
                "label": "expected_case",
                "points": [{"date": "target", "value": predicted_score}],
            },
            {
                "label": "risk_case",
                "points": [{"date": "target", "value": lower_score}],
            },
        ]

        # ── Non-causal language ───────────────────────────────────────
        r2_descriptor = "strong" if r_squared >= 0.5 else ("moderate" if r_squared >= 0.3 else "weak")
        message = (
            f"Based on the correlation observed in your own historical data "
            f"({r2_descriptor}, R²={r_squared}), reducing study hours to "
            f"{target_hours} hours/week is associated with the following "
            f"projected academic performance. This reflects a statistical "
            f"association, not a guaranteed causal outcome."
        )

        return {
            "lines": lines,
            "reliability": reliability,
            "data_point_count": n_paired,
            "message": message,
            "derived_values": {
                "target_weekly_hours": target_hours,
                "current_avg_weekly_hours": current_avg_hours,
                "predicted_score_at_target": predicted_score,
                "prediction_interval_lower": lower_score,
                "prediction_interval_upper": upper_score,
                "paired_weeks": n_paired,
                "regression_slope": round(float(model.params[1]), 4),
                "regression_intercept": round(float(model.params[0]), 4),
            },
            "correlation_r_squared": r_squared,
        }
