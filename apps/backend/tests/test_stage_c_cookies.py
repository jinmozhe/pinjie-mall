from fastapi import Response

from app.core.config import Settings
from app.core.cookies import ADMIN_COOKIES, clear_auth_cookies, set_auth_cookies
from tests.conftest import TEST_SECRETS


def _settings(*, secure: bool) -> Settings:
    return Settings(AUTH_COOKIE_SECURE=secure, **TEST_SECRETS)


def test_admin_cookie_profile_is_http_only_and_path_scoped() -> None:
    response = Response()
    set_auth_cookies(
        response,
        names=ADMIN_COOKIES,
        access_token="access-secret",
        refresh_token="refresh-secret",
        csrf_token="csrf-value",
        access_max_age=900,
        refresh_max_age=604800,
        settings=_settings(secure=True),
    )
    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 3
    assert any(
        "pinjie_admin_access=access-secret" in item and "HttpOnly" in item and "Secure" in item for item in headers
    )
    assert any(
        "pinjie_admin_refresh=refresh-secret" in item and "Path=/api/v1/admin/auth" in item and "HttpOnly" in item
        for item in headers
    )
    csrf_header = next(item for item in headers if item.startswith("pinjie_admin_csrf="))
    assert "HttpOnly" not in csrf_header
    assert "SameSite=lax" in csrf_header
    assert response.headers["cache-control"] == "no-store"


def test_admin_cookie_profile_uses_distinct_names_and_can_be_cleared() -> None:
    response = Response()
    clear_auth_cookies(response, names=ADMIN_COOKIES, settings=_settings(secure=False))
    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 3
    assert all("Max-Age=0" in item for item in headers)
    assert all("pinjie_web_" not in item for item in headers)
