"""Real PostgreSQL/Redis phone ownership races; execute only with explicit authorization."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.cache_keys import cache_keys
from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.core.resources import create_resources
from app.core.security import token_digest
from app.db.models import SecurityLoginEvent, User, UserExternalIdentity, UserSession
from app.db.transaction import transaction_scope
from app.services.consumer_auth import ConsumerAuthService
from app.services.consumer_phone import ConsumerPhoneService
from tests.conftest import TEST_SECRETS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_same_phone_race_keeps_accounts_separate_and_binding_is_idempotent():
    database_url, redis_url = os.getenv("TEST_DATABASE_URL"), os.getenv("TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.fail("Explicit isolated PostgreSQL and Redis targets are required")
    app_id = "wx" + new_uuid7().hex[-16:]
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        **{**TEST_SECRETS, "REDIS_URL": redis_url, "TEST_REDIS_URL": redis_url},
        MINIAPP_LOGIN_ENABLED=True,
        WECHAT_APP_ID=app_id,
        WECHAT_APP_SECRET="unit-wechat-only-0000000000000001",
        MINIAPP_JWT_SECRET="unit-miniapp-jwt-0000000000000001",
        MINIAPP_TOKEN_HMAC_KEY="unit-miniapp-hmac-000000000000001",
    )
    settings.validate_runtime()
    resources = create_resources(settings)
    if resources.wechat_http is not None:
        await resources.wechat_http.aclose()
    users, sessions = [new_uuid7(), new_uuid7()], [new_uuid7(), new_uuid7()]
    now = datetime.now(UTC)
    phone = "139" + str(new_uuid7().int % 100000000).zfill(8)
    metadata = RequestMetadata(
        request_id=str(new_uuid7()),
        trace_id=str(new_uuid7()),
        ip_address="127.0.0.78",
        user_agent_summary="phone-regression",
        release_version="test",
    )
    codes = [str(new_uuid7()) for _ in range(3)]

    def handler(request):
        if request.url.path == "/cgi-bin/stable_token":
            return httpx.Response(200, json={"access_token": "unit-token", "expires_in": 7200})
        body = json.loads(request.content)
        assert body["openid"] in {str(user) for user in users}
        return httpx.Response(
            200,
            json={
                "errcode": 0,
                "phone_info": {
                    "phoneNumber": phone,
                    "purePhoneNumber": phone,
                    "countryCode": "86",
                    "watermark": {"appid": app_id, "timestamp": int(now.timestamp())},
                },
            },
        )

    resources.wechat_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        async with resources.session_factory() as db, transaction_scope(db):
            for user_id, session_id in zip(users, sessions, strict=True):
                db.add(User(id=user_id, username=f"wx_{user_id.hex}", password_hash=None))
                await db.flush()
                db.add(UserExternalIdentity(user_id=user_id, provider="wechat", app_id=app_id, subject_id=str(user_id)))
                db.add(
                    UserSession(
                        id=session_id,
                        user_id=user_id,
                        family_id=new_uuid7(),
                        credential_profile="miniapp_bearer",
                        client_id="pinjie-miniapp",
                        csrf_digest=None,
                        last_seen_at=now,
                        idle_expires_at=now + timedelta(days=1),
                        absolute_expires_at=now + timedelta(days=2),
                    )
                )
        assert resources.redis is not None
        await resources.redis.set(
            cache_keys(settings).miniapp("application-token", app_id),
            json.dumps({"access_token": "unit-token", "expires_in": 7200}),
            ex=600,
        )

        async def bind(index, code):
            async with resources.session_factory() as db:
                auth = ConsumerAuthService(
                    session=db,
                    session_factory=resources.session_factory,
                    redis=resources.redis,
                    settings=settings,
                    http=resources.wechat_http,
                    metadata=metadata,
                )
                return await ConsumerPhoneService(auth).bind(
                    user_id=users[index], session_id=sessions[index], credential_version=1, code=code
                )

        results = await asyncio.wait_for(
            asyncio.gather(bind(0, codes[0]), bind(1, codes[1]), return_exceptions=True), 20
        )
        winners = [index for index, result in enumerate(results) if not isinstance(result, BaseException)]
        assert len(winners) == 1
        loser = results[1 - winners[0]]
        assert isinstance(loser, AppException) and loser.code == ErrorCode.PHONE_BINDING_CONFLICT
        winner = winners[0]
        repeated = await bind(winner, codes[2])
        assert repeated.id == users[winner] and repeated.phone_bound
        async with resources.session_factory() as db:
            rows = (await db.scalars(select(User).where(User.id.in_(users)))).all()
            assert sum(row.phone_bound for row in rows) == 1
            assert all(row.username == f"wx_{row.id.hex}" and row.password_hash is None for row in rows)
    finally:
        try:
            async with resources.session_factory() as db, transaction_scope(db):
                await db.execute(delete(UserSession).where(UserSession.id.in_(sessions)))
                await db.execute(delete(UserExternalIdentity).where(UserExternalIdentity.user_id.in_(users)))
                await db.execute(delete(User).where(User.id.in_(users)))
                await db.execute(delete(SecurityLoginEvent).where(SecurityLoginEvent.request_id == metadata.request_id))
            if resources.redis is not None:
                keys = cache_keys(settings)
                hmac_key = settings.miniapp_secrets()[1]
                await resources.redis.delete(
                    keys.miniapp("application-token", app_id),
                    *(keys.miniapp("phone-code", token_digest(f"{app_id}:{code}", hmac_key)) for code in codes),
                    *(keys.miniapp("phone-user", token_digest(str(user), hmac_key)) for user in users),
                )
        finally:
            await resources.close()
