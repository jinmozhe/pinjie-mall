"""Real PostgreSQL/Redis identity regression; no schema changes or real WeChat calls."""

import asyncio
import os

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.core.cache_keys import cache_keys
from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.core.resources import create_resources
from app.core.security import token_digest
from app.db.models import SecurityLoginEvent, SystemSetting, User, UserExternalIdentity, UserRefreshToken, UserSession
from app.db.transaction import transaction_scope
from app.services.consumer_auth import ConsumerAuthService
from tests.conftest import TEST_SECRETS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_identity_registration_rotation_and_replay_revocation() -> None:
    database_url, redis_url = os.getenv("TEST_DATABASE_URL"), os.getenv("TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.fail("Explicit isolated PostgreSQL and Redis targets are required")
    settings = Settings(
        ENVIRONMENT="test",
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        **{**TEST_SECRETS, "REDIS_URL": redis_url, "TEST_REDIS_URL": redis_url},
        MINIAPP_LOGIN_ENABLED=True,
        WECHAT_APP_ID="wx0123456789abcdef",
        WECHAT_APP_SECRET="unit-wechat-only-0000000000000001",
        MINIAPP_JWT_SECRET="unit-miniapp-jwt-0000000000000001",
        MINIAPP_TOKEN_HMAC_KEY="unit-miniapp-hmac-000000000000001",
    )
    settings.validate_runtime()
    resources = create_resources(settings)
    assert resources.wechat_http is not None
    await resources.wechat_http.aclose()
    subject = str(new_uuid7())
    resources.wechat_http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"openid": subject}))
    )
    metadata = RequestMetadata(
        request_id=str(new_uuid7()),
        trace_id=str(new_uuid7()),
        ip_address="127.0.0.77",
        user_agent_summary="miniapp-regression",
        release_version="test",
    )
    old_value = None
    user_id = None
    try:
        async with resources.session_factory() as session, transaction_scope(session):
            row = (
                await session.scalars(
                    select(SystemSetting).where(SystemSetting.setting_group == "miniapp_registration").with_for_update()
                )
            ).one()
            old_value = dict(row.setting_value)
            row.setting_value, row.revision = {"enabled": True}, row.revision + 1

        async def login():
            async with resources.session_factory() as session:
                return await ConsumerAuthService(
                    session=session,
                    session_factory=resources.session_factory,
                    redis=resources.redis,
                    settings=settings,
                    http=resources.wechat_http,
                    metadata=metadata,
                ).login("unit-code")

        first, second = await asyncio.wait_for(asyncio.gather(login(), login()), timeout=15)
        user_id = first.user.id
        assert first.user.id == second.user.id and first.session_id != second.session_id
        async with resources.session_factory() as session, transaction_scope(session):
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(UserExternalIdentity)
                    .where(UserExternalIdentity.subject_id == subject)
                )
                == 1
            )
            user = await session.get(User, user_id)
            assert user is not None and user.password_hash is None
            row = (
                await session.scalars(
                    select(SystemSetting).where(SystemSetting.setting_group == "miniapp_registration").with_for_update()
                )
            ).one()
            row.setting_value, row.revision = {"enabled": False}, row.revision + 1
        # Closing first registration does not revoke an already bound identity.
        third = await login()
        assert third.user.id == user_id
        async with resources.session_factory() as session:
            service = ConsumerAuthService(
                session=session,
                session_factory=resources.session_factory,
                redis=resources.redis,
                settings=settings,
                http=resources.wechat_http,
                metadata=metadata,
            )
            rotated = await service.refresh(first.refresh_token)
            assert rotated.refresh_token != first.refresh_token
            with pytest.raises(AppException) as reuse:
                await service.refresh(first.refresh_token)
            assert reuse.value.code == "AUTH_REFRESH_REUSE_DETECTED"
            with pytest.raises(AppException):
                await service.refresh(rotated.refresh_token)
        async with resources.session_factory() as session:
            record = await session.get(UserSession, first.session_id)
            assert record is not None and record.revoked_at is not None
            assert record.credential_profile == "miniapp_bearer" and record.csrf_digest is None
    finally:
        try:
            async with resources.session_factory() as session, transaction_scope(session):
                if user_id is None:
                    binding = (
                        await session.scalars(
                            select(UserExternalIdentity).where(UserExternalIdentity.subject_id == subject)
                        )
                    ).one_or_none()
                    user_id = binding.user_id if binding else None
                if user_id is not None:
                    ids = select(UserSession.id).where(UserSession.user_id == user_id)
                    await session.execute(delete(UserRefreshToken).where(UserRefreshToken.session_id.in_(ids)))
                    await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
                    await session.execute(delete(UserExternalIdentity).where(UserExternalIdentity.user_id == user_id))
                    await session.execute(delete(User).where(User.id == user_id))
                await session.execute(
                    delete(SecurityLoginEvent).where(SecurityLoginEvent.request_id == metadata.request_id)
                )
                if old_value is not None:
                    row = (
                        await session.scalars(
                            select(SystemSetting)
                            .where(SystemSetting.setting_group == "miniapp_registration")
                            .with_for_update()
                        )
                    ).one()
                    row.setting_value, row.revision = old_value, row.revision + 1
            if resources.redis is not None:
                await resources.redis.delete(
                    cache_keys(settings).miniapp(
                        "login-ip", token_digest(metadata.ip_address or "unknown", settings.miniapp_secrets()[1])
                    )
                )
        finally:
            await resources.close()
