"""Report committed fulfillment facts to the WeChat miniapp order platform."""

import asyncio
import hashlib
from uuid import UUID

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.repositories.external_identity import WechatIdentityRepository
from app.db.transaction import transaction_scope
from app.domains.lifecycle.repository import LifecycleRepository
from app.domains.lifecycle.schemas import WechatReceiptRead
from app.domains.orders import OrderQueryService
from app.services.orders import OrderService
from app.services.wechat_pay_client import PayProtocolError
from app.services.wechat_phone import WechatPhoneClient


class WechatShippingService:
    def __init__(
        self, session: AsyncSession, settings: Settings, http: httpx.AsyncClient | None, redis: Redis | None
    ) -> None:
        self.session, self.settings, self.http = session, settings, http
        self.tokens = WechatPhoneClient(settings, redis, http)

    async def call(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        if not self.settings.wechat_shipping_enabled or self.http is None:
            raise PayProtocolError("微信发货管理尚未配置", status=503)
        token = await self.tokens.application_token()
        try:
            async with asyncio.timeout(8):
                response = await self.http.post(
                    "https://api.weixin.qq.com" + path, json=payload, params={"access_token": token}
                )
            if response.status_code != 200 or len(response.content) > 65536:
                raise ValueError("invalid platform response")
            result = response.json()
            if not isinstance(result, dict) or result.get("errcode") != 0:
                raise ValueError("platform operation failed")
            return result
        except httpx.HTTPError, TimeoutError, ValueError:
            raise PayProtocolError("微信发货管理结果未确认，请核对原订单") from None

    async def upload(self, fulfillment_id: UUID) -> None:
        repository = LifecycleRepository(self.session)
        async with transaction_scope(self.session):
            fulfillment = await repository.fulfillment_by_id(fulfillment_id)
            if fulfillment is None:
                raise PayProtocolError("履约记录不存在", status=404)
            order = await OrderQueryService(self.session).order(fulfillment.order_id)
            if order is None or order.accepted_payment_attempt_id is None:
                raise PayProtocolError("履约缺少已接受的渠道付款", status=409)
            payment = await repository.payment(order.accepted_payment_attempt_id)
            if payment is None or payment.channel != "wechat" or payment.status != "succeeded":
                raise PayProtocolError("履约付款事实不匹配", status=409)
            if (
                payment.channel_context.get("merchant_id") != self.settings.wechat_pay_mch_id
                or payment.channel_context.get("app_id") != self.settings.wechat_app_id
            ):
                raise PayProtocolError("履约商户配置不匹配", status=409)
            identity = await WechatIdentityRepository(self.session).for_user(
                order.user_id, self.settings.wechat_app_id or ""
            )
            if identity is None or hashlib.sha256(
                identity.subject_id.encode()
            ).hexdigest() != payment.channel_context.get("payer_hash"):
                raise PayProtocolError("履约支付者身份不匹配", status=409)
            line: dict[str, object] = {"item_desc": "商城订单商品"}
            if fulfillment.product_type == "physical":
                carrier = self.settings.wechat_shipping_carriers.get(fulfillment.carrier or "")
                if not carrier or not fulfillment.tracking_number or not fulfillment.shipped_at:
                    raise PayProtocolError("请配置承运人对应的微信物流公司编码并核实运单", status=409)
                line.update({"tracking_no": fulfillment.tracking_number, "express_company": carrier})
                detail = await OrderService(self.session).read(order.user_id, order.id)
                phone = (detail.address_snapshot or {}).get("mobile")
                if isinstance(phone, str) and len(phone) >= 4:
                    line["contact"] = {"receiver_contact": "****" + phone[-4:]}
                occurred_at = fulfillment.shipped_at
            else:
                if fulfillment.status != "delivered" or fulfillment.delivered_at is None:
                    raise PayProtocolError("虚拟商品尚未完成交付", status=409)
                occurred_at = fulfillment.delivered_at
            payload: dict[str, object] = {
                "order_key": {"order_number_type": 2, "transaction_id": payment.channel_transaction_id},
                "logistics_type": 1 if fulfillment.product_type == "physical" else 3,
                "delivery_mode": 1,
                "shipping_list": [line],
                "upload_time": occurred_at.isoformat(),
                "payer": {"openid": identity.subject_id},
            }
        # A retry uses the same transaction id, fulfillment and upload_time.
        await self.call("/wxa/sec/order/upload_shipping_info", payload)

    async def receipt(self, user_id: UUID, order_id: UUID) -> WechatReceiptRead:
        async with transaction_scope(self.session):
            order = await OrderQueryService(self.session).user_order(user_id, order_id)
            if order is None or order.accepted_payment_attempt_id is None:
                raise PayProtocolError("订单不存在或尚未成交", status=404)
            payment = await LifecycleRepository(self.session).payment(order.accepted_payment_attempt_id)
            if payment is None or payment.channel != "wechat" or payment.status != "succeeded":
                raise PayProtocolError("订单没有微信付款", status=409)
            if (
                payment.channel_context.get("merchant_id") != self.settings.wechat_pay_mch_id
                or payment.channel_context.get("app_id") != self.settings.wechat_app_id
            ):
                raise PayProtocolError("订单支付配置不匹配", status=409)
            transaction_id = payment.channel_transaction_id
        result = await self.call("/wxa/sec/order/get_order", {"transaction_id": transaction_id})
        platform_order = result.get("order")
        if not isinstance(platform_order, dict) or platform_order.get("transaction_id") != transaction_id:
            raise PayProtocolError("微信订单归属未确认")
        state = platform_order.get("order_state")
        if type(state) is not int or state not in {1, 2, 3, 4, 5, 6}:
            raise PayProtocolError("微信订单状态未确认")
        return WechatReceiptRead(confirmed=state in {3, 4}, platform_state=state)
