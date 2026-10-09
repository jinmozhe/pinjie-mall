import asyncio
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from starlette.concurrency import run_in_threadpool

from app.core.identifiers import new_uuid7

Audience = Literal["pinjie-web", "pinjie-admin", "pinjie-miniapp"]

_PASSWORD_HASH = PasswordHash(
    (
        Argon2Hasher(
            memory_cost=65536,
            time_cost=3,
            parallelism=4,
            salt_len=16,
            hash_len=32,
        ),
    )
)
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$6JWfD64umkoYsmmbjxffaQ$ZUqoM9jEukAYGzjmXf52KVQwCuBwzlxE3YT6CwR+CwM"
)


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    subject_id: uuid.UUID
    session_id: uuid.UUID
    token_id: uuid.UUID
    credential_version: int
    audience: Audience
    expires_at: datetime


class PasswordManager:
    def __init__(self, max_concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def hash(self, password: str) -> str:
        async with self._semaphore:
            return await run_in_threadpool(_PASSWORD_HASH.hash, password)

    async def verify(self, password: str, password_hash: str) -> bool:
        async with self._semaphore:
            return await run_in_threadpool(_PASSWORD_HASH.verify, password, password_hash)

    async def verify_and_update(self, password: str, password_hash: str) -> tuple[bool, str | None]:
        async with self._semaphore:
            return await run_in_threadpool(_PASSWORD_HASH.verify_and_update, password, password_hash)

    async def verify_unknown_user(self, password: str) -> None:
        await self.verify(password, _DUMMY_PASSWORD_HASH)


def create_access_token(
    *,
    subject_id: uuid.UUID,
    session_id: uuid.UUID,
    credential_version: int,
    audience: Audience,
    issuer: str,
    secret: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": str(subject_id),
        "sid": str(session_id),
        "jti": str(new_uuid7()),
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "token_type": "access",
        "credential_version": credential_version,
    }
    return jwt.encode(payload, secret, algorithm="HS256"), expires_at


def decode_access_token(
    token: str,
    *,
    audience: Audience,
    issuer: str,
    secret: str,
) -> AccessTokenClaims:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience=audience,
        issuer=issuer,
        leeway=30,
        options={
            "require": [
                "iss",
                "aud",
                "sub",
                "sid",
                "jti",
                "iat",
                "nbf",
                "exp",
                "token_type",
                "credential_version",
            ]
        },
    )
    if payload.get("token_type") != "access":
        raise InvalidTokenError("unexpected token type")
    credential_version = payload.get("credential_version")
    if isinstance(credential_version, bool) or not isinstance(credential_version, int):
        raise InvalidTokenError("invalid credential version")
    try:
        subject_id = uuid.UUID(str(payload["sub"]))
        session_id = uuid.UUID(str(payload["sid"]))
        token_id = uuid.UUID(str(payload["jti"]))
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("invalid token claims") from exc
    return AccessTokenClaims(
        subject_id=subject_id,
        session_id=session_id,
        token_id=token_id,
        credential_version=credential_version,
        audience=audience,
        expires_at=expires_at,
    )


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def new_anonymized_username(user_id: uuid.UUID) -> str:
    return f"deleted-{user_id.hex[:24]}-{secrets.token_hex(8)}"


def token_digest(token: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_token_matches(token: str, expected_digest: str, key: str) -> bool:
    return hmac.compare_digest(token_digest(token, key), expected_digest)


__all__ = [
    "AccessTokenClaims",
    "Audience",
    "InvalidTokenError",
    "PasswordManager",
    "constant_time_token_matches",
    "create_access_token",
    "decode_access_token",
    "new_anonymized_username",
    "new_opaque_token",
    "token_digest",
]
