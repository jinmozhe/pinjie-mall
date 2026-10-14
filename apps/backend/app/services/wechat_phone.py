"""Official one-use phone exchange. Never replay a code after an unknown result."""

import asyncio
import re
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.cache_keys import cache_keys
from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.rate_limit import acquire_refresh_lock, release_refresh_lock
from app.core.security import token_digest

_EXCHANGE_FAILURES = (httpx.HTTPError, TimeoutError, ValueError)
_TOKEN_FAILURES = (RedisError, ValidationError)
_PHONE_VALIDATION_FAILURES = (ValidationError, ValueError)


class ApplicationToken(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    access_token: str = Field(min_length=1, max_length=2048, repr=False)
    expires_in: int = Field(gt=0, le=7200)


class Watermark(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    appid: str
    timestamp: int


class PhoneInfo(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    phone_number: str = Field(alias="phoneNumber", repr=False)
    pure_phone_number: str = Field(alias="purePhoneNumber", repr=False)
    country_code: str = Field(alias="countryCode")
    watermark: Watermark

    def normalized(self, app_id: str, now: datetime) -> str:
        number = f"+{self.country_code}{self.pure_phone_number}"
        if (
            not re.fullmatch(r"[1-9][0-9]{0,2}", self.country_code)
            or not re.fullmatch(r"[0-9]+", self.pure_phone_number)
            or not re.fullmatch(r"\+[1-9][0-9]{1,14}", number)
            or self.phone_number not in (self.pure_phone_number, number[1:], number)
            or self.watermark.appid != app_id
            or not -60 <= now.timestamp() - self.watermark.timestamp <= 300
        ):
            raise ValueError("Invalid verified phone response")
        return number


class WechatPhoneClient:
    def __init__(self, settings: Settings, redis: Redis | None, http: httpx.AsyncClient | None) -> None:
        self.settings, self.redis, self.http = settings, redis, http
        self.keys = cache_keys(settings)

    async def _post(self, path: str, data: dict[str, object], *, token: str | None = None) -> dict[str, object]:
        if self.http is None:
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信服务尚未就绪")
        try:
            async with asyncio.timeout(8):
                response = await self.http.post(
                    f"https://api.weixin.qq.com{path}",
                    json=data,
                    params={"access_token": token} if token else None,
                )
            if response.status_code != 200 or len(response.content) > 8192:
                raise ValueError("Invalid response")
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Invalid response")
        except _EXCHANGE_FAILURES:
            raise AppException(
                status_code=504,
                code=ErrorCode.PHONE_BINDING_UNKNOWN,
                message="微信验证结果未确认，请查询账户手机号状态后重新授权",
            ) from None
        return body

    async def _token(self) -> str:
        if self.redis is None or self.settings.wechat_app_id is None:
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="手机号服务尚未就绪")
        key = self.keys.miniapp("application-token", self.settings.wechat_app_id)
        owner = str(new_uuid7())
        try:
            cached = await self.redis.get(key)
            if cached:
                return ApplicationToken.model_validate_json(cached).access_token
            if not await acquire_refresh_lock(self.redis, key=key + ":lock", owner=owner, ttl_seconds=15):
                raise AppException(status_code=429, code=ErrorCode.RATE_LIMITED, message="微信凭据刷新中，请稍后重试")
            try:
                cached = await self.redis.get(key)
                if cached:
                    return ApplicationToken.model_validate_json(cached).access_token
                body = await self._post(
                    "/cgi-bin/stable_token",
                    {
                        "grant_type": "client_credential",
                        "appid": self.settings.wechat_app_id,
                        "secret": self.settings.wechat_app_secret,
                        "force_refresh": False,
                    },
                )
                if body.get("errcode", 0) != 0:
                    raise AppException(
                        status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信应用凭据获取失败"
                    )
                parsed = ApplicationToken.model_validate(body)
                if parsed.expires_in <= 10:
                    raise AppException(
                        status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信凭据即将过期，请稍后重试"
                    )
                await self.redis.set(key, parsed.model_dump_json(), ex=max(1, parsed.expires_in - 120))
                return parsed.access_token
            finally:
                await release_refresh_lock(self.redis, key=key + ":lock", owner=owner)
        except _TOKEN_FAILURES:
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信凭据缓存不可用"
            ) from None

    async def exchange(self, code: str, openid: str) -> str:
        token = await self._token()
        if self.redis is None or self.settings.wechat_app_id is None:
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="手机号服务尚未就绪")
        _, hmac_key = self.settings.miniapp_secrets()
        digest = token_digest(f"{self.settings.wechat_app_id}:{code}", hmac_key)
        try:
            consumed = await self.redis.set(self.keys.miniapp("phone-code", digest), "consumed", ex=600, nx=True)
        except RedisError:
            raise AppException(
                status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="手机号验证服务暂时不可用"
            ) from None
        if not consumed:
            raise AppException(
                status_code=409, code=ErrorCode.PHONE_CODE_INVALID, message="手机号凭证已使用，请重新授权"
            )
        body = await self._post("/wxa/business/getuserphonenumber", {"code": code, "openid": openid}, token=token)
        error = body.get("errcode", 0)
        if error != 0:
            if error in (40001, 40014, 42001):
                # Invalidate only the token that failed; a concurrent refresh must remain intact.
                key = self.keys.miniapp("application-token", self.settings.wechat_app_id)
                try:
                    await self.redis.eval(
                        "local v=redis.call('GET',KEYS[1]); if v and cjson.decode(v).access_token==ARGV[1] "
                        "then return redis.call('DEL',KEYS[1]) else return 0 end",
                        1,
                        key,
                        token,
                    )
                except RedisError:
                    raise AppException(
                        status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信凭据刷新未确认"
                    ) from None
            if error in (40029, 40013):
                raise AppException(
                    status_code=400, code=ErrorCode.PHONE_CODE_INVALID, message="手机号授权未通过，请重新授权"
                )
            if error == 45011:
                raise AppException(
                    status_code=429,
                    code=ErrorCode.RATE_LIMITED,
                    message="微信手机号验证过于频繁，请稍后重新授权",
                    headers={"Retry-After": "60"},
                )
            raise AppException(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message="微信手机号服务暂时不可用，请稍后重新授权；持续失败请联系运营",
            )
        try:
            return PhoneInfo.model_validate(body.get("phone_info")).normalized(
                self.settings.wechat_app_id, datetime.now(UTC)
            )
        except _PHONE_VALIDATION_FAILURES:
            raise AppException(
                status_code=502, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信手机号响应校验失败"
            ) from None
