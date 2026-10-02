"""
Increase Savings Rate scenario — data-driven simulation.

Computes a savings rate from real historical data and projects it forward
using the shared Prophet forecasting function with growth="flat".

Income identification: uses notes field tagging convention (notes == "income").
Untagged entries are excluded from both sides of the calculation.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from app.models.entry import Entry
from app.services.forecasting import compute_forecast
from app.services.scenarios import DataDrivenScenario

logger = logging.getLogger(__name__)

# Trailing window for current rate computation
TRAILING_MONTHS = 6
MIN_INCOME_EVENTS = 3  # Floor guard: minimum income-tagged entries in window


class IncreaseSavingsRate(DataDrivenScenario):
    """
    Scenario: What if I increase my savings rate to X%?

    - Current rate: derived from real savings entries ÷ income-tagged income_expense entries
    - Trailing window: 6 months (falls back to all-time if <3 income events in window)
    - Prophet: growth="flat", freq="MS" (monthly), horizon=60 months (5 years)
    - Chart: exactly 2 lines (current_path_expected, expected_case)
    - best_case and risk_case: explicitly empty
    - Reliability: monthly thresholds (3+ months = low_confidence, 6+ = reliable)
    """

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_rate = float(params.get("target_rate", 0.20))

        # Separate entries by category
        savings_entries = [e for e in entries if e.category == "savings"]
        income_entries = [
            e for e in entries
            if e.category == "income_expense"
            and (e.notes or "").strip().lower() == "income"
        ]

        if not income_entries:
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": 0,
                "message": "No income-tagged entries found. Tag income_expense entries with notes='income' to enable this scenario.",
                "derived_values": {"current_rate": None, "target_rate": target_rate},
                "correlation_r_squared": None,
            }

        # ── Compute current savings rate ──────────────────────────────
        cutoff_date = date.today() - timedelta(days=TRAILING_MONTHS * 30)

        # Filter to trailing window
        window_income = [e for e in income_entries if e.occurred_at >= cutoff_date]
        window_savings = [e for e in savings_entries if e.occurred_at >= cutoff_date]

        # Floor-of-3 guard: if fewer than 3 income-tagged entries in window,
        # fall back to all-time history to dampen lumpiness
        if len(window_income) < MIN_INCOME_EVENTS:
            logger.info(
                "Savings rate: only %d income events in %d-month window, "
                "falling back to all-time history for user=%s",
                len(window_income), TRAILING_MONTHS, user_id,
            )
            window_income = income_entries
            window_savings = savings_entries

        total_income = sum(float(e.value) for e in window_income)
        total_savings = sum(float(e.value) for e in window_savings)

        if total_income <= 0:
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": len(window_income),
                "message": "Total income in the analysis window is zero or negative.",
                "derived_values": {"current_rate": 0.0, "target_rate": target_rate},
                "correlation_r_squared": None,
            }

        current_rate = total_savings / total_income

        # ── Prophet forecast on income series ─────────────────────────
        # growth="flat" prevents nonsensical long-range trend extrapolation
        # freq="MS" for monthly aggregation, horizon=60 (5 years)
        forecast_result = compute_forecast(
            entries=income_entries,
            horizon_days=60,  # 60 months
            freq="MS",
            growth="flat",
            min_points_low=3,
            min_points_reliable=6,
        )

        reliability = forecast_result["reliability"]
        data_point_count = forecast_result["data_point_count"]

        if reliability == "insufficient":
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": data_point_count,
                "message": forecast_result.get("message", "Insufficient data for savings rate projection"),
                "derived_values": {"current_rate": round(current_rate, 4), "target_rate": target_rate},
                "correlation_r_squared": None,
            }

        # ── Build chart lines (cumulative running total) ──────────────
        # Line 1: current_path_expected — cumulative savings at current rate
        # Line 2: expected_case — cumulative savings at target rate
        # Both start from 0.0 to cleanly show new projected accumulation going forward.
        current_path_points = []
        expected_case_points = []
        current_running_total = 0.0
        expected_running_total = 0.0

        for fp in forecast_result["forecast_points"]:
            projected_income = fp["predicted"]

            current_running_total += projected_income * current_rate
            expected_running_total += projected_income * target_rate

            current_path_points.append({
                "date": fp["date"],
                "value": round(current_running_total, 2),
            })
            expected_case_points.append({
                "date": fp["date"],
                "value": round(expected_running_total, 2),
            })

        lines = [
            {"label": "current_path_expected", "points": current_path_points},
            {"label": "expected_case", "points": expected_case_points},
        ]

        return {
            "lines": lines,
            "reliability": reliability,
            "data_point_count": data_point_count,
            "message": None,
            "derived_values": {
                "current_rate": round(current_rate, 4),
                "target_rate": target_rate,
                "total_income_in_window": round(total_income, 2),
                "total_savings_in_window": round(total_savings, 2),
                "income_events_in_window": len(window_income),
            },
            "correlation_r_squared": None,
        }
