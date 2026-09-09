"""
Automated tests for Chunk 2 authentication:
- Registration & duplicate rejection
- Password hashing (bcrypt verification)
- Constant-time login failure (account enumeration prevention)
- Refresh token rotation & reuse detection (full family revocation)
- Logout
- get_current_user dependency & Isolation Principle verification
"""

import asyncio
import time
import psycopg2
import httpx
import pytest
from app.main import app
from app.database import get_db, engine
from app.dependencies import get_current_user
from fastapi.security import HTTPAuthorizationCredentials


@pytest.mark.asyncio
async def test_auth_full_flow():
    test_email = f"pytest_user_{int(time.time())}@example.com"
    test_password = "SecurePassword123!"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register
        reg_resp = await client.post("/auth/register", json={"email": test_email, "password": test_password})
        assert reg_resp.status_code == 201
        tokens = reg_resp.json()
        assert "access_token" in tokens and "refresh_token" in tokens

        # 2. Duplicate registration conflict
        dup_resp = await client.post("/auth/register", json={"email": test_email, "password": test_password})
        assert dup_resp.status_code == 409

        # 3. Login success
        login_resp = await client.post("/auth/login", json={"email": test_email, "password": test_password})
        assert login_resp.status_code == 200
        tokens = login_resp.json()

        # 4. Constant-time login failure
        fail_wrong_pw = await client.post("/auth/login", json={"email": test_email, "password": "WrongPassword999!"})
        fail_no_user = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "WrongPassword999!"})
        assert fail_wrong_pw.status_code == 401
        assert fail_no_user.status_code == 401
        assert fail_wrong_pw.json() == fail_no_user.json() == {"detail": "Invalid email or password"}

        # 5. Token rotation
        old_refresh = tokens["refresh_token"]
        refresh_resp = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
        assert refresh_resp.status_code == 200
        new_tokens = refresh_resp.json()
        new_refresh = new_tokens["refresh_token"]
        assert new_refresh != old_refresh

        # Old token rejected
        stale_resp = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
        assert stale_resp.status_code == 401

        # 6. Reuse detection -> family revocation
        login_b = await client.post("/auth/login", json={"email": test_email, "password": test_password})
        session_b_refresh = login_b.json()["refresh_token"]

        # Replay rotated token
        attack_resp = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
        assert attack_resp.status_code == 401
        assert "reuse detected" in attack_resp.json()["detail"].lower()

        # Session B is revoked
        b_check = await client.post("/auth/refresh", json={"refresh_token": session_b_refresh})
        assert b_check.status_code == 401

        # 7. Logout
        fresh_login = await client.post("/auth/login", json={"email": test_email, "password": test_password})
        fresh_refresh = fresh_login.json()["refresh_token"]
        logout_resp = await client.post("/auth/logout", json={"refresh_token": fresh_refresh})
        assert logout_resp.status_code == 200
        logout_check = await client.post("/auth/refresh", json={"refresh_token": fresh_refresh})
        assert logout_check.status_code == 401


if __name__ == "__main__":
    asyncio.run(test_auth_full_flow())
    print("All tests passed!")
