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
    RefundAttempt,
    RefundEvent,
    RefundItem,
    RefundRequest,
)
from app.db.transaction import transaction_scope
from app.domains.distribution import DistributionService
from app.domains.durable_tasks import DurableTaskService
from app.domains.inventory import InventoryService
from app.domains.lifecycle.repository import LifecycleRepository
from app.domains.lifecycle.schemas import (
    FulfillmentRead,
    PaymentAttemptCreate,
    PaymentAttemptRead,
    ProductReviewCreate,
    ProductReviewRead,
    ReconciliationRecordCreate,
    ReconciliationRecordRead,
    ReconciliationResolve,
    RefundAttemptRead,
    RefundRequestCreate,
    RefundRequestRead,
    RefundReview,
    ShipmentCreate,
    VerifiedPaymentConfirmation,
    VerifiedRefundConfirmation,
    VirtualDeliveryCreate,
)
from app.domains.membership.service import MembershipService
from app.domains.orders import OrderAcceptance, OrderQueryService, OrderRead
from app.domains.products import ProductService
from app.domains.purchases import PurchaseLimitService
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
        inventory: InventoryService | None = None,
        purchases: PurchaseLimitService | None = None,
        products: ProductService | None = None,
        access: UserAccessService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or LifecycleRepository(session)
        self.orders = orders or OrderQueryService(session)
        self.distribution = distribution or DistributionService(session)
        self.inventory = inventory or InventoryService.for_session(session)
        self.purchases = purchases or PurchaseLimitService.for_session(session)
        self.products = products or ProductService.for_session(session)
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

    @staticmethod
    def _refund_attempt_read(value: RefundAttempt) -> RefundAttemptRead:
        return RefundAttemptRead.model_validate(value)

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
                channel_context={"schema_version": 1, "merchant_id": None, "app_id": None, "config_version": None},
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
        await self.repository.lock_key("payment", f"{data.channel}:{data.channel_transaction_id}")
        attempt = await self.repository.payment(data.payment_attempt_id)
        if attempt is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="支付意图不存在")
        order = await self.orders.order(attempt.order_id, lock=True)
        attempt = await self.repository.payment(data.payment_attempt_id, lock=True)
        if order is None or attempt is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单或支付意图不存在")
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
        if attempt.status not in {"created", "unavailable", "pending", "unknown", "closed"}:
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
        previous_status = attempt.status
        attempt.status = "succeeded"
        attempt.channel_transaction_id = data.channel_transaction_id
        attempt.channel_paid_at = confirmed_at
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
        await DurableTaskService(self.session).enqueue_in_open_transaction(
            task_type="confirm_order",
            business_key=f"confirm-order:{attempt.id}",
            payload={"schema_version": 1, "payment_attempt_id": str(attempt.id)},
        )
        return self._payment_read(attempt)

    async def confirm_order_scheduled(self, payment_attempt_id: UUID) -> None:
        async with transaction_scope(self.session):
            await self._confirm_order_from_payment_in_open_transaction(payment_attempt_id)

    async def _confirm_order_from_payment_in_open_transaction(self, payment_attempt_id: UUID) -> None:
        await self.distribution.lock_referral_changes()
        attempt = await self.repository.payment(payment_attempt_id)
        if attempt is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="支付意图不存在")
        order = await self.orders.order(attempt.order_id, lock=True)
        attempt = await self.repository.payment(payment_attempt_id, lock=True)
        if order is None or attempt is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单或支付意图不存在")
        if attempt.status != "succeeded" or attempt.confirmed_at is None:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付资金事实尚未确认")
        if order.status == "paid":
            if order.accepted_payment_attempt_id == attempt.id:
                return
            await self._create_abnormal_refund_in_open_transaction(attempt, "duplicate_payment")
            return
        if order.status == "pending_payment" and attempt.confirmed_at < order.expires_at:
            await OrderService(self.session).confirm_payment_in_open_transaction(
                order.id, attempt.id, attempt.confirmed_at
            )
            return
        purpose = (
            "late_payment"
            if order.status == "cancelled" or attempt.confirmed_at >= order.expires_at
            else "duplicate_payment"
        )
        await self._create_abnormal_refund_in_open_transaction(attempt, purpose)
        if order.status == "pending_payment":
            order_service = OrderService(self.session)
            writable_order = await order_service.repository.order_by_id(order.id, lock=True)
            if writable_order is None or writable_order.status != "pending_payment":
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="待取消订单状态已变化")
            await order_service._cancel(writable_order, "可信支付超时", "system", None)

    async def _create_abnormal_refund_in_open_transaction(self, payment: PaymentAttempt, purpose: str) -> RefundAttempt:
        existing = [
            row
            for row in await self.repository.refund_attempts_for_payment(payment.id, lock=True)
            if row.purpose == purpose
        ]
        if existing:
            return existing[0]
        attempt = RefundAttempt(
            id=new_uuid7(),
            order_id=payment.order_id,
            payment_attempt_id=payment.id,
            refund_request_id=None,
            purpose=purpose,
            attempt_no=1,
            merchant_refund_reference=f"R5-{new_uuid7()}",
            request_hash=self._request_hash(
                {
                    "payment_attempt_id": str(payment.id),
                    "purpose": purpose,
                    "amount": str(payment.amount),
                    "currency": payment.currency,
                    "channel": payment.channel,
                }
            ),
            channel=payment.channel,
            currency=payment.currency,
            amount=payment.amount,
            status="created",
            revision=1,
        )
        await self.repository.save(attempt)
        await self.repository.save(
            RefundEvent(
                refund_request_id=None,
                refund_attempt_id=attempt.id,
                event_scope="attempt",
                event_type="state_changed",
                revision=1,
                from_status=None,
                to_status="created",
                actor_type="system",
                actor_id=None,
                reason="异常收款创建渠道退款执行意图",
            )
        )
        await DurableTaskService(self.session).enqueue_in_open_transaction(
            task_type="refund_submit",
            business_key=f"refund-submit:{attempt.id}",
            payload={"schema_version": 1, "refund_attempt_id": str(attempt.id)},
        )
        return attempt

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

    async def accept_order_in_open_transaction(
        self, order_id: UUID, data: OrderAcceptance, actor_id: UUID
    ) -> OrderRead:
        order = await self.orders.order(order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        refunds = await self.repository.refunds_for_order(order.id, lock=True)
        if any(refund.status != "rejected" for refund in refunds):
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单存在未结束退款申请，不能接单"
            )
        return await OrderService(self.session).accept_in_open_transaction(order.id, data.revision, actor_id)

    async def _ensure_no_unfinished_refunds(self, order_id: UUID) -> None:
        refunds = await self.repository.refunds_for_order(order_id, lock=True)
        if any(refund.status != "rejected" for refund in refunds):
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单存在未结束退款申请，不能继续履约"
            )

    async def ship_in_open_transaction(self, order_id: UUID, data: ShipmentCreate, actor_id: UUID) -> FulfillmentRead:
        order = await self.orders.order(order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        fulfillment = await self.repository.fulfillment(order.id, lock=True)
        if fulfillment is None or order.status != "paid" or order.product_type != "physical":
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能发货")
        if order.acceptance_status != "accepted":
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单尚未接单，不能发货")
        if fulfillment.status != "awaiting_shipment" or fulfillment.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="履约状态已变化，请重新读取"
            )
        await self._ensure_no_unfinished_refunds(order.id)
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
        await DurableTaskService(self.session).enqueue_in_open_transaction(
            task_type="auto_confirm_fulfillment",
            business_key=f"auto-confirm-fulfillment:{fulfillment.id}",
            payload={"schema_version": 1, "fulfillment_id": str(fulfillment.id)},
            available_at=fulfillment.auto_confirm_at,
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
        if order.acceptance_status != "accepted":
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单尚未接单，不能进行虚拟交付"
            )
        if fulfillment.status != "awaiting_delivery" or fulfillment.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="履约状态已变化，请重新读取"
            )
        await self._ensure_no_unfinished_refunds(order.id)
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
            delivered = await self._deliver_physical(fulfillment, "user", user_id, "用户确认收货")
            if delivered is None:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="履约状态已变化，请重新读取"
                )
            return self._fulfillment_read(delivered)

    async def auto_confirm_due(self, limit: int = 100) -> int:
        # 每次单独开启一个事务处理一条 fulfillment，与 expire_due 设计一致。
        # 避免任意一条 _deliver_physical 失败导致整批回滚。
        now = datetime.now(UTC)
        completed = 0
        for _ in range(limit):
            async with transaction_scope(self.session):
                fulfillments = await self.repository.due_fulfillments(now, 1)
                if not fulfillments:
                    break
                delivered = await self._deliver_physical(
                    fulfillments[0], "system", None, "发货满七日自动确认", auto_confirm_due=True
                )
                if delivered is not None:
                    completed += 1
        return completed

    async def auto_confirm_scheduled(self, fulfillment_id: UUID) -> bool:
        async with transaction_scope(self.session):
            fulfillment = await self.repository.fulfillment_by_id(fulfillment_id)
            if fulfillment is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="待自动确认履约不存在")
            delivered = await self._deliver_physical(
                fulfillment, "system", None, "发货满七日自动确认", auto_confirm_due=True
            )
            return delivered is not None

    async def _deliver_physical(
        self,
        fulfillment: Fulfillment,
        actor_type: str,
        actor_id: UUID | None,
        reason: str,
        *,
        auto_confirm_due: bool = False,
    ) -> Fulfillment | None:
        order = await self.orders.order(fulfillment.order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        locked_fulfillment = await self.repository.fulfillment_by_id(fulfillment.id, lock=True)
        if locked_fulfillment is None or locked_fulfillment.product_type != "physical":
            return None
        if locked_fulfillment.status != "shipped":
            return None
        if auto_confirm_due and (
            locked_fulfillment.auto_confirm_at is None or locked_fulfillment.auto_confirm_at > datetime.now(UTC)
        ):
            return None
        await self._ensure_no_unfinished_refunds(order.id)
        now = datetime.now(UTC)
        locked_fulfillment.status = "delivered"
        locked_fulfillment.delivered_at = now
        locked_fulfillment.revision += 1
        await self.repository.save(locked_fulfillment)
        await self.repository.save(
            FulfillmentEvent(
                fulfillment_id=locked_fulfillment.id,
                revision=locked_fulfillment.revision,
                from_status="shipped",
                to_status="delivered",
                actor_type=actor_type,
                actor_id=actor_id,
                reason=reason,
            )
        )
        await self.distribution.schedule_settlement_for_delivery_in_open_transaction(order.id, now)
        return locked_fulfillment

    async def create_refund(self, user_id: UUID, order_id: UUID, data: RefundRequestCreate) -> RefundRequestRead:
        request_hash = self._request_hash({"reason": data.reason})
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
            allowed_status = "awaiting_shipment" if order.product_type == "physical" else "awaiting_delivery"
            if order.status != "paid" or fulfillment is None or fulfillment.status != allowed_status:
                raise AppException(
                    status_code=409,
                    code=ErrorCode.ORDER_STATE_CONFLICT,
                    message="当前订单不满足未发货或未交付整单退款条件",
                )
            order_items = await self.orders.order_items(order.id)
            refunds = await self.repository.refunds_for_order(order.id, lock=True)
            if any(row.status != "rejected" for row in refunds):
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单已存在未结束退款申请"
                )
            items_amount = sum((item.line_amount for item in order_items), Decimal("0.00")).quantize(Decimal("0.01"))
            if items_amount != order.items_amount:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单退款商品金额快照异常"
                )
            amount = (items_amount + order.freight_amount).quantize(Decimal("0.01"))
            review_mode = "automatic" if order.acceptance_status == "pending" else "manual"
            refund = RefundRequest(
                id=new_uuid7(),
                order_id=order.id,
                user_id=user_id,
                request_id=data.request_id,
                request_hash=request_hash,
                status="requested",
                review_mode=review_mode,
                items_amount=items_amount,
                freight_amount=order.freight_amount,
                amount=amount,
                currency=order.currency,
                reason=data.reason,
                fulfillment_status_snapshot=fulfillment.status,
                revision=1,
            )
            await self.repository.save(refund)
            for order_item in order_items:
                await self.repository.save(
                    RefundItem(
                        id=new_uuid7(),
                        refund_request_id=refund.id,
                        order_item_id=order_item.id,
                        quantity=order_item.quantity,
                        amount=order_item.line_amount,
                    )
                )
            await self.repository.save(
                RefundEvent(
                    refund_request_id=refund.id,
                    refund_attempt_id=None,
                    event_scope="request",
                    event_type="state_changed",
                    revision=1,
                    from_status=None,
                    to_status="requested",
                    actor_type="user",
                    actor_id=user_id,
                    reason="用户申请退款",
                )
            )
            if review_mode == "automatic":
                await self._approve_refund_in_open_transaction(refund, note="未接单订单自动审核通过", actor_id=None)
            return self._refund_read(refund)

    async def _approve_refund_in_open_transaction(
        self, refund: RefundRequest, *, note: str, actor_id: UUID | None
    ) -> None:
        if refund.status != "requested":
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款申请状态异常")
        now = datetime.now(UTC)
        refund.status = "approved"
        refund.review_note = note
        refund.reviewed_by_id = actor_id
        refund.reviewed_at = now
        refund.revision += 1
        await self.repository.save(refund)
        await self.repository.save(
            RefundEvent(
                refund_request_id=refund.id,
                refund_attempt_id=None,
                event_scope="request",
                event_type="state_changed",
                revision=refund.revision,
                from_status="requested",
                to_status="approved",
                actor_type="admin" if actor_id is not None else "system",
                actor_id=actor_id,
                reason=note,
            )
        )
        order = await self.orders.order(refund.order_id, lock=True)
        if order is None:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款订单不存在")
        if refund.amount == 0:
            await self._complete_refund_in_open_transaction(refund, order.id, order.user_id, now)
            return
        if order.accepted_payment_attempt_id is None:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="正额订单缺少已接受支付事实"
            )
        payment = await self.repository.payment(order.accepted_payment_attempt_id, lock=True)
        if payment is None or payment.status != "succeeded" or payment.amount < refund.amount:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="原支付事实不能支持退款")
        attempt = await self.repository.refund_attempt_for_request(refund.id, lock=True)
        if attempt is None:
            attempt = RefundAttempt(
                id=new_uuid7(),
                order_id=order.id,
                payment_attempt_id=payment.id,
                refund_request_id=refund.id,
                purpose="after_sale",
                attempt_no=1,
                merchant_refund_reference=f"R5-{new_uuid7()}",
                request_hash=self._request_hash(
                    {
                        "payment_attempt_id": str(payment.id),
                        "refund_request_id": str(refund.id),
                        "amount": str(refund.amount),
                        "currency": refund.currency,
                        "channel": payment.channel,
                    }
                ),
                channel=payment.channel,
                currency=refund.currency,
                amount=refund.amount,
                status="created",
                revision=1,
            )
            await self.repository.save(attempt)
            await self.repository.save(
                RefundEvent(
                    refund_request_id=None,
                    refund_attempt_id=attempt.id,
                    event_scope="attempt",
                    event_type="state_changed",
                    revision=1,
                    from_status=None,
                    to_status="created",
                    actor_type="system",
                    actor_id=None,
                    reason="审核通过后创建退款执行意图",
                )
            )
        await DurableTaskService(self.session).enqueue_in_open_transaction(
            task_type="refund_submit",
            business_key=f"refund-submit:{attempt.id}",
            payload={"schema_version": 1, "refund_attempt_id": str(attempt.id)},
        )

    async def _complete_refund_in_open_transaction(
        self, refund: RefundRequest, order_id: UUID, user_id: UUID, completed_at: datetime
    ) -> None:
        if refund.status == "completed":
            return
        if refund.status != "approved":
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款申请尚未审核通过")
        order_items = await self.orders.order_items(order_id)
        refund_items = await self.repository.refund_items([refund.id], lock=True)
        expected = {item.id: (item.sku_id, item.quantity, item.line_amount) for item in order_items}
        actual = {item.order_item_id: item for item in refund_items}
        if set(actual) != set(expected) or any(
            (actual[item_id].quantity, actual[item_id].amount) != (quantity, amount)
            for item_id, (_, quantity, amount) in expected.items()
        ):
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款明细未完整覆盖原订单")
        archived_sku_ids = await self.products.archived_sku_ids([item.sku_id for item in order_items])
        await self.inventory.restock_from_refund_in_open_transaction(
            [
                (refund_item.id, expected[refund_item.order_item_id][0], refund_item.quantity)
                for refund_item in refund_items
            ],
            archived_sku_ids=archived_sku_ids,
        )
        await self.purchases.transition(order_id, "refunded", completed_at)
        await self.distribution.recover_for_refund_in_open_transaction(
            refund_request_id=refund.id,
            order_id=order_id,
            cumulative_refunded_amount=refund.items_amount,
            refunded_at=completed_at,
        )
        await MembershipService(session=self.session).reverse_order_consumption(
            user_id=user_id,
            order_id=order_id,
            refund_id=refund.id,
            completed_at=completed_at,
        )
        fulfillment = await self.repository.fulfillment(order_id, lock=True)
        if fulfillment is None or fulfillment.status not in {"awaiting_shipment", "awaiting_delivery"}:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款完成时履约状态异常")
        previous_fulfillment_status = fulfillment.status
        fulfillment.status = "cancelled"
        fulfillment.cancelled_at = completed_at
        fulfillment.revision += 1
        await self.repository.save(fulfillment)
        await self.repository.save(
            FulfillmentEvent(
                fulfillment_id=fulfillment.id,
                revision=fulfillment.revision,
                from_status=previous_fulfillment_status,
                to_status="cancelled",
                actor_type="system",
                actor_id=None,
                reason="整单退款完成终止履约",
            )
        )
        refund.status = "completed"
        refund.completed_at = completed_at
        refund.revision += 1
        await self.repository.save(refund)
        await self.repository.save(
            RefundEvent(
                refund_request_id=refund.id,
                refund_attempt_id=None,
                event_scope="request",
                event_type="state_changed",
                revision=refund.revision,
                from_status="approved",
                to_status="completed",
                actor_type="channel" if refund.amount > 0 else "system",
                actor_id=None,
                reason="退款资金确认或零额售后完成",
            )
        )

    async def confirm_verified_refund(self, data: VerifiedRefundConfirmation) -> RefundAttemptRead:
        async with transaction_scope(self.session):
            return await self.confirm_verified_refund_in_open_transaction(data)

    async def confirm_verified_refund_in_open_transaction(self, data: VerifiedRefundConfirmation) -> RefundAttemptRead:
        confirmed_at = self._require_aware(data.confirmed_at, "退款确认时间")
        await self.repository.lock_key("refund", f"{data.channel}:{data.channel_refund_id}")
        attempt = await self.repository.refund_attempt(data.refund_attempt_id)
        if attempt is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="退款执行不存在")
        order = await self.orders.order(attempt.order_id, lock=True)
        attempt = await self.repository.refund_attempt(data.refund_attempt_id, lock=True)
        if order is None or attempt is None:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款订单或执行不存在")
        if attempt.channel != data.channel or attempt.amount != data.amount or attempt.currency != data.currency:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款渠道、金额或币种不匹配"
            )
        payment = await self.repository.payment_by_transaction(data.channel, data.payment_transaction_id, lock=True)
        if (
            payment is None
            or payment.id != attempt.payment_attempt_id
            or payment.status != "succeeded"
            or payment.order_id != order.id
        ):
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款渠道或原支付流水不匹配"
            )
        if confirmed_at < attempt.created_at:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款确认时间早于退款执行")
        if attempt.status == "succeeded":
            if attempt.channel_refund_id != data.channel_refund_id or attempt.confirmed_at != confirmed_at:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款确认内容冲突")
            return self._refund_attempt_read(attempt)
        if attempt.status not in {"created", "processing", "unknown", "abnormal"}:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前退款执行不能确认成功")
        duplicate = await self.repository.refund_attempt_by_channel(data.channel, data.channel_refund_id, lock=True)
        if duplicate is not None and duplicate.id != attempt.id:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="渠道退款流水已被其他退款执行使用"
            )
        pending_total = sum(
            (
                row.amount
                for row in await self.repository.refund_attempts_for_payment(payment.id, lock=True)
                if row.status != "closed"
            ),
            Decimal("0.00"),
        )
        if pending_total > payment.amount:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款执行总额超过原支付金额"
            )
        previous_status = attempt.status
        attempt.status = "succeeded"
        attempt.channel_refund_id = data.channel_refund_id
        attempt.channel_refunded_at = confirmed_at
        attempt.confirmed_at = confirmed_at
        attempt.revision += 1
        await self.repository.save(attempt)
        await self.repository.save(
            RefundEvent(
                refund_request_id=None,
                refund_attempt_id=attempt.id,
                event_scope="attempt",
                event_type="state_changed",
                revision=attempt.revision,
                from_status=previous_status,
                to_status="succeeded",
                actor_type="channel",
                actor_id=None,
                reason="可信渠道退款确认",
                payload_hash=data.payload_hash,
            )
        )
        if attempt.refund_request_id is not None:
            await DurableTaskService(self.session).enqueue_in_open_transaction(
                task_type="refund_followup",
                business_key=f"refund-followup:{attempt.id}",
                payload={"schema_version": 1, "refund_attempt_id": str(attempt.id)},
            )
        return self._refund_attempt_read(attempt)

    async def complete_refund_scheduled(self, refund_attempt_id: UUID) -> None:
        async with transaction_scope(self.session):
            attempt = await self.repository.refund_attempt(refund_attempt_id)
            if attempt is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="退款执行不存在")
            order = await self.orders.order(attempt.order_id, lock=True)
            attempt = await self.repository.refund_attempt(refund_attempt_id, lock=True)
            if attempt is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="退款执行不存在")
            if attempt.refund_request_id is None:
                return
            if attempt.status != "succeeded" or attempt.confirmed_at is None:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款资金事实尚未确认")
            refund = await self.repository.refund(attempt.refund_request_id, lock=True)
            if order is None or order.status != "paid" or refund is None:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="退款申请状态异常")
            await self._complete_refund_in_open_transaction(refund, order.id, order.user_id, attempt.confirmed_at)

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
        await self._approve_refund_in_open_transaction(refund, note=data.note, actor_id=actor_id)
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
                refund_attempt_id=None,
                event_scope="request",
                event_type="state_changed",
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
            # 用户归属链验证：通过 user_order(user_id, item.order_id) 加锁读取，
            # 保证 order 属于当前用户；item 是不可变的订单事实，item.order_id 为常量，
            # 锁定后再次断言 item.order_id == order.id，消除非加锁读窗口。
            order = await self.orders.user_order(user_id, item.order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单明细不属于当前用户")
            if item.order_id != order.id:
                # 防御性断言：正常情况不可能触发，触发则说明 item 与 order 对应关系异常。
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单明细归属异常")
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
        await self.repository.lock_key(data.record_type, f"{data.channel}:{data.channel_transaction_id}")
        existing = await self.repository.reconciliation(
            data.channel, data.record_type, data.channel_transaction_id, lock=True
        )
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
        payment_attempt_id: UUID | None = None
        refund_attempt_id: UUID | None = None
        withdrawal_request_id: UUID | None = None
        if data.record_type == "payment":
            payment = await self.repository.payment_by_transaction(data.channel, data.channel_transaction_id, lock=True)
            payment_attempt_id = (
                payment.id
                if payment is not None
                and payment.status == "succeeded"
                and payment.amount == data.amount
                and payment.currency == data.currency
                else None
            )
        elif data.record_type == "refund":
            attempt = await self.repository.refund_attempt_by_channel(
                data.channel, data.channel_transaction_id, lock=True
            )
            refund_attempt_id = (
                attempt.id
                if attempt is not None
                and attempt.status == "succeeded"
                and attempt.amount == data.amount
                and attempt.currency == data.currency
                else None
            )
        else:
            withdrawal_request_id = await self.distribution.matched_withdrawal_id_in_open_transaction(
                channel=data.channel,
                channel_reference=data.channel_transaction_id,
                amount=data.amount,
                currency=data.currency,
            )
        matched = any((payment_attempt_id, refund_attempt_id, withdrawal_request_id))
        record = ReconciliationRecord(
            id=new_uuid7(),
            channel=data.channel,
            channel_transaction_id=data.channel_transaction_id,
            record_type=data.record_type,
            source_reference=data.source_reference,
            source_hash=data.source_hash,
            amount=data.amount,
            currency=data.currency,
            occurred_at=occurred_at,
            status="matched" if matched else "discrepancy",
            payment_attempt_id=payment_attempt_id,
            refund_attempt_id=refund_attempt_id,
            withdrawal_request_id=withdrawal_request_id,
            resolution_status="open",
            revision=1,
            note=None if matched else "渠道账单与本地资金事实不匹配",
        )
        await self.repository.save(record)
        return ReconciliationRecordRead.model_validate(record)

    async def resolve_reconciliation_in_open_transaction(
        self, record_id: UUID, data: ReconciliationResolve, actor_id: UUID
    ) -> ReconciliationRecordRead:
        record = await self.repository.reconciliation_by_id(record_id, lock=True)
        if record is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="对账记录不存在")
        if record.status != "discrepancy" or record.resolution_status != "open" or record.revision != data.revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="对账差异已处置或版本已变更"
            )
        record.resolution_status = "resolved"
        record.resolution_note = data.note
        record.resolved_by_id = actor_id
        record.resolved_at = datetime.now(UTC)
        record.revision += 1
        await self.repository.save(record)
        return ReconciliationRecordRead.model_validate(record)
