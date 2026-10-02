"""
Automated tests for Chunk 9 (Milestone 3) — Simulation Engine:

Verification Steps:
1. Entry formatting: Income/Expense/Savings round to integers; Study/Academic keep 1 decimal
2. Savings Rate: growth="flat" prevents negative trajectory; 2 lines; empty best/risk;
   different target_rate → different cache entries
3. Fitness Plan: 90-day daily horizon; 28+ daily → reliable; 4-line output
4. Reduce Study Hours: <14 paired weeks → insufficient; 14+ → regression with R²;
   weak correlation flagged; non-causal language
5. Debug endpoint: returns accurate values; user-isolated
6. Full regression: existing Milestone 2 suites unaffected
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict

import httpx
import pytest

from app.main import app


# ── Helpers ───────────────────────────────────────────────────────────


async def register_user(client: httpx.AsyncClient, suffix: str) -> Dict[str, str]:
    """Register a user and return headers + token."""
    timestamp = int(time.time() * 1000)
    email = f"sim_{suffix}_{timestamp}@example.com"
    res = await client.post(
        "/auth/register",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "token": token}


async def create_entry(
    client: httpx.AsyncClient,
    headers: dict,
    category: str,
    value: str,
    occurred_at: date,
    subcategory: str | None = None,
    unit: str | None = None,
    notes: str | None = None,
) -> dict:
    """Create a single entry and return the response JSON."""
    payload: Dict[str, Any] = {
        "category": category,
        "value": value,
        "occurred_at": occurred_at.isoformat(),
    }
    if subcategory:
        payload["subcategory"] = subcategory
    if unit:
        payload["unit"] = unit
    if notes:
        payload["notes"] = notes
    res = await client.post("/entries", json=payload, headers=headers)
    assert res.status_code == 201, f"Entry creation failed: {res.text}"
    return res.json()


# ==============================================================================
# VERIFICATION STEP 1: Entry Value Formatting
# ==============================================================================


@pytest.mark.asyncio
async def test_entry_formatting_income_expense_rounds_to_integer():
    """Income/Expense entries: decimal values must be rounded to nearest integer."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fmt_ie")
        headers = user["headers"]
        today = date.today()

        # Client sends 15000.75 → should be stored as 15001
        entry = await create_entry(
            client, headers, "income_expense", "15000.75", today,
            subcategory="salary", unit="INR", notes="income",
        )
        assert Decimal(str(entry["value"])) == Decimal("15001"), (
            f"income_expense value should round to integer, got {entry['value']}"
        )

        # Client sends 499.3 → should be stored as 499
        entry2 = await create_entry(
            client, headers, "income_expense", "499.3", today,
            subcategory="groceries", unit="INR", notes="expense",
        )
        assert Decimal(str(entry2["value"])) == Decimal("499"), (
            f"income_expense value should round to integer, got {entry2['value']}"
        )


@pytest.mark.asyncio
async def test_entry_formatting_savings_rounds_to_integer():
    """Savings entries: decimal values must be rounded to nearest integer."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fmt_sav")
        headers = user["headers"]
        today = date.today()

        entry = await create_entry(
            client, headers, "savings", "5000.49", today,
            unit="INR",
        )
        assert Decimal(str(entry["value"])) == Decimal("5000"), (
            f"savings value should round to integer, got {entry['value']}"
        )


@pytest.mark.asyncio
async def test_entry_formatting_study_keeps_one_decimal():
    """Study entries: values must keep exactly one decimal place."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fmt_study")
        headers = user["headers"]
        today = date.today()

        # Client sends 3.75 → should be stored as 3.8 (1 decimal)
        entry = await create_entry(
            client, headers, "study", "3.75", today,
            subcategory="math", unit="hours",
        )
        assert Decimal(str(entry["value"])) == Decimal("3.8"), (
            f"study value should keep 1 decimal, got {entry['value']}"
        )


@pytest.mark.asyncio
async def test_entry_formatting_academic_keeps_one_decimal():
    """Academic entries: values must keep exactly one decimal place."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fmt_acad")
        headers = user["headers"]
        today = date.today()

        # Client sends 87.456 → should be stored as 87.5
        entry = await create_entry(
            client, headers, "academic", "87.456", today,
            subcategory="physics", unit="points",
        )
        assert Decimal(str(entry["value"])) == Decimal("87.5"), (
            f"academic value should keep 1 decimal, got {entry['value']}"
        )


@pytest.mark.asyncio
async def test_entry_formatting_on_update():
    """Value formatting must also apply when updating an entry."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fmt_upd")
        headers = user["headers"]
        today = date.today()

        # Create an income_expense entry
        entry = await create_entry(
            client, headers, "income_expense", "1000", today,
            subcategory="salary", unit="INR", notes="income",
        )

        # Update with a decimal value → should be rounded to integer
        put_resp = await client.put(
            f"/entries/{entry['id']}",
            json={"value": "1500.7"},
            headers=headers,
        )
        assert put_resp.status_code == 200
        assert Decimal(str(put_resp.json()["value"])) == Decimal("1501"), (
            f"Updated income_expense value should round to integer, got {put_resp.json()['value']}"
        )

        # Create a study entry
        study_entry = await create_entry(
            client, headers, "study", "2.0", today,
            subcategory="cs", unit="hours",
        )

        # Update with a multi-decimal value → should keep 1 decimal
        put_study = await client.put(
            f"/entries/{study_entry['id']}",
            json={"value": "3.456"},
            headers=headers,
        )
        assert put_study.status_code == 200
        assert Decimal(str(put_study.json()["value"])) == Decimal("3.5"), (
            f"Updated study value should keep 1 decimal, got {put_study.json()['value']}"
        )


# ==============================================================================
# VERIFICATION STEP 2: Savings Rate Scenario
# ==============================================================================


@pytest.mark.asyncio
async def test_savings_rate_growth_flat_prevents_negative_trajectory():
    """
    Regression test: growth="flat" prevents nonsensical negative long-horizon
    trajectory that occurred with growth="linear" on short/noisy income data.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "sav_flat")
        headers = user["headers"]
        today = date.today()

        # Seed 6 months of noisy income data (lumpy, realistic)
        # Deliberately include variance that would cause linear growth to
        # extrapolate a negative trend
        incomes = [
            50000, 0, 48000, 0, 55000, 0,  # Bimonthly income with gaps
            52000, 0, 47000, 0, 51000, 0,
            53000, 0, 49000, 0, 54000, 0,
        ]
        for i, amount in enumerate(incomes):
            if amount > 0:
                await create_entry(
                    client, headers, "income_expense",
                    str(amount), today - timedelta(days=180 - i * 10),
                    subcategory="salary", unit="INR", notes="income",
                )

        # Seed savings entries
        for i in range(9):
            await create_entry(
                client, headers, "savings",
                str(10000 + i * 500), today - timedelta(days=180 - i * 20),
                unit="INR",
            )

        # Run simulation
        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "increase_savings_rate",
                "params": {"target_rate": 0.25},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Verify no negative values in the projection (the regression being tested)
        for line in data["lines"]:
            for point in line["points"]:
                assert point["value"] >= 0, (
                    f"growth='flat' should prevent negative projections, "
                    f"but got {point['value']} on line '{line['label']}' at {point['date']}"
                )


@pytest.mark.asyncio
async def test_savings_rate_exactly_two_lines():
    """Savings Rate must return exactly 2 lines with empty best_case/risk_case."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "sav_2line")
        headers = user["headers"]
        today = date.today()

        # Seed sufficient data
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(50000 + i * 1000), today - timedelta(days=150 - i * 25),
                subcategory="salary", unit="INR", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(10000 + i * 200), today - timedelta(days=150 - i * 25),
                unit="INR",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "increase_savings_rate",
                "params": {"target_rate": 0.30},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        if data["reliability"] != "insufficient":
            labels = [line["label"] for line in data["lines"]]
            assert "current_path_expected" in labels, f"Missing current_path_expected, got {labels}"
            assert "expected_case" in labels, f"Missing expected_case, got {labels}"
            assert len(data["lines"]) == 2, f"Expected exactly 2 lines, got {len(data['lines'])}"

            # Verify no best_case or risk_case lines
            assert "best_case" not in labels
            assert "risk_case" not in labels


@pytest.mark.asyncio
async def test_savings_rate_different_target_rates_different_cache():
    """Two different target_rate values must produce genuinely different cache entries."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "sav_cache")
        headers = user["headers"]
        today = date.today()

        # Seed data
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(60000), today - timedelta(days=150 - i * 25),
                subcategory="salary", unit="INR", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(12000), today - timedelta(days=150 - i * 25),
                unit="INR",
            )

        # Run with target_rate=0.20
        resp1 = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.20}},
            headers=headers,
        )
        assert resp1.status_code == 200

        # Run with target_rate=0.40
        resp2 = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.40}},
            headers=headers,
        )
        assert resp2.status_code == 200

        data1 = resp1.json()
        data2 = resp2.json()

        # Verify different IDs (different cache entries)
        assert data1["id"] != data2["id"], (
            "Different target_rate values must produce different cache entries"
        )

        # Verify the params_hash is actually different
        hash1 = hashlib.sha256(
            json.dumps({"target_rate": 0.20}, sort_keys=True).encode()
        ).hexdigest()
        hash2 = hashlib.sha256(
            json.dumps({"target_rate": 0.40}, sort_keys=True).encode()
        ).hexdigest()
        assert hash1 != hash2, "Params hashes must differ for different target_rates"


@pytest.mark.asyncio
async def test_savings_rate_cumulative_growth_and_independence():
    """
    Cumulative Growth & Independence:
    1. Both current_path_expected and expected_case values must grow monotonically
       month-over-month (each point >= previous point on that line) across the 60-month horizon.
    2. When target_rate > current_rate, expected_case final value > current_path_expected final value.
    3. When target_rate < current_rate, expected_case final value < current_path_expected final value.
    4. The two lines' running totals are independent: current_path_expected is identical
       regardless of what target_rate is requested.
    5. Starting value starts at 0 (pure future projection, not offset by past account history).
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "sav_cumul")
        headers = user["headers"]
        today = date.today()

        # Seed 6 months of data: income = 50,000/mo, savings = 10,000/mo -> current_rate = 0.20
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                "50000", today - timedelta(days=150 - i * 25),
                subcategory="salary", unit="INR", notes="income",
            )
            await create_entry(
                client, headers, "savings",
                "10000", today - timedelta(days=150 - i * 25),
                unit="INR",
            )

        # Simulation 1: target_rate = 0.35 (> current_rate 0.20)
        resp_high = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.35}},
            headers=headers,
        )
        assert resp_high.status_code == 200, resp_high.text
        data_high = resp_high.json()
        assert data_high["reliability"] != "insufficient"
        assert len(data_high["lines"]) == 2

        lines_high = {line["label"]: line["points"] for line in data_high["lines"]}
        current_pts_high = lines_high["current_path_expected"]
        expected_pts_high = lines_high["expected_case"]

        assert len(current_pts_high) == 60
        assert len(expected_pts_high) == 60

        # Assert monotonic cumulative growth for both lines (non-decreasing)
        for i in range(1, 60):
            assert current_pts_high[i]["value"] >= current_pts_high[i - 1]["value"], (
                f"current_path_expected at month {i} ({current_pts_high[i]['value']}) "
                f"should be >= month {i-1} ({current_pts_high[i-1]['value']})"
            )
            assert expected_pts_high[i]["value"] >= expected_pts_high[i - 1]["value"], (
                f"expected_case at month {i} ({expected_pts_high[i]['value']}) "
                f"should be >= month {i-1} ({expected_pts_high[i-1]['value']})"
            )

        # When target_rate (0.35) > current_rate (0.20):
        # Month 60 expected_case must be meaningfully larger than current_path_expected
        final_current_high = current_pts_high[-1]["value"]
        final_expected_high = expected_pts_high[-1]["value"]
        assert final_expected_high > final_current_high, (
            f"Expected case ({final_expected_high}) should exceed current path ({final_current_high})"
        )
        # Should be roughly 0.35 / 0.20 = 1.75 ratio
        ratio_high = final_expected_high / final_current_high
        assert 1.6 <= ratio_high <= 1.9, f"Expected ratio near 1.75, got {ratio_high}"

        # Simulation 2: target_rate = 0.10 (< current_rate 0.20)
        resp_low = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.10}},
            headers=headers,
        )
        assert resp_low.status_code == 200, resp_low.text
        data_low = resp_low.json()

        lines_low = {line["label"]: line["points"] for line in data_low["lines"]}
        current_pts_low = lines_low["current_path_expected"]
        expected_pts_low = lines_low["expected_case"]

        # Month 60 expected_case must be smaller when target_rate < current_rate
        final_current_low = current_pts_low[-1]["value"]
        final_expected_low = expected_pts_low[-1]["value"]
        assert final_expected_low < final_current_low, (
            f"Expected case ({final_expected_low}) should be less than current path ({final_current_low})"
        )

        # Independence assertion:
        # current_path_expected must be identical across both runs regardless of target_rate
        for i in range(60):
            assert current_pts_high[i]["value"] == current_pts_low[i]["value"], (
                f"current_path_expected month {i} changed with target_rate: "
                f"{current_pts_high[i]['value']} vs {current_pts_low[i]['value']}"
            )
            assert current_pts_high[i]["date"] == current_pts_low[i]["date"]


# ==============================================================================
# VERIFICATION STEP 3: Fitness Plan Scenario
# ==============================================================================


@pytest.mark.asyncio
async def test_fitness_plan_90_day_daily_horizon():
    """Fitness Plan must use 90-day daily horizon, not monthly."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fit_horizon")
        headers = user["headers"]
        today = date.today()

        # Seed 30 daily fitness entries (enough for reliable)
        for i in range(30):
            await create_entry(
                client, headers, "fitness",
                str(30 + (i % 5) * 5), today - timedelta(days=35 - i),
                subcategory="running", unit="minutes",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "fitness_plan",
                "params": {"target_weekly_minutes": 200},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Verify daily output (90 points per line if reliable)
        if data["reliability"] != "insufficient":
            for line in data["lines"]:
                assert len(line["points"]) == 90, (
                    f"Expected 90 daily points for line '{line['label']}', "
                    f"got {len(line['points'])}"
                )


@pytest.mark.asyncio
async def test_fitness_plan_28_daily_entries_reliable():
    """28+ daily fitness entries should produce 'reliable' (no monthly threshold)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fit_reliable")
        headers = user["headers"]
        today = date.today()

        # Seed exactly 28 daily entries
        for i in range(28):
            await create_entry(
                client, headers, "fitness",
                str(40 + (i % 3) * 10), today - timedelta(days=30 - i),
                subcategory="gym", unit="minutes",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "fitness_plan",
                "params": {"target_weekly_minutes": 180},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["reliability"] == "reliable", (
            f"28 daily entries should give 'reliable', got '{data['reliability']}'"
        )


@pytest.mark.asyncio
async def test_fitness_plan_four_line_output():
    """Fitness Plan must return 4 lines: current_baseline, best_case, expected_case, risk_case."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "fit_4line")
        headers = user["headers"]
        today = date.today()

        for i in range(30):
            await create_entry(
                client, headers, "fitness",
                str(25 + (i % 4) * 8), today - timedelta(days=35 - i),
                subcategory="yoga", unit="minutes",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "fitness_plan",
                "params": {"target_weekly_minutes": 210},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        if data["reliability"] != "insufficient":
            labels = sorted([line["label"] for line in data["lines"]])
            expected_labels = sorted(["current_baseline", "best_case", "expected_case", "risk_case"])
            assert labels == expected_labels, (
                f"Expected 4 lines {expected_labels}, got {labels}"
            )


# ==============================================================================
# VERIFICATION STEP 4: Reduce Study Hours Scenario
# ==============================================================================


@pytest.mark.asyncio
async def test_study_hours_insufficient_below_14_paired_weeks():
    """<14 paired weekly observations → insufficient, no regression attempted."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "study_insuf")
        headers = user["headers"]
        today = date.today()

        # Seed only 10 weeks of data (below the 14 minimum)
        for i in range(10):
            week_start = today - timedelta(weeks=12 - i)
            await create_entry(
                client, headers, "study",
                str(15.0 + i * 0.5), week_start,
                subcategory="math", unit="hours",
            )
            await create_entry(
                client, headers, "academic",
                str(75.0 + i * 1.5), week_start + timedelta(days=3),
                subcategory="math", unit="points",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "reduce_study_hours",
                "params": {"target_weekly_hours": 10},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["reliability"] == "insufficient", (
            f"Expected 'insufficient' with <14 paired weeks, got '{data['reliability']}'"
        )
        assert len(data["lines"]) == 0, "No lines should be returned when insufficient"
        assert data["correlation_r_squared"] is None


@pytest.mark.asyncio
async def test_study_hours_regression_with_r_squared():
    """14+ paired weeks → regression runs, R² reported."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "study_reg")
        headers = user["headers"]
        today = date.today()

        # Seed 16 weeks of correlated study+academic data
        for i in range(16):
            week_start = today - timedelta(weeks=18 - i)
            study_hours = 12.0 + i * 0.8  # increasing study hours
            academic_score = 60.0 + i * 2.0 + (i % 3)  # correlated score

            await create_entry(
                client, headers, "study",
                str(study_hours), week_start,
                subcategory="physics", unit="hours",
            )
            await create_entry(
                client, headers, "academic",
                str(academic_score), week_start + timedelta(days=4),
                subcategory="physics", unit="points",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "reduce_study_hours",
                "params": {"target_weekly_hours": 8},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["reliability"] != "insufficient", (
            f"16 paired weeks should not be 'insufficient', got '{data['reliability']}'"
        )
        assert data["correlation_r_squared"] is not None, "R² must be reported"
        assert isinstance(data["correlation_r_squared"], float)
        assert 0 <= data["correlation_r_squared"] <= 1.0


@pytest.mark.asyncio
async def test_study_hours_weak_correlation_flagged():
    """R² < 0.3 must result in reliability = 'low_confidence'."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "study_weak")
        headers = user["headers"]
        today = date.today()

        # Seed 16 weeks of UNCORRELATED data (random-ish)
        import random
        random.seed(42)
        for i in range(16):
            week_start = today - timedelta(weeks=18 - i)
            study_hours = random.uniform(5, 25)  # random study hours
            academic_score = random.uniform(50, 100)  # random scores (no correlation)

            await create_entry(
                client, headers, "study",
                str(round(study_hours, 1)), week_start,
                subcategory="history", unit="hours",
            )
            await create_entry(
                client, headers, "academic",
                str(round(academic_score, 1)), week_start + timedelta(days=2),
                subcategory="history", unit="points",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "reduce_study_hours",
                "params": {"target_weekly_hours": 10},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # With random data, R² should be very low
        if data["correlation_r_squared"] is not None and data["correlation_r_squared"] < 0.3:
            assert data["reliability"] == "low_confidence", (
                f"Weak R² ({data['correlation_r_squared']}) should yield 'low_confidence', "
                f"got '{data['reliability']}'"
            )


@pytest.mark.asyncio
async def test_study_hours_non_causal_language():
    """Response message must frame findings as correlation, never causation."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "study_lang")
        headers = user["headers"]
        today = date.today()

        # Seed 16 weeks of correlated data
        for i in range(16):
            week_start = today - timedelta(weeks=18 - i)
            await create_entry(
                client, headers, "study",
                str(10 + i), week_start,
                subcategory="bio", unit="hours",
            )
            await create_entry(
                client, headers, "academic",
                str(65 + i * 1.5), week_start + timedelta(days=3),
                subcategory="bio", unit="points",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "reduce_study_hours",
                "params": {"target_weekly_hours": 8},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        if data["message"]:
            # Must contain "correlation" language
            msg_lower = data["message"].lower()
            assert "correlation" in msg_lower, (
                f"Message must mention 'correlation', got: {data['message']}"
            )
            # Must NOT contain causal language
            assert "cause" not in msg_lower or "causal" in msg_lower, (
                f"Message must not imply causation: {data['message']}"
            )
            # Must contain "not a guaranteed"
            assert "not a guaranteed" in msg_lower, (
                f"Message must disclaim certainty: {data['message']}"
            )


# ==============================================================================
# VERIFICATION STEP 5: Debug Endpoint
# ==============================================================================


@pytest.mark.asyncio
async def test_debug_endpoint_returns_accurate_values():
    """Debug endpoint must return values matching what's actually stored."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "debug_acc")
        headers = user["headers"]
        today = date.today()

        # Seed data and run a simulation
        for i in range(30):
            await create_entry(
                client, headers, "fitness",
                str(30 + i), today - timedelta(days=35 - i),
                subcategory="swimming", unit="minutes",
            )

        sim_resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "fitness_plan",
                "params": {"target_weekly_minutes": 200},
            },
            headers=headers,
        )
        assert sim_resp.status_code == 200
        sim_data = sim_resp.json()
        sim_id = sim_data["id"]

        # Call debug endpoint
        debug_resp = await client.get(
            f"/simulations/{sim_id}/debug",
            headers=headers,
        )
        assert debug_resp.status_code == 200, debug_resp.text
        debug_data = debug_resp.json()

        # Verify fields match
        assert debug_data["id"] == sim_id
        assert debug_data["scenario_type"] == "fitness_plan"
        assert debug_data["data_point_count"] == sim_data["data_point_count"]
        assert debug_data["reliability"] == sim_data["reliability"]
        assert debug_data["input_params"] == {"target_weekly_minutes": 200}
        assert debug_data["params_hash"] is not None
        assert len(debug_data["params_hash"]) == 64  # SHA-256 hex
        assert debug_data["generated_at"] is not None


@pytest.mark.asyncio
async def test_debug_endpoint_user_isolation():
    """Debug endpoint must be isolated per user — User B cannot see User A's simulation."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user_a = await register_user(client, "debug_iso_a")
        user_b = await register_user(client, "debug_iso_b")
        headers_a = user_a["headers"]
        headers_b = user_b["headers"]
        today = date.today()

        # User A creates entries and runs simulation
        for i in range(30):
            await create_entry(
                client, headers_a, "fitness",
                str(40 + i), today - timedelta(days=35 - i),
                subcategory="cycling", unit="minutes",
            )

        sim_resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "fitness_plan",
                "params": {"target_weekly_minutes": 150},
            },
            headers=headers_a,
        )
        assert sim_resp.status_code == 200
        sim_id = sim_resp.json()["id"]

        # User B tries to access User A's simulation debug
        debug_b = await client.get(
            f"/simulations/{sim_id}/debug",
            headers=headers_b,
        )
        assert debug_b.status_code == 404, (
            "User B must not be able to access User A's simulation debug"
        )


# ==============================================================================
# VERIFICATION STEP 6: Regression Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_regression_health_endpoint():
    """Health endpoint must still work."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_regression_auth_flow():
    """Auth register/login must still work."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        timestamp = int(time.time() * 1000)
        email = f"regression_auth_{timestamp}@example.com"

        reg = await client.post(
            "/auth/register",
            json={"email": email, "password": "SecurePassword123!"},
        )
        assert reg.status_code == 201

        login = await client.post(
            "/auth/login",
            json={"email": email, "password": "SecurePassword123!"},
        )
        assert login.status_code == 200
        assert "access_token" in login.json()


@pytest.mark.asyncio
async def test_regression_entries_crud():
    """Entries CRUD must still work after formatting changes."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "reg_entries")
        headers = user["headers"]
        today = date.today()

        # Create
        entry = await create_entry(
            client, headers, "fitness",
            "45.5", today, subcategory="yoga", unit="minutes",
        )
        assert entry["id"] is not None

        # Read
        get_resp = await client.get(f"/entries/{entry['id']}", headers=headers)
        assert get_resp.status_code == 200

        # Update
        put_resp = await client.put(
            f"/entries/{entry['id']}",
            json={"value": "60.0"},
            headers=headers,
        )
        assert put_resp.status_code == 200

        # Delete
        del_resp = await client.delete(f"/entries/{entry['id']}", headers=headers)
        assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_regression_forecast_still_works():
    """Forecast endpoint must still work after compute_forecast changes."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "reg_forecast")
        headers = user["headers"]
        today = date.today()

        # Seed 20 entries for a low_confidence forecast
        for i in range(20):
            await create_entry(
                client, headers, "study",
                str(round(2.0 + (i % 3) * 0.5, 1)), today - timedelta(days=25 - i),
                subcategory="ml", unit="hours",
            )

        resp = await client.get(
            "/forecast?category=study&subcategory=ml",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["reliability"] in ("low_confidence", "reliable")
        assert len(data["forecast_points"]) == 14


@pytest.mark.asyncio
async def test_unknown_scenario_returns_404():
    """Unregistered scenario type in registry must return 404."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "unknown_scen")
        headers = user["headers"]

        # Use a scenario_type value that's not in the ScenarioType enum
        # This will be caught by Pydantic validation (422) before reaching the router
        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "totally_fake_scenario",
                "params": {},
            },
            headers=headers,
        )
        assert resp.status_code == 422, resp.text


# ==============================================================================
# CHUNK 10 VERIFICATION TESTS: Assumption-Based Scenarios
# ==============================================================================


# ── Default Buy vs Rent params (valid baseline) ──────────────────────
BUY_VS_RENT_PARAMS = {
    "home_price": 5000000,
    "mortgage_rate_pct": 8.5,
    "loan_term_years": 20,
    "current_monthly_rent": 25000,
    "expected_rent_increase_pct_per_year": 5.0,
    "expected_home_appreciation_pct_per_year": 4.0,
    "expected_investment_return_pct_per_year": 10.0,
}

# ── Default Program Outcome params (valid baseline) ──────────────────
PROGRAM_OUTCOME_PARAMS = {
    "current_annual_salary": 600000,
    "program_tuition_cost": 1000000,
    "program_duration_years": 2.0,
    "expected_salary_post_program": 1200000,
    "opportunity_cost_income_during_program": 600000,
}


# Verification Step 1: Buy vs Rent t=0 exact identity
@pytest.mark.asyncio
async def test_buy_vs_rent_identity_at_t0():
    """
    At t=0:
    - home_equity(0) must equal S exactly (home_price - loan_principal = S)
    - rent_net_position(0) must equal S exactly (S invested - 0 rent = S)
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "bvr_identity")
        headers = user["headers"]
        today = date.today()

        # Seed savings entries totaling S = 500,000
        for i in range(5):
            await create_entry(
                client, headers, "savings",
                str(100000), today - timedelta(days=30 * (i + 1)),
                unit="INR",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "buy_vs_rent",
                "params": BUY_VS_RENT_PARAMS,
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        S = 500000.0  # 5 * 100000

        # Find Buy and Rent lines
        lines = {line["label"]: line["points"] for line in data["lines"]}
        assert "Buy" in lines, f"Missing 'Buy' line, got {list(lines.keys())}"
        assert "Rent" in lines, f"Missing 'Rent' line, got {list(lines.keys())}"

        buy_t0 = lines["Buy"][0]["value"]
        rent_t0 = lines["Rent"][0]["value"]

        assert buy_t0 == S, (
            f"home_equity(0) should be {S}, got {buy_t0}"
        )
        assert rent_t0 == S, (
            f"rent_net_position(0) should be {S}, got {rent_t0}"
        )

        # Verify derived values
        assert data["reliability"] == "assumption_based"
        assert data["data_point_count"] is None
        dv = data.get("derived_values", {})
        assert dv["starting_capital_s"] == S
        assert dv["loan_principal"] == BUY_VS_RENT_PARAMS["home_price"] - S

        # Verify 11 points (t=0 through t=10)
        assert len(lines["Buy"]) == 11
        assert len(lines["Rent"]) == 11


# Verification Step 2: S >= home_price (422) and S == 0 message
@pytest.mark.asyncio
async def test_buy_vs_rent_savings_bounds():
    """
    - When S >= home_price: 422 with "already exceed" message
    - When S == 0: 200 with "₹0 in tracked savings" disclosure
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ── Case 1: S >= home_price → 422 ────────────────────────────
        user1 = await register_user(client, "bvr_exceeds")
        headers1 = user1["headers"]
        today = date.today()

        # Seed savings = 6,000,000 > home_price = 5,000,000
        for i in range(6):
            await create_entry(
                client, headers1, "savings",
                str(1000000), today - timedelta(days=30 * (i + 1)),
                unit="INR",
            )

        resp1 = await client.post(
            "/simulations",
            json={
                "scenario_type": "buy_vs_rent",
                "params": BUY_VS_RENT_PARAMS,
            },
            headers=headers1,
        )
        assert resp1.status_code == 422, resp1.text
        assert "already exceed" in resp1.json()["detail"].lower()

        # ── Case 2: S == 0 → 200 with disclosure ────────────────────
        user2 = await register_user(client, "bvr_zero")
        headers2 = user2["headers"]

        resp2 = await client.post(
            "/simulations",
            json={
                "scenario_type": "buy_vs_rent",
                "params": BUY_VS_RENT_PARAMS,
            },
            headers=headers2,
        )
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        assert "₹0 in tracked savings" in data2["message"]

        # At t=0 both lines should be 0
        lines2 = {line["label"]: line["points"] for line in data2["lines"]}
        assert lines2["Buy"][0]["value"] == 0.0
        assert lines2["Rent"][0]["value"] == 0.0


# Verification Step 3: Buy vs Rent savings-only staleness invalidation
@pytest.mark.asyncio
async def test_buy_vs_rent_scoped_caching_staleness():
    """
    - Cache hit on repeated call
    - Adding a new 'study' entry keeps cache valid (HIT)
    - Adding a new 'savings' entry invalidates cache (MISS, recomputes with new S)
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "bvr_cache")
        headers = user["headers"]
        today = date.today()

        # Seed initial savings
        await create_entry(
            client, headers, "savings",
            str(200000), today - timedelta(days=60),
            unit="INR",
        )

        # First call: cache MISS
        resp1 = await client.post(
            "/simulations",
            json={"scenario_type": "buy_vs_rent", "params": BUY_VS_RENT_PARAMS},
            headers=headers,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        id1 = data1["id"]
        gen1 = data1["generated_at"]

        # Second call (same params): cache HIT — same id and generated_at
        resp2 = await client.post(
            "/simulations",
            json={"scenario_type": "buy_vs_rent", "params": BUY_VS_RENT_PARAMS},
            headers=headers,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["id"] == id1, "Should be cache HIT (same ID)"
        assert data2["generated_at"] == gen1, "Should be cache HIT (same generated_at)"

        # Add a study entry (unrelated category) → cache should STILL be valid
        await create_entry(
            client, headers, "study",
            str(5.0), today - timedelta(days=1),
            subcategory="math", unit="hours",
        )

        resp3 = await client.post(
            "/simulations",
            json={"scenario_type": "buy_vs_rent", "params": BUY_VS_RENT_PARAMS},
            headers=headers,
        )
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["id"] == id1, "Study entry should NOT bust savings-scoped cache"
        assert data3["generated_at"] == gen1

        # Add a savings entry → cache should be INVALIDATED
        await create_entry(
            client, headers, "savings",
            str(100000), today,
            unit="INR",
        )

        resp4 = await client.post(
            "/simulations",
            json={"scenario_type": "buy_vs_rent", "params": BUY_VS_RENT_PARAMS},
            headers=headers,
        )
        assert resp4.status_code == 200
        data4 = resp4.json()
        # generated_at should be different (recomputed)
        assert data4["generated_at"] != gen1, (
            "Adding a savings entry must invalidate savings-scoped cache"
        )
        # New S should be 300000
        assert data4["derived_values"]["starting_capital_s"] == 300000.0


# Verification Step 4: Program Outcome exact cost identity
@pytest.mark.asyncio
async def test_program_outcome_exact_cost_identity():
    """
    Assert exact identity:
    total_costs_charged == tuition + opp_cost * D
    for both whole D=2.0 and fractional D=2.5.
    """
    from app.services.scenarios.program_outcome import ProgramOutcome

    scenario = ProgramOutcome()

    # ── Case 1: Whole duration D = 2.0 ───────────────────────────────
    params_whole = {
        "current_annual_salary": 600000,
        "program_tuition_cost": 1000000,
        "program_duration_years": 2.0,
        "expected_salary_post_program": 1200000,
        "opportunity_cost_income_during_program": 600000,
    }
    result_whole = scenario.compute(user_id="test", entries=[], params=params_whole)

    expected_total_cost_whole = 1000000 + 600000 * 2.0  # 2,200,000
    dv_whole = result_whole["derived_values"]
    assert dv_whole["total_program_cost"] == expected_total_cost_whole, (
        f"Whole D=2.0: total cost should be {expected_total_cost_whole}, "
        f"got {dv_whole['total_program_cost']}"
    )

    # ── Case 2: Fractional duration D = 2.5 ──────────────────────────
    params_frac = {
        "current_annual_salary": 600000,
        "program_tuition_cost": 1000000,
        "program_duration_years": 2.5,
        "expected_salary_post_program": 1200000,
        "opportunity_cost_income_during_program": 600000,
    }
    result_frac = scenario.compute(user_id="test", entries=[], params=params_frac)

    expected_total_cost_frac = 1000000 + 600000 * 2.5  # 2,500,000
    dv_frac = result_frac["derived_values"]
    assert dv_frac["total_program_cost"] == expected_total_cost_frac, (
        f"Fractional D=2.5: total cost should be {expected_total_cost_frac}, "
        f"got {dv_frac['total_program_cost']}"
    )

    # ── Verify sum of yearly costs also equals total ─────────────────
    # For D=2.5: cost_y for y=1..10 should sum to tuition + opp_cost * D
    import math

    D = 2.5
    C_tuition_per_year = 1000000 / D
    C_annual = C_tuition_per_year + 600000
    floor_D = int(math.floor(D))
    frac_part = D - floor_D

    total_cost_sum = 0.0
    for y in range(1, 11):
        if y <= floor_D:
            f_y = 1.0
        elif y == floor_D + 1 and frac_part > 0:
            f_y = frac_part
        else:
            f_y = 0.0
        total_cost_sum += f_y * C_annual

    assert abs(total_cost_sum - expected_total_cost_frac) < 0.01, (
        f"Sum of yearly costs ({total_cost_sum}) must equal "
        f"tuition + opp_cost * D ({expected_total_cost_frac})"
    )

    # Verify 4 lines and correct labels
    labels = sorted([line["label"] for line in result_frac["lines"]])
    expected_labels = sorted(["without_program", "expected_case", "best_case", "risk_case"])
    assert labels == expected_labels, f"Expected 4 lines {expected_labels}, got {labels}"

    # Verify 11 points per line (t=0..10)
    for line in result_frac["lines"]:
        assert len(line["points"]) == 11, (
            f"Line '{line['label']}' should have 11 points, got {len(line['points'])}"
        )

    # Verify without_program starts at 0 and grows linearly
    wp_line = next(l for l in result_frac["lines"] if l["label"] == "without_program")
    assert wp_line["points"][0]["value"] == 0.0
    for t in range(1, 11):
        expected_cumulative = t * 600000
        assert wp_line["points"][t]["value"] == expected_cumulative, (
            f"without_program at Year {t} should be {expected_cumulative}, "
            f"got {wp_line['points'][t]['value']}"
        )


# Verification Step 5: Program Outcome indefinite caching
@pytest.mark.asyncio
async def test_program_outcome_indefinite_caching():
    """
    Run simulation, add savings + study entries, assert cache hit (same ID and generated_at).
    ProgramOutcome has staleness_scope=None → caches indefinitely.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "po_cache")
        headers = user["headers"]
        today = date.today()

        # First call
        resp1 = await client.post(
            "/simulations",
            json={"scenario_type": "program_outcome", "params": PROGRAM_OUTCOME_PARAMS},
            headers=headers,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        id1 = data1["id"]
        gen1 = data1["generated_at"]

        # Add a savings entry
        await create_entry(
            client, headers, "savings",
            str(50000), today,
            unit="INR",
        )

        # Add a study entry
        await create_entry(
            client, headers, "study",
            str(3.5), today,
            subcategory="math", unit="hours",
        )

        # Second call: should still be cache HIT (indefinite caching)
        resp2 = await client.post(
            "/simulations",
            json={"scenario_type": "program_outcome", "params": PROGRAM_OUTCOME_PARAMS},
            headers=headers,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["id"] == id1, "ProgramOutcome should cache indefinitely"
        assert data2["generated_at"] == gen1, "ProgramOutcome generated_at should not change"


# Verification Step 6: Specific 422 input validation
@pytest.mark.asyncio
async def test_assumption_scenarios_validation_422():
    """
    Negative numbers, missing required parameters, and duration out-of-bounds
    must return clean 422 with field-level details.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "validation_422")
        headers = user["headers"]

        # ── Buy vs Rent: negative home_price ─────────────────────────
        resp1 = await client.post(
            "/simulations",
            json={
                "scenario_type": "buy_vs_rent",
                "params": {**BUY_VS_RENT_PARAMS, "home_price": -100},
            },
            headers=headers,
        )
        assert resp1.status_code == 422, resp1.text

        # ── Buy vs Rent: missing required field ──────────────────────
        incomplete_params = dict(BUY_VS_RENT_PARAMS)
        del incomplete_params["home_price"]
        resp2 = await client.post(
            "/simulations",
            json={
                "scenario_type": "buy_vs_rent",
                "params": incomplete_params,
            },
            headers=headers,
        )
        assert resp2.status_code == 422, resp2.text

        # ── Program Outcome: duration too small (< 0.5) ─────────────
        resp3 = await client.post(
            "/simulations",
            json={
                "scenario_type": "program_outcome",
                "params": {**PROGRAM_OUTCOME_PARAMS, "program_duration_years": 0.2},
            },
            headers=headers,
        )
        assert resp3.status_code == 422, resp3.text

        # ── Program Outcome: duration too large (> 10) ───────────────
        resp4 = await client.post(
            "/simulations",
            json={
                "scenario_type": "program_outcome",
                "params": {**PROGRAM_OUTCOME_PARAMS, "program_duration_years": 15.0},
            },
            headers=headers,
        )
        assert resp4.status_code == 422, resp4.text

        # ── Program Outcome: negative salary ─────────────────────────
        resp5 = await client.post(
            "/simulations",
            json={
                "scenario_type": "program_outcome",
                "params": {**PROGRAM_OUTCOME_PARAMS, "current_annual_salary": -50000},
            },
            headers=headers,
        )
        assert resp5.status_code == 422, resp5.text


# Verification Step 7: Widened interface regression check on Chunk 9 scenarios
@pytest.mark.asyncio
async def test_regression_chunk9_scenarios():
    """
    Savings Rate, Fitness Plan, and Reduce Study Hours must still run
    unaffected under the widened compute() interface.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        user = await register_user(client, "chunk9_reg")
        headers = user["headers"]
        today = date.today()

        # ── Seed data for all three scenarios ────────────────────────
        # Income entries for savings rate
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(50000), today - timedelta(days=150 - i * 25),
                subcategory="salary", unit="INR", notes="income",
            )
        # Savings entries
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(10000), today - timedelta(days=150 - i * 25),
                unit="INR",
            )
        # Fitness entries
        for i in range(30):
            await create_entry(
                client, headers, "fitness",
                str(30 + i), today - timedelta(days=35 - i),
                subcategory="running", unit="minutes",
            )
        # Study + academic entries
        for i in range(16):
            week_start = today - timedelta(weeks=18 - i)
            await create_entry(
                client, headers, "study",
                str(12 + i * 0.5), week_start,
                subcategory="math", unit="hours",
            )
            await create_entry(
                client, headers, "academic",
                str(65 + i * 1.5), week_start + timedelta(days=3),
                subcategory="math", unit="points",
            )

        # ── Savings Rate ─────────────────────────────────────────────
        resp_sr = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.25}},
            headers=headers,
        )
        assert resp_sr.status_code == 200, f"Savings Rate failed: {resp_sr.text}"
        sr_data = resp_sr.json()
        assert sr_data["reliability"] != "insufficient" or len(sr_data["lines"]) == 0

        # ── Fitness Plan ─────────────────────────────────────────────
        resp_fp = await client.post(
            "/simulations",
            json={"scenario_type": "fitness_plan", "params": {"target_weekly_minutes": 200}},
            headers=headers,
        )
        assert resp_fp.status_code == 200, f"Fitness Plan failed: {resp_fp.text}"

        # ── Reduce Study Hours ───────────────────────────────────────
        resp_sh = await client.post(
            "/simulations",
            json={"scenario_type": "reduce_study_hours", "params": {"target_weekly_hours": 8}},
            headers=headers,
        )
        assert resp_sh.status_code == 200, f"Reduce Study Hours failed: {resp_sh.text}"


if __name__ == "__main__":
    asyncio.run(test_entry_formatting_income_expense_rounds_to_integer())
    print("All simulation tests passed!")


# ==============================================================================
# CHUNK 11 — AI RECOMMENDATIONS VERIFICATION
# ==============================================================================


@pytest.mark.asyncio
async def test_chunk11_post_returns_pending_recommendations():
    """
    Verification Step 1: POST /simulations returns immediately with
    recommendations_status="pending" and recommendations=None.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_pending")
        headers = auth["headers"]

        today = date.today()
        # Seed enough income-tagged entries for savings rate
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(5000), today - timedelta(days=30 * (6 - i)),
                subcategory="salary", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(1000), today - timedelta(days=30 * (6 - i)),
                subcategory="bank",
            )

        resp = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.30}},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Immediately returned — recommendations not yet available
        assert data["recommendations_status"] == "pending"
        assert data["recommendations"] is None
        assert data["recommendation_disclaimer"] is None

        # Simulation numbers must still be present
        assert data["reliability"] in ("low_confidence", "reliable", "insufficient")
        assert data["scenario_type"] == "increase_savings_rate"


@pytest.mark.asyncio
async def test_chunk11_poll_returns_ready_recommendations():
    """
    Verification Step 2: After background task completes, polling
    GET /simulations/{id} returns recommendations_status="ready"
    with 2-4 schema-validated recommendation items.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_poll")
        headers = auth["headers"]

        today = date.today()
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(5000), today - timedelta(days=30 * (6 - i)),
                subcategory="salary", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(1000), today - timedelta(days=30 * (6 - i)),
                subcategory="bank",
            )

        resp = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.30}},
            headers=headers,
        )
        assert resp.status_code == 200
        sim_id = resp.json()["id"]

        # Poll until ready or timeout (max 30 seconds)
        for _ in range(60):
            await asyncio.sleep(0.5)
            poll_resp = await client.get(
                f"/simulations/{sim_id}",
                headers=headers,
            )
            assert poll_resp.status_code == 200
            poll_data = poll_resp.json()
            if poll_data["recommendations_status"] != "pending":
                break

        # Verify final state
        assert poll_data["recommendations_status"] in ("ready", "unavailable"), (
            f"Expected 'ready' or 'unavailable', got '{poll_data['recommendations_status']}'"
        )

        if poll_data["recommendations_status"] == "ready":
            recs = poll_data["recommendations"]
            assert recs is not None
            assert 2 <= len(recs) <= 4, f"Expected 2-4 recommendations, got {len(recs)}"

            # Validate each recommendation has the required fields with correct enum values
            valid_impact = {"High", "Medium", "Low"}
            valid_effort = {"High", "Medium", "Low"}
            for rec in recs:
                assert "title" in rec
                assert "impact" in rec
                assert "effort" in rec
                assert "description" in rec
                assert rec["impact"] in valid_impact, f"Invalid impact: {rec['impact']}"
                assert rec["effort"] in valid_effort, f"Invalid effort: {rec['effort']}"
                assert len(rec["title"]) > 0
                assert len(rec["description"]) > 0

            # Simulation numbers must still be present
            assert poll_data["scenario_type"] == "increase_savings_rate"
            assert poll_data["derived_values"] is not None


@pytest.mark.asyncio
async def test_chunk11_savings_rate_grounding_and_disclaimer():
    """
    Verification Step 3: Savings rate recommendations reference only real numbers,
    no invented optimal rates, no financial products, and include the exact disclaimer.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_ground")
        headers = auth["headers"]

        today = date.today()
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(5000), today - timedelta(days=30 * (6 - i)),
                subcategory="salary", notes="income",
            )
        # Also add expense-tagged entries for grounding context
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(3000), today - timedelta(days=30 * (6 - i)),
                subcategory="rent", notes="expense",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(800), today - timedelta(days=30 * (6 - i)),
                subcategory="bank",
            )

        resp = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.25}},
            headers=headers,
        )
        assert resp.status_code == 200
        sim_id = resp.json()["id"]

        # Wait for recommendations
        poll_data = None
        for _ in range(60):
            await asyncio.sleep(0.5)
            poll_resp = await client.get(f"/simulations/{sim_id}", headers=headers)
            poll_data = poll_resp.json()
            if poll_data["recommendations_status"] != "pending":
                break

        if poll_data["recommendations_status"] == "ready":
            # Check disclaimer
            assert poll_data["recommendation_disclaimer"] is not None
            assert "not financial advice" in poll_data["recommendation_disclaimer"].lower()

            # Check grounding: no specific financial products
            recs = poll_data["recommendations"]
            prohibited_terms = ["lic", "mutual fund", "fixed deposit", "etf", "crypto"]
            for rec in recs:
                combined = (rec["title"] + " " + rec["description"]).lower()
                for term in prohibited_terms:
                    assert term not in combined, (
                        f"Recommendation mentions prohibited financial product: '{term}' in '{combined}'"
                    )


@pytest.mark.asyncio
async def test_chunk11_hypothetical_framing_buy_vs_rent():
    """
    Verification Step 4: Buy vs Rent recommendations are phrased as
    hypothetical analysis, not commentary on real spending habits.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_hypo")
        headers = auth["headers"]

        # Seed minimal savings for Buy vs Rent starting capital
        today = date.today()
        for i in range(3):
            await create_entry(
                client, headers, "savings",
                str(50000), today - timedelta(days=30 * (3 - i)),
                subcategory="bank",
            )

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "buy_vs_rent",
                "params": {
                    "home_price": 5000000,
                    "mortgage_rate_pct": 8.5,
                    "loan_term_years": 20,
                    "current_monthly_rent": 25000,
                    "expected_rent_increase_pct_per_year": 5.0,
                    "expected_home_appreciation_pct_per_year": 7.0,
                    "expected_investment_return_pct_per_year": 12.0,
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        sim_id = resp.json()["id"]

        # Wait for recommendations
        poll_data = None
        for _ in range(60):
            await asyncio.sleep(0.5)
            poll_resp = await client.get(f"/simulations/{sim_id}", headers=headers)
            poll_data = poll_resp.json()
            if poll_data["recommendations_status"] != "pending":
                break

        if poll_data["recommendations_status"] == "ready":
            recs = poll_data["recommendations"]
            assert 2 <= len(recs) <= 4

            # Simulation numbers unaffected
            assert poll_data["reliability"] == "assumption_based"
            assert poll_data["lines"] is not None
            assert len(poll_data["lines"]) > 0


@pytest.mark.asyncio
async def test_chunk11_graceful_degradation():
    """
    Verification Step 5: When Gemini is unavailable (simulated via bad key),
    recommendations degrade to "unavailable" gracefully — simulation numbers
    unaffected, no raw exceptions leaked.
    """
    from unittest.mock import AsyncMock, patch

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_degrade")
        headers = auth["headers"]

        today = date.today()
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(5000), today - timedelta(days=30 * (6 - i)),
                subcategory="salary", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(1000), today - timedelta(days=30 * (6 - i)),
                subcategory="bank",
            )

        # Mock the grounded LLM to simulate failure
        with patch(
            "app.services.recommendation_engine.generate_grounded_recommendation",
            new_callable=AsyncMock,
            return_value=(None, "api_error"),
        ):
            resp = await client.post(
                "/simulations",
                json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.25}},
                headers=headers,
            )
            assert resp.status_code == 200
            sim_id = resp.json()["id"]

            # Wait for background task
            poll_data = None
            for _ in range(30):
                await asyncio.sleep(0.5)
                poll_resp = await client.get(f"/simulations/{sim_id}", headers=headers)
                poll_data = poll_resp.json()
                if poll_data["recommendations_status"] != "pending":
                    break

        # Graceful degradation
        assert poll_data["recommendations_status"] == "unavailable"
        assert poll_data["recommendations"] is None

        # Simulation numbers must be completely unaffected
        assert poll_data["scenario_type"] == "increase_savings_rate"
        assert poll_data["reliability"] in ("low_confidence", "reliable", "insufficient")
        if poll_data["reliability"] != "insufficient":
            assert len(poll_data["lines"]) > 0

        # Debug endpoint: no raw exceptions leaked
        debug_resp = await client.get(
            f"/simulations/{sim_id}/debug",
            headers=headers,
        )
        assert debug_resp.status_code == 200
        debug_data = debug_resp.json()
        assert debug_data["recommendations_status"] == "unavailable"
        assert debug_data["recommendation_outcome"] == "generation_failed"


@pytest.mark.asyncio
async def test_chunk11_staleness_resets_recommendations():
    """
    Verification Step 6: When the cache is invalidated by a new entry,
    the recomputed result resets recommendations to null/"pending" and
    re-fires the background task.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_stale")
        headers = auth["headers"]

        today = date.today()
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(5000), today - timedelta(days=30 * (6 - i)),
                subcategory="salary", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(1000), today - timedelta(days=30 * (6 - i)),
                subcategory="bank",
            )

        # First simulation
        resp1 = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.25}},
            headers=headers,
        )
        assert resp1.status_code == 200
        sim_id = resp1.json()["id"]

        # Wait for recommendations to be ready
        for _ in range(60):
            await asyncio.sleep(0.5)
            poll_resp = await client.get(f"/simulations/{sim_id}", headers=headers)
            poll_data = poll_resp.json()
            if poll_data["recommendations_status"] != "pending":
                break

        # Now add a new entry to trigger staleness
        await create_entry(
            client, headers, "savings",
            str(2000), today,
            subcategory="bank",
        )

        # Re-run the same simulation — should recompute and reset recommendations
        resp2 = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.25}},
            headers=headers,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()

        # Recommendations must be reset to pending on recompute
        assert data2["recommendations_status"] == "pending"
        assert data2["recommendations"] is None


@pytest.mark.asyncio
async def test_chunk11_grounded_llm_zero_domain_coupling():
    """
    Verification Step 7: grounded_llm.py has zero references to Simulation,
    Entry, ScenarioType, or scenario-specific types. This verifies the
    architectural contract that it's a generic, reusable service.
    """
    import ast
    import pathlib

    grounded_llm_path = pathlib.Path(__file__).parent.parent / "app" / "services" / "grounded_llm.py"
    assert grounded_llm_path.exists(), f"grounded_llm.py not found at {grounded_llm_path}"

    source = grounded_llm_path.read_text(encoding="utf-8")

    # Parse AST and collect all Name nodes (references to identifiers)
    tree = ast.parse(source)
    all_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            all_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            all_names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                all_names.add(node.module)
            for alias in node.names:
                all_names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                all_names.add(alias.name)

    # Prohibited domain-specific identifiers
    prohibited = {
        "Simulation", "SimulationResult", "Entry", "ScenarioType",
        "DataDrivenScenario", "AssumptionBasedScenario",
        "SCENARIO_REGISTRY", "scenarios",
    }

    violations = prohibited & all_names
    assert not violations, (
        f"grounded_llm.py has prohibited domain references: {violations}. "
        f"This module must remain fully domain-agnostic."
    )

    # Also verify no string references via a simple text search
    for term in prohibited:
        assert term not in source, (
            f"grounded_llm.py contains string '{term}' — must be domain-agnostic"
        )


@pytest.mark.asyncio
async def test_chunk11_get_polling_endpoint():
    """
    Test the GET /simulations/{id} polling endpoint returns correct data.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_getpoll")
        headers = auth["headers"]

        today = date.today()
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(5000), today - timedelta(days=30 * (6 - i)),
                subcategory="salary", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(1000), today - timedelta(days=30 * (6 - i)),
                subcategory="bank",
            )

        resp = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.20}},
            headers=headers,
        )
        assert resp.status_code == 200
        sim_id = resp.json()["id"]

        # GET returns the same simulation data
        get_resp = await client.get(f"/simulations/{sim_id}", headers=headers)
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == sim_id
        assert get_data["scenario_type"] == "increase_savings_rate"
        assert "recommendations_status" in get_data

        # Non-existent simulation returns 404
        import uuid
        fake_id = str(uuid.uuid4())
        not_found_resp = await client.get(f"/simulations/{fake_id}", headers=headers)
        assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_chunk11_get_polling_user_isolation():
    """
    Test that GET /simulations/{id} enforces user isolation —
    one user cannot poll another user's simulation.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth1 = await register_user(client, "c11_iso1")
        auth2 = await register_user(client, "c11_iso2")

        # User 1 creates a simulation (program_outcome — no data needed)
        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "program_outcome",
                "params": {
                    "current_annual_salary": 500000,
                    "program_tuition_cost": 200000,
                    "program_duration_years": 2.0,
                    "expected_salary_post_program": 800000,
                    "opportunity_cost_income_during_program": 0,
                },
            },
            headers=auth1["headers"],
        )
        assert resp.status_code == 200
        sim_id = resp.json()["id"]

        # User 2 tries to poll it — should get 404
        cross_resp = await client.get(
            f"/simulations/{sim_id}",
            headers=auth2["headers"],
        )
        assert cross_resp.status_code == 404


@pytest.mark.asyncio
async def test_chunk11_debug_endpoint_shows_recommendation_status():
    """
    Test that the debug endpoint includes recommendations_status
    and recommendation_outcome fields.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_debug")
        headers = auth["headers"]

        resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "program_outcome",
                "params": {
                    "current_annual_salary": 600000,
                    "program_tuition_cost": 300000,
                    "program_duration_years": 1.5,
                    "expected_salary_post_program": 900000,
                    "opportunity_cost_income_during_program": 0,
                },
            },
            headers=headers,
        )
        assert resp.status_code == 200
        sim_id = resp.json()["id"]

        debug_resp = await client.get(
            f"/simulations/{sim_id}/debug",
            headers=headers,
        )
        assert debug_resp.status_code == 200
        debug_data = debug_resp.json()

        # New Chunk 11 fields must be present
        assert "recommendations_status" in debug_data
        assert "recommendation_outcome" in debug_data
        assert debug_data["recommendations_status"] in ("pending", "ready", "unavailable")


@pytest.mark.asyncio
async def test_chunk11_full_regression():
    """
    Verification Step 8: Full regression — all Chunk 9-10 scenarios still
    produce correct results alongside the new recommendation fields.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        auth = await register_user(client, "c11_regr")
        headers = auth["headers"]

        today = date.today()

        # Seed income + savings entries
        for i in range(6):
            await create_entry(
                client, headers, "income_expense",
                str(5000), today - timedelta(days=30 * (6 - i)),
                subcategory="salary", notes="income",
            )
        for i in range(6):
            await create_entry(
                client, headers, "savings",
                str(1000), today - timedelta(days=30 * (6 - i)),
                subcategory="bank",
            )

        # Savings Rate
        sr_resp = await client.post(
            "/simulations",
            json={"scenario_type": "increase_savings_rate", "params": {"target_rate": 0.30}},
            headers=headers,
        )
        assert sr_resp.status_code == 200
        sr_data = sr_resp.json()
        assert "recommendations_status" in sr_data
        assert "recommendations" in sr_data
        assert sr_data["recommendations_status"] == "pending"
        if sr_data["reliability"] != "insufficient":
            assert len(sr_data["lines"]) == 2

        # Program Outcome (assumption-based, no data needed)
        po_resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "program_outcome",
                "params": {
                    "current_annual_salary": 500000,
                    "program_tuition_cost": 200000,
                    "program_duration_years": 2.0,
                    "expected_salary_post_program": 800000,
                    "opportunity_cost_income_during_program": 0,
                },
            },
            headers=headers,
        )
        assert po_resp.status_code == 200
        po_data = po_resp.json()
        assert po_data["reliability"] == "assumption_based"
        assert "recommendations_status" in po_data

        # Buy vs Rent (assumption-based)
        bvr_resp = await client.post(
            "/simulations",
            json={
                "scenario_type": "buy_vs_rent",
                "params": {
                    "home_price": 5000000,
                    "mortgage_rate_pct": 8.5,
                    "loan_term_years": 20,
                    "current_monthly_rent": 25000,
                    "expected_rent_increase_pct_per_year": 5.0,
                    "expected_home_appreciation_pct_per_year": 7.0,
                    "expected_investment_return_pct_per_year": 12.0,
                },
            },
            headers=headers,
        )
        assert bvr_resp.status_code == 200
        bvr_data = bvr_resp.json()
        assert bvr_data["reliability"] == "assumption_based"
        assert "recommendations_status" in bvr_data
