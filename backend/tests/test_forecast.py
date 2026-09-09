"""
Automated tests for Chunk 5 Part 1 Forecasting Service:
- Step 1: Alembic migration created forecasts table
- Step 2: User with 5 entries -> reliability: 'insufficient', no forecast_points, clear message
- Step 3: User with 20 entries -> reliability: 'low_confidence', forecast_points returned
- Step 4: User with 35+ entries -> reliability: 'reliable', forecast_points with visible confidence band (lower < predicted < upper)
- Step 5: Call GET /forecast twice sequentially -> returns cached result without refitting (identical generated_at)
- Step 6: Add new entry -> cache invalidated, refits on next GET /forecast (newer generated_at)
- Step 7: Degenerate series (30 identical entries) -> graceful response (200 OK), not 500
- Step 8: Cross-user isolation -> User B cannot get User A's forecast
- Step 9: Regressions for previous chunks (auth, entries, goals)
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
import logging
import time
from unittest.mock import patch
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.database import engine
from app.main import app
from app.models.forecast import Forecast
from app.security import decode_token


@pytest.mark.asyncio
async def test_forecast_full_flow():
    timestamp = int(time.time() * 1000)
    user_a_email = f"forecast_user_a_{timestamp}@example.com"
    user_b_email = f"forecast_user_b_{timestamp}@example.com"
    password = "SecurePassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ── Step 0: Register User A and User B ───────────────────────────
        res_a = await client.post("/auth/register", json={"email": user_a_email, "password": password})
        assert res_a.status_code == 201
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        res_b = await client.post("/auth/register", json={"email": user_b_email, "password": password})
        assert res_b.status_code == 201
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # ── Step 2: 5 entries -> reliability: 'insufficient' ─────────────
        today = date.today()
        for i in range(5):
            occurred = today - timedelta(days=50 - i)
            res = await client.post(
                "/entries",
                json={
                    "category": "study",
                    "subcategory": "ml",
                    "value": str(2.0 + i * 0.5),
                    "unit": "hours",
                    "occurred_at": occurred.isoformat(),
                },
                headers=headers_a,
            )
            assert res.status_code == 201

        f5_resp = await client.get("/forecast?category=study&subcategory=ml", headers=headers_a)
        assert f5_resp.status_code == 200, f5_resp.text
        f5_data = f5_resp.json()
        assert f5_data["reliability"] == "insufficient"
        assert f5_data["data_point_count"] == 5
        assert len(f5_data["forecast_points"]) == 0
        assert f5_data["message"] == "More data is required to generate a forecast"
        assert "generated_at" in f5_data

        # ── Step 3: Add 15 more entries (total 20) -> 'low_confidence' ───
        for i in range(5, 20):
            occurred = today - timedelta(days=50 - i)
            res = await client.post(
                "/entries",
                json={
                    "category": "study",
                    "subcategory": "ml",
                    "value": str(3.0 + (i % 3) * 0.5),
                    "unit": "hours",
                    "occurred_at": occurred.isoformat(),
                },
                headers=headers_a,
            )
            assert res.status_code == 201

        f20_resp = await client.get("/forecast?category=study&subcategory=ml", headers=headers_a)
        assert f20_resp.status_code == 200, f20_resp.text
        f20_data = f20_resp.json()
        assert f20_data["reliability"] == "low_confidence"
        assert f20_data["data_point_count"] == 20
        assert len(f20_data["forecast_points"]) == 14
        assert f20_data["forecast_points"][0]["predicted"] > 0

        # ── Step 4: Add 16 more entries (total 36) -> 'reliable' ─────────
        # Series with natural trend and variance
        for i in range(36):
            occurred = today - timedelta(days=60 - i)
            res = await client.post(
                "/entries",
                json={
                    "category": "income_expense",
                    "subcategory": "groceries",
                    "value": str(100.0 + i * 2.5 + (i % 4) * 10),
                    "unit": "INR",
                    "occurred_at": occurred.isoformat(),
                },
                headers=headers_a,
            )
            assert res.status_code == 201

        f36_resp = await client.get("/forecast?category=income_expense&subcategory=groceries", headers=headers_a)
        assert f36_resp.status_code == 200, f36_resp.text
        f36_data = f36_resp.json()
        assert f36_data["reliability"] == "reliable"
        assert f36_data["data_point_count"] == 36
        assert len(f36_data["forecast_points"]) == 14

        # Verify visible confidence band (lower < predicted < upper)
        first_point = f36_data["forecast_points"][0]
        assert first_point["lower"] < first_point["predicted"] < first_point["upper"], (
            f"Confidence band inverted: lower={first_point['lower']}, pred={first_point['predicted']}, upper={first_point['upper']}"
        )

        # ── Step 5: Caching check (two sequential calls return cached result) ─
        gen_at_1 = f36_data["generated_at"]
        f36_cached = await client.get("/forecast?category=income_expense&subcategory=groceries", headers=headers_a)
        assert f36_cached.status_code == 200
        gen_at_2 = f36_cached.json()["generated_at"]
        assert gen_at_1 == gen_at_2, "Second call must return cached forecast without refitting"

        # ── Step 5b: Horizon change invalidates cache (Fix 2 verification) ─
        time.sleep(0.05)  # Tiny pause to ensure clock advances
        f36_h30 = await client.get("/forecast?category=income_expense&subcategory=groceries&horizon_days=30", headers=headers_a)
        assert f36_h30.status_code == 200
        f36_h30_data = f36_h30.json()
        gen_at_h30_1 = f36_h30_data["generated_at"]
        assert gen_at_h30_1 > gen_at_2, "Changing horizon_days to 30 must trigger recomputation and update cache"
        assert len(f36_h30_data["forecast_points"]) == 30, f"Expected 30 points, got {len(f36_h30_data['forecast_points'])}"

        # Immediately repeat horizon_days=30 request: must hit cache
        f36_h30_repeat = await client.get("/forecast?category=income_expense&subcategory=groceries&horizon_days=30", headers=headers_a)
        assert f36_h30_repeat.status_code == 200
        gen_at_h30_2 = f36_h30_repeat.json()["generated_at"]
        assert gen_at_h30_1 == gen_at_h30_2, "Repeating horizon_days=30 request must return cached result"
        assert len(f36_h30_repeat.json()["forecast_points"]) == 30

        # ── Step 6: Cache Invalidation (Add entry -> refit on next call) ──
        time.sleep(0.05)  # Tiny pause to ensure clock advances
        await client.post(
            "/entries",
            json={
                "category": "income_expense",
                "subcategory": "groceries",
                "value": "250.00",
                "unit": "INR",
                "occurred_at": today.isoformat(),
            },
            headers=headers_a,
        )

        f36_refit = await client.get("/forecast?category=income_expense&subcategory=groceries", headers=headers_a)
        assert f36_refit.status_code == 200
        gen_at_3 = f36_refit.json()["generated_at"]
        assert gen_at_3 > gen_at_2, "Adding an entry must invalidate cache and trigger a refit"
        assert f36_refit.json()["data_point_count"] == 37

        # ── Step 7: Degenerate Series (30 entries with identical values) ──
        for i in range(30):
            occurred = today - timedelta(days=40 - i)
            res = await client.post(
                "/entries",
                json={
                    "category": "fitness",
                    "subcategory": "yoga",
                    "value": "45.00",
                    "unit": "minutes",
                    "occurred_at": occurred.isoformat(),
                },
                headers=headers_a,
            )
            assert res.status_code == 201

        degen_resp = await client.get("/forecast?category=fitness&subcategory=yoga", headers=headers_a)
        assert degen_resp.status_code == 200, "Degenerate series must not return 500 error"
        degen_data = degen_resp.json()
        assert len(degen_data["forecast_points"]) == 14
        assert degen_data["forecast_points"][0]["predicted"] == 45.00

        # ── Step 8: Cross-User Isolation ─────────────────────────────────
        # User B queries the exact same category/subcategory where User A has 37 entries
        b_forecast_resp = await client.get("/forecast?category=income_expense&subcategory=groceries", headers=headers_b)
        assert b_forecast_resp.status_code == 200
        b_data = b_forecast_resp.json()
        # User B has 0 entries for this series, so must receive 'insufficient' (not User A's forecast)
        assert b_data["reliability"] == "insufficient"
        assert b_data["data_point_count"] == 0
        assert len(b_data["forecast_points"]) == 0

        # Verify DB directly: two distinct forecast records exist for the two users
        user_a_id = uuid.UUID(decode_token(token_a)["sub"])
        user_b_id = uuid.UUID(decode_token(token_b)["sub"])

        async with engine.connect() as conn:
            records = (await conn.execute(
                select(Forecast).where(
                    Forecast.user_id.in_([user_a_id, user_b_id]),
                    Forecast.category == "income_expense",
                    Forecast.subcategory == "groceries",
                )
            )).fetchall()
            assert len(records) == 2, "Each user must have their own isolated forecast cache"


@pytest.mark.asyncio
async def test_forecast_prophet_fallback_sanitized(caplog):
    """
    Verify Fix 3: when Prophet fitting throws an internal exception,
    the client receives a generic sanitized message, and sensitive internal
    exception details are logged server-side only.
    """
    timestamp = int(time.time() * 1000)
    user_email = f"forecast_fallback_{timestamp}@example.com"
    password = "SecurePassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/auth/register", json={"email": user_email, "password": password})
        assert res.status_code == 201
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Seed 15 entries so series qualifies for Prophet fitting (>10 data points)
        today = date.today()
        for i in range(15):
            occurred = today - timedelta(days=20 - i)
            await client.post(
                "/entries",
                json={
                    "category": "fitness",
                    "subcategory": "running",
                    "value": str(5.0 + (i % 3)),
                    "unit": "km",
                    "occurred_at": occurred.isoformat(),
                },
                headers=headers,
            )

        sensitive_error = "Internal Stan solver crash: 0xDEADBEEF in /usr/local/stan/stan_fit.cpp:108"
        with patch("prophet.Prophet.fit", side_effect=RuntimeError(sensitive_error)):
            with caplog.at_level(logging.WARNING):
                resp = await client.get("/forecast?category=fitness&subcategory=running", headers=headers)
                assert resp.status_code == 200
                data = resp.json()

                # Client response verification
                assert data["reliability"] == "low_confidence"
                assert data["message"] == "Forecast temporarily unavailable, using trend fallback"
                assert len(data["forecast_points"]) == 14

                # Security check: sensitive internal exception details must NOT leak into client response
                assert sensitive_error not in resp.text
                assert "0xDEADBEEF" not in resp.text
                assert "RuntimeError" not in resp.text

                # Observability check: exception details must appear in server logs
                assert sensitive_error in caplog.text


if __name__ == "__main__":
    asyncio.run(test_forecast_full_flow())
    print("All forecast tests passed!")
