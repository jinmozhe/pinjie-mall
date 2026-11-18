"""Channel protocol regression assets. Run only with explicit pytest authorization."""

import base64
import hashlib
import json
import re
import time
from decimal import Decimal

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.core.payload_sanitizer import is_sensitive_route
from app.services.wechat_pay_client import PayProtocolError, WechatPayClient, cents
from app.services.wechat_reconciliation import parse_bill


@pytest.fixture
def pay_material(tmp_path):
    merchant = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    platform = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path, public_path = tmp_path / "merchant.pem", tmp_path / "platform.pem"
    private_path.write_bytes(
        merchant.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    public_path.write_bytes(
        platform.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    settings = Settings(
        _env_file=None,
        WECHAT_PAY_ENABLED=True,
        WECHAT_APP_ID="wx0123456789abcdef",
        WECHAT_PAY_MCH_ID="1900000100",
        WECHAT_PAY_MERCHANT_SERIAL_NO="AB1234",
        WECHAT_PAY_PRIVATE_KEY_PATH=str(private_path),
        WECHAT_PAY_PUBLIC_KEY_PATH=str(public_path),
        WECHAT_PAY_PUBLIC_KEY_ID="PUB_KEY_ID_unit",
        WECHAT_PAY_API_V3_KEY="a" * 32,
        WECHAT_PAY_CONFIG_VERSION="unit-v1",
        WECHAT_PAY_NOTIFY_URL="https://pay.example.com/api/v1/payments/wechat/notify",
        WECHAT_PAY_REFUND_NOTIFY_URL="https://pay.example.com/api/v1/refunds/wechat/notify",
    )
    return settings, merchant, platform


def signed_headers(platform, body, *, timestamp=None):
    stamp, nonce = timestamp or str(int(time.time())), "unit-nonce"
    signature = platform.sign(
        stamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n", padding.PKCS1v15(), hashes.SHA256()
    )
    return httpx.Headers(
        {
            "Wechatpay-Serial": "PUB_KEY_ID_unit",
            "Wechatpay-Timestamp": stamp,
            "Wechatpay-Nonce": nonce,
            "Wechatpay-Signature": base64.b64encode(signature).decode(),
        }
    )


@pytest.mark.asyncio
async def test_request_signature_uses_exact_method_path_query_and_body(pay_material):
    settings, merchant, platform = pay_material

    def handler(request):
        auth = dict(re.findall(r'([a-z_]+)="([^"]+)"', request.headers["Authorization"]))
        canonical = (
            f"{request.method}\n{request.url.raw_path.decode()}\n{auth['timestamp']}\n{auth['nonce_str']}\n".encode()
            + request.content
            + b"\n"
        )
        merchant.public_key().verify(
            base64.b64decode(auth["signature"]), canonical, padding.PKCS1v15(), hashes.SHA256()
        )
        body = b'{"prepay_id":"unit-prepay"}'
        return httpx.Response(200, content=body, headers=signed_headers(platform, body))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = WechatPayClient(settings, http)
        assert await client.request("POST", "/v3/unit?name=test", {"amount": 101}) == {"prepay_id": "unit-prepay"}
        params = client.parameters("unit-prepay")
        canonical = f"{settings.wechat_app_id}\n{params.time_stamp}\n{params.nonce_str}\n{params.package}\n".encode()
        merchant.public_key().verify(base64.b64decode(params.pay_sign), canonical, padding.PKCS1v15(), hashes.SHA256())


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["changed_body", "unknown_key", "expired", "invalid_base64", "signature_probe"])
async def test_rejects_untrusted_response(pay_material, kind):
    settings, _, platform = pay_material
    body = b'{"trade_state":"SUCCESS"}'
    headers = signed_headers(platform, body, timestamp="1" if kind == "expired" else None)
    if kind == "unknown_key":
        headers["Wechatpay-Serial"] = "PUB_KEY_ID_untrusted"
    if kind == "invalid_base64":
        headers["Wechatpay-Signature"] = "not-base64%"
    if kind == "signature_probe":
        headers["Wechatpay-Signature"] = "WECHATPAY/SIGNTEST/unit"
    async with httpx.AsyncClient() as http:
        client = WechatPayClient(settings, http)
        with pytest.raises(PayProtocolError):
            client.verify(headers, body + b" " if kind == "changed_body" else body)


@pytest.mark.asyncio
async def test_notification_decrypts_only_after_signature_verification(pay_material):
    settings, _, platform = pay_material
    plain = {"mchid": settings.wechat_pay_mch_id, "out_trade_no": "unit-order"}
    cipher = AESGCM(settings.wechat_pay_api_v3_key.encode()).encrypt(
        b"unit-nonce12", json.dumps(plain).encode(), b"transaction"
    )
    body = json.dumps(
        {
            "id": "notice-1",
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "algorithm": "AEAD_AES_256_GCM",
                "nonce": "unit-nonce12",
                "associated_data": "transaction",
                "ciphertext": base64.b64encode(cipher).decode(),
            },
        }
    ).encode()
    async with httpx.AsyncClient() as http:
        client = WechatPayClient(settings, http)
        assert client.notification(signed_headers(platform, body), body) == ("notice-1", "TRANSACTION.SUCCESS", plain)
        wrong = settings.model_copy(update={"wechat_pay_api_v3_key": "b" * 32})
        with pytest.raises(PayProtocolError):
            WechatPayClient(wrong, http).notification(signed_headers(platform, body), body)


@pytest.mark.asyncio
async def test_bill_download_requires_trusted_host_and_signed_metadata_hash(pay_material):
    settings, _, _ = pay_material
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"bill"))) as http:
        client = WechatPayClient(settings, http)
        metadata = {
            "hash_type": "SHA1",
            "hash_value": hashlib.sha1(b"bill").hexdigest(),
            "download_url": "https://api.mch.weixin.qq.com/v3/billdownload/file?token=unit",
        }
        assert await client.download_bill(metadata) == b"bill"
        with pytest.raises(PayProtocolError):
            await client.download_bill({**metadata, "download_url": "https://evil.example/v3/billdownload/file"})
        with pytest.raises(PayProtocolError):
            await client.download_bill({**metadata, "hash_value": "0" * 40})


@pytest.mark.parametrize("amount", ["0", "-1", "0.001", "21474836.48", "NaN", "Infinity"])
def test_rejects_invalid_money(amount):
    with pytest.raises(PayProtocolError):
        cents(Decimal(amount))


def test_money_conversion_is_exact():
    assert cents(Decimal("123456.78")) == 12345678


def test_enabled_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(_env_file=None, WECHAT_PAY_ENABLED=True).validate_wechat_pay()
    Settings(_env_file=None).validate_wechat_pay()


@pytest.mark.parametrize("prefix", ["/api/v1", "/custom/api"])
def test_payment_notification_bodies_are_never_loggable(prefix):
    assert is_sensitive_route(prefix + "/payments/wechat/notify")
    assert is_sensitive_route(prefix + "/refunds/wechat/notify")


def test_key_material_cannot_be_loaded_from_public_media(pay_material):
    settings, _, _ = pay_material
    unsafe = settings.model_copy(
        update={"wechat_pay_private_key_path": str(settings.upload_local_root / "private.pem")}
    )
    with pytest.raises(ValueError, match="public media"):
        unsafe.validate_wechat_pay()


def test_bill_uses_gross_order_amount_not_discounted_settlement():
    content = (
        "交易时间,公众账号ID,商户号,微信订单号,商户订单号,交易状态,货币种类,应结订单金额,订单金额\n"
        "`2026-11-17 12:00:00,`wxunit,`1900000100,`wxtransaction,`merchantorder,`SUCCESS,`CNY,`8.00,`10.00\n"
        "总交易单数,订单总金额\n`1,`10.00\n"
    ).encode()
    records, pending = parse_bill(content, merchant_id="1900000100", bill_date="2026-11-17", kind="SUCCESS")
    assert pending == 0 and len(records) == 1
    assert records[0].amount == Decimal("10.00")
    with pytest.raises(PayProtocolError):
        parse_bill(
            content.replace(b"`1,`10.00", b"`2,`10.00"),
            merchant_id="1900000100",
            bill_date="2026-11-17",
            kind="SUCCESS",
        )
