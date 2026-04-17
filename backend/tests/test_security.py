from __future__ import annotations

import pytest
from jose import JWTError, jwt

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.config import get_settings


def test_hash_and_verify_password() -> None:
    password = "StrongPass1"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPass1", hashed)


def test_access_token_round_trip() -> None:
    token = create_access_token("user-123", "ANALYST")

    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["role"] == "ANALYST"
    assert payload["type"] == "access"


def test_refresh_token_hashing_is_stable() -> None:
    raw_token, token_hash = generate_refresh_token()

    assert hash_refresh_token(raw_token) == token_hash


def test_decode_rejects_invalid_token_type() -> None:
    settings = get_settings()
    token = jwt.encode(
        {"sub": "user-123", "role": "ANALYST", "type": "refresh"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(JWTError):
        decode_access_token(token)
