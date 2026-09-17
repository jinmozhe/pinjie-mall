"""四阶段边界回归资产；仅在明确授权 pytest 后执行。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.payload_sanitizer import is_sensitive_route
from app.db.models.distribution import (
    CommissionRecord,
    CommissionRecovery,
    WalletAccount,
    WalletLedger,
    WithdrawalRequest,
)
from app.db.models.inventory import InventoryAccount
from app.db.models.product import Category, Product, ProductSku
from app.db.models.reservation import InventoryReservation, InventoryReservationEvent
from app.domains.cart.schemas import CartItemUpdate
from app.domains.distribution.schemas import ReferralBindIn, WithdrawalCreate, WithdrawalReview
from app.domains.distribution.service import DistributionService
from app.domains.inventory.schemas import InventoryAdjustment
from app.domains.inventory.service import InventoryService
from app.domains.lifecycle.schemas import VerifiedRefundConfirmation
from app.domains.orders.schemas import CheckoutLine, CheckoutRequest
from app.domains.products.schemas import CheckoutSku
from app.domains.products.service import ProductService
from app.services.cart import CartService
from app.services.orders import OrderService
from app.services.payment_lifecycle import LifecycleService


class Session:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class Access:
    async def require_active_user(self, user_id):
        pass


class InventoryStore:
    def __init__(self, available=10, reserved=0):
        self.account = InventoryAccount(sku_id=new_uuid7(), available=available, reserved=reserved, revision=1)
        self.rows = []
        self.events = []

    async def accounts(self, sku_ids):
        return [self.account] if self.account.sku_id in sku_ids else []

    async def get(self, sku_id, *, lock=False):
        return self.account

    async def movement(self, sku_id, request_id):
        return None

    async def reservations(self, order_id):
        return [row for row in self.rows if row.order_id == order_id]

    async def save(self, value):
        if isinstance(value, InventoryReservation) and value not in self.rows:
            self.rows.append(value)
        if isinstance(value, InventoryReservationEvent):
            self.events.append(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["confirmed", "released"])
async def test_inventory_transitions_preserve_versions_balances_and_idempotency(status):
    store = InventoryStore()
    service = InventoryService(store)
    order_id = new_uuid7()
    quantities = {store.account.sku_id: 3}
    await service.reserve(order_id, quantities)
    await service.reserve(order_id, quantities)
    assert (store.account.available, store.account.reserved, store.account.revision) == (7, 3, 2)
    await service.transition_reservations(order_id, quantities, status)
    await service.transition_reservations(order_id, quantities, status)
    assert (store.account.available, store.account.reserved, store.account.revision) == (
        10 if status == "released" else 7,
        0,
        3,
    )
    assert [
        (event.before_available, event.after_available, event.before_reserved, event.after_reserved)
        for event in store.events
    ] == [(10, 7, 0, 3), (7, 10 if status == "released" else 7, 3, 0)]


@pytest.mark.asyncio
async def test_inventory_adjustment_cannot_fill_capacity_reserved_for_order_release():
    store = InventoryStore(available=2147483646, reserved=1)
    with pytest.raises(AppException) as error:
        await InventoryService(store).adjust(
            store.account.sku_id,
            InventoryAdjustment(request_id=new_uuid7(), revision=1, quantity_delta=1, reason="盘点"),
            new_uuid7(),
        )
    assert error.value.code == "INVENTORY_QUANTITY_REJECTED"
    assert store.account.available == 2147483646


@pytest.mark.asyncio
async def test_payment_cannot_confirm_missing_or_mismatched_inventory_reservations():
    store = InventoryStore()
    with pytest.raises(AppException) as error:
        await InventoryService(store).transition_reservations(new_uuid7(), {store.account.sku_id: 1}, "confirmed")
    assert error.value.code == "ORDER_STOCK_REJECTED"
    assert store.account.available == 10
    assert not store.events


class CatalogStore:
    def __init__(self):
        self.parent = Category(
            id=new_uuid7(), name="停用父分类", is_active=False, parent_id=None, sort_order=0, revision=1
        )
        self.category = Category(
            id=new_uuid7(), name="启用子分类", is_active=True, parent_id=self.parent.id, sort_order=0, revision=1
        )
        self.product = Product(
            id=new_uuid7(),
            category_id=self.category.id,
            name="商品",
            product_type="virtual",
            status="on_sale",
            revision=1,
        )
        self.sku = ProductSku(
            id=new_uuid7(),
            product_id=self.product.id,
            code="SKU",
            specifications={},
            price=Decimal("1"),
            weight_grams=0,
            is_active=True,
        )

    async def categories(self):
        return [self.parent, self.category]

    async def checkout_skus(self, sku_ids):
        return [(self.sku, self.product)]


@pytest.mark.asyncio
async def test_hidden_parent_category_also_blocks_checkout():
    store = CatalogStore()
    with pytest.raises(AppException) as error:
        await ProductService(store).checkout_skus([store.sku.id])
    assert error.value.code == "CHECKOUT_INVALID"


class Products:
    def __init__(self, price):
        self.sku = CheckoutSku(
            id=new_uuid7(),
            product_id=new_uuid7(),
            code="VIRTUAL",
            specifications={},
            price=Decimal(price),
            weight_grams=0,
            product_name="商品",
            product_type="virtual",
            product_revision=1,
            shipping_template_id=None,
        )

    async def checkout_skus(self, sku_ids):
        return [self.sku]


@pytest.mark.asyncio
@pytest.mark.parametrize(("price", "quantity"), [("0.00", 1), ("9999999999999.99", 2)])
async def test_checkout_rejects_unpayable_and_overflow_orders_before_persistence(price, quantity):
    products = Products(price)
    service = OrderService(Session(), products=products)
    with pytest.raises(AppException) as error:
        await service.preview(
            new_uuid7(),
            CheckoutRequest(request_id=new_uuid7(), items=[CheckoutLine(sku_id=products.sku.id, quantity=quantity)]),
        )
    assert error.value.code == "CHECKOUT_INVALID"


class CartStore:
    def __init__(self):
        self.item = SimpleNamespace(revision=3, quantity=2, selected=True)

    async def lock_user(self, user_id):
        pass

    async def get(self, user_id, item_id, *, lock=False):
        return self.item


@pytest.mark.asyncio
async def test_cart_stale_write_is_rejected_before_mutating_selection():
    store, session = CartStore(), Session()
    with pytest.raises(AppException) as error:
        await CartService(session, store, access=Access()).update(
            new_uuid7(), new_uuid7(), CartItemUpdate(revision=2, selected=False)
        )
    assert error.value.code == "CART_REVISION_CONFLICT"
    assert store.item.selected
    assert session.rollbacks == 1 and session.commits == 0


class RefundStore:
    def __init__(self):
        self.row = SimpleNamespace(
            id=new_uuid7(),
            order_id=new_uuid7(),
            status="approved",
            amount=Decimal("10.00"),
            currency="CNY",
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
        self.writes = []

    async def lock_key(self, kind, value):
        pass

    async def refund(self, refund_id, *, lock=False):
        return self.row

    async def save(self, value):
        self.writes.append(value)


class Orders:
    async def order(self, order_id, *, lock=False):
        return SimpleNamespace(id=order_id, status="paid", currency="CNY")


@pytest.mark.asyncio
async def test_refund_confirmation_cannot_claim_a_different_amount():
    store = RefundStore()
    service = LifecycleService(Session(), store, orders=Orders())
    data = VerifiedRefundConfirmation(
        refund_request_id=store.row.id,
        channel="wechat",
        payment_transaction_id="payment",
        channel_refund_id="refund",
        amount="9.99",
        currency="CNY",
        confirmed_at=datetime.now(UTC),
        payload_hash="a" * 64,
    )
    with pytest.raises(AppException) as error:
        await service.confirm_verified_refund(data)
    assert error.value.code == "ORDER_STATE_CONFLICT"
    assert store.row.status == "approved" and not store.writes


class DistributionStore:
    def __init__(self, *, settled=False):
        self.commission = CommissionRecord(
            id=new_uuid7(),
            beneficiary_user_id=new_uuid7(),
            base_amount=Decimal("0.30"),
            amount=Decimal("0.03"),
            recovered_amount=Decimal("0.00"),
            status="settled" if settled else "frozen",
        )
        self.account = WalletAccount(
            id=new_uuid7(),
            available_amount=Decimal("0.02"),
            frozen_amount=Decimal("0.00"),
            debt_amount=Decimal("0.00"),
            revision=1,
        )
        self.recoveries = {}
        self.ledgers = []
        self.withdrawal_row = None

    async def commissions_for_order(self, order_id, *, lock=False):
        return [self.commission]

    async def lock_wallets(self, user_ids):
        pass

    async def recovery(self, commission_id, refund_id):
        return self.recoveries.get(refund_id)

    async def wallet(self, user_id, wallet_type, *, lock=False):
        return self.account

    async def withdrawal(self, withdrawal_id, *, lock=False):
        return self.withdrawal_row

    async def save(self, value):
        if isinstance(value, CommissionRecovery):
            self.recoveries[value.refund_request_id] = value
        if isinstance(value, WalletLedger):
            self.ledgers.append(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("settled", [False, True])
async def test_split_refunds_recover_full_commission_without_rounding_leak(settled):
    store = DistributionStore(settled=settled)
    service = DistributionService(Session(), store)
    order_id = new_uuid7()
    # 单笔 0.03 元退款对应佣金只有 0.003 元；逐笔舍入会全部漏追。
    for number in range(1, 11):
        refund_id = new_uuid7()
        for _ in range(2):
            await service.recover_for_refund_in_open_transaction(
                refund_request_id=refund_id,
                order_id=order_id,
                cumulative_refunded_amount=Decimal("0.03") * number,
                refunded_at=datetime.now(UTC),
            )
    assert store.commission.recovered_amount == Decimal("0.03")
    assert store.commission.status == "recovered"
    assert sum((item.amount for item in store.recoveries.values()), Decimal("0")) == Decimal("0.03")
    if settled:
        assert store.account.available_amount == Decimal("0.00")
        assert store.account.debt_amount == Decimal("0.01")
        assert sum((item.debt_delta for item in store.ledgers), Decimal("0")) == Decimal("0.01")
    else:
        assert not store.ledgers


@pytest.mark.asyncio
async def test_rejected_withdrawal_offsets_refund_debt_before_releasing_available_funds():
    store = DistributionStore()
    store.account.available_amount = Decimal("0.00")
    store.account.frozen_amount = Decimal("10.00")
    store.account.debt_amount = Decimal("3.00")
    now = datetime.now(UTC)
    store.withdrawal_row = WithdrawalRequest(
        id=new_uuid7(),
        user_id=new_uuid7(),
        amount=Decimal("10.00"),
        currency="CNY",
        destination_reference="masked",
        status="requested",
        revision=1,
        created_at=now,
        updated_at=now,
    )
    result = await DistributionService(Session(), store).reject_withdrawal_in_open_transaction(
        store.withdrawal_row.id, WithdrawalReview(revision=1, note="驳回"), new_uuid7()
    )
    assert result.status == "rejected"
    assert (store.account.available_amount, store.account.frozen_amount, store.account.debt_amount) == (
        Decimal("7.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    assert (store.ledgers[0].amount, store.ledgers[0].frozen_delta, store.ledgers[0].debt_delta) == (
        Decimal("7.00"),
        Decimal("-10.00"),
        Decimal("-3.00"),
    )


@pytest.mark.asyncio
async def test_withdrawal_with_refund_debt_cannot_be_approved():
    store = DistributionStore()
    store.account.debt_amount = Decimal("1.00")
    store.withdrawal_row = WithdrawalRequest(
        id=new_uuid7(), user_id=new_uuid7(), amount=Decimal("10.00"), status="requested", revision=1
    )
    with pytest.raises(AppException) as error:
        await DistributionService(Session(), store).approve_withdrawal_in_open_transaction(
            store.withdrawal_row.id, WithdrawalReview(revision=1, note="通过"), new_uuid7()
        )
    assert error.value.code == "WITHDRAWAL_STATE_CONFLICT"
    assert store.withdrawal_row.status == "requested"


def test_whitespace_does_not_satisfy_referral_or_withdrawal_minimum_length():
    with pytest.raises(ValidationError):
        ReferralBindIn(invitation_code="        ")
    with pytest.raises(ValidationError):
        WithdrawalCreate(request_id=new_uuid7(), amount="1.00", destination_reference=" ")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/addresses",
        "/api/v1/addresses/{address_id}",
        "/api/v1/orders/{order_id}/refunds",
        "/api/v1/distribution/me/withdrawals",
        "/api/v1/admin/orders/{order_id}/fulfillment/shipment",
        "/api/v1/admin/refunds/{refund_id}/approve",
    ],
)
def test_commerce_private_bodies_are_never_captured_on_error(path):
    assert is_sensitive_route(path)


def test_commerce_privacy_route_prefix_does_not_match_unrelated_paths():
    assert not is_sensitive_route("/api/v1/orders-export-public")
