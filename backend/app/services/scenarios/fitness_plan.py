"""
Fitness Plan scenario — data-driven simulation.

Projects cumulative workout minutes forward with deterministic daily pacing
and an 80% variability band scaling with sqrt(D) for independent days.
Deliberately deviates from Prophet's compute_forecast because its business formula is deterministic.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.models.entry import Entry
from app.services.scenarios import DataDrivenScenario

logger = logging.getLogger(__name__)


class FitnessPlan(DataDrivenScenario):
    """
    Scenario: What does my fitness trajectory look like at my current pace
    vs. a target frequency?

    - Cumulative projection starting from 0 at D=0
    - Historical daily avg & sample std dev calculated over calendar days (zero-filling rest days)
    - 80% two-sided variability band (z = 1.2816) scaling with sqrt(D)
    - Tiers: < 14 days insufficient, 14-27 low_confidence, >= 28 reliable
    - Chart: 4 lines (current_baseline, expected_case, best_case, risk_case)
    """

    staleness_scope: Optional[str] = "fitness"

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_weekly_minutes = float(params.get("target_weekly_minutes", 150))
        horizon_days = int(params.get("horizon_days", 90))
        history_days = params.get("history_days")
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
                    "historical_daily_avg": 0.0,
                    "daily_std_dev": 0.0,
                    "upper_bound_spread": 0.0,
                    "lower_bound_spread": 0.0,
                    "confidence_level": 0.8,
                    "history_window_days": 0,
                    "target_daily_minutes": round(target_daily_minutes, 2),
                    "target_weekly_minutes": target_weekly_minutes,
                    "horizon_days": horizon_days,
                },
                "correlation_r_squared": None,
            }

        first_fitness_date = min(e.occurred_at for e in fitness_entries)
        today = date.today()

        if history_days is not None:
            window_start = max(first_fitness_date, today - timedelta(days=int(history_days) - 1))
        else:
            window_start = first_fitness_date
        window_end = today

        n_days = (window_end - window_start).days + 1
        if n_days < 1:
            n_days = 1

        # Sum sessions per calendar day, zero-filling rest days
        daily_sums: Dict[date, float] = {}
        for e in fitness_entries:
            if window_start <= e.occurred_at <= window_end:
                daily_sums[e.occurred_at] = daily_sums.get(e.occurred_at, 0.0) + float(e.value)

        daily_series = [daily_sums.get(window_start + timedelta(days=i), 0.0) for i in range(n_days)]
        historical_daily_avg = sum(daily_series) / n_days
        daily_std_dev = statistics.stdev(daily_series) if n_days >= 2 else 0.0

        # 80% two-sided normal z = 1.2816
        z = 1.2816
        spread = z * daily_std_dev

        # Reliability tiers by calendar days in history window
        if n_days < 14:
            reliability = "insufficient"
        elif n_days < 28:
            reliability = "low_confidence"
        else:
            reliability = "reliable"

        derived_values = {
            "historical_daily_avg": round(historical_daily_avg, 2),
            "daily_std_dev": round(daily_std_dev, 2),
            "upper_bound_spread": round(spread, 2),
            "lower_bound_spread": round(spread, 2),
            "confidence_level": 0.8,
            "history_window_days": n_days,
            "target_daily_minutes": round(target_daily_minutes, 2),
            "target_weekly_minutes": target_weekly_minutes,
            "horizon_days": horizon_days,
        }

        if reliability == "insufficient":
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": n_days,
                "message": f"Insufficient fitness history ({n_days} calendar days). At least 14 days required.",
                "derived_values": derived_values,
                "correlation_r_squared": None,
            }

        # Build 4 cumulative trajectories from Y-intercept = 0 at D=0
        baseline_points = []
        expected_points = []
        best_points = []
        risk_points = []

        for d in range(horizon_days + 1):
            pt_date = (today + timedelta(days=d)).isoformat()
            if d == 0:
                base_v = 0.0
                exp_v = 0.0
                best_v = 0.0
                risk_v = 0.0
            else:
                base_v = historical_daily_avg * d
                exp_v = target_daily_minutes * d
                band_offset = z * daily_std_dev * math.sqrt(d)
                best_v = exp_v + band_offset
                risk_v = max(0.0, exp_v - band_offset)

            baseline_points.append({"x": d, "date": pt_date, "value": round(base_v, 2)})
            expected_points.append({"x": d, "date": pt_date, "value": round(exp_v, 2)})
            best_points.append({"x": d, "date": pt_date, "value": round(best_v, 2)})
            risk_points.append({"x": d, "date": pt_date, "value": round(risk_v, 2)})

        lines = [
            {"label": "current_baseline", "points": baseline_points},
            {"label": "expected_case", "points": expected_points},
            {"label": "best_case", "points": best_points},
            {"label": "risk_case", "points": risk_points},
        ]

        return {
            "lines": lines,
            "reliability": reliability,
            "data_point_count": n_days,
            "message": None,
            "derived_values": derived_values,
            "correlation_r_squared": None,
        }
