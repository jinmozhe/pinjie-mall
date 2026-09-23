import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models.commerce_lifecycle import Fulfillment, FulfillmentEvent
from app.db.models.order import Order, OrderEvent, OrderItem
from app.db.transaction import transaction_scope
from app.domains.addresses.repository import AddressRepository
from app.domains.addresses.service import AddressService
from app.domains.distribution.commission_freeze import freeze_order_commission_sources
from app.domains.distribution.service import DistributionService
from app.domains.durable_tasks.service import DurableTaskService
from app.domains.inventory.repository import InventoryRepository
from app.domains.inventory.service import InventoryService
from app.domains.lifecycle.repository import LifecycleRepository
from app.domains.membership.repository import MembershipRepository
from app.domains.membership.schemas import CommerceQuoteRequest, QuoteItemInput
from app.domains.membership.service import MembershipService
from app.domains.orders.repository import OrderRepository
from app.domains.orders.schemas import (
    AdminOrderSummary,
    CheckoutQuote,
    CheckoutRequest,
    OrderItemRead,
    OrderRead,
    QuoteLine,
)
from app.domains.products.repository import ProductRepository
from app.domains.products.service import ProductService
from app.domains.purchases.repository import PurchaseLimitRepository
from app.domains.purchases.service import PurchaseLimitService
from app.domains.users import UserAccessService


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        repository: OrderRepository | None = None,
        *,
        access: UserAccessService | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or OrderRepository(session)
        self.products = ProductService(ProductRepository(session))
        self.inventory = InventoryService(InventoryRepository(session))
        self.addresses = AddressService(AddressRepository(session))
        self.membership = MembershipService(session=session)
        self.membership_repository = MembershipRepository(session)
        self.purchases = PurchaseLimitService(PurchaseLimitRepository(session))
        self.access = access or UserAccessService(session)

    @staticmethod
    def _normalize(data: CheckoutRequest) -> list[tuple[UUID, int]]:
        quantities: defaultdict[UUID, int] = defaultdict(int)
        for item in data.items:
            quantities[item.sku_id] += item.quantity
        if any(value > 999 for value in quantities.values()):
            raise AppException(status_code=422, code=ErrorCode.CHECKOUT_INVALID, message="单个 SKU 数量不能超过 999")
        return sorted(quantities.items(), key=lambda item: item[0].hex)

    async def _quote(self, user_id: UUID, data: CheckoutRequest) -> CheckoutQuote:
        normalized = self._normalize(data)
        catalog = await self.products.checkout_skus([sku_id for sku_id, _ in normalized])
        product_type = catalog[0].product_type
        if any(item.product_type != product_type for item in catalog):
            raise AppException(status_code=422, code=ErrorCode.CHECKOUT_INVALID, message="实物和虚拟商品必须分开下单")
        address_snapshot: dict[str, object] | None = None
        province_code: str | None = None
        if product_type == "physical":
            if data.address_id is None:
                raise AppException(status_code=422, code=ErrorCode.CHECKOUT_INVALID, message="实物订单必须选择收货地址")
            address = await self.addresses.snapshot(user_id, data.address_id)
            address_snapshot = {
                "schema_version": 1,
                "source_address_id": str(address.id),
                "source_address_revision": address.revision,
                **address.model_dump(mode="json", exclude={"id", "revision", "is_default"}),
            }
            province_code = address.province_code
        elif data.address_id is not None:
            raise AppException(status_code=422, code=ErrorCode.CHECKOUT_INVALID, message="虚拟订单不能填写收货地址")
        pricing = await self.membership.quote(
            user_id,
            CommerceQuoteRequest(
                items=[QuoteItemInput(sku_id=sku, quantity=qty) for sku, qty in normalized], province_code=province_code
            ),
        )
        level_snapshot = pricing.buyer_level_snapshot
        product_repository = ProductRepository(self.session)
        products = {
            sku.id: (sku, product)
            for sku, product in await product_repository.checkout_skus([line.sku_id for line in pricing.items])
        }
        categories = {category.id: category for category in await product_repository.categories()}
        lines: list[QuoteLine] = []
        for priced in pricing.items:
            sku, product = products[priced.sku_id]
            chain = []
            category_id: UUID | None = product.category_id
            while category_id is not None:
                category = categories.get(category_id)
                if category is None:
                    raise AppException(status_code=409, code=ErrorCode.CATEGORY_UNAVAILABLE, message="商品分类链异常")
                chain.append(category)
                category_id = category.parent_id
            chain.reverse()
            brand = await product_repository.brand(product.brand_id) if product.brand_id else None
            lines.append(
                QuoteLine(
                    sku_id=sku.id,
                    product_id=product.id,
                    product_name=product.name,
                    sku_code=sku.code,
                    specifications=sku.specifications,
                    quantity=priced.quantity,
                    unit_price=priced.unit_price,
                    line_amount=priced.line_amount,
                    product_revision=product.revision,
                    product_type=product_type,
                    weight_grams=sku.weight_grams,
                    purchase_limit_quantity=product.purchase_limit_quantity,
                    price_snapshot=priced.pricing_snapshot,
                    category_snapshot={
                        "schema_version": 1,
                        "category": {"id": str(chain[-1].id), "name": chain[-1].name, "revision": chain[-1].revision},
                        "ancestors": [
                            {"id": str(value.id), "name": value.name, "revision": value.revision}
                            for value in chain[:-1]
                        ],
                    },
                    brand_snapshot={
                        "schema_version": 1,
                        "id": str(brand.id),
                        "name": brand.name,
                        "revision": brand.revision,
                    }
                    if brand
                    else None,
                    commission_snapshot={"schema_version": 1, "source_amount": "0.00", "source_mode": None},
                )
            )
        lines.sort(key=lambda item: item.sku_id.hex)
        shipping = pricing.shipping_snapshot
        payload = {
            "lines": [line.model_dump(mode="json") for line in lines],
            "shipping": shipping,
            "address": address_snapshot,
            "level": level_snapshot,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CheckoutQuote(
            items=lines,
            shipping_snapshot=shipping,
            product_type=product_type,
            items_amount=pricing.items_amount,
            freight_amount=pricing.freight_amount,
            total_amount=pricing.total_amount,
            address_id=data.address_id,
            address_snapshot=address_snapshot,
            buyer_level_id=pricing.buyer_level_id,
            buyer_level_snapshot=level_snapshot,
            fingerprint=fingerprint,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )

    async def preview(self, user_id: UUID, data: CheckoutRequest) -> CheckoutQuote:
        await self.access.require_active_user(user_id)
        quote = await self._quote(user_id, data)
        await self.inventory.require_available({item.sku_id: item.quantity for item in quote.items})
        return quote

    async def create(self, user_id: UUID, data: CheckoutRequest) -> OrderRead:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            await self.repository.lock_user_checkout(user_id)
            normalized = self._normalize(data)
            request_hash = hashlib.sha256(
                json.dumps(
                    {
                        "items": [(str(sku), quantity) for sku, quantity in normalized],
                        "address_id": str(data.address_id) if data.address_id else None,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            existing = await self.repository.order_by_request(user_id, data.request_id, lock=True)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_REQUEST_CONFLICT, message="请求号已用于其他订单"
                    )
                return await self._read(existing)
            await self.products.lock_changes()
            quote = await self._quote(user_id, data)
            if data.quote_fingerprint != quote.fingerprint:
                raise AppException(
                    status_code=409, code=ErrorCode.CHECKOUT_STALE_QUOTE, message="报价已变化，请重新预览"
                )
            order = Order(
                id=new_uuid7(),
                user_id=user_id,
                request_id=data.request_id,
                request_hash=request_hash,
                quote_fingerprint=quote.fingerprint,
                product_type=quote.product_type,
                status="pending_payment",
                currency="CNY",
                items_amount=quote.items_amount,
                freight_amount=quote.freight_amount,
                total_amount=quote.total_amount,
                address_snapshot=quote.address_snapshot,
                shipping_snapshot=quote.shipping_snapshot,
                buyer_level_id=quote.buyer_level_id,
                buyer_level_snapshot=quote.buyer_level_snapshot,
                commission_policy_id=None,
                commission_result_snapshot=None,
                pricing_version="platform_v1",
                expires_at=quote.expires_at,
                revision=1,
                acceptance_status="pending",
            )
            await self.repository.save(order)
            for line in quote.items:
                await self.repository.save(
                    OrderItem(
                        id=new_uuid7(),
                        order_id=order.id,
                        product_id=line.product_id,
                        sku_id=line.sku_id,
                        product_name=line.product_name,
                        sku_code=line.sku_code,
                        specifications=line.specifications,
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                        line_amount=line.line_amount,
                        price_snapshot=line.price_snapshot,
                        commission_snapshot=line.commission_snapshot,
                        category_snapshot=line.category_snapshot,
                        brand_snapshot=line.brand_snapshot,
                        weight_grams=line.weight_grams,
                        product_revision=line.product_revision,
                    )
                )
            await self.inventory.reserve(order.id, {line.sku_id: line.quantity for line in quote.items})
            await self.purchases.reserve(
                order.id,
                user_id,
                [(line.product_id, line.quantity, line.purchase_limit_quantity) for line in quote.items],
            )
            await DurableTaskService(self.session).enqueue_in_open_transaction(
                task_type="expire_order",
                business_key=str(order.id),
                payload={"schema_version": 1, "order_id": str(order.id)},
                available_at=order.expires_at,
            )
            await self.repository.save(
                OrderEvent(
                    id=new_uuid7(),
                    order_id=order.id,
                    revision=1,
                    event_type="created",
                    from_status=None,
                    to_status="pending_payment",
                    actor_type="user",
                    actor_id=user_id,
                    reason="创建订单",
                )
            )
            await freeze_order_commission_sources(self.session, order.id)
            if order.total_amount == 0:
                await self.confirm_zero_in_open_transaction(order.id, datetime.now(UTC))
            return await self._read(order)

    async def confirm_zero_in_open_transaction(self, order_id: UUID, confirmed_at: datetime) -> OrderRead:
        order = await self.repository.order_by_id(order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        if order.status == "paid" and order.settlement_kind == "zero_amount":
            return await self._read(order)
        if order.status != "pending_payment" or order.total_amount != 0:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能零元成交")
        await self._confirm(order, confirmed_at, "zero_amount", None)
        return await self._read(order)

    async def confirm_payment_in_open_transaction(
        self, order_id: UUID, payment_attempt_id: UUID, confirmed_at: datetime
    ) -> OrderRead:
        order = await self.repository.order_by_id(order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        if order.status == "paid":
            if order.accepted_payment_attempt_id != payment_attempt_id:
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付确认标识冲突")
            return await self._read(order)
        if order.status != "pending_payment" or order.total_amount <= 0:
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能确认支付")
        await self._confirm(order, confirmed_at, "channel", payment_attempt_id)
        return await self._read(order)

    async def accept_in_open_transaction(self, order_id: UUID, revision: int, actor_id: UUID) -> OrderRead:
        order = await self.repository.order_by_id(order_id, lock=True)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        if order.acceptance_status == "accepted":
            return await self._read(order)
        if order.status != "paid" or order.acceptance_status != "pending" or order.revision != revision:
            raise AppException(
                status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="订单接单状态已变化，请重新读取"
            )
        order.acceptance_status = "accepted"
        order.accepted_at = datetime.now(UTC)
        order.accepted_by_id = actor_id
        order.revision += 1
        await self.repository.save(order)
        await self.repository.save(
            OrderEvent(
                id=new_uuid7(),
                order_id=order.id,
                revision=order.revision,
                event_type="accepted",
                from_status="paid",
                to_status="paid",
                actor_type="admin",
                actor_id=actor_id,
                reason="管理员接单",
            )
        )
        return await self._read(order)

    async def _confirm(
        self, order: Order, confirmed_at: datetime, settlement: str, payment_attempt_id: UUID | None
    ) -> None:
        if (
            confirmed_at.tzinfo is None
            or confirmed_at.astimezone(UTC) < order.created_at
            or (settlement == "channel" and confirmed_at.astimezone(UTC) >= order.expires_at)
        ):
            raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付确认时间无效")
        items = await self.repository.items(order.id)
        await self.inventory.transition_reservations(
            order.id, {item.sku_id: item.quantity for item in items}, "confirmed", archived_sku_ids=set()
        )
        await self.purchases.transition(order.id, "confirmed", confirmed_at)
        order.status, order.paid_at, order.settlement_kind = "paid", confirmed_at.astimezone(UTC), settlement
        order.accepted_payment_attempt_id, order.zero_confirmation_id = (
            payment_attempt_id,
            new_uuid7() if settlement == "zero_amount" else None,
        )
        order.revision += 1
        await self.repository.save(order)
        fulfillment_status = "awaiting_shipment" if order.product_type == "physical" else "awaiting_delivery"
        fulfillment = Fulfillment(
            id=new_uuid7(), order_id=order.id, product_type=order.product_type, status=fulfillment_status, revision=1
        )
        self.session.add(fulfillment)
        await self.session.flush()
        self.session.add(
            FulfillmentEvent(
                id=new_uuid7(),
                fulfillment_id=fulfillment.id,
                revision=1,
                from_status=None,
                to_status=fulfillment_status,
                actor_type="payment",
                actor_id=None,
                reason="可信成交后创建履约单",
            )
        )
        await self.session.flush()
        await DistributionService(self.session).freeze_commissions_for_payment_in_open_transaction(
            order_id=order.id, source_user_id=order.user_id, base_amount=order.items_amount, paid_at=confirmed_at
        )
        await self.repository.save(
            OrderEvent(
                id=new_uuid7(),
                order_id=order.id,
                revision=order.revision,
                event_type="zero_confirmed" if settlement == "zero_amount" else "payment_confirmed",
                from_status="pending_payment",
                to_status="paid",
                actor_type="system" if settlement == "zero_amount" else "payment",
                actor_id=None,
                reason="零元内部确认" if settlement == "zero_amount" else "可信支付确认",
            )
        )

    async def cancel(self, user_id: UUID, order_id: UUID, *, reason: str = "用户取消") -> OrderRead:
        async with transaction_scope(self.session):
            await self.access.require_active_user(user_id)
            order = await self.repository.order(user_id, order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            if order.status == "cancelled":
                return await self._read(order)
            if order.status != "pending_payment":
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能取消")
            if await self._payment_blocks_release_in_open_transaction(order):
                raise AppException(
                    status_code=409,
                    code=ErrorCode.ORDER_STATE_CONFLICT,
                    message="存在已成功或待确认的支付，暂不能释放订单资源",
                )
            await self._cancel(order, reason, "user", user_id)
            return await self._read(order)

    async def _cancel(self, order: Order, reason: str, actor_type: str, actor_id: UUID | None) -> None:
        items = await self.repository.items(order.id)
        await self.inventory.transition_reservations(
            order.id,
            {item.sku_id: item.quantity for item in items},
            "released",
            archived_sku_ids=await self.products.archived_sku_ids([item.sku_id for item in items]),
        )
        now = datetime.now(UTC)
        await self.purchases.transition(order.id, "released", now)
        order.status, order.cancelled_at, order.cancel_reason, order.revision = (
            "cancelled",
            now,
            reason,
            order.revision + 1,
        )
        await self.repository.save(order)
        await self.repository.save(
            OrderEvent(
                id=new_uuid7(),
                order_id=order.id,
                revision=order.revision,
                event_type="cancelled",
                from_status="pending_payment",
                to_status="cancelled",
                actor_type=actor_type,
                actor_id=actor_id,
                reason=reason,
            )
        )

    async def _payment_blocks_release_in_open_transaction(self, order: Order) -> bool:
        attempts = await LifecycleRepository(self.session).payment_attempts_for_order(order.id, lock=True)
        succeeded = [attempt for attempt in attempts if attempt.status == "succeeded"]
        if succeeded:
            tasks = DurableTaskService(self.session)
            for attempt in succeeded:
                await tasks.enqueue_in_open_transaction(
                    task_type="confirm_order",
                    business_key=f"confirm-order:{attempt.id}",
                    payload={"schema_version": 1, "payment_attempt_id": str(attempt.id)},
                )
            return True
        unresolved = [attempt for attempt in attempts if attempt.status in {"created", "pending", "unknown"}]
        if unresolved:
            tasks = DurableTaskService(self.session)
            for attempt in unresolved:
                await tasks.enqueue_in_open_transaction(
                    task_type="payment_query",
                    business_key=f"payment-query:{attempt.id}",
                    payload={"schema_version": 1, "payment_attempt_id": str(attempt.id)},
                )
            return True
        return False

    async def expire_due(self, limit: int = 100) -> int:
        completed, now = 0, datetime.now(UTC)
        async with transaction_scope(self.session):
            for order in await self.repository.expired_orders(now, limit):
                if await self._payment_blocks_release_in_open_transaction(order):
                    continue
                await self._cancel(order, "待付款超时", "system", None)
                completed += 1
        return completed

    async def expire_scheduled(self, order_id: UUID) -> bool:
        async with transaction_scope(self.session):
            order = await self.repository.order_by_id(order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="待过期订单不存在")
            if order.status != "pending_payment" or order.expires_at > datetime.now(UTC):
                return False
            if await self._payment_blocks_release_in_open_transaction(order):
                return False
            await self._cancel(order, "待付款超时", "system", None)
            return True

    async def _read(self, order: Order) -> OrderRead:
        return OrderRead(
            id=order.id,
            status=order.status,
            product_type=order.product_type,
            items_amount=order.items_amount,
            freight_amount=order.freight_amount,
            total_amount=order.total_amount,
            address_snapshot=order.address_snapshot,
            shipping_snapshot=order.shipping_snapshot,
            buyer_level_snapshot=order.buyer_level_snapshot,
            settlement_kind=order.settlement_kind,
            expires_at=order.expires_at,
            acceptance_status=order.acceptance_status,
            created_at=order.created_at,
            revision=order.revision,
            items=[OrderItemRead.model_validate(item) for item in await self.repository.items(order.id)],
        )

    async def read(self, user_id: UUID, order_id: UUID) -> OrderRead:
        order = await self.repository.order(user_id, order_id)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        return await self._read(order)

    async def admin_page(self, page: int, page_size: int) -> PageResult[AdminOrderSummary]:
        rows, total = await self.repository.page(page, page_size)
        return PageResult[AdminOrderSummary].create(
            items=[AdminOrderSummary.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def admin_read(self, order_id: UUID) -> OrderRead:
        order = await self.repository.order_by_id(order_id)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        return await self._read(order)
