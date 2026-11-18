"""WeChat Pay v3 protocol boundary. No database or business state transitions."""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.lifecycle import PayParameters


class PayProtocolError(AppException):
    def __init__(
        self, message: str = "微信支付响应未通过可信校验", *, channel_code: str = "", status: int = 502
    ) -> None:
        super().__init__(status_code=status, code=ErrorCode.SERVICE_UNAVAILABLE, message=message)
        self.channel_code = channel_code


class PayAmount(BaseModel):
    model_config = ConfigDict(strict=True)
    total: int = Field(gt=0)
    currency: str


class PayPayer(BaseModel):
    openid: str = Field(min_length=1)


class PayTransaction(BaseModel):
    appid: str
    mchid: str
    out_trade_no: str
    transaction_id: str | None = None
    trade_state: str
    success_time: datetime | None = None
    amount: PayAmount | None = None
    payer: PayPayer | None = None


class RefundAmount(BaseModel):
    model_config = ConfigDict(strict=True)
    total: int = Field(gt=0)
    refund: int = Field(gt=0)
    currency: str


class PayRefund(BaseModel):
    mchid: str | None = None
    out_trade_no: str
    transaction_id: str
    out_refund_no: str
    refund_id: str
    status: str
    success_time: datetime | None = None
    amount: RefundAmount


def cents(amount: Decimal) -> int:
    value = amount * 100
    if not value.is_finite() or value != value.to_integral_value() or not 0 < value <= 2147483647:
        raise PayProtocolError("支付金额超出渠道范围", status=409)
    return int(value)


def payload_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


class WechatPayClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        settings.validate_wechat_pay()
        self.settings = settings
        self.http = http
        try:
            private = serialization.load_pem_private_key(
                Path(settings.wechat_pay_private_key_path).read_bytes(), password=None
            )
            public = serialization.load_pem_public_key(Path(settings.wechat_pay_public_key_path).read_bytes())
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("WeChat Pay key material cannot be loaded") from exc
        if not isinstance(private, rsa.RSAPrivateKey) or not isinstance(public, rsa.RSAPublicKey):
            raise ValueError("WeChat Pay requires RSA keys")
        if private.key_size != 2048 or public.key_size != 2048:
            raise ValueError("WeChat Pay requires 2048-bit RSA keys")
        self.private = private
        self.public = public

    def sign(self, message: bytes) -> str:
        return base64.b64encode(self.private.sign(message, padding.PKCS1v15(), hashes.SHA256())).decode()

    def authorization(self, method: str, path: str, body: bytes = b"") -> str:
        timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
        signature = self.sign(f"{method}\n{path}\n{timestamp}\n{nonce}\n".encode() + body + b"\n")
        return (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{self.settings.wechat_pay_mch_id}",nonce_str="{nonce}",'
            f'timestamp="{timestamp}",serial_no="{self.settings.wechat_pay_merchant_serial_no}",signature="{signature}"'
        )

    async def download_bill(self, metadata: dict[str, Any]) -> bytes:
        url, digest = metadata.get("download_url"), metadata.get("hash_value")
        if metadata.get("hash_type") != "SHA1" or not isinstance(url, str) or not isinstance(digest, str):
            raise PayProtocolError("账单下载元数据无效")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.mch.weixin.qq.com"
            or parsed.path != "/v3/billdownload/file"
            or parsed.fragment
        ):
            raise PayProtocolError("账单下载地址不受信任")
        path = parsed.path + "?" + parsed.query
        content = bytearray()
        try:
            async with (
                asyncio.timeout(30),
                self.http.stream(
                    "GET",
                    url,
                    headers={"Authorization": self.authorization("GET", path)},
                ) as response,
            ):
                if response.status_code != 200:
                    raise PayProtocolError("账单下载失败")
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 20 * 1024 * 1024:
                        raise PayProtocolError("账单超过单次处理上限")
        except httpx.HTTPError, TimeoutError:
            raise PayProtocolError("账单下载未完成") from None
        # WeChat bill downloads have no response signature. The hash comes from signed metadata.
        if not secrets.compare_digest(hashlib.sha1(content).hexdigest(), digest.lower()):
            raise PayProtocolError("账单内容完整性校验失败")
        return bytes(content)

    def verify(self, headers: httpx.Headers, body: bytes) -> None:
        try:
            serial = headers["Wechatpay-Serial"]
            timestamp = headers["Wechatpay-Timestamp"]
            nonce = headers["Wechatpay-Nonce"]
            signature = headers["Wechatpay-Signature"]
            if len(timestamp) > 12 or not timestamp.isascii() or not timestamp.isdigit():
                raise ValueError("invalid timestamp")
            if serial != self.settings.wechat_pay_public_key_id or abs(int(timestamp) - time.time()) > 300:
                raise ValueError("untrusted key or timestamp")
            if not nonce or len(nonce) > 256 or len(signature) > 512:
                raise ValueError("invalid nonce")
            message = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n"
            self.public.verify(base64.b64decode(signature, validate=True), message, padding.PKCS1v15(), hashes.SHA256())
        except (KeyError, ValueError, InvalidSignature) as exc:
            raise PayProtocolError() from exc

    async def request(self, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, Any]:
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        authorization = self.authorization(method, path, body)
        content = bytearray()
        try:
            async with asyncio.timeout(10):
                async with self.http.stream(
                    method,
                    "https://api.mch.weixin.qq.com" + path,
                    content=body,
                    headers={
                        "Authorization": authorization,
                        "Wechatpay-Serial": self.settings.wechat_pay_public_key_id,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                ) as response:
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 1024 * 1024:
                            raise PayProtocolError("微信支付响应超过处理上限")
        except (httpx.HTTPError, TimeoutError) as exc:
            raise PayProtocolError("微信支付结果暂未确认，请稍后查询") from exc
        self.verify(response.headers, bytes(content))
        try:
            result = json.loads(content) if content else {}
            if not isinstance(result, dict):
                raise ValueError("invalid object")
        except ValueError as exc:
            raise PayProtocolError() from exc
        if not response.is_success:
            code = result.get("code")
            raise PayProtocolError(
                "微信支付请求未完成，请查询原交易", channel_code=code if isinstance(code, str) else ""
            )
        return result

    def parameters(self, prepay_id: str) -> PayParameters:
        timestamp, nonce = str(int(time.time())), secrets.token_hex(16)
        package = "prepay_id=" + prepay_id
        return PayParameters(
            timeStamp=timestamp,
            nonceStr=nonce,
            package=package,
            paySign=self.sign(f"{self.settings.wechat_app_id}\n{timestamp}\n{nonce}\n{package}\n".encode()),
        )

    def notification(self, headers: httpx.Headers, body: bytes) -> tuple[str, str, dict[str, Any]]:
        self.verify(headers, body)
        try:
            envelope = json.loads(body)
            if not isinstance(envelope, dict):
                raise ValueError("invalid notification")
            event_id, event_type, resource = envelope["id"], envelope["event_type"], envelope["resource"]
            if not isinstance(event_id, str) or not 1 <= len(event_id) <= 128 or not isinstance(event_type, str):
                raise ValueError("invalid event")
            if resource["algorithm"] != "AEAD_AES_256_GCM":
                raise ValueError("invalid algorithm")
            plain = AESGCM(self.settings.wechat_pay_api_v3_key.encode()).decrypt(
                resource["nonce"].encode(),
                base64.b64decode(resource["ciphertext"], validate=True),
                resource.get("associated_data", "").encode(),
            )
            data = json.loads(plain)
            if not isinstance(data, dict):
                raise ValueError("invalid resource")
            return event_id, event_type, data
        except (KeyError, TypeError, AttributeError, ValueError, InvalidTag) as exc:
            raise PayProtocolError("微信通知解密或结构校验失败", status=400) from exc
