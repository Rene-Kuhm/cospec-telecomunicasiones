import time

import pytest

from app.core.exceptions import AuthError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)


TEST_PLAIN_PW = "T3st_Pl@in_PW!"  # noqa: S105 — test fixture, not a real credential


def test_hash_password_and_verify():
    hashed = hash_password(TEST_PLAIN_PW)
    assert hashed != TEST_PLAIN_PW
    assert verify_password(TEST_PLAIN_PW, hashed) is True
    assert verify_password("wrong_input", hashed) is False


def test_hash_password_different_salts():
    hash1 = hash_password(TEST_PLAIN_PW)
    hash2 = hash_password(TEST_PLAIN_PW)
    # bcrypt generates different salts each time
    assert hash1 != hash2
    # But both should verify correctly
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True


def test_create_and_decode_access_token():
    token = create_access_token(
        user_id="test-user-id",
        role="admin",
        email="admin@example.com",
    )
    assert isinstance(token, str)
    assert len(token) > 0

    payload = decode_access_token(token)
    assert payload["sub"] == "test-user-id"
    assert payload["role"] == "admin"
    assert payload["email"] == "admin@example.com"
    assert payload["type"] == "access"


def test_expired_token_raises_auth_error(monkeypatch):
    """Test that an expired token raises AuthError."""
    import app.core.security as sec_module  # noqa: PLC0415

    # Create a token that is already expired by patching expiry
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415
    from jose import jwt  # noqa: PLC0415
    from app.config import settings  # noqa: PLC0415

    payload = {
        "sub": "test-user-id",
        "role": "admin",
        "email": "test@example.com",
        "iat": datetime.now(UTC) - timedelta(hours=1),
        "exp": datetime.now(UTC) - timedelta(minutes=1),  # already expired
        "type": "access",
    }
    expired_token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(AuthError) as exc_info:
        decode_access_token(expired_token)
    assert exc_info.value.http_status == 401
    assert exc_info.value.code == "INVALID_TOKEN"


def test_hash_token_is_deterministic():
    sample = "fixture-input-abc"  # not a real token
    hash1 = hash_token(sample)
    hash2 = hash_token(sample)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest = 64 chars
    assert hash1 != sample


def test_hash_token_different_inputs_give_different_hashes():
    hash1 = hash_token("input-a")
    hash2 = hash_token("input-b")
    assert hash1 != hash2
