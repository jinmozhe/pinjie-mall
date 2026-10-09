"""Security regressions. Execution requires explicit pytest authorization; no real WeChat requests."""

import logging
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import Response
from jwt import InvalidTokenError
from pydantic import ValidationError

from app.api.miniapp_dependencies import require_miniapp_profile
from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.logging import configure_logging
from app.core.payload_sanitizer import is_sensitive_route
from app.core.request_metadata import RequestMetadata
from app.core.restricted_html import legacy_text_to_html, restricted_html
from app.core.security import create_access_token, decode_access_token
from app.domains.auth.miniapp_schemas import MiniappLoginIn, MiniappRefreshIn
from app.services.miniapp_auth import MiniappAuthService
from tests.conftest import TEST_SECRETS


def miniapp_settings(**changes: object) -> Settings:
    values = {
        "ENVIRONMENT": "local",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/unit_only",
        **TEST_SECRETS,
        "MINIAPP_LOGIN_ENABLED": True,
        "WECHAT_APP_ID": "wx0123456789abcdef",
        "WECHAT_APP_SECRET": "unit-wechat-only-0000000000000001",
        "MINIAPP_JWT_SECRET": "unit-miniapp-jwt-0000000000000001",
        "MINIAPP_TOKEN_HMAC_KEY": "unit-miniapp-hmac-000000000000001",
        **changes,
    }
    return Settings.model_validate(values)


@pytest.mark.parametrize(
    "content",
    [
        "<script>alert(1)</script>",
        '<p onclick="alert(1)">x</p>',
        '<a href="https://example.com">x</a>',
        '<img src="https://example.com/a.png">',
        "<svg><script>x</script></svg>",
        '<p style="color:red;background:url(x)">x</p>',
        "<!--secret--><p>x</p>",
        "<p><strong>x</p>",
    ],
)
def test_description_rejects_unsafe_or_ambiguous_html(content: str) -> None:
    with pytest.raises(ValueError):
        restricted_html(content)


def test_text_migration_never_interprets_markup() -> None:
    result = legacy_text_to_html("<script>x</script>\n第二行")
    assert "<script>" not in result and "&lt;script&gt;" in result and "<br>" in result
    assert restricted_html(result) == result
    assert (
        restricted_html('<p><span style="color: rgb(180, 35, 24)">红色</span></p>')
        == '<p><span style="color: #b42318;">红色</span></p>'
    )


def test_profile_and_key_separation() -> None:
    settings = miniapp_settings()
    settings.validate_runtime()
    token, _ = create_access_token(
        subject_id=new_uuid7(),
        session_id=new_uuid7(),
        credential_version=1,
        audience="pinjie-miniapp",
        issuer=settings.jwt_issuer,
        secret=settings.miniapp_secrets()[0],
        ttl_seconds=60,
    )
    for audience, key in [
        ("pinjie-web", settings.authentication_secrets()[0]),
        ("pinjie-miniapp", settings.authentication_secrets()[0]),
        ("pinjie-admin", settings.miniapp_secrets()[0]),
    ]:
        with pytest.raises(InvalidTokenError):
            decode_access_token(token, audience=audience, issuer=settings.jwt_issuer, secret=key)
    with pytest.raises(ValueError):
        miniapp_settings(MINIAPP_JWT_SECRET=settings.web_jwt_secret).miniapp_secrets()
    request = MagicMock(headers={"cookie": "pinjie_web_access=unit-only"})
    with pytest.raises(AppException) as failure:
        require_miniapp_profile(request, Response())
    assert failure.value.status_code == 400


def test_secrets_are_not_repr_or_error_body_candidates() -> None:
    assert "unit-code" not in repr(MiniappLoginIn(code="unit-code"))
    assert "x" * 64 not in repr(MiniappRefreshIn(refresh_token="x" * 64))
    assert is_sensitive_route("/api/v1/miniapp/auth/login")
    assert is_sensitive_route("/api/v1/miniapp/addresses")
    with pytest.raises(ValidationError):
        MiniappLoginIn(code="unit", openid="client-forged")
    settings = miniapp_settings()
    configure_logging(settings)
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["expired", "server", "malformed", "timeout"])
async def test_exchange_failures_hide_external_payload(failure: str) -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("unit-secret in external URL", request=request)
        if failure == "expired":
            return httpx.Response(200, json={"errcode": 40163, "errmsg": "unit-secret"})
        if failure == "malformed":
            return httpx.Response(200, content=b"unit-secret")
        return httpx.Response(500, json={"errmsg": "unit-secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        service = MiniappAuthService(
            session=MagicMock(),
            session_factory=MagicMock(),
            redis=None,
            settings=miniapp_settings(),
            http=http,
            metadata=RequestMetadata(
                request_id=str(new_uuid7()),
                trace_id=str(new_uuid7()),
                ip_address="127.0.0.1",
                user_agent_summary="unit",
                release_version="unit",
            ),
        )
        with pytest.raises(AppException) as rejected:
            await service._exchange("unit-code")
        assert "unit-secret" not in str(rejected.value)
        assert rejected.value.status_code == (401 if failure == "expired" else 503)


@pytest.mark.asyncio
async def test_exchange_accepts_only_trusted_openid() -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.weixin.qq.com"
        assert request.url.params["grant_type"] == "authorization_code"
        return httpx.Response(200, json={"openid": "unit-trusted-openid", "session_key": "never-store-this"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        service = MiniappAuthService(
            session=MagicMock(),
            session_factory=MagicMock(),
            redis=None,
            settings=miniapp_settings(),
            http=http,
            metadata=RequestMetadata(
                request_id=str(new_uuid7()),
                trace_id=str(new_uuid7()),
                ip_address=None,
                user_agent_summary=None,
                release_version="unit",
            ),
        )
        identity = await service._exchange("unit-code")
        assert identity.openid == "unit-trusted-openid"
        assert "session_key" not in identity.model_dump()
