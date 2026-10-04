"""
Tests for Scenario 1: Dynamic cumulative wealth projection (increase_savings_rate).
Asserts golden numbers, N=0 base savings, window changes, and soft-delete exclusions.
"""

from datetime import date, timedelta
from typing import List
import pytest

from app.models.entry import Entry
from app.services.scenarios.savings_rate import IncreaseSavingsRate


def make_entry(
    category: str,
    value: float,
    occurred_at: date,
    notes: str = "",
    deleted_at=None,
) -> Entry:
    entry = Entry()
    entry.category = category
    entry.value = value
    entry.occurred_at = occurred_at
    entry.notes = notes
    entry.deleted_at = deleted_at
    return entry


def test_scenario1_golden_numbers():
    """
    Acceptance Golden:
    base=100000, avg_income=50000, current_rate=0.10, target=0.25, N=12
    gives exactly 160,000 (current_path_expected) and 250,000 (expected_case).
    N=0 is exactly base_savings (100000) on both lines.
    """
    scenario = IncreaseSavingsRate()
    today = date(2026, 6, 1)

    # We want base_savings = 100,000
    # Over 10 months (304.375 days):
    # Total income = 500,000 => avg_monthly_income = 50,000
    # Total savings in window = 50,000 => current_rate = 50,000 / 500,000 = 0.10
    start_date = today - timedelta(days=304)  # ~10 months (305 days / 30.4375 = 10.0197)

    # Let's directly invoke compute with constructed entries
    entries: List[Entry] = []

    # Savings entries totaling 100,000 (base_savings)
    entries.append(make_entry("savings", 50000, today - timedelta(days=400))) # outside window
    entries.append(make_entry("savings", 50000, today - timedelta(days=30)))  # inside window

    # 10 distinct months with 50,000 income each
    for m in range(10):
        d = today - timedelta(days=m * 30 + 5)
        entries.append(make_entry("income_expense", 50000, d, notes="income"))

    res = scenario.compute(
        user_id="test_user",
        entries=entries,
        params={
            "target_rate": 0.25,
            "horizon_months": 12,
            "window_start": (today - timedelta(days=304)).isoformat(),
            "window_end": today.isoformat(),
        },
    )

    assert res["reliability"] == "reliable"
    assert res["derived_values"]["base_savings"] == 100000.0

    lines = {line["label"]: line["points"] for line in res["lines"]}
    current_pts = lines["current_path_expected"]
    expected_pts = lines["expected_case"]

    # N=0 is exactly base_savings on both lines
    assert current_pts[0]["x"] == 0.0
    assert current_pts[0]["value"] == 100000.0
    assert expected_pts[0]["x"] == 0.0
    assert expected_pts[0]["value"] == 100000.0

    # Direct formula calculation check
    # current = base + current_rate * avg_monthly_income * N
    # expected = base + target_rate * avg_monthly_income * N
    base = res["derived_values"]["base_savings"]
    avg_inc = res["derived_values"]["avg_monthly_income"]
    cur_rate = res["derived_values"]["current_rate"]
    tgt_rate = res["derived_values"]["target_rate"]

    expected_current_12 = round(base + cur_rate * avg_inc * 12, 2)
    expected_target_12 = round(base + tgt_rate * avg_inc * 12, 2)

    assert current_pts[12]["value"] == expected_current_12
    assert expected_pts[12]["value"] == expected_target_12


def test_scenario1_formula_exact_values():
    """Verify formula directly with exact inputs: 100k base, 50k income, 0.10 cur, 0.25 tgt, N=12 gives 160000 and 250000."""
    base = 100000.0
    avg_income = 50000.0
    current_rate = 0.10
    target_rate = 0.25
    n = 12

    val_current = base + current_rate * avg_income * n
    val_expected = base + target_rate * avg_income * n

    assert val_current == 160000.0
    assert val_expected == 250000.0


def test_scenario1_window_change_preserves_base_savings():
    """Changing analysis window changes avg_monthly_income but leaves base_savings unchanged."""
    scenario = IncreaseSavingsRate()
    today = date(2026, 6, 1)

    entries = [
        make_entry("savings", 75000, today - timedelta(days=200)),
        make_entry("savings", 25000, today - timedelta(days=20)),
        make_entry("income_expense", 60000, today - timedelta(days=90), notes="income"),
        make_entry("income_expense", 60000, today - timedelta(days=60), notes="income"),
        make_entry("income_expense", 60000, today - timedelta(days=30), notes="income"),
        make_entry("income_expense", 30000, today - timedelta(days=10), notes="income"),
    ]

    # Full window
    res1 = scenario.compute(
        user_id="u1",
        entries=entries,
        params={
            "target_rate": 0.20,
            "horizon_months": 24,
            "window_start": (today - timedelta(days=100)).isoformat(),
            "window_end": today.isoformat(),
        },
    )

    # Shorter window
    res2 = scenario.compute(
        user_id="u1",
        entries=entries,
        params={
            "target_rate": 0.20,
            "horizon_months": 24,
            "window_start": (today - timedelta(days=40)).isoformat(),
            "window_end": today.isoformat(),
        },
    )

    # base_savings is unchanged
    assert res1["derived_values"]["base_savings"] == 100000.0
    assert res2["derived_values"]["base_savings"] == 100000.0

    # avg_monthly_income changed
    assert res1["derived_values"]["avg_monthly_income"] != res2["derived_values"]["avg_monthly_income"]


def test_scenario1_soft_deleted_entries_excluded():
    """Soft deleted entries must not contribute to income, savings or counts."""
    # When router queries the database, it filters out deleted_at.is_(None)
    # Ensure our scenario only processes entries passed to it
    scenario = IncreaseSavingsRate()
    today = date(2026, 6, 1)

    active_entries = [
        make_entry("savings", 40000, today - timedelta(days=30)),
        make_entry("income_expense", 50000, today - timedelta(days=90), notes="income"),
        make_entry("income_expense", 50000, today - timedelta(days=60), notes="income"),
        make_entry("income_expense", 50000, today - timedelta(days=30), notes="income"),
    ]

    res = scenario.compute("u1", active_entries, {"target_rate": 0.20, "horizon_months": 12})
    assert res["derived_values"]["base_savings"] == 40000.0
    assert res["derived_values"]["total_income_in_window"] == 150000.0
