"""
Fitness Plan scenario — data-driven simulation.

Projects fitness activity forward using the shared Prophet forecasting function
with daily aggregation and 90-day horizon. Full Best/Expected/Risk chart with
4 lines using Prophet's confidence intervals.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from app.models.entry import Entry
from app.services.forecasting import compute_forecast
from app.services.scenarios import DataDrivenScenario

logger = logging.getLogger(__name__)

# Trailing window for computing current average
TRAILING_DAYS = 30


class FitnessPlan(DataDrivenScenario):
    """
    Scenario: What does my fitness trajectory look like at my current pace
    vs. a target frequency?

    - Horizon: 90 days, daily aggregation
    - growth="linear" (default — shorter horizon means less extrapolation risk)
    - Reliability: standard daily thresholds (14/28)
    - Chart: 4 lines (current_baseline, best_case, expected_case, risk_case)
    """

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_weekly_minutes = float(params.get("target_weekly_minutes", 150))
        target_daily_minutes = target_weekly_minutes / 7.0

        # Filter to fitness entries only
        fitness_entries = [e for e in entries if e.category == "fitness"]

        if not fitness_entries:
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": 0,
                "message": "No fitness entries found to generate a fitness plan projection.",
                "derived_values": {
                    "current_avg_daily_minutes": None,
                    "target_daily_minutes": round(target_daily_minutes, 2),
                },
                "correlation_r_squared": None,
            }

        # ── Compute current average daily minutes ─────────────────────
        cutoff = date.today() - timedelta(days=TRAILING_DAYS)
        recent = [e for e in fitness_entries if e.occurred_at >= cutoff]
        if recent:
            current_avg = sum(float(e.value) for e in recent) / TRAILING_DAYS
        else:
            # Fall back to all-time average
            total_days = max(
                1,
                (max(e.occurred_at for e in fitness_entries)
                 - min(e.occurred_at for e in fitness_entries)).days + 1,
            )
            current_avg = sum(float(e.value) for e in fitness_entries) / total_days

        # ── Prophet forecast ──────────────────────────────────────────
        # 90-day horizon, daily aggregation, standard thresholds
        forecast_result = compute_forecast(
            entries=fitness_entries,
            horizon_days=90,
            freq="D",
            growth="linear",
            min_points_low=14,
            min_points_reliable=28,
        )

        reliability = forecast_result["reliability"]
        data_point_count = forecast_result["data_point_count"]

        if reliability == "insufficient":
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": data_point_count,
                "message": forecast_result.get("message", "Insufficient fitness data for projection."),
                "derived_values": {
                    "current_avg_daily_minutes": round(current_avg, 2),
                    "target_daily_minutes": round(target_daily_minutes, 2),
                },
                "correlation_r_squared": None,
            }

        # ── Build 4-line chart ────────────────────────────────────────
        current_baseline_points = []
        best_case_points = []
        expected_case_points = []
        risk_case_points = []

        for fp in forecast_result["forecast_points"]:
            current_baseline_points.append({
                "date": fp["date"],
                "value": round(current_avg, 2),
            })
            best_case_points.append({
                "date": fp["date"],
                "value": round(fp["upper"], 2),
            })
            expected_case_points.append({
                "date": fp["date"],
                "value": round(fp["predicted"], 2),
            })
            risk_case_points.append({
                "date": fp["date"],
                "value": round(fp["lower"], 2),
            })

        lines = [
            {"label": "current_baseline", "points": current_baseline_points},
            {"label": "best_case", "points": best_case_points},
            {"label": "expected_case", "points": expected_case_points},
            {"label": "risk_case", "points": risk_case_points},
        ]

        return {
            "lines": lines,
            "reliability": reliability,
            "data_point_count": data_point_count,
            "message": None,
            "derived_values": {
                "current_avg_daily_minutes": round(current_avg, 2),
                "target_daily_minutes": round(target_daily_minutes, 2),
                "target_weekly_minutes": target_weekly_minutes,
            },
            "correlation_r_squared": None,
        }
