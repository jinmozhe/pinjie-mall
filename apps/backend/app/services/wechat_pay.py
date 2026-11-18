"""Transaction orchestration for the ordinary-merchant WeChat payment channel."""

import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.commerce_lifecycle import (
    PaymentAttempt,
    PaymentEvent,
    RefundAttempt,
    RefundEvent,
    WechatPayNotification,
)
from app.db.repositories.external_identity import WechatIdentityRepository
from app.db.transaction import transaction_scope
from app.domains.durable_tasks import DurableTaskService, TaskDeferred
from app.domains.lifecycle import (
    PaymentAttemptCreate,
    PaymentAttemptRead,
    PaymentStatusRead,
    VerifiedPaymentConfirmation,
    VerifiedRefundConfirmation,
)
from app.domains.lifecycle.repository import LifecycleRepository
from app.services.orders import OrderService
from app.services.payment_lifecycle import LifecycleService
from app.services.wechat_pay_client import (
    PayProtocolError,
    PayRefund,
    PayTransaction,
    WechatPayClient,
    cents,
    payload_hash,
)


class WechatPaymentService:
    def __init__(self, session: AsyncSession, settings: Settings, client: WechatPayClient | None) -> None:
        self.session, self.settings, self.client = session, settings, client
        self.lifecycle = LifecycleService(session)
        self.repository = LifecycleRepository(session)
        self.tasks = DurableTaskService(session)

    def require_client(self) -> WechatPayClient:
        if self.client is None:
            raise PayProtocolError("微信支付渠道尚未配置", status=503)
        return self.client

    def snapshot(self, openid: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "merchant_id": self.settings.wechat_pay_mch_id,
            "app_id": self.settings.wechat_app_id,
            "config_version": self.settings.wechat_pay_config_version,
            "payer_hash": hashlib.sha256(openid.encode()).hexdigest(),
        }

    def validate_context(self, attempt: PaymentAttempt) -> None:
        if (
            attempt.channel != "wechat"
            or attempt.channel_context.get("merchant_id") != self.settings.wechat_pay_mch_id
            or attempt.channel_context.get("app_id") != self.settings.wechat_app_id
        ):
            raise PayProtocolError("历史支付配置与当前商户不一致，需人工核对", status=409)

    def read_attempt(self, attempt: PaymentAttempt) -> PaymentAttemptRead:
        result = PaymentAttemptRead.model_validate(attempt)
        if (
            self.client
            and self.settings.wechat_pay_enabled
            and attempt.status == "pending"
            and not attempt.close_requested
            and attempt.prepay_id
            and attempt.channel_expires_at
            and attempt.channel_expires_at > datetime.now(UTC)
        ):
            self.validate_context(attempt)
            result.payment_parameters = self.client.parameters(attempt.prepay_id)
        return result

    async def status(self, user_id: UUID, order_id: UUID, request_id: UUID | None = None) -> PaymentStatusRead:
        async with transaction_scope(self.session):
            order = await self.lifecycle.orders.user_order(user_id, order_id)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            if request_id is not None:
                attempt = await self.repository.payment_by_request(user_id, request_id)
                if attempt is not None and attempt.order_id != order_id:
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_REQUEST_CONFLICT, message="支付请求归属冲突"
                    )
            else:
                rows = await self.repository.payment_attempts_for_order(order_id)
                wechat_rows = [row for row in reversed(rows) if row.channel == "wechat"]
                attempt = next(
                    (row for row in wechat_rows if row.status in {"created", "pending", "unknown", "succeeded"}), None
                )
                if attempt is None:
                    attempt = next(iter(wechat_rows), None)
                if order.accepted_payment_attempt_id is not None:
                    attempt = next((row for row in wechat_rows if row.id == order.accepted_payment_attempt_id), None)
            return PaymentStatusRead(
                enabled=self.settings.wechat_pay_enabled and self.client is not None,
                attempt=self.read_attempt(attempt) if attempt else None,
                wechat_transaction_id=attempt.channel_transaction_id
                if attempt and attempt.status == "succeeded"
                else None,
                wechat_receipt_enabled=self.settings.wechat_shipping_enabled,
            )

    async def initiate(self, user_id: UUID, order_id: UUID, data: PaymentAttemptCreate) -> PaymentAttemptRead:
        if data.channel != "wechat" or not self.settings.wechat_pay_enabled:
            return await self.lifecycle.initiate_payment(user_id, order_id, data)
        self.require_client()
        async with transaction_scope(self.session):
            await self.repository.lock_key("payment-request", f"{user_id}:{data.request_id}")
            await self.lifecycle.access.require_active_user(user_id)
            order = await self.lifecycle.orders.user_order(user_id, order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            existing = await self.repository.payment_by_request(user_id, data.request_id, lock=True)
            if existing is not None:
                if existing.order_id != order_id or existing.channel != "wechat":
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_REQUEST_CONFLICT, message="支付请求归属冲突"
                    )
                return self.read_attempt(existing)
            if order.status != "pending_payment" or order.total_amount <= 0:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能发起渠道支付"
                )
            for active in await self.repository.payment_attempts_for_order(order_id, lock=True):
                if active.status in {"created", "pending", "unknown", "succeeded"}:
                    return self.read_attempt(active)
            if order.expires_at <= datetime.now(UTC) + timedelta(seconds=65):
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_EXPIRED, message="订单剩余支付时间不足，请等待订单关闭"
                )
            identity = await WechatIdentityRepository(self.session).for_user(user_id, self.settings.wechat_app_id or "")
            if identity is None:
                raise PayProtocolError("当前账户缺少对应小程序的微信身份", status=409)
            cents(order.total_amount)
            attempt = PaymentAttempt(
                id=new_uuid7(),
                order_id=order_id,
                user_id=user_id,
                request_id=data.request_id,
                request_hash=payload_hash({"channel": data.channel}),
                channel="wechat",
                merchant_reference=new_uuid7().hex,
                status="created",
                amount=order.total_amount,
                currency=order.currency,
                channel_context=self.snapshot(identity.subject_id),
                revision=1,
                channel_expires_at=order.expires_at,
                close_requested=False,
            )
            await self.repository.save(attempt)
            await self.repository.save(
                PaymentEvent(
                    payment_attempt_id=attempt.id,
                    revision=1,
                    from_status=None,
                    to_status="created",
                    reason="微信支付意图已持久化",
                )
            )
            await self.enqueue("payment_submit", attempt.id)
            await self.enqueue("payment_query", attempt.id, delay=15)
            attempt_id = attempt.id
        try:
            await self.submit(attempt_id)
        except PayProtocolError:
            async with transaction_scope(self.session):
                saved = await self.locked_payment(attempt_id)
                if saved.status not in {"succeeded", "closed"}:
                    saved.unavailable_reason = "支付结果未确认，请查询原交易或联系支持"
                    await self.transition(saved, "unknown", "同步下单结果未知，持久任务继续核对")
                    await self.repository.save(saved)
        except TaskDeferred:
            result = await self.status(user_id, order_id)
            if result.attempt is None:
                raise PayProtocolError("支付意图尚未读取，请查询原请求", status=409) from None
            return result.attempt
        async with transaction_scope(self.session):
            final_attempt = await self.repository.payment(attempt_id, lock=True)
            if final_attempt is None:
                raise RuntimeError("persisted payment disappeared")
            return self.read_attempt(final_attempt)

    async def enqueue(self, kind: str, entity_id: UUID, *, delay: int = 0) -> None:
        key = (
            "notification_id"
            if kind == "wechat_notification"
            else ("refund_attempt_id" if kind.startswith("refund_") else "payment_attempt_id")
        )
        await self.tasks.enqueue_in_open_transaction(
            task_type=kind,
            business_key=f"{kind.replace('_', '-')}:{entity_id}",
            payload={"schema_version": 1, key: str(entity_id)},
            available_at=datetime.now(UTC) + timedelta(seconds=delay),
            max_failures=10,
        )

    async def transition(self, attempt: PaymentAttempt, status: str, reason: str) -> None:
        if attempt.status == status or attempt.status == "succeeded":
            return
        previous = attempt.status
        attempt.status, attempt.revision = status, attempt.revision + 1
        if status == "closed":
            attempt.prepay_id = None
        await self.repository.save(attempt)
        await self.repository.save(
            PaymentEvent(
                payment_attempt_id=attempt.id,
                revision=attempt.revision,
                from_status=previous,
                to_status=status,
                reason=reason,
            )
        )

    async def locked_payment(self, attempt_id: UUID) -> PaymentAttempt:
        observed = await self.repository.payment(attempt_id)
        if observed is None:
            raise PayProtocolError("支付意图不存在", status=404)
        await self.lifecycle.orders.order(observed.order_id, lock=True)
        attempt = await self.repository.payment(attempt_id, lock=True)
        if attempt is None:
            raise RuntimeError("payment disappeared")
        self.validate_context(attempt)
        return attempt

    async def submit(self, attempt_id: UUID, *, recover: bool = False) -> None:
        client = self.require_client()
        async with transaction_scope(self.session):
            attempt = await self.locked_payment(attempt_id)
            if attempt.status in {"closed", "succeeded", "unavailable"} or attempt.prepay_id:
                return
            now = datetime.now(UTC)
            if attempt.submission_started_at is not None:
                # Recovery goes through the stable merchant number, never an automatic second submit.
                if attempt.submission_started_at > now - timedelta(seconds=30):
                    raise TaskDeferred(30)
                if not recover:
                    await self.enqueue("payment_query", attempt.id)
                    return
            if (
                attempt.close_requested
                or not attempt.channel_expires_at
                or attempt.channel_expires_at <= now + timedelta(seconds=65)
            ):
                if attempt.submission_started_at is None:
                    await self.transition(attempt, "closed", "提交前支付窗口已关闭")
                return
            identity = await WechatIdentityRepository(self.session).for_user(
                attempt.user_id, self.settings.wechat_app_id or ""
            )
            if identity is None or hashlib.sha256(
                identity.subject_id.encode()
            ).hexdigest() != attempt.channel_context.get("payer_hash"):
                raise PayProtocolError("支付者身份发生变化", status=409)
            request: dict[str, object] = {
                "appid": self.settings.wechat_app_id,
                "mchid": self.settings.wechat_pay_mch_id,
                "description": "商城订单",
                "out_trade_no": attempt.merchant_reference,
                "time_expire": attempt.channel_expires_at.isoformat(),
                "notify_url": self.settings.wechat_pay_notify_url,
                "amount": {"total": cents(attempt.amount), "currency": attempt.currency},
                "payer": {"openid": identity.subject_id},
            }
            attempt.submission_started_at = now
            await self.transition(attempt, "unknown", "下单请求已领取，等待渠道确认")
        response = await client.request("POST", "/v3/pay/transactions/jsapi", request)
        prepay_id = response.get("prepay_id")
        if not isinstance(prepay_id, str) or not 1 <= len(prepay_id) <= 128:
            raise PayProtocolError()
        async with transaction_scope(self.session):
            attempt = await self.locked_payment(attempt_id)
            if attempt.status not in {"succeeded", "closed"}:
                attempt.prepay_id = prepay_id
                attempt.unavailable_reason = None
                await self.transition(attempt, "pending", "微信预支付会话已确认")

    async def query(self, attempt_id: UUID, *, close: bool = False) -> None:
        client = self.require_client()
        if close:
            async with transaction_scope(self.session):
                attempt = await self.locked_payment(attempt_id)
                attempt.close_requested = True
                await self.repository.save(attempt)
        async with transaction_scope(self.session):
            attempt = await self.locked_payment(attempt_id)
            if attempt.status in {"succeeded", "unavailable"}:
                return
            finished = attempt.status == "closed"
            if not finished and attempt.submission_started_at is None:
                if attempt.close_requested or (
                    attempt.channel_expires_at and attempt.channel_expires_at <= datetime.now(UTC)
                ):
                    await self.transition(attempt, "closed", "渠道请求尚未发送，关闭支付")
                    finished = True
                else:
                    raise TaskDeferred()
            if (
                not finished
                and attempt.submission_started_at
                and attempt.submission_started_at > datetime.now(UTC) - timedelta(seconds=15)
            ):
                raise TaskDeferred()
            reference = quote(attempt.merchant_reference, safe="")
            should_close = attempt.close_requested or bool(
                attempt.channel_expires_at and attempt.channel_expires_at <= datetime.now(UTC)
            )
            created = attempt.created_at
        if finished:
            await self.expire_order(attempt.order_id)
            return
        try:
            data = await client.request(
                "GET", f"/v3/pay/transactions/out-trade-no/{reference}?mchid={self.settings.wechat_pay_mch_id}"
            )
        except PayProtocolError as exc:
            if exc.channel_code != "ORDER_NOT_EXIST":
                raise
            # A previous request can still be in flight. Keep the intent unresolved until its payment window ends.
            if not should_close:
                await self.submit(attempt_id, recover=True)
                raise TaskDeferred(30) from exc
            if datetime.now(UTC) < created + timedelta(seconds=90):
                raise TaskDeferred(30) from exc
            async with transaction_scope(self.session):
                attempt = await self.locked_payment(attempt_id)
                if not attempt.channel_expires_at or attempt.channel_expires_at > datetime.now(UTC):
                    raise TaskDeferred(30)
                await self.transition(attempt, "closed", "支付窗口结束且渠道确认无订单")
            await self.expire_order(attempt.order_id)
            return
        try:
            payment = PayTransaction.model_validate(data)
        except ValidationError as exc:
            raise PayProtocolError() from exc
        if payment.trade_state == "SUCCESS":
            await self.confirm_payment(payment)
            return
        async with transaction_scope(self.session):
            attempt = await self.locked_payment(attempt_id)
            self.check_payment_identity(attempt, payment)
            if payment.trade_state in {"CLOSED", "REVOKED", "PAYERROR"}:
                await self.transition(attempt, "closed", "微信确认支付不可继续")
                closed_order = attempt.order_id
            elif payment.trade_state in {"NOTPAY", "USERPAYING"}:
                closed_order = None
            else:
                raise PayProtocolError("微信支付状态需要人工核对", status=409)
        if closed_order is not None:
            await self.expire_order(closed_order)
            return
        if should_close:
            await client.request(
                "POST",
                f"/v3/pay/transactions/out-trade-no/{reference}/close",
                {"mchid": self.settings.wechat_pay_mch_id},
            )
            async with transaction_scope(self.session):
                attempt = await self.locked_payment(attempt_id)
                await self.transition(attempt, "closed", "微信关单成功")
            await self.expire_order(attempt.order_id)
            return
        if payment.trade_state == "NOTPAY":
            await self.submit(attempt_id, recover=True)
        if datetime.now(UTC) - created > timedelta(days=3):
            raise PayProtocolError("支付查询超过恢复窗口，需人工核对", status=409)
        raise TaskDeferred(15)

    async def expire_order(self, order_id: UUID) -> None:
        await OrderService(self.session).complete_channel_close(order_id)

    def check_payment_identity(self, attempt: PaymentAttempt, payment: PayTransaction) -> None:
        self.validate_context(attempt)
        if (
            payment.mchid != self.settings.wechat_pay_mch_id
            or payment.appid != self.settings.wechat_app_id
            or payment.out_trade_no != attempt.merchant_reference
        ):
            raise PayProtocolError("微信订单商户或应用归属不匹配", status=409)

    async def confirm_payment(self, payment: PayTransaction, *, payer_hash: str | None = None) -> None:
        async with transaction_scope(self.session):
            attempt = await self.repository.payment_by_reference(payment.out_trade_no)
            if attempt is None:
                raise PayProtocolError("微信资金流水未匹配本地意图", status=409)
            self.check_payment_identity(attempt, payment)
            digest = payer_hash or (
                hashlib.sha256(payment.payer.openid.encode()).hexdigest() if payment.payer else None
            )
            if (
                payment.trade_state != "SUCCESS"
                or not payment.transaction_id
                or not payment.success_time
                or payment.success_time.tzinfo is None
                or payment.success_time < attempt.created_at.replace(microsecond=0)
                or not payment.amount
                or payment.amount.total != cents(attempt.amount)
                or payment.amount.currency != attempt.currency
                or digest != attempt.channel_context.get("payer_hash")
            ):
                raise PayProtocolError("微信支付资金事实不匹配", status=409)
            await self.lifecycle.confirm_verified_payment_in_open_transaction(
                VerifiedPaymentConfirmation(
                    payment_attempt_id=attempt.id,
                    channel="wechat",
                    channel_transaction_id=payment.transaction_id,
                    amount=attempt.amount,
                    currency="CNY",
                    confirmed_at=payment.success_time,
                    payload_hash=payload_hash(payment.model_dump(mode="json")),
                )
            )

    async def receive(self, headers: httpx.Headers, body: bytes, *, refund: bool) -> None:
        client = self.require_client()
        event_id, event_type, data = client.notification(headers, body)
        allowed = {"REFUND.SUCCESS", "REFUND.ABNORMAL", "REFUND.CLOSED"} if refund else {"TRANSACTION.SUCCESS"}
        if event_type not in allowed or data.get("mchid") != self.settings.wechat_pay_mch_id:
            raise PayProtocolError("微信通知类型或商户不匹配", status=400)
        try:
            if refund:
                amount = data.get("amount")
                if not isinstance(amount, dict):
                    raise ValueError("missing refund amount")
                # Domestic refund notifications omit currency; this protocol only supports CNY.
                normalized = PayRefund.model_validate(
                    {**data, "status": data.get("refund_status"), "amount": {"currency": "CNY", **amount}}
                ).model_dump(mode="json")
                if event_type != "REFUND." + str(normalized["status"]):
                    raise ValueError("inconsistent refund event")
            else:
                payment = PayTransaction.model_validate(data)
                if (
                    payment.appid != self.settings.wechat_app_id
                    or payment.trade_state != "SUCCESS"
                    or payment.payer is None
                ):
                    raise ValueError("inconsistent payment event")
                normalized = payment.model_dump(mode="json", exclude={"payer"})
                normalized["payer_hash"] = hashlib.sha256(payment.payer.openid.encode()).hexdigest()
        except (ValidationError, ValueError) as exc:
            raise PayProtocolError("微信通知字段无效", status=400) from exc
        digest = payload_hash({"event_type": event_type, "payload": normalized})
        async with transaction_scope(self.session):
            await self.repository.lock_key("wechat-notification", f"{self.settings.wechat_pay_mch_id}:{event_id}")
            existing = await self.repository.notification_by_reference(self.settings.wechat_pay_mch_id, event_id)
            if existing is not None:
                if existing.payload_hash != digest:
                    raise PayProtocolError("重复通知内容冲突", status=409)
                return
            notification = WechatPayNotification(
                id=new_uuid7(),
                merchant_id=self.settings.wechat_pay_mch_id,
                notification_id=event_id,
                event_type=event_type,
                payload_hash=digest,
                config_version=self.settings.wechat_pay_config_version,
                verified_payload=normalized,
                status="pending",
            )
            await self.repository.save(notification)
            await self.enqueue("wechat_notification", notification.id)

    async def process_notification(self, notification_id: UUID) -> None:
        async with transaction_scope(self.session):
            row = await self.repository.notification(notification_id)
            if row is None:
                raise PayProtocolError("支付通知不存在", status=404)
            if row.status == "processed":
                return
            data, event = dict(row.verified_payload), row.event_type
        if event == "TRANSACTION.SUCCESS":
            await self.confirm_payment(PayTransaction.model_validate(data), payer_hash=str(data["payer_hash"]))
        else:
            await self.confirm_refund(PayRefund.model_validate(data))
        async with transaction_scope(self.session):
            row = await self.repository.notification(notification_id)
            if row is None:
                raise RuntimeError("payment notification disappeared")
            row.status = "processed"
            await self.repository.save(row)

    async def refund(self, refund_id: UUID, *, submit: bool) -> None:
        client = self.require_client()
        async with transaction_scope(self.session):
            observed = await self.repository.refund_attempt(refund_id)
            if observed is None:
                raise PayProtocolError("退款执行不存在", status=404)
            payment = await self.locked_payment(observed.payment_attempt_id)
            attempt = await self.repository.refund_attempt(refund_id, lock=True)
            if attempt is None:
                raise RuntimeError("refund disappeared")
            if attempt.status in {"succeeded", "closed"}:
                return
            if attempt.channel != "wechat" or payment.status != "succeeded":
                raise PayProtocolError("原支付资金事实未确认", status=409)
            reference, started = attempt.merchant_refund_reference, attempt.created_at
            can_resubmit = attempt.status in {"created", "unknown"}
            do_submit = submit and attempt.status == "created"
            if do_submit:
                await self.refund_transition(attempt, "unknown", "退款请求已领取，等待渠道确认")
                await self.enqueue("refund_query", attempt.id, delay=30)
            request: dict[str, object] = {
                "transaction_id": payment.channel_transaction_id,
                "out_refund_no": reference,
                "notify_url": self.settings.wechat_pay_refund_notify_url,
                "amount": {
                    "refund": cents(attempt.amount),
                    "total": cents(payment.amount),
                    "currency": attempt.currency,
                },
            }
        try:
            data = await client.request(
                "POST" if do_submit else "GET",
                "/v3/refund/domestic/refunds"
                if do_submit
                else f"/v3/refund/domestic/refunds/{quote(reference, safe='')}",
                request if do_submit else None,
            )
        except PayProtocolError as exc:
            if (
                can_resubmit
                and exc.channel_code == "RESOURCE_NOT_EXISTS"
                and datetime.now(UTC) - started > timedelta(seconds=60)
            ):
                # Same refund number is the channel idempotency key; querying precedes resubmission.
                data = await client.request("POST", "/v3/refund/domestic/refunds", request)
            else:
                raise
        try:
            result = PayRefund.model_validate(data)
        except ValidationError as exc:
            raise PayProtocolError() from exc
        await self.confirm_refund(result)
        if result.status == "ABNORMAL":
            raise PayProtocolError("退款异常，需在微信商户平台处理后恢复查询任务", status=409)
        if result.status == "PROCESSING":
            if datetime.now(UTC) - started > timedelta(days=7):
                raise PayProtocolError("退款超过自动恢复窗口，需人工核对", status=409)
            raise TaskDeferred(60)

    async def refund_transition(self, attempt: RefundAttempt, status: str, reason: str) -> None:
        if attempt.status == status or attempt.status == "succeeded":
            return
        previous = attempt.status
        attempt.status, attempt.revision = status, attempt.revision + 1
        await self.repository.save(attempt)
        await self.repository.save(
            RefundEvent(
                refund_attempt_id=attempt.id,
                refund_request_id=None,
                event_scope="attempt",
                event_type="state_changed",
                revision=attempt.revision,
                from_status=previous,
                to_status=status,
                actor_type="channel",
                reason=reason,
            )
        )

    async def confirm_refund(self, result: PayRefund) -> None:
        async with transaction_scope(self.session):
            await self.repository.lock_key("refund", f"wechat:{result.refund_id}")
            observed = await self.repository.refund_by_reference(result.out_refund_no)
            if observed is None:
                raise PayProtocolError("退款流水未匹配本地执行", status=409)
            payment = await self.locked_payment(observed.payment_attempt_id)
            attempt = await self.repository.refund_attempt(observed.id, lock=True)
            if (
                attempt is None
                or (result.mchid is not None and result.mchid != self.settings.wechat_pay_mch_id)
                or result.transaction_id != payment.channel_transaction_id
                or result.out_trade_no != payment.merchant_reference
                or result.amount.total != cents(payment.amount)
                or result.amount.refund != cents(attempt.amount)
                or result.amount.currency != attempt.currency
            ):
                raise PayProtocolError("退款渠道资金事实不匹配", status=409)
            if result.status == "SUCCESS":
                if result.success_time is None or result.success_time.tzinfo is None:
                    raise PayProtocolError("退款成功时间无效")
                await self.lifecycle.confirm_verified_refund_in_open_transaction(
                    VerifiedRefundConfirmation(
                        refund_attempt_id=attempt.id,
                        channel="wechat",
                        payment_transaction_id=result.transaction_id,
                        channel_refund_id=result.refund_id,
                        amount=attempt.amount,
                        currency="CNY",
                        confirmed_at=result.success_time,
                        payload_hash=payload_hash(result.model_dump(mode="json")),
                    )
                )
            elif attempt.status != "succeeded":
                status = {"PROCESSING": "processing", "ABNORMAL": "abnormal", "CLOSED": "closed"}.get(result.status)
                if status is None:
                    raise PayProtocolError("退款状态无法识别")
                if attempt.status == "closed" and status != "closed":
                    raise PayProtocolError("退款终态与渠道事实冲突", status=409)
                await self.refund_transition(attempt, status, "微信退款状态已核验")
