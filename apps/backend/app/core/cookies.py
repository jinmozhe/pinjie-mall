from dataclasses import dataclass

from fastapi import Response

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class CookieNames:
    access: str
    refresh: str
    csrf: str
    refresh_path: str


ADMIN_COOKIES = CookieNames(
    access="pinjie_admin_access",
    refresh="pinjie_admin_refresh",
    csrf="pinjie_admin_csrf",
    refresh_path="/api/v1/admin/auth",
)


def set_auth_cookies(
    response: Response,
    *,
    names: CookieNames,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    access_max_age: int,
    refresh_max_age: int,
    settings: Settings,
) -> None:
    response.set_cookie(
        names.access,
        access_token,
        max_age=access_max_age,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        names.refresh,
        refresh_token,
        max_age=refresh_max_age,
        path=names.refresh_path,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        names.csrf,
        csrf_token,
        max_age=refresh_max_age,
        path="/",
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_auth_cookies(response: Response, *, names: CookieNames, settings: Settings) -> None:
    response.delete_cookie(
        names.access,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        names.refresh,
        path=names.refresh_path,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        names.csrf,
        path="/",
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


__all__ = ["ADMIN_COOKIES", "CookieNames", "clear_auth_cookies", "set_auth_cookies"]
