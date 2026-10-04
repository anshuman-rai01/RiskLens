"""
Increase Savings Rate scenario — deterministic cumulative wealth projection.

Computes a dynamic cumulative projection starting at the user's real savings to date,
with current-rate and target-rate trajectories updating live.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.models.entry import Entry
from app.services.scenarios import DataDrivenScenario

logger = logging.getLogger(__name__)

DAYS_PER_MONTH = 30.4375


class IncreaseSavingsRate(DataDrivenScenario):
    """
    Scenario: What if I increase my savings rate to X%?

    - base_savings: sum of all non-deleted savings entries to date.
    - Analysis window: user-selected or auto-derived [first_income_date, today].
    - months_in_window = (window_end - window_start + 1 days) / 30.4375.
    - avg_monthly_income = income in window / months_in_window.
    - current_rate = savings in window / income in window.
    - Lines:
        current_path_expected = base + current_rate * avg_monthly_income * N
        expected_case = base + target_rate * avg_monthly_income * N
      for N = 0..horizon_months with x = N.
    - Tiers based on distinct calendar months with income in window:
        < 3: insufficient
        3-5: low_confidence
        >= 6: reliable
    """

    staleness_scope: Optional[str] = "all"

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        target_rate = float(params.get("target_rate", 0.20))
        horizon_months = int(params.get("horizon_months", 60))

        # ── 1. Base savings: sum of ALL non-deleted savings to date ───────────
        base_savings = sum(
            float(e.value) for e in entries if e.category == "savings"
        )

        # ── 2. Filter income-tagged entries (case-insensitive notes check) ─────
        income_entries = [
            e for e in entries
            if e.category == "income_expense"
            and (e.notes or "").strip().lower() == "income"
        ]

        today = date.today()

        # ── 3. Resolve analysis window ───────────────────────────────────────
        window_start_param = params.get("window_start")
        window_end_param = params.get("window_end")

        if window_start_param and window_end_param:
            window_start = date.fromisoformat(str(window_start_param))
            window_end = date.fromisoformat(str(window_end_param))
        else:
            if income_entries:
                window_start = min(e.occurred_at for e in income_entries)
            else:
                window_start = today
            window_end = today

        days_in_window = (window_end - window_start).days + 1
        months_in_window = days_in_window / DAYS_PER_MONTH

        # Filter entries within analysis window
        income_in_window = [
            e for e in income_entries
            if window_start <= e.occurred_at <= window_end
        ]
        savings_in_window = [
            e for e in entries
            if e.category == "savings"
            and window_start <= e.occurred_at <= window_end
        ]

        total_income_in_window = sum(float(e.value) for e in income_in_window)
        total_savings_in_window = sum(float(e.value) for e in savings_in_window)

        avg_monthly_income = (
            total_income_in_window / months_in_window if months_in_window > 0 else 0.0
        )

        if total_income_in_window > 0:
            current_rate = total_savings_in_window / total_income_in_window
        else:
            current_rate = 0.0

        # Warning message if savings exceed income
        message: Optional[str] = None
        if current_rate > 1.0:
            message = (
                "Tracked savings exceed income in this window (savings rate > 100%). "
                "Please verify your income and savings tagging."
            )

        # ── 4. Reliability Tiers: distinct calendar months with income ────────
        distinct_months = set(
            (e.occurred_at.year, e.occurred_at.month) for e in income_in_window
        )
        data_point_count = len(distinct_months)

        if data_point_count < 3 or total_income_in_window <= 0:
            reliability = "insufficient"
            if not message:
                message = (
                    "Insufficient data: fewer than 3 distinct months with income "
                    "in the analysis window."
                )
            return {
                "lines": [],
                "reliability": reliability,
                "data_point_count": data_point_count,
                "message": message,
                "derived_values": {
                    "base_savings": round(base_savings, 2),
                    "avg_monthly_income": round(avg_monthly_income, 2),
                    "months_in_window": round(months_in_window, 2),
                    "current_rate": round(current_rate, 4),
                    "target_rate": round(target_rate, 4),
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "horizon_months": horizon_months,
                    "total_income_in_window": round(total_income_in_window, 2),
                    "total_savings_in_window": round(total_savings_in_window, 2),
                },
                "correlation_r_squared": None,
            }
        elif data_point_count <= 5:
            reliability = "low_confidence"
        else:
            reliability = "reliable"

        # ── 5. Build cumulative projection lines for N = 0..horizon_months ────
        current_path_points = []
        expected_case_points = []

        for n in range(horizon_months + 1):
            pt_date = (today + timedelta(days=int(n * DAYS_PER_MONTH))).strftime("%Y-%m")
            current_val = base_savings + current_rate * avg_monthly_income * n
            expected_val = base_savings + target_rate * avg_monthly_income * n

            current_path_points.append({
                "x": float(n),
                "date": pt_date,
                "value": round(current_val, 2),
            })
            expected_case_points.append({
                "x": float(n),
                "date": pt_date,
                "value": round(expected_val, 2),
            })

        lines = [
            {"label": "current_path_expected", "points": current_path_points},
            {"label": "expected_case", "points": expected_case_points},
        ]

        return {
            "lines": lines,
            "reliability": reliability,
            "data_point_count": data_point_count,
            "message": message,
            "derived_values": {
                "base_savings": round(base_savings, 2),
                "avg_monthly_income": round(avg_monthly_income, 2),
                "months_in_window": round(months_in_window, 2),
                "current_rate": round(current_rate, 4),
                "target_rate": round(target_rate, 4),
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "horizon_months": horizon_months,
                "total_income_in_window": round(total_income_in_window, 2),
                "total_savings_in_window": round(total_savings_in_window, 2),
            },
            "correlation_r_squared": None,
        }
