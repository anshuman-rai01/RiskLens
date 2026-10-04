"""
Buy vs Rent scenario — assumption-based simulation.

Compares buying a home (with mortgage and property equity) versus continuing
to rent and investing the initial capital and monthly savings differences into a portfolio.

Features:
- Pure function simulate_buy_vs_rent(params) unit-testable without a database.
- Fair equal starting resources K = down_payment + closing_costs.
- Amortization with 0% interest handling.
- Refundable security deposit returned at horizon without double counting.
- Symmetric monthly cashflow investing for cheaper side.
- Nominal or real (inflation deflated) output basis.
- Linearly interpolated break-even year (or null if never crosses).
- Affordability metrics based on tracked savings.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from app.models.entry import Entry
from app.services.scenarios import AssumptionBasedScenario

logger = logging.getLogger(__name__)


def simulate_buy_vs_rent(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pure simulation function for Buy vs Rent comparison (CC2, Section 6).
    Unit-testable without a database.
    """
    # ── 1. Extract params with defaults ──────────────────────────
    home_price = float(params["home_price"])
    down_payment_pct = float(params.get("down_payment_pct", 20.0))
    apprec_pct = float(params.get("expected_home_appreciation_pct_per_year", 7.0))
    maint_pct = float(params.get("maintenance_pct_per_year", 1.0))
    tax_pct = float(params.get("property_tax_pct_per_year", 1.0))
    selling_costs_pct = float(params.get("selling_costs_pct", 6.0))

    mortgage_rate_pct = float(params["mortgage_rate_pct"])
    loan_term_years = int(params["loan_term_years"])
    closing_costs_pct = float(params.get("closing_costs_pct", 3.0))

    current_monthly_rent = float(params["current_monthly_rent"])
    rent_increase_pct = float(params.get("expected_rent_increase_pct_per_year", 5.0))
    security_deposit_months = float(params.get("security_deposit_months", 2.0))

    investment_return_pct = float(params.get("expected_investment_return_pct_per_year", 12.0))
    inflation_pct = float(params.get("inflation_pct_per_year", 5.0))
    output_basis = str(params.get("output_basis", "nominal")).lower()
    portfolio_gains_tax_pct = float(params.get("portfolio_gains_tax_pct", 0.0))
    property_gains_tax_pct = float(params.get("property_gains_tax_pct", 0.0))

    horizon_years = int(params.get("horizon_years") or loan_term_years)

    # ── 2. Initial capital K and deposit D0 ──────────────────────
    down_payment = (down_payment_pct / 100.0) * home_price
    closing_costs = (closing_costs_pct / 100.0) * home_price
    K = down_payment + closing_costs

    loan_amount = home_price - down_payment
    loan_term_months = loan_term_years * 12
    horizon_months = horizon_years * 12

    D0 = security_deposit_months * current_monthly_rent
    if D0 > K:
        raise ValueError(f"Security deposit ({D0:,.2f}) exceeds initial required capital ({K:,.2f})")

    # ── 3. Mortgage EMI ──────────────────────────────────────────
    r_m = (mortgage_rate_pct / 100.0) / 12.0
    if loan_term_months <= 0 or loan_amount <= 0:
        monthly_emi = 0.0
    elif r_m == 0:
        monthly_emi = loan_amount / loan_term_months
    else:
        factor = (1.0 + r_m) ** loan_term_months
        monthly_emi = loan_amount * (r_m * factor) / (factor - 1.0)

    # ── 4. Monthly growth rates ──────────────────────────────────
    apprec_monthly = (1.0 + apprec_pct / 100.0) ** (1.0 / 12.0) - 1.0
    invest_monthly = (1.0 + investment_return_pct / 100.0) ** (1.0 / 12.0) - 1.0

    # ── 5. Month 0 state ─────────────────────────────────────────
    # Buyer starts with home and loan, 0 portfolio
    home_value = home_price
    loan_balance = loan_amount
    buyer_portfolio = 0.0
    buyer_cost_basis = 0.0

    # Renter pays deposit D0, invests K - D0
    renter_portfolio = K - D0
    renter_cost_basis = K - D0
    deposit = D0

    total_rent_paid = 0.0
    total_interest_paid = 0.0

    # Record monthly net positions: month -> (buy_net, rent_net)
    # At month 0:
    prop_exit_0 = home_value * (1.0 - selling_costs_pct / 100.0)
    prop_gain_0 = max(0.0, prop_exit_0 - home_price)
    prop_tax_0 = (property_gains_tax_pct / 100.0) * prop_gain_0
    buy_net_0 = prop_exit_0 - loan_balance - prop_tax_0 + buyer_portfolio

    rent_net_0 = renter_portfolio + deposit

    monthly_positions: List[Tuple[int, float, float]] = [(0, buy_net_0, rent_net_0)]

    # ── 6. Monthly simulation loop ───────────────────────────────
    for m in range(1, horizon_months + 1):
        # 1. Portfolios grow with investment return
        buyer_portfolio *= (1.0 + invest_monthly)
        renter_portfolio *= (1.0 + invest_monthly)

        # 2. Home appreciation
        home_value *= (1.0 + apprec_monthly)

        # 3. Buyer mortgage repayment
        if m <= loan_term_months and loan_balance > 0:
            interest_m = loan_balance * r_m
            total_interest_paid += interest_m
            principal_m = min(loan_balance, monthly_emi - interest_m)
            loan_balance = max(0.0, loan_balance - principal_m)
            cur_emi = monthly_emi
        else:
            cur_emi = 0.0

        # 4. Outflows
        # Maintenance and property tax are based on current home value
        monthly_maint_tax = ((maint_pct + tax_pct) / 100.0 / 12.0) * home_value
        buyer_outflow = cur_emi + monthly_maint_tax

        # Renter outflow escalates annually
        year_idx = (m - 1) // 12
        rent_m = current_monthly_rent * ((1.0 + rent_increase_pct / 100.0) ** year_idx)
        total_rent_paid += rent_m
        renter_outflow = rent_m

        # 5. Difference investing (symmetric cashflow)
        if buyer_outflow < renter_outflow:
            diff = renter_outflow - buyer_outflow
            buyer_portfolio += diff
            buyer_cost_basis += diff
        elif renter_outflow < buyer_outflow:
            diff = buyer_outflow - renter_outflow
            renter_portfolio += diff
            renter_cost_basis += diff

        # 6. Net positions at month m
        # Buyer net position:
        buyer_port_gains = max(0.0, buyer_portfolio - buyer_cost_basis)
        buyer_port_tax = (portfolio_gains_tax_pct / 100.0) * buyer_port_gains
        net_buyer_port = buyer_portfolio - buyer_port_tax

        prop_exit = home_value * (1.0 - selling_costs_pct / 100.0)
        prop_gain = max(0.0, prop_exit - home_price)
        prop_tax = (property_gains_tax_pct / 100.0) * prop_gain

        buy_net = prop_exit - loan_balance - prop_tax + net_buyer_port

        # Renter net position:
        renter_port_gains = max(0.0, renter_portfolio - renter_cost_basis)
        renter_port_tax = (portfolio_gains_tax_pct / 100.0) * renter_port_gains
        net_renter_port = renter_portfolio - renter_port_tax
        # Security deposit returned
        rent_net = net_renter_port + deposit

        # Deflate if real output basis
        if output_basis == "real":
            deflator = (1.0 + inflation_pct / 100.0) ** (m / 12.0)
            b_rep = buy_net / deflator if deflator > 0 else buy_net
            r_rep = rent_net / deflator if deflator > 0 else rent_net
        else:
            b_rep = buy_net
            r_rep = rent_net

        monthly_positions.append((m, b_rep, r_rep))

    # ── 7. Break-even year calculation ───────────────────────────
    # The first month where Buy - Rent >= 0 and stays so through the horizon
    break_even_year: Optional[float] = None
    diffs = [b - r for (_, b, r) in monthly_positions]

    # Find earliest month m* where diffs[k] >= 0 for all k in m*..horizon_months
    cross_month: Optional[int] = None
    for m in range(0, horizon_months + 1):
        if all(diffs[k] >= 0 for k in range(m, horizon_months + 1)):
            cross_month = m
            break

    if cross_month is not None:
        if cross_month == 0:
            break_even_year = 0.0
        else:
            # Linear interpolation between cross_month - 1 and cross_month
            d_prev = diffs[cross_month - 1]
            d_curr = diffs[cross_month]
            if (d_curr - d_prev) != 0:
                fraction = -d_prev / (d_curr - d_prev)
            else:
                fraction = 0.0
            break_even_m = (cross_month - 1) + fraction
            break_even_year = round(break_even_m / 12.0, 1)

    # ── 8. Emit yearly points ────────────────────────────────────
    buy_points = []
    rent_points = []
    for y in range(horizon_years + 1):
        m = y * 12
        b_val = monthly_positions[m][1]
        r_val = monthly_positions[m][2]
        buy_points.append({"x": y, "date": f"Year {y}", "value": round(b_val, 2)})
        rent_points.append({"x": y, "date": f"Year {y}", "value": round(r_val, 2)})

    final_buy = buy_points[-1]["value"]
    final_rent = rent_points[-1]["value"]

    if break_even_year is None:
        message = "Buying does not break even within the projection horizon under these assumptions."
    else:
        message = f"Buying breaks even against renting after approximately {break_even_year:.1f} years."

    derived_values = {
        "monthly_emi": round(monthly_emi, 2),
        "initial_capital_required": round(K, 2),
        "total_rent_paid": round(total_rent_paid, 2),
        "total_interest_paid": round(total_interest_paid, 2),
        "buy_net_position": round(final_buy, 2),
        "rent_net_position": round(final_rent, 2),
        "net_difference": round(final_buy - final_rent, 2),
        "break_even_year": break_even_year,
        "output_basis": output_basis,
        "horizon_years": horizon_years,
        "home_price": home_price,
        "down_payment": round(down_payment, 2),
        "closing_costs": round(closing_costs, 2),
    }

    lines = [
        {"label": "Buy", "points": buy_points},
        {"label": "Rent", "points": rent_points},
    ]

    return {
        "lines": lines,
        "derived_values": derived_values,
        "message": message,
        "reliability": "assumption_based",
        "data_point_count": None,
        "correlation_r_squared": None,
    }


class BuyVsRent(AssumptionBasedScenario):
    """
    Scenario: Should I buy a home or continue renting?
    Calculated via simulate_buy_vs_rent with real tracked savings informing affordability.
    """

    staleness_scope = "savings"

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Tracked savings informs the affordability chip (D4)
        savings_entries = [
            e for e in entries
            if e.category == "savings" and (e.deleted_at is None)
        ]
        S = sum(float(e.value) for e in savings_entries)

        result = simulate_buy_vs_rent(params)

        K = result["derived_values"]["initial_capital_required"]
        coverage_pct = round((S / K * 100.0) if K > 0 else 100.0, 1)

        result["derived_values"]["tracked_savings"] = round(S, 2)
        result["derived_values"]["capital_coverage_pct"] = coverage_pct

        return result
