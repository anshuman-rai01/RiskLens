"""
Automated tests for Chunk 4 Goals CRUD:
- Step 1: Alembic migration creates goals table cleanly
- Step 2: Create goal with target_value=100 -> current_value=0, progress_percent=0.0, is_completed=false
- Step 3: Update current_value to 50 -> progress_percent=50.0, is_completed=false
- Step 4: Update current_value to 100 -> progress_percent=100.0, is_completed=true
- Step 5: Update current_value to 150 (overshoot) -> progress_percent capped at 100.0, is_completed=true
- Step 6: Attempt target_value=0 or negative -> 422 rejected
- Step 7: User B isolation -> 404 on User A's goal (GET, PUT, DELETE)
- Step 8: Soft-delete -> omitted from list & single GET, persists in DB with deleted_at
- Step 9: Sort order (near deadline before no deadline) & include_completed filter
- Step 10: Regression of previous chunks
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
import time
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.database import engine
from app.main import app
from app.models.goal import Goal


@pytest.mark.asyncio
async def test_goals_full_flow():
    timestamp = int(time.time() * 1000)
    user_a_email = f"goal_user_a_{timestamp}@example.com"
    user_b_email = f"goal_user_b_{timestamp}@example.com"
    password = "SecurePassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ── Auth Setup ───────────────────────────────────────────────────
        res_a = await client.post("/auth/register", json={"email": user_a_email, "password": password})
        assert res_a.status_code == 201, res_a.text
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        res_b = await client.post("/auth/register", json={"email": user_b_email, "password": password})
        assert res_b.status_code == 201, res_b.text
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # ── Step 2: Create goal with target_value=100 ─────────────────────
        today = date.today()
        target_deadline = today + timedelta(days=30)

        create_resp = await client.post(
            "/goals",
            json={
                "name": "Read 50 books",
                "target_value": "100.00",
                "unit": "chapters",
                "deadline": target_deadline.isoformat(),
            },
            headers=headers_a,
        )
        assert create_resp.status_code == 201, create_resp.text
        goal_data = create_resp.json()
        goal_id = goal_data["id"]

        assert goal_data["name"] == "Read 50 books"
        assert Decimal(str(goal_data["target_value"])) == Decimal("100.00")
        assert Decimal(str(goal_data["current_value"])) == Decimal("0.00")
        assert goal_data["progress_percent"] == 0.0
        assert goal_data["is_completed"] is False
        assert goal_data["unit"] == "chapters"
        assert goal_data["deadline"] == target_deadline.isoformat()
        assert "created_at" in goal_data
        assert "updated_at" in goal_data
        # Information hygiene check
        assert "user_id" not in goal_data
        assert "deleted_at" not in goal_data

        # Also test frontend alias "title" and "target"
        alias_resp = await client.post(
            "/goals",
            json={
                "title": "Save for emergency fund",
                "target": "50000.00",
                "unit": "INR",
            },
            headers=headers_a,
        )
        assert alias_resp.status_code == 201
        alias_goal = alias_resp.json()
        assert alias_goal["name"] == "Save for emergency fund"
        assert Decimal(str(alias_goal["target_value"])) == Decimal("50000.00")
        assert Decimal(str(alias_goal["current_value"])) == Decimal("0.00")

        # ── Step 3: Update current_value to 50 ────────────────────────────
        put_50 = await client.put(
            f"/goals/{goal_id}",
            json={"current_value": "50.00"},
            headers=headers_a,
        )
        assert put_50.status_code == 200, put_50.text
        data_50 = put_50.json()
        assert Decimal(str(data_50["current_value"])) == Decimal("50.00")
        assert data_50["progress_percent"] == 50.0
        assert data_50["is_completed"] is False

        # ── Step 4: Update current_value to 100 ───────────────────────────
        put_100 = await client.put(
            f"/goals/{goal_id}",
            json={"current_value": "100.00"},
            headers=headers_a,
        )
        assert put_100.status_code == 200, put_100.text
        data_100 = put_100.json()
        assert Decimal(str(data_100["current_value"])) == Decimal("100.00")
        assert data_100["progress_percent"] == 100.0
        assert data_100["is_completed"] is True

        # ── Step 5: Update current_value to 150 (overshoot) ───────────────
        put_150 = await client.put(
            f"/goals/{goal_id}",
            json={"current_value": "150.00"},
            headers=headers_a,
        )
        assert put_150.status_code == 200, put_150.text
        data_150 = put_150.json()
        assert Decimal(str(data_150["current_value"])) == Decimal("150.00")
        # progress_percent must be capped at 100.0, NOT 150.0
        assert data_150["progress_percent"] == 100.0
        assert data_150["is_completed"] is True

        # ── Step 6: Target value <= 0 rejected ────────────────────────────
        # target_value = 0
        zero_target = await client.post(
            "/goals",
            json={"name": "Zero Goal", "target_value": "0"},
            headers=headers_a,
        )
        assert zero_target.status_code == 422, "target_value=0 must be rejected"

        # target_value negative
        neg_target = await client.post(
            "/goals",
            json={"name": "Negative Goal", "target_value": "-10.00"},
            headers=headers_a,
        )
        assert neg_target.status_code == 422, "negative target_value must be rejected"

        # ── Part 0 Checks ────────────────────────────────────────────────
        # Check 1: No current/current_value supplied -> defaults to 0 (verified above in Step 2)
        assert Decimal(str(goal_data["current_value"])) == Decimal("0.00")
        assert goal_data["progress_percent"] == 0.0

        # Check 2: POST /goals with current: "23" (frontend field name)
        fe_curr_resp = await client.post(
            "/goals",
            json={"title": "Frontend Goal", "target": "50.00", "current": "23"},
            headers=headers_a,
        )
        assert fe_curr_resp.status_code == 201, fe_curr_resp.text
        fe_curr_data = fe_curr_resp.json()
        assert Decimal(str(fe_curr_data["current_value"])) == Decimal("23.00")
        assert fe_curr_data["progress_percent"] == 46.0
        assert fe_curr_data["is_completed"] is False

        # Check 3: POST /goals with current_value: "23" (backend field name)
        be_curr_resp = await client.post(
            "/goals",
            json={"name": "Backend Goal", "target_value": "50.00", "current_value": "23"},
            headers=headers_a,
        )
        assert be_curr_resp.status_code == 201, be_curr_resp.text
        be_curr_data = be_curr_resp.json()
        assert Decimal(str(be_curr_data["current_value"])) == Decimal("23.00")
        assert be_curr_data["progress_percent"] == 46.0

        # Check 4: POST /goals with negative current_value -> 422
        neg_curr_1 = await client.post(
            "/goals",
            json={"name": "Negative Current", "target_value": "100.00", "current": "-5.00"},
            headers=headers_a,
        )
        assert neg_curr_1.status_code == 422, "negative current must be rejected"

        neg_curr_2 = await client.post(
            "/goals",
            json={"name": "Negative Current", "target_value": "100.00", "current_value": "-5.00"},
            headers=headers_a,
        )
        assert neg_curr_2.status_code == 422, "negative current_value must be rejected"


        # ── Step 7: Cross-user isolation (User B cannot access User A's goal) ─
        get_b = await client.get(f"/goals/{goal_id}", headers=headers_b)
        assert get_b.status_code == 404, "User B must get 404 for User A's goal"
        assert get_b.json()["detail"] == "Goal not found"

        put_b = await client.put(
            f"/goals/{goal_id}",
            json={"current_value": "0.00"},
            headers=headers_b,
        )
        assert put_b.status_code == 404, "User B cannot edit User A's goal"

        del_b = await client.delete(f"/goals/{goal_id}", headers=headers_b)
        assert del_b.status_code == 404, "User B cannot delete User A's goal"

        list_b = await client.get("/goals", headers=headers_b)
        assert list_b.status_code == 200
        assert list_b.json()["total"] == 0
        assert len(list_b.json()["items"]) == 0

        # ── Step 8: Soft delete & DB persistence ─────────────────────────
        del_a = await client.delete(f"/goals/{goal_id}", headers=headers_a)
        assert del_a.status_code == 204

        # Disappears from single GET
        get_after_del = await client.get(f"/goals/{goal_id}", headers=headers_a)
        assert get_after_del.status_code == 404

        # Already deleted -> 404 on repeat delete
        del_repeat = await client.delete(f"/goals/{goal_id}", headers=headers_a)
        assert del_repeat.status_code == 404

        # Direct database query check: row persists with deleted_at set
        async with engine.connect() as conn:
            row = await conn.execute(
                select(Goal).where(Goal.id == uuid.UUID(goal_id))
            )
            db_goal = row.first()
            assert db_goal is not None, "Soft-deleted goal must persist in database"
            assert db_goal.deleted_at is not None, "deleted_at must be populated"

        # ── Step 9: Sort order & deadline handling ───────────────────────
        # Create Goal 1 with near deadline (5 days)
        near_deadline = today + timedelta(days=5)
        g_near_resp = await client.post(
            "/goals",
            json={"name": "Urgent Project", "target_value": "10.00", "deadline": near_deadline.isoformat()},
            headers=headers_a,
        )
        assert g_near_resp.status_code == 201
        g_near_id = g_near_resp.json()["id"]

        # Create Goal 2 with distant deadline (60 days)
        distant_deadline = today + timedelta(days=60)
        g_dist_resp = await client.post(
            "/goals",
            json={"name": "Distant Target", "target_value": "20.00", "deadline": distant_deadline.isoformat()},
            headers=headers_a,
        )
        assert g_dist_resp.status_code == 201
        g_dist_id = g_dist_resp.json()["id"]

        # Create Goal 3 with no deadline (open-ended)
        g_open_resp = await client.post(
            "/goals",
            json={"name": "Open Target", "target_value": "30.00"},
            headers=headers_a,
        )
        assert g_open_resp.status_code == 201
        g_open_id = g_open_resp.json()["id"]

        # Mark distant goal as completed (current_value = target_value)
        await client.put(f"/goals/{g_dist_id}", json={"current_value": "20.00"}, headers=headers_a)

        # Query all goals:
        # Expected sort:
        # Incomplete goals first: Urgent (deadline in 5d), then Open (null deadline last)
        # Completed goals last: Distant (completed, 100%)
        list_sorted = await client.get("/goals", headers=headers_a)
        assert list_sorted.status_code == 200
        items = list_sorted.json()["items"]
        item_ids = [item["id"] for item in items]

        # Verify urgent goal appears before open goal
        assert item_ids.index(g_near_id) < item_ids.index(g_open_id), "Urgent deadline must precede open deadline"
        # Verify incomplete goals appear before completed goals
        assert item_ids.index(g_open_id) < item_ids.index(g_dist_id), "Incomplete goals must precede completed goals"

        # Query with include_completed=false
        list_incomplete_only = await client.get("/goals?include_completed=false", headers=headers_a)
        assert list_incomplete_only.status_code == 200
        incomplete_ids = [item["id"] for item in list_incomplete_only.json()["items"]]
        assert g_near_id in incomplete_ids
        assert g_open_id in incomplete_ids
        assert g_dist_id not in incomplete_ids, "Completed goals must be filtered out when include_completed=false"


if __name__ == "__main__":
    asyncio.run(test_goals_full_flow())
    print("All goals tests passed!")
