"""
Automated tests for Chunk 3 Entries CRUD:
- User isolation: User B cannot list, retrieve, modify, or delete User A's entries
- Category immutability on update (subcategory is editable; see test_entry_label_and_max_value_editable)
- Soft delete: hidden from API, but row persists in DB with deleted_at timestamp
- Filtering & pagination: category, subcategory, date range (from/to), limit/offset
- Validations: valid categories, future-date cutoff (> today + 1 day), non-finite numbers
- Regression: health and auth endpoints continue to function
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
from app.models.entry import Entry


@pytest.mark.asyncio
async def test_entries_full_flow():
    timestamp = int(time.time() * 1000)
    user_a_email = f"user_a_{timestamp}@example.com"
    user_b_email = f"user_b_{timestamp}@example.com"
    password = "SecurePassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ── Step 0: Register User A and User B ───────────────────────────
        res_a = await client.post("/auth/register", json={"email": user_a_email, "password": password})
        assert res_a.status_code == 201, res_a.text
        token_a = res_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        res_b = await client.post("/auth/register", json={"email": user_b_email, "password": password})
        assert res_b.status_code == 201, res_b.text
        token_b = res_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # ── Step 1: User A creates 3 entries across multiple categories ──
        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        payload_1 = {
            "category": "income_expense",
            "subcategory": "freelance",
            "value": "15000",
            "unit": "INR",
            "occurred_at": today.isoformat(),
            "notes": "Backend milestone payment",
        }
        resp_1 = await client.post("/entries", json=payload_1, headers=headers_a)
        assert resp_1.status_code == 201, resp_1.text
        entry_1 = resp_1.json()
        assert entry_1["category"] == "income_expense"
        assert entry_1["subcategory"] == "freelance"
        assert Decimal(str(entry_1["value"])) == Decimal("15000")
        assert entry_1["unit"] == "INR"
        assert entry_1["occurred_at"] == today.isoformat()
        assert entry_1["notes"] == "Backend milestone payment"
        assert "id" in entry_1
        assert "created_at" in entry_1
        assert "updated_at" in entry_1
        # Crucial security check: internal user_id and deleted_at must NEVER leak
        assert "user_id" not in entry_1
        assert "deleted_at" not in entry_1

        payload_2 = {
            "category": "study",
            "subcategory": "distributed_systems",
            "value": "3.5",
            "unit": "hours",
            "occurred_at": yesterday.isoformat(),
            "notes": "Read Raft consensus paper",
        }
        resp_2 = await client.post("/entries", json=payload_2, headers=headers_a)
        assert resp_2.status_code == 201, resp_2.text
        entry_2 = resp_2.json()

        payload_3 = {
            "category": "habits",
            "subcategory": "morning_run",
            "value": "1.0",
            "unit": "count",
            "occurred_at": two_days_ago.isoformat(),
            "notes": "5km run completed",
        }
        resp_3 = await client.post("/entries", json=payload_3, headers=headers_a)
        assert resp_3.status_code == 201, resp_3.text
        entry_3 = resp_3.json()

        # ── Step 2: Isolation Test — User B sees none of User A's entries ─
        list_b = await client.get("/entries", headers=headers_b)
        assert list_b.status_code == 200
        data_b = list_b.json()
        assert data_b["total"] == 0
        assert len(data_b["items"]) == 0

        # User B cannot access User A's entry by ID (must return 404, not 403)
        get_b = await client.get(f"/entries/{entry_1['id']}", headers=headers_b)
        assert get_b.status_code == 404
        assert get_b.json()["detail"] == "Entry not found"

        # User B cannot modify or delete User A's entry
        put_b = await client.put(
            f"/entries/{entry_1['id']}",
            json={"value": "99999.00"},
            headers=headers_b,
        )
        assert put_b.status_code == 404

        del_b = await client.delete(f"/entries/{entry_1['id']}", headers=headers_b)
        assert del_b.status_code == 404

        # ── Step 3: Filtering & Pagination for User A ────────────────────
        # All 3 entries
        list_a = await client.get("/entries", headers=headers_a)
        assert list_a.status_code == 200
        assert list_a.json()["total"] == 3
        assert len(list_a.json()["items"]) == 3

        # Filter by category
        filter_cat = await client.get("/entries?category=study", headers=headers_a)
        assert filter_cat.status_code == 200
        assert filter_cat.json()["total"] == 1
        assert filter_cat.json()["items"][0]["id"] == entry_2["id"]

        # Filter by subcategory
        filter_sub = await client.get("/entries?subcategory=freelance", headers=headers_a)
        assert filter_sub.status_code == 200
        assert filter_sub.json()["total"] == 1
        assert filter_sub.json()["items"][0]["id"] == entry_1["id"]

        # Filter by date range (yesterday to today)
        filter_date = await client.get(
            f"/entries?from={yesterday.isoformat()}&to={today.isoformat()}",
            headers=headers_a,
        )
        assert filter_date.status_code == 200
        assert filter_date.json()["total"] == 2

        # Pagination
        paged = await client.get("/entries?limit=1&offset=1", headers=headers_a)
        assert paged.status_code == 200
        assert len(paged.json()["items"]) == 1
        assert paged.json()["total"] == 3

        # ── Step 4: Category Immutability on Update ──────────────────────
        # Attempting to change category must be rejected with 422
        bad_put_cat = await client.put(
            f"/entries/{entry_1['id']}",
            json={"category": "fitness"},
            headers=headers_a,
        )
        assert bad_put_cat.status_code == 422, "Updating category must be rejected"

        # Subcategory is the user-facing label and IS editable (covered in
        # test_entry_label_and_max_value_editable, kept separate so this flow's
        # later steps can keep relying on entry_1's original subcategory).

        # Valid update: update value and notes
        time.sleep(0.01)  # tiny pause to ensure timestamp advances
        valid_put = await client.put(
            f"/entries/{entry_1['id']}",
            json={"value": "17500.00", "notes": "Updated freelance amount"},
            headers=headers_a,
        )
        assert valid_put.status_code == 200
        updated_entry = valid_put.json()
        assert Decimal(str(updated_entry["value"])) == Decimal("17500.00")
        assert updated_entry["notes"] == "Updated freelance amount"
        assert updated_entry["updated_at"] >= entry_1["updated_at"]

        # ── Step 5: Soft Delete ──────────────────────────────────────────
        del_resp = await client.delete(f"/entries/{entry_2['id']}", headers=headers_a)
        assert del_resp.status_code == 204

        # Entry 2 is now hidden from API read
        get_del = await client.get(f"/entries/{entry_2['id']}", headers=headers_a)
        assert get_del.status_code == 404

        # Entry 2 is excluded from list
        list_after_del = await client.get("/entries", headers=headers_a)
        assert list_after_del.json()["total"] == 2
        retrieved_ids = [item["id"] for item in list_after_del.json()["items"]]
        assert entry_2["id"] not in retrieved_ids

        # Attempting to delete again returns 404
        del_again = await client.delete(f"/entries/{entry_2['id']}", headers=headers_a)
        assert del_again.status_code == 404

        # Verify DB directly: the row still exists in PostgreSQL with deleted_at set
        async with engine.connect() as conn:
            row = await conn.execute(
                select(Entry).where(Entry.id == uuid.UUID(entry_2["id"]))
            )
            db_entry = row.first()
            assert db_entry is not None, "Soft-deleted row must persist in database"
            # deleted_at column is present and not null
            assert db_entry.deleted_at is not None, "deleted_at must be populated in database"

        # ── Step 6: Validations ──────────────────────────────────────────
        # Invalid category (e.g. 'goals' is excluded from this chunk, or bogus string)
        bad_cat_1 = await client.post(
            "/entries",
            json={
                "category": "goals",
                "value": "100.0",
                "occurred_at": today.isoformat(),
            },
            headers=headers_a,
        )
        assert bad_cat_1.status_code == 422

        bad_cat_2 = await client.post(
            "/entries",
            json={
                "category": "invalid_category_xyz",
                "value": "100.0",
                "occurred_at": today.isoformat(),
            },
            headers=headers_a,
        )
        assert bad_cat_2.status_code == 422

        # Future-dated occurred_at:
        # Today + 1 day is permitted (timezone edge cases)
        tomorrow = today + timedelta(days=1)
        valid_future = await client.post(
            "/entries",
            json={
                "category": "fitness",
                "subcategory": "yoga",
                "value": "45",
                "unit": "minutes",
                "occurred_at": tomorrow.isoformat(),
            },
            headers=headers_a,
        )
        assert valid_future.status_code == 201, "Tomorrow (today + 1d) must be tolerated"

        # Far future (today + 2 days or more) must be rejected with 422
        far_future = today + timedelta(days=2)
        invalid_future = await client.post(
            "/entries",
            json={
                "category": "fitness",
                "subcategory": "yoga",
                "value": "45",
                "unit": "minutes",
                "occurred_at": far_future.isoformat(),
            },
            headers=headers_a,
        )
        assert invalid_future.status_code == 422, "Dates beyond today + 1 day must be rejected"

        # Non-finite / overflow number
        invalid_num = await client.post(
            "/entries",
            json={
                "category": "fitness",
                "value": "1e999",
                "occurred_at": today.isoformat(),
            },
            headers=headers_a,
        )
        assert invalid_num.status_code == 422

        # ── Step 7: Regression Test (Chunks 1 & 2) ────────────────────────
        # Health check
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["status"] == "ok"
        assert health_data["db"] == "connected"

        # Auth login & refresh
        login_resp = await client.post(
            "/auth/login",
            json={"email": user_a_email, "password": password},
        )
        assert login_resp.status_code == 200
        ref_tok = login_resp.json()["refresh_token"]

        rotate_resp = await client.post("/auth/refresh", json={"refresh_token": ref_tok})
        assert rotate_resp.status_code == 200
        assert "access_token" in rotate_resp.json()


if __name__ == "__main__":
    asyncio.run(test_entries_full_flow())
    print("All entries tests passed!")


@pytest.mark.asyncio
async def test_entry_label_and_max_value_editable():
    """
    Regression for "fields can't be updated on edit":
    - subcategory (the label: description / vault / course / activity / habit) is editable
    - notes (structured field for several categories) is editable
    - max_value (maximum marks) round-trips on create and update, with no upper bound
    - category is still immutable
    - editing a label drops the OLD series' cached forecast (otherwise it looks fresh
      while still containing the moved point)
    """
    from app.models.forecast import Forecast  # local import: only this test needs it

    ts = int(time.time() * 1000)
    password = "SecurePassword123!"
    today = date.today()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/auth/register", json={"email": f"edit_{ts}@example.com", "password": password})
        assert res.status_code == 201, res.text
        headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

        # ── subcategory + notes editable ─────────────────────────────────
        created = await client.post(
            "/entries",
            json={
                "category": "fitness",
                "subcategory": "Running",
                "value": "30",
                "unit": "minutes",
                "occurred_at": today.isoformat(),
                "notes": "moderate",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        entry = created.json()
        assert entry["max_value"] is None

        edited = await client.put(
            f"/entries/{entry['id']}",
            json={"subcategory": "  Yoga  ", "notes": "low"},
            headers=headers,
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["subcategory"] == "Yoga"  # trimmed
        assert edited.json()["notes"] == "low"
        assert edited.json()["category"] == "fitness"

        # category is still immutable
        bad = await client.put(f"/entries/{entry['id']}", json={"category": "study"}, headers=headers)
        assert bad.status_code == 422

        # ── max_value: round-trip, large values allowed, invalid rejected ─
        acad = await client.post(
            "/entries",
            json={
                "category": "academic",
                "subcategory": "ML Algorithms",
                "value": "42",
                "unit": "score",
                "max_value": "50",
                "occurred_at": today.isoformat(),
                "notes": "Midterm",
            },
            headers=headers,
        )
        assert acad.status_code == 201, acad.text
        assert Decimal(str(acad.json()["max_value"])) == Decimal("50")

        bumped = await client.put(
            f"/entries/{acad.json()['id']}",
            json={"value": "480", "max_value": "500", "subcategory": "ML Algorithms II", "notes": "Final"},
            headers=headers,
        )
        assert bumped.status_code == 200, bumped.text
        body = bumped.json()
        assert Decimal(str(body["max_value"])) == Decimal("500"), "maximum marks must not be capped at 100"
        assert body["subcategory"] == "ML Algorithms II" and body["notes"] == "Final"

        for bad_max in ("0", "-5"):
            r = await client.put(f"/entries/{acad.json()['id']}", json={"max_value": bad_max}, headers=headers)
            assert r.status_code == 422, f"max_value={bad_max} must be rejected"

        # ── moving an entry out of a series drops that series' cached forecast ─
        user_id = (await client.get("/profile", headers=headers)).json()["user_id"]
        async with engine.connect() as conn:
            await conn.execute(
                Forecast.__table__.insert().values(
                    id=uuid.uuid4(),
                    user_id=uuid.UUID(user_id),
                    category="habits",
                    subcategory="Meditate",
                    generated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                    horizon_days=14,
                    forecast_points=[],
                    data_point_count=3,
                    reliability="insufficient",
                )
            )
            await conn.commit()

        habit = await client.post(
            "/entries",
            json={"category": "habits", "subcategory": "Meditate", "value": "1", "unit": "count",
                  "occurred_at": today.isoformat()},
            headers=headers,
        )
        assert habit.status_code == 201, habit.text

        async def cached_series() -> list[str | None]:
            async with engine.connect() as conn:
                rows = await conn.execute(
                    select(Forecast.subcategory).where(
                        Forecast.user_id == uuid.UUID(user_id), Forecast.category == "habits"
                    )
                )
                return [r[0] for r in rows]

        assert await cached_series() == ["Meditate"]

        # Same label re-saved: nothing moves, cache must survive
        same = await client.put(f"/entries/{habit.json()['id']}", json={"subcategory": "Meditate"}, headers=headers)
        assert same.status_code == 200
        assert await cached_series() == ["Meditate"]

        # Renamed: old series cache is dropped
        moved = await client.put(f"/entries/{habit.json()['id']}", json={"subcategory": "Meditate 10m"}, headers=headers)
        assert moved.status_code == 200
        assert await cached_series() == []
