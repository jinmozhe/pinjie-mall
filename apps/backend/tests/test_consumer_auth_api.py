"""Consumer authentication migration regressions; pytest execution requires authorization."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from sqlalchemy.exc import SQLAlchemyError

from app.api import dependencies
from app.api.account_dependencies import consumer_profile
from app.core.config import Settings
from app.core.identifiers import new_uuid7
from app.core.security import create_access_token
from app.main import create_app
from tests.conftest import TEST_SECRETS


@pytest.fixture
async def consumer_client(monkeypatch):
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="local",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost:5432/unit_only",
        **TEST_SECRETS,
        MINIAPP_LOGIN_ENABLED=True,
        WECHAT_APP_ID="wx0123456789abcdef",
        WECHAT_APP_SECRET="unit-wechat-only-0000000000000001",
        MINIAPP_JWT_SECRET="unit-miniapp-jwt-0000000000000001",
        MINIAPP_TOKEN_HMAC_KEY="unit-miniapp-hmac-000000000000001",
    )
    app = create_app(settings)
    app.state.resources = SimpleNamespace(redis=object())
    now = datetime.now(UTC)
    user = SimpleNamespace(
        id=new_uuid7(), display_name="消费者", avatar=None, credential_version=1, is_active=True, deleted_at=None
    )
    session = SimpleNamespace(
        id=new_uuid7(),
        user_id=user.id,
        user=user,
        credential_profile="miniapp_bearer",
        client_id="pinjie-miniapp",
        csrf_digest=None,
        revoked_at=None,
        idle_expires_at=now + timedelta(days=7),
        absolute_expires_at=now + timedelta(days=30),
    )
    repository = SimpleNamespace(get_web=AsyncMock(return_value=session))
    monkeypatch.setattr(dependencies, "SessionRepository", lambda _: repository)

    async def database():
        yield AsyncMock()

    app.dependency_overrides[dependencies.get_db_session] = database

    def token(*, audience="pinjie-miniapp", secret=None, subject_id=None, credential_version=1):
        return create_access_token(
            subject_id=subject_id or user.id,
            session_id=session.id,
            credential_version=credential_version,
            audience=audience,
            issuer=settings.jwt_issuer,
            secret=secret or settings.miniapp_secrets()[0],
            ttl_seconds=300,
        )[0]

    artifacts = {
        "user": {"id": user.id, "display_name": user.display_name, "avatar": None},
        "session_id": session.id,
        "access_token": token(),
        "refresh_token": "r" * 64,
        "access_expires_at": now + timedelta(minutes=5),
        "idle_expires_at": session.idle_expires_at,
        "absolute_expires_at": session.absolute_expires_at,
    }
    auth = SimpleNamespace(
        settings=settings,
        login=AsyncMock(return_value=artifacts),
        refresh=AsyncMock(return_value=artifacts),
        logout=AsyncMock(),
    )
    app.dependency_overrides[dependencies.get_consumer_auth_service] = lambda: auth
    profile = SimpleNamespace(update_profile=AsyncMock(return_value=user))
    app.dependency_overrides[consumer_profile] = lambda: profile
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        yield SimpleNamespace(
            app=app,
            client=client,
            user=user,
            session=session,
            repository=repository,
            settings=settings,
            token=token,
            auth=auth,
            profile=profile,
        )


@pytest.mark.asyncio
async def test_wechat_login_and_refresh_use_body_credentials_without_cookie(consumer_client):
    ctx = consumer_client
    response = await ctx.client.post("/api/v1/auth/login", json={"code": "one-use-code"})
    assert response.status_code == 200
    assert response.json()["data"]["refresh_token"] == "r" * 64
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    ctx.auth.login.assert_awaited_once_with("one-use-code")
    response = await ctx.client.post("/api/v1/auth/refresh", json={"refresh_token": "r" * 64})
    assert response.status_code == 200
    ctx.auth.refresh.assert_awaited_once_with("r" * 64)


@pytest.mark.asyncio
async def test_password_login_payload_is_rejected_without_fallback(consumer_client):
    ctx = consumer_client
    response = await ctx.client.post("/api/v1/auth/login", json={"username": "old-user", "password": "old-password"})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    ctx.auth.login.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("cookie", ["pinjie_web_access=old", "pinjie_admin_access=admin"])
@pytest.mark.parametrize("with_bearer", [False, True])
async def test_cookie_and_mixed_credentials_cannot_authenticate_consumer(consumer_client, cookie, with_bearer):
    ctx = consumer_client
    headers = {"Cookie": cookie}
    if with_bearer:
        headers["Authorization"] = f"Bearer {ctx.token()}"
    response = await ctx.client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    ctx.repository.get_web.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer broken", "Bearer"])
async def test_missing_or_invalid_bearer_is_rejected(consumer_client, authorization):
    ctx = consumer_client
    headers = {"Authorization": authorization} if authorization else {}
    response = await ctx.client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    ctx.repository.get_web.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "audience",
        "signature",
        "subject",
        "version",
        "profile",
        "client",
        "csrf",
        "revoked",
        "expired",
        "disabled",
        "deleted",
    ],
)
async def test_bearer_checks_identity_session_and_account(consumer_client, failure):
    ctx = consumer_client
    kwargs = {}
    if failure == "audience":
        kwargs["audience"] = "pinjie-admin"
    elif failure == "signature":
        kwargs["secret"] = ctx.settings.authentication_secrets()[1]
    elif failure == "subject":
        kwargs["subject_id"] = new_uuid7()
    elif failure == "version":
        kwargs["credential_version"] = 2
    elif failure == "profile":
        ctx.session.credential_profile = "browser_cookie"
    elif failure == "client":
        ctx.session.client_id = "pinjie-web"
    elif failure == "csrf":
        ctx.session.csrf_digest = "browser-only"
    elif failure == "revoked":
        ctx.session.revoked_at = datetime.now(UTC)
    elif failure == "expired":
        ctx.session.idle_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif failure == "disabled":
        ctx.user.is_active = False
    elif failure == "deleted":
        ctx.user.deleted_at = datetime.now(UTC)
    response = await ctx.client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {ctx.token(**kwargs)}"})
    assert response.status_code == (403 if failure in {"disabled", "deleted"} else 401)


@pytest.mark.asyncio
async def test_bearer_can_write_profile_without_csrf_and_cannot_access_admin(consumer_client):
    ctx = consumer_client
    headers = {"Authorization": f"Bearer {ctx.token()}"}
    response = await ctx.client.patch("/api/v1/users/me", headers=headers, json={"display_name": "新昵称"})
    assert response.status_code == 200
    args = ctx.profile.update_profile.await_args.args
    assert args[0] == ctx.user.id and args[1].display_name == "新昵称"
    assert set(response.json()["data"]) == {"id", "display_name", "avatar"}
    response = await ctx.client.get("/api/v1/admin/auth/me", headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_database_failure_does_not_fall_back_to_another_identity(consumer_client):
    ctx = consumer_client
    ctx.repository.get_web.side_effect = SQLAlchemyError("unavailable")
    response = await ctx.client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {ctx.token()}"})
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_retired_routes_and_duplicate_operations_are_absent():
    app = create_app(Settings.model_construct())
    paths = app.openapi()["paths"]
    assert not any(path.startswith("/api/v1/miniapp") for path in paths)
    assert "/api/v1/auth/register" not in paths
    assert "/api/v1/users/me/password" not in paths
    assert "delete" not in paths["/api/v1/users/me"]
    assert "post" not in paths["/api/v1/distribution/me/withdrawals"]
    assert paths["/api/v1/orders"]["post"]["security"] == [{"ConsumerBearer": []}]
    operations = [
        (context.path, method)
        for context in iter_route_contexts(app.routes)
        if isinstance(context.route, APIRoute)
        for method in context.methods
    ]
    assert ("/api/v1/orders", "POST") in operations
    assert len(operations) == len(set(operations))
