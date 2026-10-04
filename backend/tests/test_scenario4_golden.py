from datetime import date
import pytest
from app.services.scenarios.buy_vs_rent import simulate_buy_vs_rent, BuyVsRent
from app.models.entry import Entry


def test_buy_vs_rent_golden_emi():
    """
    Acceptance golden: ₹50,00,000 price, 20% down, 8.5%, 20 y gives 34,712.93 EMI.
    """
    params = {
        "home_price": 5000000.0,
        "down_payment_pct": 20.0,
        "mortgage_rate_pct": 8.5,
        "loan_term_years": 20,
        "current_monthly_rent": 25000.0,
        "expected_rent_increase_pct_per_year": 5.0,
        "expected_home_appreciation_pct_per_year": 7.0,
        "expected_investment_return_pct_per_year": 12.0,
    }
    res = simulate_buy_vs_rent(params)
    assert res["derived_values"]["monthly_emi"] == 34712.93


def test_buy_vs_rent_deposit_no_double_count():
    """
    With all returns, escalation, fees and taxes at 0% and 0 deposit, Rent(0) = K exactly.
    With a deposit of D0, Rent(0) = (K - D0) + D0 = K (no double count).
    """
    base_params = {
        "home_price": 1000000.0,
        "down_payment_pct": 20.0,
        "closing_costs_pct": 0.0,
        "selling_costs_pct": 0.0,
        "maintenance_pct_per_year": 0.0,
        "property_tax_pct_per_year": 0.0,
        "mortgage_rate_pct": 0.0,
        "loan_term_years": 20,
        "current_monthly_rent": 5000.0,
        "expected_rent_increase_pct_per_year": 0.0,
        "expected_home_appreciation_pct_per_year": 0.0,
        "expected_investment_return_pct_per_year": 0.0,
        "inflation_pct_per_year": 0.0,
        "portfolio_gains_tax_pct": 0.0,
        "property_gains_tax_pct": 0.0,
    }

    # Case A: 0 deposit
    params_a = dict(base_params, security_deposit_months=0.0)
    res_a = simulate_buy_vs_rent(params_a)
    K_a = res_a["derived_values"]["initial_capital_required"]
    assert K_a == 200000.0  # 20% of 1,000,000
    rent_line_a = next(l for l in res_a["lines"] if l["label"] == "Rent")
    assert rent_line_a["points"][0]["value"] == 200000.0

    # Case B: deposit of 2 months = 10,000
    params_b = dict(base_params, security_deposit_months=2.0)
    res_b = simulate_buy_vs_rent(params_b)
    K_b = res_b["derived_values"]["initial_capital_required"]
    assert K_b == 200000.0
    rent_line_b = next(l for l in res_b["lines"] if l["label"] == "Rent")
    # Rent(0) = (K - D0) + D0 = K
    assert rent_line_b["points"][0]["value"] == 200000.0


def test_buy_vs_rent_buyer_portfolio_grows_after_loan_paid():
    """
    Symmetry test: After the loan is paid off, EMI is 0, so buyer outflow is much lower
    than escalating rent. Buyer invests the difference, and their portfolio grows.
    """
    params = {
        "home_price": 1000000.0,
        "down_payment_pct": 50.0,
        "mortgage_rate_pct": 5.0,
        "loan_term_years": 5,      # 5 year loan
        "horizon_years": 10,       # 10 year horizon
        "current_monthly_rent": 20000.0,
        "expected_rent_increase_pct_per_year": 5.0,
        "expected_home_appreciation_pct_per_year": 5.0,
        "expected_investment_return_pct_per_year": 10.0,
    }
    res = simulate_buy_vs_rent(params)
    buy_line = next(l for l in res["lines"] if l["label"] == "Buy")
    # From year 5 to year 10, home equity and buyer portfolio grow strongly
    val_y5 = buy_line["points"][5]["value"]
    val_y10 = buy_line["points"][10]["value"]
    assert val_y10 > val_y5


def test_buy_vs_rent_break_even_null_when_never_crosses():
    """
    When rent is extremely cheap compared to high home price, buying never breaks even.
    break_even_year must be None.
    """
    params = {
        "home_price": 10000000.0,  # 1 Crore
        "down_payment_pct": 20.0,
        "mortgage_rate_pct": 12.0,
        "loan_term_years": 20,
        "current_monthly_rent": 5000.0,  # Only 5k rent
        "expected_rent_increase_pct_per_year": 1.0,
        "expected_home_appreciation_pct_per_year": 0.0,
        "expected_investment_return_pct_per_year": 15.0,
    }
    res = simulate_buy_vs_rent(params)
    assert res["derived_values"]["break_even_year"] is None
    assert "does not break even" in res["message"]


def test_buy_vs_rent_affordability_chip():
    """
    Tracked savings correctly populates tracked_savings and capital_coverage_pct (D4 fix).
    """
    scenario = BuyVsRent()
    entries = [
        Entry(
            user_id="user-1",
            category="savings",
            subcategory="vault",
            value=100000.0,
            occurred_at=date(2026, 1, 1),
            deleted_at=None,
        )
    ]
    params = {
        "home_price": 1000000.0,
        "down_payment_pct": 20.0,
        "closing_costs_pct": 5.0,
        "mortgage_rate_pct": 8.0,
        "loan_term_years": 20,
        "current_monthly_rent": 10000.0,
        "expected_rent_increase_pct_per_year": 5.0,
        "expected_home_appreciation_pct_per_year": 6.0,
        "expected_investment_return_pct_per_year": 10.0,
    }
    res = scenario.compute("user-1", entries, params)
    K = res["derived_values"]["initial_capital_required"]
    assert K == 250000.0  # 20% down + 5% closing = 25% of 1M = 250k
    assert res["derived_values"]["tracked_savings"] == 100000.0
    assert res["derived_values"]["capital_coverage_pct"] == 40.0  # 100k / 250k = 40%
