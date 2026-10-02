"""
Program Outcome scenario — assumption-based simulation.

Projects the financial trajectory of enrolling in a program (MBA, bootcamp,
certification, etc.) versus staying at the current salary. Ignores real
tracked entries entirely — all inputs are user-stated assumptions.

Staleness scope: None — caches indefinitely. No real data dependency.

Chart: 4 lines over a 10-year annual horizon (11 points, t=0..10):
- "without_program": flat salary, cumulative earnings
- "expected_case": post-program salary at stated expectation
- "best_case": +10% post-program salary perturbation
- "risk_case": -10% post-program salary perturbation

Cost prorating identity (must hold exactly for both integer and fractional D):
    sum(cost_y for y=1..10) == tuition + opp_cost * D
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

from app.models.entry import Entry
from app.services.scenarios import AssumptionBasedScenario

logger = logging.getLogger(__name__)

HORIZON_YEARS = 10
SALARY_PERTURBATION = 0.10  # ±10% for best/risk cases


class ProgramOutcome(AssumptionBasedScenario):
    """
    Scenario: What if I enroll in this program?

    - Cost prorating: tuition spread evenly over D years, opp cost per year
    - Fractional year handling: partial enrollment in ceil(D) year
    - Post-program salary perturbation: ±10% for best/risk cases
    - 10-year horizon, 4 chart lines, cumulative net earnings starting at 0
    - reliability = "assumption_based", data_point_count = None
    """

    # Indefinite caching — no real data dependency
    staleness_scope = None

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        # entries parameter is deliberately ignored for this scenario

        # ── Extract params ────────────────────────────────────────────
        current_annual_salary = float(params["current_annual_salary"])
        tuition = float(params["program_tuition_cost"])
        D = float(params["program_duration_years"])
        expected_salary_post = float(params["expected_salary_post_program"])
        opp_cost_annual = float(params["opportunity_cost_income_during_program"])

        # ── Cost prorating ────────────────────────────────────────────
        # Tuition per year: C_tuition = tuition / D
        # Opportunity cost per year: C_opp = opp_cost_annual
        # Total annual cost during enrollment: C_annual = C_tuition + C_opp
        C_tuition_per_year = tuition / D
        C_annual = C_tuition_per_year + opp_cost_annual

        floor_D = int(math.floor(D))
        fractional_part = D - floor_D

        def enrolled_fraction(y: int) -> float:
            """Fraction of year y spent enrolled in the program."""
            if y <= floor_D:
                return 1.0
            elif y == floor_D + 1 and fractional_part > 0:
                return fractional_part
            else:
                return 0.0

        def post_program_fraction(y: int) -> float:
            """Fraction of year y spent post-program (earning new salary)."""
            return 1.0 - enrolled_fraction(y)

        def cost_in_year(y: int) -> float:
            """Cost charged in year y (prorated for fractional enrollment)."""
            return enrolled_fraction(y) * C_annual

        # ── Build chart lines ─────────────────────────────────────────

        # Without Program: flat salary, cumulative
        without_program_points = []
        for t in range(HORIZON_YEARS + 1):
            cumulative = t * current_annual_salary
            without_program_points.append({
                "date": f"Year {t}",
                "value": round(cumulative, 2),
            })

        # With Program: three perturbation trajectories
        def build_program_line(post_salary: float) -> List[Dict[str, Any]]:
            """
            Build cumulative net position line for a given post-program salary.

            In year y:
              net_cash_flow = post_program_fraction(y) * post_salary - cost_in_year(y)
            Cumulative at year t = sum of net_cash_flow for y=1..t
            """
            points = []
            cumulative = 0.0

            for t in range(HORIZON_YEARS + 1):
                if t == 0:
                    # Starting point: 0
                    points.append({"date": f"Year {t}", "value": 0.0})
                else:
                    p_frac = post_program_fraction(t)
                    c_year = cost_in_year(t)
                    net_cash_flow = p_frac * post_salary - c_year
                    cumulative += net_cash_flow
                    points.append({
                        "date": f"Year {t}",
                        "value": round(cumulative, 2),
                    })
            return points

        # Three salary perturbations
        expected_points = build_program_line(expected_salary_post)
        best_points = build_program_line(expected_salary_post * (1 + SALARY_PERTURBATION))
        risk_points = build_program_line(expected_salary_post * (1 - SALARY_PERTURBATION))

        lines = [
            {"label": "without_program", "points": without_program_points},
            {"label": "expected_case", "points": expected_points},
            {"label": "best_case", "points": best_points},
            {"label": "risk_case", "points": risk_points},
        ]

        message = (
            f"Post-program salary projections use a ±{int(SALARY_PERTURBATION * 100)}% "
            f"perturbation band around the expected salary of ₹{expected_salary_post:,.0f}. "
            f"The 'without program' path assumes a flat annual salary of "
            f"₹{current_annual_salary:,.0f} throughout the 10-year horizon."
        )

        return {
            "lines": lines,
            "reliability": "assumption_based",
            "data_point_count": None,
            "message": message,
            "derived_values": {
                "program_duration_years": D,
                "total_program_cost": round(tuition + opp_cost_annual * D, 2),
                "tuition_per_year": round(C_tuition_per_year, 2),
                "best_case_salary": round(expected_salary_post * (1 + SALARY_PERTURBATION), 2),
                "risk_case_salary": round(expected_salary_post * (1 - SALARY_PERTURBATION), 2),
            },
            "correlation_r_squared": None,
        }
