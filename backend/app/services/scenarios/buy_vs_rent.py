"""
Buy vs Rent scenario — assumption-based simulation.

Compares buying a home (with mortgage) versus continuing to rent and
investing the savings. Uses real tracked savings entries to derive the
starting capital S (down payment / initial investment).

Staleness scope: "savings" — only invalidated when savings entries change.
Unrelated entry changes (study, fitness) do not bust the cache.

Chart: 2 lines ("Buy", "Rent") over a 10-year annual horizon (11 points, t=0..10).

Identity guarantees:
- home_equity(0) = S exactly (home_price - loan_principal = S)
- rent_net_position(0) = S exactly (S invested - 0 cumulative rent = S)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

from fastapi import HTTPException, status

from app.models.entry import Entry
from app.services.scenarios import AssumptionBasedScenario

logger = logging.getLogger(__name__)

HORIZON_YEARS = 10


class BuyVsRent(AssumptionBasedScenario):
    """
    Scenario: Should I buy a home or continue renting?

    - Starting capital S: derived from real savings entries
    - Buy path: amortized mortgage with home appreciation
    - Rent path: S invested with compound returns, minus cumulative rent
    - 10-year annual horizon (11 points for t=0, 1, ..., 10)
    - 2 chart lines: "Buy" (home equity) and "Rent" (net investment position)
    """

    # Scoped staleness: only invalidate cache when savings entries change
    staleness_scope = "savings"

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        # ── Extract and validate params ───────────────────────────────
        home_price = float(params["home_price"])
        mortgage_rate_pct = float(params["mortgage_rate_pct"])
        loan_term_years = int(params["loan_term_years"])
        current_monthly_rent = float(params["current_monthly_rent"])
        rent_increase_pct = float(params["expected_rent_increase_pct_per_year"])
        appreciation_pct = float(params["expected_home_appreciation_pct_per_year"])
        investment_return_pct = float(params["expected_investment_return_pct_per_year"])

        # ── Derive starting capital S from real savings entries ───────
        savings_entries = [
            e for e in entries
            if e.category == "savings"
        ]
        S = sum(float(e.value) for e in savings_entries)

        # ── Validate S against home_price ─────────────────────────────
        if S >= home_price:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Your tracked savings already exceed the home price — "
                       "this comparison isn't meaningful.",
            )

        # ── Build disclosure message ──────────────────────────────────
        if S == 0:
            message = (
                "This comparison uses ₹0 in tracked savings. "
                "Growth-rate assumptions beyond that are hypothetical, not derived from data."
            )
        else:
            message = (
                f"This comparison uses ₹{S:,.0f} in tracked savings. "
                "Growth-rate assumptions beyond that are hypothetical, not derived from data."
            )

        # ── BUY PATH ─────────────────────────────────────────────────
        # Loan principal
        P = home_price - S

        # Monthly interest rate
        r_m = mortgage_rate_pct / 100.0 / 12.0

        # Total months in loan
        N = loan_term_years * 12

        # Monthly mortgage payment (amortization formula)
        if r_m == 0:
            monthly_payment = P / N
        else:
            monthly_payment = P * (r_m * (1 + r_m) ** N) / ((1 + r_m) ** N - 1)

        # Track loan balance month by month for the 10-year horizon
        # We need balance at months 0, 12, 24, ..., 120
        loan_balance = [0.0] * (HORIZON_YEARS * 12 + 1)  # B[0] through B[120]
        loan_balance[0] = P  # initial balance = principal

        for m in range(1, HORIZON_YEARS * 12 + 1):
            if m <= N:
                # Interest portion this month
                interest = loan_balance[m - 1] * r_m
                # Principal portion
                principal_payment = monthly_payment - interest
                loan_balance[m] = max(0.0, loan_balance[m - 1] - principal_payment)
            else:
                # Loan is paid off
                loan_balance[m] = 0.0

        # Build Buy line: home_equity(t) = home_value(t) - loan_balance(12*t)
        appreciation_rate = appreciation_pct / 100.0
        buy_points = []
        for t in range(HORIZON_YEARS + 1):
            home_value_t = home_price * (1 + appreciation_rate) ** t
            balance_at_t = loan_balance[12 * t]
            equity = home_value_t - balance_at_t
            buy_points.append({
                "date": f"Year {t}",
                "value": round(equity, 2),
            })

        # ── RENT PATH ────────────────────────────────────────────────
        investment_rate = investment_return_pct / 100.0
        rent_increase_rate = rent_increase_pct / 100.0

        rent_points = []
        cumulative_rent_paid = 0.0

        for t in range(HORIZON_YEARS + 1):
            # Investment value: S compounded annually
            investment_value = S * (1 + investment_rate) ** t

            # Cumulative rent paid through year t
            # annual_rent(k) = 12 * current_monthly_rent * (1 + rent_increase_rate)^(k-1)
            # cumulative_rent_paid(t) = sum_{k=1}^{t} annual_rent(k)
            if t > 0:
                annual_rent_this_year = (
                    12 * current_monthly_rent * (1 + rent_increase_rate) ** (t - 1)
                )
                cumulative_rent_paid += annual_rent_this_year

            net_position = investment_value - cumulative_rent_paid
            rent_points.append({
                "date": f"Year {t}",
                "value": round(net_position, 2),
            })

        # ── Build response ────────────────────────────────────────────
        lines = [
            {"label": "Buy", "points": buy_points},
            {"label": "Rent", "points": rent_points},
        ]

        return {
            "lines": lines,
            "reliability": "assumption_based",
            "data_point_count": None,
            "message": message,
            "derived_values": {
                "starting_capital_s": round(S, 2),
                "loan_principal": round(P, 2),
                "monthly_mortgage_payment": round(monthly_payment, 2),
                "savings_entries_count": len(savings_entries),
            },
            "correlation_r_squared": None,
        }
