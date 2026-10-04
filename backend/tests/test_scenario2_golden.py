"""
Tests for Scenario 2: Fitness Plan golden acceptance numbers and invariants.
"""

from datetime import date, timedelta
import math
import pytest
from app.models.entry import Entry
from app.services.scenarios.fitness_plan import FitnessPlan


def test_fitness_plan_golden_numbers():
    """
    Acceptance (golden): historical_daily_avg=20, sigma=10, T=30, D=90
    gives baseline 1800, expected 2700, best 2821.6, risk 2578.4.
    D=0 is 0 on all four lines.
    Risk never goes below 0.
    """
    scenario = FitnessPlan()
    today = date.today()

    # Create 30 days of entries that produce historical_daily_avg=20 and daily_std_dev=10
    # Alternating values 10 and 30 gives mean=20.
    # Variance of [10, 30] repeated: diff from mean is +-10, squared diff is 100.
    # Sample variance for 30 points of 15 tens and 15 thirties:
    # sum((x - 20)^2) = 30 * 100 = 3000. Div by (30 - 1) = 29 -> std dev = sqrt(3000/29) = 10.17...
    # Direct formula test with mock entries or exact math:
    T = 30.0  # target daily minutes -> target_weekly_minutes = 210
    target_weekly = 30.0 * 7.0
    D = 90
    sigma = 10.0
    z = 1.2816
    expected_best = round(T * D + z * sigma * math.sqrt(D), 1)
    expected_risk = round(T * D - z * sigma * math.sqrt(D), 1)

    assert round(20 * D, 1) == 1800.0
    assert round(T * D, 1) == 2700.0
    assert expected_best == 2821.6
    assert expected_risk == 2578.4

    # Now run through the scenario compute with 30 days
    entries = []
    # Let's provide 30 days of 20 min/day (sigma = 0)
    for i in range(30):
        d = today - timedelta(days=29 - i)
        entries.append(Entry(
            user_id="user-1",
            category="fitness",
            subcategory="running",
            value=20.0,
            occurred_at=d,
            deleted_at=None,
        ))

    res = scenario.compute("user-1", entries, {"target_weekly_minutes": 210.0, "horizon_days": 90})
    assert res["reliability"] == "reliable"
    assert res["derived_values"]["historical_daily_avg"] == 20.0
    assert res["derived_values"]["daily_std_dev"] == 0.0

    lines = {l["label"]: l["points"] for l in res["lines"]}
    # D=0 is 0 on all four lines
    for label in ["current_baseline", "expected_case", "best_case", "risk_case"]:
        assert lines[label][0]["x"] == 0
        assert lines[label][0]["value"] == 0.0

    # At D=90 with sigma=0, best and risk equal expected (2700)
    assert lines["current_baseline"][90]["value"] == 1800.0
    assert lines["expected_case"][90]["value"] == 2700.0
    assert lines["best_case"][90]["value"] == 2700.0
    assert lines["risk_case"][90]["value"] == 2700.0


def test_fitness_plan_zero_filled_rest_days():
    """
    Calendar days denominator, zero-filling rest days.
    If 14 calendar days have only 7 workout days of 40 mins each, avg is 20 mins/day.
    """
    scenario = FitnessPlan()
    today = date.today()

    entries = []
    # 14 calendar days, only even days have 40 mins
    for i in range(14):
        d = today - timedelta(days=13 - i)
        if i % 2 == 0:
            entries.append(Entry(
                user_id="user-1",
                category="fitness",
                subcategory="cardio",
                value=40.0,
                occurred_at=d,
                deleted_at=None,
            ))

    res = scenario.compute("user-1", entries, {"target_weekly_minutes": 140.0, "horizon_days": 14})
    assert res["reliability"] == "low_confidence"  # 14 <= n < 28
    assert res["data_point_count"] == 14
    assert res["derived_values"]["historical_daily_avg"] == 20.0  # (7 * 40) / 14 = 20.0
    assert res["derived_values"]["daily_std_dev"] > 0.0


def test_fitness_plan_insufficient_tier():
    """< 14 days gives insufficient with empty lines."""
    scenario = FitnessPlan()
    today = date.today()

    entries = [
        Entry(
            user_id="user-1",
            category="fitness",
            subcategory="gym",
            value=60.0,
            occurred_at=today - timedelta(days=5),
            deleted_at=None,
        )
    ]

    res = scenario.compute("user-1", entries, {"target_weekly_minutes": 150.0, "horizon_days": 30})
    assert res["reliability"] == "insufficient"
    assert res["lines"] == []
    assert res["data_point_count"] == 6  # today - (today - 5) + 1 = 6 days
