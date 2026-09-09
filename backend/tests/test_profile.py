"""
Automated tests for User Profile and baseline limit endpoints:
- GET /profile returns default profile for new user
- PUT /profile updates baseline limits and onboarding state
- User isolation: User B cannot access or see User A's profile
- Validation: Negative numeric limits rejected with 422
- Authentication: 401 when unauthenticated
"""

from __future__ import annotations

from decimal import Decimal
import time

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_profile_full_flow():
    timestamp = int(time.time() * 1000)
    user_a_email = f"profile_user_a_{timestamp}@example.com"
    user_b_email = f"profile_user_b_{timestamp}@example.com"
    password = "SecurePassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated request -> 401
        res_unauth = await client.get("/profile")
        assert res_unauth.status_code == 401

        # Register User A and User B
        res_a = await client.post("/auth/register", json={"email": user_a_email, "password": password})
        assert res_a.status_code == 201
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        res_b = await client.post("/auth/register", json={"email": user_b_email, "password": password})
        assert res_b.status_code == 201
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. GET /profile for User A -> Default Profile
        res_p1 = await client.get("/profile", headers=headers_a)
        assert res_p1.status_code == 200, res_p1.text
        p1 = res_p1.json()
        assert p1["name"] == ""
        assert p1["role"] == "student"
        assert p1["currency"] == "INR"
        assert p1["onboarded"] is False
        assert p1["monthly_spending_cap"] is None

        # 3. PUT /profile for User A -> Update fields
        update_payload = {
            "name": "Jane Doe",
            "age": 26,
            "role": "professional",
            "monthly_spending_cap": "45000.00",
            "monthly_savings_target": "15000.00",
            "weekly_study_hours": "10.5",
            "weekly_fitness_minutes": 180,
            "weekly_habit_completions": 5,
            "onboarded": True,
        }
        res_update = await client.put("/profile", json=update_payload, headers=headers_a)
        assert res_update.status_code == 200, res_update.text
        updated = res_update.json()
        assert updated["name"] == "Jane Doe"
        assert updated["age"] == 26
        assert updated["role"] == "professional"
        assert Decimal(str(updated["monthly_spending_cap"])) == Decimal("45000.00")
        assert Decimal(str(updated["monthly_savings_target"])) == Decimal("15000.00")
        assert Decimal(str(updated["weekly_study_hours"])) == Decimal("10.50")
        assert updated["weekly_fitness_minutes"] == 180
        assert updated["weekly_habit_completions"] == 5
        assert updated["onboarded"] is True

        # 4. GET /profile for User B -> Cross-user isolation (User B still has default)
        res_b_prof = await client.get("/profile", headers=headers_b)
        assert res_b_prof.status_code == 200
        p_b = res_b_prof.json()
        assert p_b["name"] == ""
        assert p_b["role"] == "student"
        assert p_b["onboarded"] is False
        assert p_b["monthly_spending_cap"] is None

        # 5. Validation error: Negative cap rejected with 422
        res_neg = await client.put(
            "/profile",
            json={"monthly_spending_cap": "-500.00"},
            headers=headers_a,
        )
        assert res_neg.status_code == 422
