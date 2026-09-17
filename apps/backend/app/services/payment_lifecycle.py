import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models.commerce_lifecycle import (
    Fulfillment,
    FulfillmentEvent,
    PaymentAttempt,
    PaymentEvent,
    ProductReview,
    ReconciliationRecord,
    RefundEvent,
    RefundItem,
    RefundRequest,
)
from app.db.transaction import transaction_scope
from app.domains.distribution import DistributionService
from app.domains.lifecycle.repository import LifecycleRepository
from app.domains.lifecycle.schemas import (
    FulfillmentRead,
    PaymentAttemptCreate,
    PaymentAttemptRead,
    ProductReviewCreate,
    ProductReviewRead,
    ReconciliationRecordCreate,
    ReconciliationRecordRead,
    RefundRequestCreate,
    RefundRequestRead,
    RefundReview,
    ShipmentCreate,
    VerifiedPaymentConfirmation,
    VerifiedRefundConfirmation,
    VirtualDeliveryCreate,
)
from app.domains.orders import OrderQueryService
from app.domains.users import UserAccessService
from app.services.orders import OrderService


class LifecycleService:
    def __init__(
        self,
        session: AsyncSession,
        repository: LifecycleRepository | None = None,
        *,
        orders: OrderQueryService | None = None,
        distribution: DistributionService | None = None,
        access: UserAccessService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or LifecycleRepository(session)
        self.orders = orders or OrderQueryService(session)
        self.distribution = distribution or DistributionService(session)
        self.access = access or UserAccessService(session)

    @staticmethod
    def _request_hash(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _require_aware(value: datetime, label: str) -> datetime:
        if value.tzinfo is None:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message=f"{label}必须包含时区")
        return value.astimezone(UTC)

    @staticmethod
    def _payment_read(value: PaymentAttempt) -> PaymentAttemptRead:
        return PaymentAttemptRead.model_validate(value)

    @staticmethod
    def _fulfillment_read(value: Fulfillment) -> FulfillmentRead:
        return FulfillmentRead.model_validate(value)

    @staticmethod
    def _refund_read(value: RefundRequest) -> RefundRequestRead:
        return RefundRequestRead.model_validate(value)

    async def initiate_payment(self, user_id: UUID, order_id: UUID, data: PaymentAttemptCreate) -> PaymentAttemptRead:
        request_hash = self._request_hash({"channel": data.channel})
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            order = await self.orders.user_order(user_id, order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            existing = await self.repository.payment_by_request(user_id, data.request_id, lock=True)
            if existing is not None:
                if existing.order_id != order_id or existing.request_hash != request_hash:
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_REQUEST_CONFLICT, message="支付请求号已用于其他支付意图"
                    )
                return self._payment_read(existing)
            if order.status != "pending_payment":
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能发起支付")
            if order.total_amount <= 0:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="零金额订单不支持外部资金支付"
                )
            now = datetime.now(UTC)
            if order.expires_at <= now:
                raise AppException(status_code=409, code=ErrorCode.ORDER_EXPIRED, message="订单已超过支付时限")
            attempt = PaymentAttempt(
                id=new_uuid7(),
                order_id=order.id,
                user_id=user_id,
                request_id=data.request_id,
                request_hash=request_hash,
                channel=data.channel,
                merchant_reference=f"M3-{new_uuid7()}",
                status="unavailable",
                amount=order.total_amount,
                currency=order.currency,
                unavailable_reason="支付渠道尚未配置",
                revision=1,
            )
            await self.repository.save(attempt)
            await self.repository.save(
                PaymentEvent(
                    payment_attempt_id=attempt.id,
                    revision=1,
                    from_status=None,
                    to_status="unavailable",
                    reason="支付渠道尚未配置",
                    payload_hash=None,
                )
            )
            return self._payment_read(attempt)

    async def confirm_verified_payment(self, data: VerifiedPaymentConfirmation) -> PaymentAttemptRead:
        async with transaction_scope(self.session):
            return await self.confirm_verified_payment_in_open_transaction(data)

    async def confirm_verified_payment_in_open_transaction(
        self, data: VerifiedPaymentConfirmation
    ) -> PaymentAttemptRead:
        confirmed_at = self._require_aware(data.confirmed_at, "支付确认时间")
        await self.distribution.lock_referral_changes()
        await self.repository.lock_key("payment", f"{data.channel}:{data.channel_transaction_id}")
        attempt = await self.repository.payment(data.payment_attempt_id)
        if attempt is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="支付意图不存在")
        order = await self.orders.order(attempt.order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        attempt = await self.repository.payment(data.payment_attempt_id, lock=True)
        if attempt is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="支付意图不存在")
        if attempt.channel != data.channel:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付渠道不匹配")
        if attempt.status == "succeeded":
            if (
                attempt.channel_transaction_id != data.channel_transaction_id
                or attempt.amount != data.amount
                or attempt.currency != data.currency
                or attempt.confirmed_at != confirmed_at
            ):
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付确认内容冲突")
            return self._payment_read(attempt)
        if attempt.status not in {"created", "pending", "unknown"}:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前支付意图不能确认")
        if attempt.amount != data.amount or attempt.currency != data.currency:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付金额或币种不匹配")
        duplicate = await self.repository.payment_by_transaction(data.channel, data.channel_transaction_id, lock=True)
        if duplicate is not None and duplicate.id != attempt.id:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="渠道交易流水已被其他支付意图使用"
            )
        if order.total_amount != attempt.amount or order.currency != attempt.currency:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单金额或币种不匹配")
        await OrderService(self.session).confirm_payment_in_open_transaction(
            order.id,
            f"{attempt.channel}:{data.channel_transaction_id}",
            confirmed_at,
        )
        fulfillment = await self.repository.fulfillment(order.id, lock=True)
        if fulfillment is None:
            initial_status = "awaiting_shipment" if order.product_type == "physical" else "awaiting_delivery"
            fulfillment = Fulfillment(
                id=new_uuid7(),
                order_id=order.id,
                product_type=order.product_type,
                status=initial_status,
                revision=1,
            )
            await self.repository.save(fulfillment)
            await self.repository.save(
                FulfillmentEvent(
                    fulfillment_id=fulfillment.id,
                    revision=1,
                    from_status=None,
                    to_status=initial_status,
                    actor_type="payment",
                    actor_id=None,
                    reason="可信支付确认后创建履约单",
                )
            )
        previous_status = attempt.status
        attempt.status = "succeeded"
        attempt.channel_transaction_id = data.channel_transaction_id
        attempt.unavailable_reason = None
        attempt.confirmed_at = confirmed_at
        attempt.revision += 1
        await self.repository.save(attempt)
        await self.repository.save(
            PaymentEvent(
                payment_attempt_id=attempt.id,
                revision=attempt.revision,
                from_status=previous_status,
                to_status="succeeded",
                reason="可信渠道支付确认",
                payload_hash=data.payload_hash,
            )
        )
        await self.distribution.freeze_commissions_for_payment_in_open_transaction(
            order_id=order.id,
            source_user_id=order.user_id,
            base_amount=order.items_amount,
            paid_at=confirmed_at,
        )
        return self._payment_read(attempt)

    async def fulfillment_for_user(self, user_id: UUID, order_id: UUID) -> FulfillmentRead:
        order = await self.orders.user_order(user_id, order_id)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        fulfillment = await self.repository.fulfillment(order.id)
        if fulfillment is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单尚未创建履约单")
        return self._fulfillment_read(fulfillment)

    async def admin_fulfillment(self, order_id: UUID) -> FulfillmentRead:
        fulfillment = await self.repository.fulfillment(order_id)
        if fulfillment is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单尚未创建履约单")
        return self._fulfillment_read(fulfillment)

    async def admin_refunds(self, page: int, page_size: int) -> PageResult[RefundRequestRead]:
        rows, total = await self.repository.refund_page(page, page_size)
        return PageResult[RefundRequestRead].create(
            items=[self._refund_read(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def ship_in_open_transaction(self, order_id: UUID, data: ShipmentCreate, actor_id: UUID) -> FulfillmentRead:
        order = await self.orders.order(order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        fulfillment = await self.repository.fulfillment(order.id, lock=True)
        if fulfillment is None or order.status != "paid" or order.product_type != "physical":
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能发货")
        if fulfillment.status != "awaiting_shipment" or fulfillment.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="履约状态已变化，请重新读取"
            )
        now = datetime.now(UTC)
        fulfillment.status = "shipped"
        fulfillment.carrier = data.carrier
        fulfillment.tracking_number = data.tracking_number
        fulfillment.shipped_at = now
        fulfillment.auto_confirm_at = now + timedelta(days=7)
        fulfillment.updated_by_id = actor_id
        fulfillment.revision += 1
        await self.repository.save(fulfillment)
        await self.repository.save(
            FulfillmentEvent(
                fulfillment_id=fulfillment.id,
                revision=fulfillment.revision,
                from_status="awaiting_shipment",
                to_status="shipped",
                actor_type="admin",
                actor_id=actor_id,
                reason="管理员发货",
            )
        )
        return self._fulfillment_read(fulfillment)

    async def deliver_virtual_in_open_transaction(
        self, order_id: UUID, data: VirtualDeliveryCreate, actor_id: UUID
    ) -> FulfillmentRead:
        order = await self.orders.order(order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        fulfillment = await self.repository.fulfillment(order.id, lock=True)
        if fulfillment is None or order.status != "paid" or order.product_type != "virtual":
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能进行虚拟交付")
        if fulfillment.status != "awaiting_delivery" or fulfillment.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="履约状态已变化，请重新读取"
            )
        now = datetime.now(UTC)
        fulfillment.status = "delivered"
        fulfillment.delivery_reference = data.delivery_reference
        fulfillment.delivered_at = now
        fulfillment.updated_by_id = actor_id
        fulfillment.revision += 1
        await self.repository.save(fulfillment)
        await self.repository.save(
            FulfillmentEvent(
                fulfillment_id=fulfillment.id,
                revision=fulfillment.revision,
                from_status="awaiting_delivery",
                to_status="delivered",
                actor_type="admin",
                actor_id=actor_id,
                reason="管理员完成虚拟交付",
            )
        )
        await self.distribution.schedule_settlement_for_delivery_in_open_transaction(order.id, now)
        return self._fulfillment_read(fulfillment)

    async def confirm_receipt(self, user_id: UUID, order_id: UUID, revision: int) -> FulfillmentRead:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            order = await self.orders.user_order(user_id, order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            fulfillment = await self.repository.fulfillment(order.id, lock=True)
            if fulfillment is None or fulfillment.product_type != "physical":
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能确认收货")
            if fulfillment.status == "delivered":
                return self._fulfillment_read(fulfillment)
            if fulfillment.status != "shipped" or fulfillment.revision != revision:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="履约状态已变化，请重新读取"
                )
            await self._deliver_physical(fulfillment, "user", user_id, "用户确认收货")
            return self._fulfillment_read(fulfillment)

    async def auto_confirm_due(self, limit: int = 100) -> int:
        now = datetime.now(UTC)
        async with transaction_scope(self.session):
            fulfillments = await self.repository.due_fulfillments(now, limit)
            for fulfillment in fulfillments:
                await self._deliver_physical(fulfillment, "system", None, "发货满七日自动确认")
            return len(fulfillments)

    async def _deliver_physical(
        self, fulfillment: Fulfillment, actor_type: str, actor_id: UUID | None, reason: str
    ) -> None:
        now = datetime.now(UTC)
        fulfillment.status = "delivered"
        fulfillment.delivered_at = now
        fulfillment.revision += 1
        await self.repository.save(fulfillment)
        await self.repository.save(
            FulfillmentEvent(
                fulfillment_id=fulfillment.id,
                revision=fulfillment.revision,
                from_status="shipped",
                to_status="delivered",
                actor_type=actor_type,
                actor_id=actor_id,
                reason=reason,
            )
        )
        await self.distribution.schedule_settlement_for_delivery_in_open_transaction(fulfillment.order_id, now)

    async def create_refund(self, user_id: UUID, order_id: UUID, data: RefundRequestCreate) -> RefundRequestRead:
        normalized: dict[UUID, int] = {}
        for line in data.items:
            normalized[line.order_item_id] = normalized.get(line.order_item_id, 0) + line.quantity
        request_lines = [
            {"order_item_id": str(item_id), "quantity": quantity}
            for item_id, quantity in sorted(normalized.items(), key=lambda item: item[0].hex)
        ]
        request_hash = self._request_hash({"items": request_lines, "reason": data.reason})
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            order = await self.orders.user_order(user_id, order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            existing = await self.repository.refund_by_request(user_id, data.request_id, lock=True)
            if existing is not None:
                if existing.order_id != order.id or existing.request_hash != request_hash:
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_REQUEST_CONFLICT, message="退款请求号已用于其他退款申请"
                    )
                return self._refund_read(existing)
            fulfillment = await self.repository.fulfillment(order.id, lock=True)
            if order.status != "paid" or fulfillment is None or fulfillment.status != "delivered":
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="仅已交付订单可以申请退款"
                )
            order_items = await self.orders.order_items(order.id)
            item_by_id = {item.id: item for item in order_items}
            if set(normalized) - set(item_by_id):
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款明细不属于当前订单"
                )
            refunds = await self.repository.refunds_for_order(order.id, lock=True)
            active_statuses = {"requested", "approved", "processing", "unknown", "succeeded"}
            active_refunds = [refund for refund in refunds if refund.status in active_statuses]
            refund_items = await self.repository.refund_items([refund.id for refund in active_refunds], lock=True)
            reserved_quantity: dict[UUID, int] = {}
            for item in refund_items:
                reserved_quantity[item.order_item_id] = reserved_quantity.get(item.order_item_id, 0) + item.quantity
            amount = Decimal("0.00")
            for order_item_id, quantity in normalized.items():
                order_item = item_by_id[order_item_id]
                if order_item.unit_price <= 0:
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="零金额明细不能申请资金退款"
                    )
                if quantity > order_item.quantity - reserved_quantity.get(order_item_id, 0):
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款数量超过可退款数量"
                    )
                amount += order_item.unit_price * quantity
            amount = amount.quantize(Decimal("0.01"))
            if (
                amount <= 0
                or amount + sum((item.amount for item in active_refunds), Decimal("0.00")) > order.items_amount
            ):
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款金额超过商品实付金额"
                )
            refund = RefundRequest(
                id=new_uuid7(),
                order_id=order.id,
                user_id=user_id,
                request_id=data.request_id,
                request_hash=request_hash,
                status="requested",
                amount=amount,
                currency=order.currency,
                reason=data.reason,
                revision=1,
            )
            await self.repository.save(refund)
            for order_item_id, quantity in normalized.items():
                order_item = item_by_id[order_item_id]
                await self.repository.save(
                    RefundItem(
                        id=new_uuid7(),
                        refund_request_id=refund.id,
                        order_item_id=order_item_id,
                        quantity=quantity,
                        amount=(order_item.unit_price * quantity).quantize(Decimal("0.01")),
                    )
                )
            await self.repository.save(
                RefundEvent(
                    refund_request_id=refund.id,
                    revision=1,
                    from_status=None,
                    to_status="requested",
                    actor_type="user",
                    actor_id=user_id,
                    reason="用户申请退款",
                )
            )
            return self._refund_read(refund)

    async def confirm_verified_refund(self, data: VerifiedRefundConfirmation) -> RefundRequestRead:
        async with transaction_scope(self.session):
            return await self.confirm_verified_refund_in_open_transaction(data)

    async def confirm_verified_refund_in_open_transaction(self, data: VerifiedRefundConfirmation) -> RefundRequestRead:
        confirmed_at = self._require_aware(data.confirmed_at, "退款确认时间")
        await self.repository.lock_key("refund", f"{data.channel}:{data.channel_refund_id}")
        refund = await self.repository.refund(data.refund_request_id)
        if refund is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="退款申请不存在")
        order = await self.orders.order(refund.order_id, lock=True)
        refund = await self.repository.refund(data.refund_request_id, lock=True)
        if refund is None or order is None or order.status != "paid":
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款订单状态异常")
        if refund.amount != data.amount or refund.currency != data.currency or order.currency != data.currency:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款金额或币种不匹配")
        payment = await self.repository.payment_by_transaction(data.channel, data.payment_transaction_id)
        if payment is None or payment.status != "succeeded" or payment.order_id != order.id:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款渠道或原支付流水不匹配"
            )
        if confirmed_at < refund.created_at:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款确认时间早于退款申请")
        if refund.status == "succeeded":
            if (
                refund.channel != data.channel
                or refund.channel_refund_id != data.channel_refund_id
                or refund.confirmed_at != confirmed_at
            ):
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款确认内容冲突")
            return self._refund_read(refund)
        if refund.status not in {"approved", "processing", "unknown"}:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前退款申请不能确认成功")
        duplicate = await self.repository.refund_by_channel(data.channel, data.channel_refund_id)
        if duplicate is not None and duplicate.id != refund.id:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="渠道退款流水已被其他退款申请使用"
            )
        prior_refunds = await self.repository.refunds_for_order(order.id)
        cumulative_amount = refund.amount + sum(
            (item.amount for item in prior_refunds if item.status == "succeeded"), Decimal("0.00")
        )
        if cumulative_amount > order.items_amount:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="累计退款超过商品实付金额")
        previous_status = refund.status
        refund.status = "succeeded"
        refund.channel_refund_id = data.channel_refund_id
        refund.channel = data.channel
        refund.confirmed_at = confirmed_at
        refund.revision += 1
        await self.repository.save(refund)
        await self.repository.save(
            RefundEvent(
                refund_request_id=refund.id,
                revision=refund.revision,
                from_status=previous_status,
                to_status="succeeded",
                actor_type="payment",
                actor_id=None,
                reason="可信渠道退款确认",
                payload_hash=data.payload_hash,
            )
        )
        await self.distribution.recover_for_refund_in_open_transaction(
            refund_request_id=refund.id,
            order_id=order.id,
            cumulative_refunded_amount=cumulative_amount,
            refunded_at=confirmed_at,
        )
        return self._refund_read(refund)

    async def refunds_for_user(self, user_id: UUID, order_id: UUID) -> list[RefundRequestRead]:
        order = await self.orders.user_order(user_id, order_id)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        return [self._refund_read(refund) for refund in await self.repository.refunds_for_order(order.id)]

    async def approve_refund_in_open_transaction(
        self, refund_id: UUID, data: RefundReview, actor_id: UUID
    ) -> RefundRequestRead:
        refund = await self.repository.refund(refund_id, lock=True)
        if refund is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="退款申请不存在")
        if refund.status != "requested" or refund.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款状态已变化，请重新读取"
            )
        now = datetime.now(UTC)
        refund.status = "approved"
        refund.review_note = data.note
        refund.reviewed_by_id = actor_id
        refund.reviewed_at = now
        refund.revision += 1
        await self.repository.save(refund)
        await self.repository.save(
            RefundEvent(
                refund_request_id=refund.id,
                revision=refund.revision,
                from_status="requested",
                to_status="approved",
                actor_type="admin",
                actor_id=actor_id,
                reason=data.note,
            )
        )
        return self._refund_read(refund)

    async def reject_refund_in_open_transaction(
        self, refund_id: UUID, data: RefundReview, actor_id: UUID
    ) -> RefundRequestRead:
        refund = await self.repository.refund(refund_id, lock=True)
        if refund is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="退款申请不存在")
        if refund.status != "requested" or refund.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款状态已变化，请重新读取"
            )
        now = datetime.now(UTC)
        refund.status = "rejected"
        refund.review_note = data.note
        refund.reviewed_by_id = actor_id
        refund.reviewed_at = now
        refund.revision += 1
        await self.repository.save(refund)
        await self.repository.save(
            RefundEvent(
                refund_request_id=refund.id,
                revision=refund.revision,
                from_status="requested",
                to_status="rejected",
                actor_type="admin",
                actor_id=actor_id,
                reason=data.note,
            )
        )
        return self._refund_read(refund)

    async def create_review(self, user_id: UUID, order_item_id: UUID, data: ProductReviewCreate) -> ProductReviewRead:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            item = await self.orders.order_item(order_item_id)
            if item is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单明细不存在")
            order = await self.orders.user_order(user_id, item.order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单明细不属于当前用户")
            fulfillment = await self.repository.fulfillment(order.id, lock=True)
            if fulfillment is None or fulfillment.status != "delivered":
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="仅已交付订单明细可以评价"
                )
            existing = await self.repository.review_for_item(user_id, item.id, lock=True)
            if existing is not None:
                if existing.rating == data.rating and existing.content == data.content:
                    return ProductReviewRead.model_validate(existing)
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单明细已经评价")
            now = datetime.now(UTC)
            review = ProductReview(
                id=new_uuid7(),
                user_id=user_id,
                order_item_id=item.id,
                product_id=item.product_id,
                rating=data.rating,
                content=data.content,
                is_published=True,
                published_at=now,
            )
            await self.repository.save(review)
            return ProductReviewRead.model_validate(review)

    async def public_reviews(self, product_id: UUID, page: int, page_size: int) -> PageResult[ProductReviewRead]:
        rows, total = await self.repository.public_reviews(product_id, page, page_size)
        return PageResult[ProductReviewRead].create(
            items=[ProductReviewRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def reconcile_in_open_transaction(self, data: ReconciliationRecordCreate) -> ReconciliationRecordRead:
        occurred_at = self._require_aware(data.occurred_at, "对账发生时间")
        await self.repository.lock_key("payment", f"{data.channel}:{data.channel_transaction_id}")
        existing = await self.repository.reconciliation(data.channel, data.channel_transaction_id, lock=True)
        if existing is not None:
            if (
                existing.source_hash != data.source_hash
                or existing.amount != data.amount
                or existing.currency != data.currency
                or existing.occurred_at != occurred_at
                or existing.source_reference != data.source_reference
            ):
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="渠道账单流水内容冲突")
            return ReconciliationRecordRead.model_validate(existing)
        payment = await self.repository.payment_by_transaction(data.channel, data.channel_transaction_id, lock=True)
        payment_attempt_id = (
            payment.id
            if payment is not None
            and payment.status == "succeeded"
            and payment.amount == data.amount
            and payment.currency == data.currency
            else None
        )
        record = ReconciliationRecord(
            id=new_uuid7(),
            channel=data.channel,
            channel_transaction_id=data.channel_transaction_id,
            source_reference=data.source_reference,
            source_hash=data.source_hash,
            amount=data.amount,
            currency=data.currency,
            occurred_at=occurred_at,
            status="matched" if payment_attempt_id is not None else "discrepancy",
            payment_attempt_id=payment_attempt_id,
            note=None if payment_attempt_id is not None else "渠道账单与本地支付事实不匹配",
        )
        await self.repository.save(record)
        return ReconciliationRecordRead.model_validate(record)
