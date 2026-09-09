"""
Automated tests for Chunk 6 Alerts (Threshold + Trend, On-Demand Reconciliation):
- Step 1: Alembic migration creates alerts cleanly (table, FK, indexes)
- Step 2: Goal with deadline and low progress relative to elapsed time -> risk threshold alert
- Step 3: Catch up goal progress -> GET /alerts resolves previous alert (same row, resolved_at set)
- Step 4: Third GET /alerts with no change -> no new alert, no duplicates
- Step 5: Series with 20+ entries + outlier value outside confidence band -> trend alert appears
- Step 6: Series with only 5 entries (insufficient data) -> no trend alert fabricated
- Step 7: User B cross-user isolation -> zero of User A's alerts appear
- Step 8: GET /alerts?status=all -> resolved alert appears in history
- Step 9: Internal error path -> no raw exception text in response body (500 sanitized)
- Step 10: Full regression suite across all chunks
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import time
from unittest.mock import patch
import uuid

import httpx
import pytest
from sqlalchemy import inspect, select, text

from app.database import engine
from app.main import app
from app.models.alert import Alert
from app.models.goal import Goal


@pytest.mark.asyncio
async def test_alerts_full_flow():
    timestamp = int(time.time() * 1000)
    user_a_email = f"alert_user_a_{timestamp}@example.com"
    user_b_email = f"alert_user_b_{timestamp}@example.com"
    password = "SecurePassword123!"

    # ── Step 1: Verify Table and Indexes Cleanly Exist ──────────────
    async with engine.connect() as conn:
        def check_schema(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            assert "alerts" in tables, "alerts table missing"

            columns = {col["name"]: col for col in inspector.get_columns("alerts")}
            expected_cols = [
                "id",
                "user_id",
                "category",
                "subcategory",
                "kind",
                "severity",
                "message",
                "triggered_at",
                "resolved_at",
            ]
            for col in expected_cols:
                assert col in columns, f"Column {col} missing in alerts table"

            indexes = {idx["name"] for idx in inspector.get_indexes("alerts")}
            assert "ix_alerts_user_resolved" in indexes
            assert "ix_alerts_user_category_sub_kind" in indexes

        await conn.run_sync(check_schema)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Auth Setup: User A and User B
        res_a = await client.post("/auth/register", json={"email": user_a_email, "password": password})
        assert res_a.status_code == 201, res_a.text
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        res_b = await client.post("/auth/register", json={"email": user_b_email, "password": password})
        assert res_b.status_code == 201, res_b.text
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # ── Step 2: Create Goal with Deadline, Artificially Low Progress ───
        # Deadline 5 days from now
        today = date.today()
        deadline_date = today + timedelta(days=5)

        goal_res = await client.post(
            "/goals",
            json={
                "name": "Complete 100 LeetCode Problems",
                "target_value": "100.00",
                "current_value": "5.00",
                "deadline": deadline_date.isoformat(),
            },
            headers=headers_a,
        )
        assert goal_res.status_code == 201, goal_res.text
        goal_id = uuid.UUID(goal_res.json()["id"])

        # Artificially age goal creation date to 20 days ago via direct DB update
        # Total days = 25, Days elapsed = 20 -> Expected = 80.0%, Actual = 5.0% -> Pace gap = -75.0% (< -15.0%)
        artificially_aged_created_at = datetime.now(timezone.utc) - timedelta(days=20)
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE goals SET created_at = :aged WHERE id = :gid"),
                {"aged": artificially_aged_created_at, "gid": goal_id},
            )

        # Query GET /alerts -> Expect 1 risk threshold alert
        alerts_res_step2 = await client.get("/alerts", headers=headers_a)
        assert alerts_res_step2.status_code == 200, alerts_res_step2.text
        step2_data = alerts_res_step2.json()
        assert step2_data["total"] == 1
        assert len(step2_data["items"]) == 1

        alert_1 = step2_data["items"][0]
        assert alert_1["category"] == "goals"
        assert alert_1["subcategory"] == str(goal_id)
        assert alert_1["kind"] == "threshold"
        assert alert_1["severity"] == "risk"
        assert "critically behind pace" in alert_1["message"]
        assert alert_1["resolved_at"] is None
        alert_1_id = alert_1["id"]

        # ── Step 3: Catch Up Goal Progress -> Alert Resolved In-Place ────
        # Update current_value to 85.00 (Actual = 85%, Expected = 80% -> Pace gap = +5.0% >= -5.0%)
        goal_update_res = await client.put(
            f"/goals/{goal_id}",
            json={"current_value": "85.00"},
            headers=headers_a,
        )
        assert goal_update_res.status_code == 200, goal_update_res.text

        # Query GET /alerts -> Active alerts should now be empty
        alerts_res_step3 = await client.get("/alerts", headers=headers_a)
        assert alerts_res_step3.status_code == 200, alerts_res_step3.text
        step3_data = alerts_res_step3.json()
        assert step3_data["total"] == 0
        assert step3_data["items"] == []

        # Directly inspect DB: Same alert row exists, resolved_at is populated!
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT id, resolved_at FROM alerts WHERE id = :aid"),
                    {"aid": uuid.UUID(alert_1_id)},
                )
            ).mappings().one_or_none()
            assert row is not None, "Original alert row was deleted instead of reconciled"
            assert row["resolved_at"] is not None, "resolved_at was not populated"

        # ── Step 4: Call GET /alerts a Third Time with No Change ───────────
        # Confirm no new alert created for resolved condition and no duplicate
        alerts_res_step4 = await client.get("/alerts", headers=headers_a)
        assert alerts_res_step4.status_code == 200
        step4_data = alerts_res_step4.json()
        assert step4_data["total"] == 0
        assert step4_data["items"] == []

        async with engine.connect() as conn:
            user_id_a = (
                await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": user_a_email},
                )
            ).scalar_one()
            count = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM alerts WHERE user_id = :uid "
                        "AND category = 'goals' AND subcategory = :gid"
                    ),
                    {"uid": user_id_a, "gid": str(goal_id)},
                )
            ).scalar_one()
            assert count == 1, f"Expected exactly 1 DB alert row for user, found {count}"

        # ── Step 5: Series with 20+ Entries + Outlier -> Trend Alert ────────
        # Populate 20 daily entries of steady study hours (value=10.00)
        for i in range(20):
            entry_date = today - timedelta(days=25 - i)
            res = await client.post(
                "/entries",
                json={
                    "category": "study",
                    "subcategory": "math",
                    "value": "10.00",
                    "occurred_at": entry_date.isoformat(),
                },
                headers=headers_a,
            )
            assert res.status_code == 201, res.text

        # Add 1 more entry with an outlier value clearly outside the confidence band
        outlier_date = today
        res = await client.post(
            "/entries",
            json={
                "category": "study",
                "subcategory": "math",
                "value": "1000.00",
                "occurred_at": outlier_date.isoformat(),
            },
            headers=headers_a,
        )
        assert res.status_code == 201, res.text

        # Call GET /alerts -> Trend alert should appear
        alerts_res_step5 = await client.get("/alerts", headers=headers_a)
        assert alerts_res_step5.status_code == 200, alerts_res_step5.text
        step5_data = alerts_res_step5.json()

        trend_alerts = [a for a in step5_data["items"] if a["kind"] == "trend"]
        assert len(trend_alerts) >= 1, "Expected trend alert for outlier entry"
        trend_alert = trend_alerts[0]
        assert trend_alert["category"] == "study"
        assert trend_alert["subcategory"] == "math"
        assert trend_alert["severity"] in ("warning", "risk")
        assert "deviates" in trend_alert["message"] or "outside" in trend_alert["message"]
        assert trend_alert["resolved_at"] is None

        # ── Step 6: Series with Only 5 Entries -> No Trend Alert Fabricated ─
        # Create a series with only 5 entries (insufficient data for statistical forecasting)
        for i in range(5):
            res = await client.post(
                "/entries",
                json={
                    "category": "fitness",
                    "subcategory": "running",
                    "value": "500.00",
                    "occurred_at": (today - timedelta(days=10 - i)).isoformat(),
                },
                headers=headers_a,
            )
            assert res.status_code == 201, res.text

        alerts_res_step6 = await client.get("/alerts", headers=headers_a)
        assert alerts_res_step6.status_code == 200
        step6_data = alerts_res_step6.json()

        fitness_trend_alerts = [
            a for a in step6_data["items"]
            if a["category"] == "fitness" and a["kind"] == "trend"
        ]
        assert len(fitness_trend_alerts) == 0, (
            "Trend alert fabricated for series with insufficient data (< 14 points)"
        )

        # ── Step 7: User B Cross-User Isolation ───────────────────────────
        alerts_res_user_b = await client.get("/alerts", headers=headers_b)
        assert alerts_res_user_b.status_code == 200, alerts_res_user_b.text
        b_data = alerts_res_user_b.json()
        assert b_data["total"] == 0
        assert b_data["items"] == []

        # ── Step 8: GET /alerts?status=all Includes Resolved Alerts ───────
        all_alerts_res = await client.get("/alerts?status=all", headers=headers_a)
        assert all_alerts_res.status_code == 200, all_alerts_res.text
        all_data = all_alerts_res.json()

        # The resolved threshold alert from Step 2 & 3 must be visible in history
        resolved_alerts = [
            a for a in all_data["items"]
            if a["id"] == alert_1_id
        ]
        assert len(resolved_alerts) == 1, "Resolved alert missing from status=all"
        assert resolved_alerts[0]["resolved_at"] is not None

        # ── Step 9: Internal Error Path -> Sanitized 500 (No str(exc) Leak) ─
        with patch("app.routers.alerts.compute_threshold_alerts", side_effect=RuntimeError("SensitiveDbSecret12345")):
            err_res = await client.get("/alerts", headers=headers_a)
            assert err_res.status_code == 500
            assert "SensitiveDbSecret12345" not in err_res.text
            assert err_res.json()["detail"] == "Unable to process alerts at this time"


@pytest.mark.asyncio
async def test_alerts_unauthenticated_and_validation():
    """Verify 401 when unauthenticated and 422 for invalid status parameter."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Unauthenticated request
        res = await client.get("/alerts")
        assert res.status_code == 401

        # Register user
        timestamp = int(time.time() * 1000)
        res_auth = await client.post(
            "/auth/register",
            json={"email": f"auth_val_{timestamp}@example.com", "password": "SecurePassword123!"},
        )
        token = res_auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Invalid status parameter
        res_invalid = await client.get("/alerts?status=invalid_status", headers=headers)
        assert res_invalid.status_code == 422


@pytest.mark.asyncio
async def test_threshold_alert_severity_bands_and_in_place_update():
    """
    Verify threshold severity band transitions:
    - -15 <= pace_gap < -5 -> warning
    - pace_gap < -15 -> risk
    - In-place update preserves id and triggered_at while mutating severity/message
    """
    timestamp = int(time.time() * 1000)
    email = f"bands_{timestamp}@example.com"
    password = "SecurePassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/auth/register", json={"email": email, "password": password})
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        today = date.today()
        # Total days: 20. Target: 100.
        goal_res = await client.post(
            "/goals",
            json={
                "name": "Save Money",
                "target_value": "100.00",
                "current_value": "40.00",
                "deadline": (today + timedelta(days=10)).isoformat(),
            },
            headers=headers,
        )
        goal_id = uuid.UUID(goal_res.json()["id"])

        # Age goal creation to 10 days ago (Total 20 days, Elapsed 10 days -> Expected = 50.0%)
        # Actual = 40.0% -> Pace gap = 40.0 - 50.0 = -10.0% (Warning band: -15 <= gap < -5)
        aged_date = datetime.now(timezone.utc) - timedelta(days=10)
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE goals SET created_at = :aged WHERE id = :gid"),
                {"aged": aged_date, "gid": goal_id},
            )

        # First check: expect warning
        res_warning = await client.get("/alerts", headers=headers)
        assert res_warning.status_code == 200
        items_w = res_warning.json()["items"]
        assert len(items_w) == 1
        assert items_w[0]["severity"] == "warning"
        orig_id = items_w[0]["id"]
        orig_triggered_at = items_w[0]["triggered_at"]

        # Escalate shortfall: drop progress to 20.00 (Actual = 20.0% -> Pace gap = 20.0 - 50.0 = -30.0% < -15.0%)
        update_res = await client.put(
            f"/goals/{goal_id}",
            json={"current_value": "20.00"},
            headers=headers,
        )
        assert update_res.status_code == 200

        # Second check: in-place escalation to risk
        res_risk = await client.get("/alerts", headers=headers)
        assert res_risk.status_code == 200
        items_r = res_risk.json()["items"]
        assert len(items_r) == 1
        assert items_r[0]["severity"] == "risk"
        # Must preserve original alert ID and triggered_at timestamp (update-in-place)
        assert items_r[0]["id"] == orig_id
        assert items_r[0]["triggered_at"] == orig_triggered_at


def test_alert_computation_pure_logic():
    """Unit test pure computation functions for threshold and trend logic."""
    from decimal import Decimal
    from app.models.entry import Entry
    from app.models.forecast import Forecast
    from app.models.goal import Goal
    from app.services.alerting import compute_threshold_alerts, compute_trend_alerts

    today = date.today()
    now_utc = datetime.now(timezone.utc)

    # 1. Goal with no deadline is skipped
    g_no_deadline = Goal(
        id=uuid.uuid4(),
        name="No Deadline Goal",
        target_value=Decimal("100.00"),
        current_value=Decimal("10.00"),
        deadline=None,
        created_at=now_utc - timedelta(days=10),
        deleted_at=None,
    )
    assert compute_threshold_alerts([g_no_deadline], current_date=today) == []

    # 2. Completed goal is skipped
    g_completed = Goal(
        id=uuid.uuid4(),
        name="Completed Goal",
        target_value=Decimal("100.00"),
        current_value=Decimal("100.00"),
        deadline=today + timedelta(days=5),
        created_at=now_utc - timedelta(days=10),
        deleted_at=None,
    )
    assert compute_threshold_alerts([g_completed], current_date=today) == []

    # 3. Forecast with insufficient reliability is skipped
    f_insufficient = Forecast(
        id=uuid.uuid4(),
        category="study",
        subcategory="physics",
        reliability="insufficient",
        forecast_points=[{"date": today.isoformat(), "lower": 10.0, "upper": 20.0, "predicted": 15.0}],
    )
    e_outlier = Entry(
        id=uuid.uuid4(),
        category="study",
        subcategory="physics",
        value=Decimal("999.00"),
        occurred_at=today,
        deleted_at=None,
    )
    res_insufficient = compute_trend_alerts([f_insufficient], {("study", "physics"): e_outlier})
    assert res_insufficient == []

    # 4. Forecast deviation <= 1.5x band -> warning, > 1.5x band -> risk
    f_reliable = Forecast(
        id=uuid.uuid4(),
        category="savings",
        subcategory="emergency",
        reliability="reliable",
        forecast_points=[{"date": today.isoformat(), "lower": 100.0, "upper": 200.0, "predicted": 150.0}],
    )
    # band_width = 100. 1.5 * band_width = 150. Upper limit for warning = 200 + 150 = 350.
    # Value 300 -> deviation = 100 <= 150 -> warning
    e_warn = Entry(
        id=uuid.uuid4(),
        category="savings",
        subcategory="emergency",
        value=Decimal("300.00"),
        occurred_at=today,
        deleted_at=None,
    )
    res_warn = compute_trend_alerts([f_reliable], {("savings", "emergency"): e_warn})
    assert len(res_warn) == 1
    assert res_warn[0].severity == "warning"

    # Value 400 -> deviation = 200 > 150 -> risk
    e_risk = Entry(
        id=uuid.uuid4(),
        category="savings",
        subcategory="emergency",
        value=Decimal("400.00"),
        occurred_at=today,
        deleted_at=None,
    )
    res_risk = compute_trend_alerts([f_reliable], {("savings", "emergency"): e_risk})
    assert len(res_risk) == 1
    assert res_risk[0].severity == "risk"


@pytest.mark.asyncio
async def test_baseline_alert_computation_pure_logic() -> None:
    """Test pure logic of profile baseline alerts (Decision A)."""
    from decimal import Decimal
    from app.models.profile import Profile
    from app.services.alerting import compute_baseline_alerts

    ref_date = date(2026, 9, 15)  # Tuesday, day 15 of 30 days in Sept (weekday=1 -> day 2 of 7)
    user_id = uuid.uuid4()

    # 1. Profile is None -> empty list
    assert compute_baseline_alerts(None, current_date=ref_date) == []

    # 2. Monthly spending cap (1000.00)
    p_spend = Profile(
        user_id=user_id,
        monthly_spending_cap=Decimal("1000.00"),
    )
    # Under 90%: no alert
    assert compute_baseline_alerts(p_spend, month_spending=Decimal("899.00"), current_date=ref_date) == []
    # 90% to <100%: warning
    alerts_warn = compute_baseline_alerts(p_spend, month_spending=Decimal("900.00"), current_date=ref_date)
    assert len(alerts_warn) == 1
    assert alerts_warn[0].severity == "warning"
    assert alerts_warn[0].category == "income_expense"
    assert alerts_warn[0].subcategory == "monthly_spending_cap"
    # >= 100%: risk
    alerts_risk = compute_baseline_alerts(p_spend, month_spending=Decimal("1050.00"), current_date=ref_date)
    assert len(alerts_risk) == 1
    assert alerts_risk[0].severity == "risk"

    # 3. Monthly savings target (1000.00)
    # On day 15 of 30, prorated target = 500.00
    # < 50% (< 250): risk. < 75% (< 375): warning. >= 375: ok.
    p_save = Profile(
        user_id=user_id,
        monthly_savings_target=Decimal("1000.00"),
    )
    assert compute_baseline_alerts(p_save, month_savings=Decimal("375.00"), current_date=ref_date) == []
    save_warn = compute_baseline_alerts(p_save, month_savings=Decimal("300.00"), current_date=ref_date)
    assert len(save_warn) == 1
    assert save_warn[0].severity == "warning"
    assert save_warn[0].category == "savings"
    save_risk = compute_baseline_alerts(p_save, month_savings=Decimal("200.00"), current_date=ref_date)
    assert len(save_risk) == 1
    assert save_risk[0].severity == "risk"

    # 4. Weekly study hours (14.0h target)
    # ref_date is Tuesday (weekday=1, days_elapsed=2). Prorated = 14 * 2 / 7 = 4.0h.
    # < 50% (< 2.0h): risk. < 75% (< 3.0h): warning. >= 3.0h: ok.
    p_study = Profile(
        user_id=user_id,
        weekly_study_hours=Decimal("14.00"),
    )
    assert compute_baseline_alerts(p_study, week_study_hours=Decimal("3.50"), current_date=ref_date) == []
    study_warn = compute_baseline_alerts(p_study, week_study_hours=Decimal("2.50"), current_date=ref_date)
    assert len(study_warn) == 1
    assert study_warn[0].severity == "warning"
    study_risk = compute_baseline_alerts(p_study, week_study_hours=Decimal("1.50"), current_date=ref_date)
    assert len(study_risk) == 1
    assert study_risk[0].severity == "risk"


@pytest.mark.asyncio
async def test_goal_collision_resolution_decision_b() -> None:
    """Verify that two goals with identical names do not collide in alert reconciliation (Decision B)."""
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    email = f"collision_test_{ts}@example.com"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg_res = await client.post("/auth/register", json={"email": email, "password": "SecurePassword123!"})
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        today = date.today()
        deadline = today + timedelta(days=5)

        # Create Goal 1 with name "Read 10 Books"
        g1_res = await client.post(
            "/goals",
            json={"name": "Read 10 Books", "target_value": "100.00", "current_value": "5.00", "deadline": deadline.isoformat()},
            headers=headers,
        )
        assert g1_res.status_code == 201
        g1_id = g1_res.json()["id"]

        # Create Goal 2 with EXACT SAME name "Read 10 Books"
        g2_res = await client.post(
            "/goals",
            json={"name": "Read 10 Books", "target_value": "200.00", "current_value": "10.00", "deadline": deadline.isoformat()},
            headers=headers,
        )
        assert g2_res.status_code == 201
        g2_id = g2_res.json()["id"]

        # Age both goals to 20 days ago
        aged = datetime.now(timezone.utc) - timedelta(days=20)
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE goals SET created_at = :aged WHERE id IN (:g1, :g2)"), {"aged": aged, "g1": g1_id, "g2": g2_id})

        # Query GET /alerts -> must return TWO distinct alerts, one for each goal id
        alerts_res = await client.get("/alerts", headers=headers)
        assert alerts_res.status_code == 200
        data = alerts_res.json()
        assert data["total"] == 2
        subcats = {a["subcategory"] for a in data["items"]}
        assert g1_id in subcats
        assert g2_id in subcats


@pytest.mark.asyncio
async def test_profile_baseline_alerts_integration() -> None:
    """Verify end-to-end profile baseline alerting through GET /alerts (Decision A)."""
    ts = int(datetime.now(timezone.utc).timestamp() * 1000)
    email = f"baseline_e2e_{ts}@example.com"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg_res = await client.post("/auth/register", json={"email": email, "password": "SecurePassword123!"})
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Set profile monthly spending cap to 1000.00
        profile_res = await client.put(
            "/profile",
            json={"monthly_spending_cap": "1000.00", "currency": "INR"},
            headers=headers,
        )
        assert profile_res.status_code == 200

        # Initially: no spending -> 0 alerts
        alerts_res1 = await client.get("/alerts", headers=headers)
        assert alerts_res1.status_code == 200
        assert alerts_res1.json()["total"] == 0

        # Add expense entry of 920.00 (92% of cap -> warning)
        today = date.today().isoformat()
        entry_res1 = await client.post(
            "/entries",
            json={
                "category": "income_expense",
                "subcategory": "Groceries",
                "value": "920.00",
                "unit": "INR",
                "occurred_at": today,
                "notes": "expense",
            },
            headers=headers,
        )
        assert entry_res1.status_code == 201

        alerts_res2 = await client.get("/alerts", headers=headers)
        assert alerts_res2.status_code == 200
        items2 = alerts_res2.json()["items"]
        assert len(items2) == 1
        assert items2[0]["category"] == "income_expense"
        assert items2[0]["subcategory"] == "monthly_spending_cap"
        assert items2[0]["severity"] == "warning"

        # Add second expense of 100.00 (total 1020.00 -> exceeds cap -> in-place risk)
        entry_res2 = await client.post(
            "/entries",
            json={
                "category": "income_expense",
                "subcategory": "Dining",
                "value": "100.00",
                "unit": "INR",
                "occurred_at": today,
                "notes": "expense",
            },
            headers=headers,
        )
        assert entry_res2.status_code == 201

        alerts_res3 = await client.get("/alerts", headers=headers)
        assert alerts_res3.status_code == 200
        items3 = alerts_res3.json()["items"]
        assert len(items3) == 1
        assert items3[0]["severity"] == "risk"
        assert items3[0]["id"] == items2[0]["id"]  # In-place update preserving row ID

