"""Password hashing (argon2id) and JWT access tokens."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from clear_helper.config import JWT_ALGORITHM
from clear_helper.models import Role

_hasher = PasswordHasher()

# Used to spend the same hashing time when the user does not exist (mitigates user enumeration).
_DUMMY_HASH = _hasher.hash("clear-helper-dummy-password")

_REQUIRED_CLAIMS = ["sub", "tid", "role", "exp", "iat"]


class InvalidTokenError(Exception):
    """Raised when an access token is missing, malformed, expired or has invalid claims."""


@dataclass(frozen=True, slots=True)
class TokenClaims:
    sub: uuid.UUID
    tid: uuid.UUID
    role: Role
    exp: datetime
    iat: datetime


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> None:
    """Burn the same CPU time as a real verification; result is always discarded."""
    verify_password(_DUMMY_HASH, password)


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: Role,
    secret: str,
    expires_minutes: int,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "role": role.value,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": _REQUIRED_CLAIMS},
        )
        return TokenClaims(
            sub=uuid.UUID(str(payload["sub"])),
            tid=uuid.UUID(str(payload["tid"])),
            role=Role(payload["role"]),
            exp=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
            iat=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        )
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise InvalidTokenError(type(exc).__name__) from exc
