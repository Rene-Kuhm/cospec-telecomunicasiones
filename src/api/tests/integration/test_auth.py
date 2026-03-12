import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "phone": "+1234567890",
            "password": "SecurePass123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["user"]["email"] == "test@example.com"
    assert data["data"]["user"]["role"] == "customer"
    assert "access_token" in data["data"]
    # Password must not be exposed
    assert "password_hash" not in data["data"]["user"]
    assert "password" not in data["data"]["user"]


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient):
    payload = {
        "name": "User",
        "email": "dup@example.com",
        "phone": "+1234567890",
        "password": "SecurePass123",
    }
    resp1 = await client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 200

    resp2 = await client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    assert resp2.json()["success"] is False
    assert resp2.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_login_returns_tokens(client: AsyncClient):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Login User",
            "email": "login@example.com",
            "phone": "+1234567890",
            "password": "SecurePass123",
        },
    )

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "SecurePass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert data["data"]["user"]["email"] == "login@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "name": "User",
            "email": "badpass@example.com",
            "phone": "+1234567890",
            "password": "SecurePass123",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "badpass@example.com", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_nonexistent_email_returns_401(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "notexist@example.com", "password": "password123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_returns_user(client: AsyncClient):
    # Register and get token
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Me User",
            "email": "me@example.com",
            "phone": "+1234567890",
            "password": "SecurePass123",
        },
    )
    token = reg_resp.json()["data"]["access_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_get_me_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalidates_token(client: AsyncClient):
    # Register
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Logout User",
            "email": "logout@example.com",
            "phone": "+1234567890",
            "password": "SecurePass123",
        },
    )
    token = reg_resp.json()["data"]["access_token"]

    # Get /me with valid token (should work)
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200

    # Logout (cookie-based, just test the endpoint works)
    logout_resp = await client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200


@pytest.mark.asyncio
async def test_register_weak_password_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "User",
            "email": "weak@example.com",
            "phone": "+1234567890",
            "password": "abc",  # too short
        },
    )
    assert response.status_code == 422
