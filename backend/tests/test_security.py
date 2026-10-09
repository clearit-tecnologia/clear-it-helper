from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from clear_helper.models import Role
from clear_helper.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)

SECRET = "unit-test-secret-with-at-least-32-chars"


def test_hash_and_verify_password() -> None:
    hashed = hash_password("s3nh@-forte")
    assert hashed.startswith("$argon2id$")
    assert hashed != "s3nh@-forte"
    assert verify_password(hashed, "s3nh@-forte")
    assert not verify_password(hashed, "wrong")
    assert not password_needs_rehash(hashed)


def test_verify_password_with_invalid_hash_returns_false() -> None:
    assert not verify_password("not-a-hash", "whatever")


def test_token_roundtrip_contains_required_claims() -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC).replace(microsecond=0)
    token = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        role=Role.ADMIN,
        secret=SECRET,
        expires_minutes=30,
        now=now,
    )

    raw = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert set(raw) == {"sub", "tid", "role", "exp", "iat"}

    claims = decode_access_token(token, secret=SECRET)
    assert claims.sub == user_id
    assert claims.tid == tenant_id
    assert claims.role is Role.ADMIN
    assert claims.iat == now
    assert claims.exp == now + timedelta(minutes=30)


def test_expired_token_is_rejected() -> None:
    token = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role=Role.MEMBER,
        secret=SECRET,
        expires_minutes=1,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_token_with_wrong_secret_is_rejected() -> None:
    token = create_access_token(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role=Role.MEMBER,
        secret=SECRET,
        expires_minutes=5,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="another-secret-with-at-least-32-chars")


def test_token_missing_tenant_claim_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "admin", "iat": now, "exp": now + timedelta(minutes=5)},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_token_with_none_algorithm_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tid": str(uuid.uuid4()),
            "role": "admin",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        None,
        algorithm="none",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)
