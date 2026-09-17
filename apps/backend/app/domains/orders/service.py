import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.order import Order, OrderEvent, OrderItem
from app.db.models.reservation import InventoryReservation
from app.db.models.shipping import ShippingTemplate
from app.db.transaction import transaction_scope
from app.domains.addresses.schemas import AddressRead
from app.domains.shipping.schemas import FreightQuoteInput, ShippingTemplateRead, calculate_freight

from .repository import OrderRepository
from .schemas import CheckoutQuote, CheckoutRequest, OrderItemRead, OrderRead, QuoteLine, ShippingQuoteGroup


@dataclass
class ShippingGroup:
    template: ShippingTemplate | None
    pieces: int = 0
    weight_grams: int = 0
    items_amount: Decimal = Decimal("0.00")


class OrderService:
    def __init__(self, session: AsyncSession, repository: OrderRepository | None = None) -> None:
        self.session = session
        self.repository = repository or OrderRepository(session)

    @staticmethod
    def _normalize(data: CheckoutRequest) -> list[tuple[UUID, int]]:
        merged: dict[UUID, int] = {}
        for item in data.items:
            merged[item.sku_id] = merged.get(item.sku_id, 0) + item.quantity
        if any(quantity > 999 for quantity in merged.values()):
            raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="同一 SKU 数量超过上限")
        return sorted(merged.items(), key=lambda pair: pair[0].hex)

    @staticmethod
    def _fingerprint(
        lines: list[QuoteLine], shipping: list[ShippingQuoteGroup], address: dict[str, object] | None
    ) -> str:
        payload = {
            "lines": [line.model_dump(mode="json") for line in lines],
            "shipping": [group.model_dump(mode="json") for group in shipping],
            "address": address,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def _quote(self, user_id: UUID, data: CheckoutRequest, *, lock: bool = False) -> CheckoutQuote:
        normalized = self._normalize(data)
        catalog = await self.repository.catalog([sku_id for sku_id, _ in normalized], lock=lock)
        if len(catalog) != len(normalized):
            raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="SKU 不存在")
        types = {product.product_type for _, product, _ in catalog}
        if lock:
            template_ids = sorted(
                {product.shipping_template_id for _, product, _ in catalog if product.shipping_template_id is not None},
                key=lambda template_id: template_id.hex,
            )
            templates = await self.repository.lock_templates(template_ids)
            if len(templates) != len(template_ids):
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="运费模板不可用")
            templates_by_id = {template.id: template for template in templates}
            catalog = [
                (
                    sku,
                    product,
                    templates_by_id.get(template_id) if (template_id := product.shipping_template_id) else None,
                )
                for sku, product, _ in catalog
            ]
        by_sku = {sku.id: (sku, product, template) for sku, product, template in catalog}
        if len(types) != 1:
            raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="实物和虚拟商品必须分开下单")
        product_type = next(iter(types))
        address_snapshot: dict[str, object] | None = None
        province_code: str | None = None
        if product_type == "physical":
            if data.address_id is None:
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="实物订单必须选择收货地址")
            address = await self.repository.address(user_id, data.address_id, lock=lock)
            if address is None:
                raise AppException(status_code=404, code=ErrorCode.CHECKOUT_INVALID, message="收货地址不存在")
            address_read = AddressRead.model_validate(address)
            address_snapshot = address_read.model_dump(mode="json")
            province_code = address_read.province_code
        elif data.address_id is not None:
            raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="虚拟订单不能填写收货地址")

        lines: list[QuoteLine] = []
        grouped: dict[tuple[UUID | None, int | None], ShippingGroup] = {}
        for sku_id, quantity in normalized:
            sku, product, template = by_sku[sku_id]
            if product.status != "on_sale" or not sku.is_active:
                raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="商品或 SKU 已下架")
            line_amount = (sku.price * quantity).quantize(Decimal("0.01"))
            lines.append(
                QuoteLine(
                    sku_id=sku.id,
                    product_id=product.id,
                    product_name=product.name,
                    sku_code=sku.code,
                    specifications=sku.specifications,
                    quantity=quantity,
                    unit_price=sku.price,
                    line_amount=line_amount,
                    weight_grams=sku.weight_grams,
                    product_revision=product.revision,
                    product_type=product.product_type,
                    shipping_template_id=product.shipping_template_id,
                )
            )
            key = (product.shipping_template_id, template.revision if template else None)
            group = grouped.setdefault(key, ShippingGroup(template=template))
            group.pieces += quantity
            group.weight_grams += sku.weight_grams * quantity
            group.items_amount += line_amount

        shipping: list[ShippingQuoteGroup] = []
        for (template_id, revision), group in grouped.items():
            template = group.template
            amount = group.items_amount
            freight = Decimal("0.00")
            if product_type == "physical":
                if template is None or not template.is_active:
                    raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="运费模板不可用")
                if province_code is None:
                    raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="收货地址不可用")
                freight = calculate_freight(
                    ShippingTemplateRead.model_validate(template),
                    FreightQuoteInput(
                        province_code=province_code,
                        pieces=group.pieces,
                        weight_grams=group.weight_grams,
                        items_amount=amount,
                    ),
                )
            shipping.append(
                ShippingQuoteGroup(
                    template_id=template_id,
                    revision=revision,
                    product_type=product_type,
                    pieces=group.pieces,
                    weight_grams=group.weight_grams,
                    items_amount=amount,
                    freight=freight,
                )
            )
        items_amount = sum((line.line_amount for line in lines), Decimal("0.00"))
        freight_amount = sum((group.freight for group in shipping), Decimal("0.00"))
        now = datetime.now(UTC)
        return CheckoutQuote(
            items=lines,
            shipping=shipping,
            product_type=product_type,
            items_amount=items_amount,
            freight_amount=freight_amount,
            total_amount=items_amount + freight_amount,
            address_id=data.address_id,
            address_snapshot=address_snapshot,
            fingerprint=self._fingerprint(lines, shipping, address_snapshot),
            expires_at=now + timedelta(minutes=30),
        )

    async def preview(self, user_id: UUID, data: CheckoutRequest) -> CheckoutQuote:
        return await self._quote(user_id, data)

    async def create(self, user_id: UUID, data: CheckoutRequest) -> OrderRead:
        async with transaction_scope(self.session):
            await self.repository.lock_user_checkout(user_id)
            await self.repository.lock_catalog()
            existing = await self.repository.order_by_request(user_id, data.request_id, lock=True)
            normalized_payload = {
                "items": [item.model_dump(mode="json") for item in data.items],
                "address_id": str(data.address_id) if data.address_id else None,
            }
            request_hash = hashlib.sha256(
                json.dumps(normalized_payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise AppException(
                        status_code=409, code=ErrorCode.ORDER_REQUEST_CONFLICT, message="请求号已用于其他订单"
                    )
                return await self._read(existing, user_id)
            quote = await self._quote(user_id, data, lock=True)
            if data.quote_fingerprint != quote.fingerprint:
                raise AppException(
                    status_code=409, code=ErrorCode.CHECKOUT_STALE_QUOTE, message="报价已变化，请重新预览"
                )
            accounts = await self.repository.inventory_accounts([line.sku_id for line in quote.items])
            if len(accounts) != len(quote.items):
                raise AppException(status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="SKU 库存账户不存在")
            account_by_sku = {account.sku_id: account for account in accounts}
            for line in quote.items:
                account = account_by_sku[line.sku_id]
                if account.available < line.quantity:
                    raise AppException(status_code=409, code=ErrorCode.ORDER_STOCK_REJECTED, message="库存不足")
                account.available -= line.quantity
                account.reserved += line.quantity
            order = Order(
                id=new_uuid7(),
                user_id=user_id,
                request_id=data.request_id,
                request_hash=request_hash,
                quote_fingerprint=quote.fingerprint,
                product_type=quote.product_type,
                items_amount=quote.items_amount,
                freight_amount=quote.freight_amount,
                total_amount=quote.total_amount,
                address_snapshot=quote.address_snapshot,
                shipping_snapshot=[group.model_dump(mode="json") for group in quote.shipping],
                pricing_version="m2-2026-09-17",
                expires_at=quote.expires_at,
                revision=1,
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
                        weight_grams=line.weight_grams,
                        product_revision=line.product_revision,
                    )
                )
                await self.repository.save(
                    InventoryReservation(order_id=order.id, sku_id=line.sku_id, quantity=line.quantity)
                )
            await self.repository.save(
                OrderEvent(
                    order_id=order.id,
                    revision=1,
                    from_status=None,
                    to_status="pending_payment",
                    actor_type="user",
                    actor_id=user_id,
                    reason="创建订单",
                )
            )
            return await self._read(order, user_id)

    async def confirm_payment(self, order_id: UUID, payment_reference: str, confirmed_at: datetime) -> OrderRead:
        async with transaction_scope(self.session):
            order = await self.repository.order_by_id(order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            if order.status == "paid":
                if order.payment_reference != payment_reference:
                    raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付确认标识冲突")
                return await self._read(order, order.user_id)
            if order.status != "pending_payment":
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单不能确认支付")
            if confirmed_at.tzinfo is None:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付确认时间必须包含时区"
                )
            if confirmed_at.astimezone(UTC) >= order.expires_at:
                raise AppException(
                    status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="支付确认已超过订单支付时限"
                )
            reservations = await self.repository.reservations(order.id, lock=True)
            accounts = await self.repository.inventory_accounts([item.sku_id for item in reservations])
            account_by_sku = {account.sku_id: account for account in accounts}
            for reservation in reservations:
                if reservation.status != "reserved":
                    raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="库存占用状态异常")
                account = account_by_sku[reservation.sku_id]
                account.reserved -= reservation.quantity
                reservation.status = "confirmed"
                reservation.revision += 1
            order.status = "paid"
            order.paid_at = confirmed_at
            order.payment_reference = payment_reference
            order.revision += 1
            await self.repository.save(order)
            await self.repository.save(
                OrderEvent(
                    order_id=order.id,
                    revision=order.revision,
                    from_status="pending_payment",
                    to_status="paid",
                    actor_type="payment",
                    actor_id=None,
                    reason="可信支付确认",
                )
            )
            return await self._read(order, order.user_id)

    async def expire_due(self, limit: int = 100) -> int:
        now = datetime.now(UTC)
        async with transaction_scope(self.session):
            expired = await self.repository.expired_orders(now, limit)
            for order in expired:
                reservations = await self.repository.reservations(order.id, lock=True)
                accounts = await self.repository.inventory_accounts([item.sku_id for item in reservations])
                account_by_sku = {account.sku_id: account for account in accounts}
                for reservation in reservations:
                    if reservation.status == "reserved":
                        account = account_by_sku[reservation.sku_id]
                        account.available += reservation.quantity
                        account.reserved -= reservation.quantity
                        reservation.status = "released"
                        reservation.released_at = now
                        reservation.revision += 1
                order.status = "cancelled"
                order.cancelled_at = now
                order.cancel_reason = "待付款超时"
                order.revision += 1
                await self.repository.save(order)
                await self.repository.save(
                    OrderEvent(
                        order_id=order.id,
                        revision=order.revision,
                        from_status="pending_payment",
                        to_status="cancelled",
                        actor_type="system",
                        actor_id=None,
                        reason="待付款超时",
                    )
                )
            return len(expired)

    async def _read(self, order: Order, user_id: UUID) -> OrderRead:
        items = await self.repository.items(order.id)
        return OrderRead(
            id=order.id,
            status=order.status,
            product_type=order.product_type,
            items_amount=order.items_amount,
            freight_amount=order.freight_amount,
            total_amount=order.total_amount,
            address_snapshot=order.address_snapshot,
            expires_at=order.expires_at,
            created_at=order.created_at,
            revision=order.revision,
            items=[OrderItemRead.model_validate(item) for item in items],
        )

    async def read(self, user_id: UUID, order_id: UUID) -> OrderRead:
        order = await self.repository.order(user_id, order_id)
        if order is None:
            raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
        return await self._read(order, user_id)

    async def cancel(self, user_id: UUID, order_id: UUID, *, reason: str = "用户取消") -> OrderRead:
        async with transaction_scope(self.session):
            order = await self.repository.order(user_id, order_id, lock=True)
            if order is None:
                raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
            if order.status == "cancelled":
                return await self._read(order, user_id)
            if order.status != "pending_payment":
                raise AppException(status_code=409, code=ErrorCode.ORDER_STATE_CONFLICT, message="当前订单状态不能取消")
            reservations = await self.repository.reservations(order.id, lock=True)
            accounts = await self.repository.inventory_accounts([item.sku_id for item in reservations])
            account_by_sku = {account.sku_id: account for account in accounts}
            now = datetime.now(UTC)
            for reservation in reservations:
                if reservation.status != "reserved":
                    continue
                account = account_by_sku[reservation.sku_id]
                account.available += reservation.quantity
                account.reserved -= reservation.quantity
                reservation.status = "released"
                reservation.released_at = now
                reservation.revision += 1
            order.status = "cancelled"
            order.cancelled_at = now
            order.cancel_reason = reason
            order.revision += 1
            await self.repository.save(order)
            await self.repository.save(
                OrderEvent(
                    order_id=order.id,
                    revision=order.revision,
                    from_status="pending_payment",
                    to_status="cancelled",
                    actor_type="user",
                    actor_id=user_id,
                    reason=reason,
                )
            )
            return await self._read(order, user_id)
