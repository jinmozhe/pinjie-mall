"""真实 PostgreSQL 运营链路。外层事务隔离测试数据，服务提交使用 savepoint。

不模拟 SQL、领域服务或审计；可信支付确认 DTO 只在测试中构造，不调用真实资金渠道。
独立连接的竞争与提交可见性由 test_commerce_concurrency 覆盖。
"""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.batch import ActiveStatusBatch, VersionedTarget
from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.db.models import Admin, Asset, User
from app.db.models.commerce_lifecycle import Fulfillment, PaymentAttempt
from app.db.models.distribution import CommissionRecord
from app.db.models.order import Order
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.db.transaction import transaction_scope
from app.domains.addresses import AddressInput, AddressService
from app.domains.addresses.repository import AddressRepository
from app.domains.cart.schemas import CartItemInput, CartItemUpdate
from app.domains.distribution import DistributionService, ReferralBindIn, WithdrawalCreate, WithdrawalReview
from app.domains.inventory import InventoryAdjustment, InventoryService
from app.domains.inventory.repository import InventoryRepository
from app.domains.lifecycle.schemas import (
    PaymentAttemptCreate,
    ProductReviewCreate,
    ReconciliationRecordCreate,
    RefundRequestCreate,
    RefundReview,
    ShipmentCreate,
    VerifiedPaymentConfirmation,
    VerifiedRefundConfirmation,
    VirtualDeliveryCreate,
)
from app.domains.orders import CheckoutLine, CheckoutRequest
from app.domains.products import (
    CategoryInput,
    CategoryUpdate,
    ProductCreate,
    ProductService,
    ProductStatusUpdate,
    ProductUpdate,
    SkuUpdate,
)
from app.domains.products.repository import ProductRepository
from app.domains.products.schemas import ProductStatusBatch, SkuInput, SkuStatusBatch
from app.domains.shipping import ShippingService, ShippingTemplateInput
from app.domains.shipping.repository import ShippingRepository
from app.domains.shipping.schemas import FreightQuoteInput
from app.services.cart import CartService
from app.services.commerce import AddressApplicationService, CommerceService
from app.services.commerce_reporting import (
    _RESOURCES,
    AdminWalletRead,
    CommerceFilters,
    CommerceReportingService,
    SelectedCommerceIds,
)
from app.services.distribution import AdminDistributionApplicationService
from app.services.lifecycle import AdminLifecycleApplicationService
from app.services.orders import OrderService
from app.services.payment_lifecycle import LifecycleService
from app.services.security_events import AuditCoordinator


@pytest.fixture
async def shop():
    url = os.environ["TEST_DATABASE_URL"]
    settings = Settings(_env_file=None, ENVIRONMENT="test", DATABASE_URL=url, TEST_DATABASE_URL=url)
    settings.validate_database_runtime()
    engine = create_async_engine(
        url, connect_args={"server_settings": {"lock_timeout": "5000ms", "statement_timeout": "15000ms"}}
    )
    async with engine.connect() as connection:
        outer = await connection.begin()
        factory = async_sessionmaker(connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
        async with factory() as session:
            actor = new_uuid7()
            users = [new_uuid7() for _ in range(3)]
            image = new_uuid7()
            async with transaction_scope(session):
                session.add(
                    Admin(
                        id=actor,
                        username=f"commerce-{actor.hex}",
                        password_hash="unused-test-hash",
                        is_active=True,
                        is_superuser=True,
                    )
                )
                session.add_all(
                    [
                        User(id=u, username=f"commerce-{u.hex}", password_hash="unused-test-hash", is_active=True)
                        for u in users
                    ]
                )
                session.add(
                    Asset(
                        id=image,
                        uploader_type="admin",
                        uploader_id=actor,
                        storage_driver="local",
                        file_key=f"test/{image}.png",
                        original_name="test.png",
                        mime_type="image/png",
                        file_size=1,
                        file_hash="a" * 64,
                        url=f"/uploads/{image}.png",
                        scene="general",
                    )
                )
            access = CommerceAccessRepository(session)
            audit = AuditCoordinator(
                session=session,
                session_factory=factory,
                actor_id=actor,
                metadata=RequestMetadata(str(new_uuid7()), str(new_uuid7()), "127.0.0.1", "pytest", "test"),
            )
            products = ProductService(ProductRepository(session))
            commerce = CommerceService(
                products=products,
                inventory=InventoryService(InventoryRepository(session)),
                shipping=ShippingService(ShippingRepository(session)),
                access=access,
                audit=audit,
                actor_id=actor,
            )
            lifecycle = LifecycleService(session)
            distribution = DistributionService(session)
            context = SimpleNamespace(
                session=session,
                commerce=commerce,
                products=products,
                actor=actor,
                users=users,
                image=image,
                lifecycle=lifecycle,
                distribution=distribution,
                orders=OrderService(session),
                cart=CartService(session),
                admin_lifecycle=AdminLifecycleApplicationService(
                    lifecycle=lifecycle, access=access, audit=audit, actor_id=actor
                ),
                admin_distribution=AdminDistributionApplicationService(
                    distribution=distribution, access=access, audit=audit, actor_id=actor
                ),
                reporting=CommerceReportingService(session),
                addresses=AddressApplicationService(
                    session, AddressService(AddressRepository(session)), access, users[0]
                ),
            )
            try:
                yield context
            finally:
                await session.rollback()
        await outer.rollback()
    await engine.dispose()


async def prepare_product(shop, physical=False):
    category = await shop.commerce.create_category(CategoryInput(name="运营测试分类"))
    shipping = await shop.commerce.create_shipping(
        ShippingTemplateInput(
            name="测试运费",
            pricing_method="piece",
            regions=[dict(provinces=[], first_unit=1, first_price="2.00", additional_unit=1, additional_price="1.00")],
        )
    )
    data = ProductCreate(
        name="运营测试商品",
        category_id=category.id,
        product_type="physical" if physical else "virtual",
        shipping_template_id=shipping.id if physical else None,
        image_asset_ids=[shop.image],
        skus=[SkuInput(code=f"SKU-{new_uuid7().hex}", price="100.00", weight_grams=100 if physical else 0)],
    )
    product = await shop.commerce.create_product(data)
    await shop.commerce.adjust_inventory(
        product.skus[0].id, InventoryAdjustment(request_id=new_uuid7(), revision=1, quantity_delta=50, reason="入库")
    )
    product = await shop.commerce.set_product_status(product.id, ProductStatusUpdate(revision=1, status="on_sale"))
    return product, category, shipping, data


async def prepare_paid_order(shop, physical=False):
    product, category, shipping, data = await prepare_product(shop, physical)
    profiles = [await shop.distribution.activate_profile(u) for u in shop.users]
    await shop.distribution.bind_referrer(shop.users[1], ReferralBindIn(invitation_code=profiles[2].invitation_code))
    await shop.distribution.bind_referrer(shop.users[0], ReferralBindIn(invitation_code=profiles[1].invitation_code))
    address = None
    if physical:
        address = await shop.addresses.create(
            AddressInput(
                receiver_name="测试收件人",
                mobile="13800000000",
                province_code="110000",
                city_code="110100",
                district_code="110101",
                province="北京",
                city="北京",
                district="东城",
                street_address="测试地址",
                is_default=True,
            )
        )
    request = CheckoutRequest(
        request_id=new_uuid7(),
        items=[CheckoutLine(sku_id=product.skus[0].id, quantity=2)],
        address_id=address.id if address else None,
    )
    preview = await shop.orders.preview(shop.users[0], request)
    order = await shop.orders.create(
        shop.users[0], request.model_copy(update={"quote_fingerprint": preview.fingerprint})
    )
    attempt_input = PaymentAttemptCreate(request_id=new_uuid7(), channel="wechat")
    attempt = await shop.lifecycle.initiate_payment(shop.users[0], order.id, attempt_input)
    assert attempt.status == "unavailable"
    assert (await shop.lifecycle.initiate_payment(shop.users[0], order.id, attempt_input)).id == attempt.id
    # 仅测试隔离库模拟未来渠道 adapter 已提交意图，不添加运行环境假成功入口。
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(PaymentAttempt).where(PaymentAttempt.id == attempt.id).values(status="pending")
        )
    confirmation = VerifiedPaymentConfirmation(
        payment_attempt_id=attempt.id,
        channel="wechat",
        channel_transaction_id=f"TEST-{attempt.id}",
        amount=order.total_amount,
        currency="CNY",
        confirmed_at=datetime.now(UTC),
        payload_hash="b" * 64,
    )
    confirmed = await shop.lifecycle.confirm_verified_payment(confirmation)
    assert confirmed.status == "succeeded"
    assert (await shop.lifecycle.confirm_verified_payment(confirmation)).id == attempt.id
    return order, product, confirmation


@pytest.mark.integration
async def test_catalog_operating_flow_and_atomic_batch_conflicts(shop):
    product, category, shipping, data = await prepare_product(shop)
    second = await shop.commerce.create_category(CategoryInput(name="第二分类"))
    assert (
        await shop.commerce.product_page(
            1, 20, search=product.skus[0].code, category_id=category.id, status="on_sale", product_type="virtual"
        )
    ).total == 1
    assert (await shop.commerce.product_page(1, 20, search="没有此名称")).total == 0
    assert (await shop.commerce.public_product_read(product.id)).images
    assert (await shop.commerce.public_product_page(1, 20)).total >= 1
    # 批次先修改一个有效目标，随后版本冲突；整个事务及版本必须回滚。
    with pytest.raises(AppException) as conflict:
        await shop.commerce.categories_status_batch(
            ActiveStatusBatch(
                targets=[VersionedTarget(id=category.id, revision=1), VersionedTarget(id=second.id, revision=99)],
                is_active=False,
            )
        )
    assert conflict.value.code == "CATEGORY_REVISION_CONFLICT"
    categories = {c.id: c for c in await shop.commerce.categories()}
    assert categories[category.id].is_active and categories[category.id].revision == 1
    await shop.session.commit()
    await shop.commerce.categories_status_batch(
        ActiveStatusBatch(targets=[VersionedTarget(id=second.id, revision=1)], is_active=False)
    )
    assert second.id not in {c.id for c in await shop.commerce.categories(public=True)}
    await shop.session.commit()
    await shop.commerce.update_category(second.id, CategoryUpdate(name="已恢复", revision=2, is_active=True))
    product = await shop.commerce.update_product(
        product.id,
        ProductUpdate(
            **data.model_dump(exclude={"skus", "description"}), revision=product.revision, description="新版说明"
        ),
    )
    assert product.description == "新版说明"
    sku = product.skus[0]
    product = await shop.commerce.write_sku(
        product.id, SkuUpdate(**sku.model_dump(exclude={"id"}), revision=product.revision), sku.id
    )
    product = await shop.commerce.write_sku(
        product.id,
        SkuUpdate(
            code=f"NEW-{new_uuid7().hex}",
            specifications={"套餐": "第二档"},
            price="120.00",
            weight_grams=0,
            revision=product.revision,
        ),
    )
    extra = next(s for s in product.skus if s.id != sku.id)
    assert (await shop.commerce.inventory_read(extra.id)).available == 0
    await shop.session.commit()
    product = await shop.commerce.skus_status_batch(
        product.id, SkuStatusBatch(sku_ids=[extra.id], revision=product.revision, is_active=False)
    )
    assert not next(s for s in product.skus if s.id == extra.id).is_active
    with pytest.raises(AppException):
        await shop.commerce.skus_status_batch(
            product.id, SkuStatusBatch(sku_ids=[sku.id], revision=product.revision, is_active=False)
        )
    assert next(s for s in (await shop.commerce.product_read(product.id)).skus if s.id == sku.id).is_active
    await shop.session.commit()
    assert (
        await shop.commerce.products_status_batch(
            ProductStatusBatch(targets=[VersionedTarget(id=product.id, revision=product.revision)], status="off_sale")
        )
    ).completed_count == 1
    product = await shop.commerce.product_read(product.id)
    await shop.session.commit()
    await shop.commerce.products_status_batch(
        ProductStatusBatch(targets=[VersionedTarget(id=product.id, revision=product.revision)], status="on_sale")
    )
    quote = await shop.commerce.shipping_quote(
        shipping.id, FreightQuoteInput(province_code="110000", pieces=3, weight_grams=0, items_amount="300.00")
    )
    assert quote.freight == Decimal("4.00")
    assert (await shop.commerce.shipping_page(1, 100)).total >= 1
    await shop.session.commit()
    await shop.commerce.shipping_status_batch(
        ActiveStatusBatch(targets=[VersionedTarget(id=shipping.id, revision=shipping.revision)], is_active=False)
    )
    assert not (await shop.commerce.shipping_read(shipping.id)).is_active
    assert (await shop.commerce.inventory_history(sku.id, 1, 20)).total == 1


@pytest.mark.integration
@pytest.mark.parametrize("physical", [False, True])
async def test_paid_delivery_refund_wallet_and_reporting_flow(shop, physical):
    order, product, confirmation = await prepare_paid_order(shop, physical)
    assert (await shop.orders.admin_read(order.id)).status == "paid"
    assert (await shop.lifecycle.fulfillment_for_user(shop.users[0], order.id)).revision == 1
    await shop.session.commit()
    if physical:
        delivered = await shop.admin_lifecycle.ship(
            order.id, ShipmentCreate(carrier="测试物流", tracking_number="TEST-001", revision=1)
        )
        assert delivered.status == "shipped"
        delivered = await shop.lifecycle.confirm_receipt(shop.users[0], order.id, delivered.revision)
    else:
        delivered = await shop.admin_lifecycle.deliver_virtual(
            order.id, VirtualDeliveryCreate(delivery_reference="测试交付凭证", revision=1)
        )
    assert delivered.status == "delivered"
    commission_page = await shop.distribution.commissions_for_user(shop.users[1], 1, 20)
    assert commission_page.total == 1 and commission_page.items[0].amount == Decimal("20.00")
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(CommissionRecord)
            .where(CommissionRecord.order_id == order.id)
            .values(settle_after=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await shop.distribution.settle_due() == 2
    assert await shop.distribution.settle_due() == 0
    wallets = await shop.distribution.wallets_for_user(shop.users[1])
    assert {w.wallet_type: w.available_amount for w in wallets} == {
        "commission": Decimal("20.00"),
        "consumption": Decimal("0.00"),
    }
    withdrawal_input = WithdrawalCreate(request_id=new_uuid7(), amount="15.00", destination_reference="测试脱敏目标")
    withdrawal = await shop.distribution.create_withdrawal(shop.users[1], withdrawal_input)
    assert (await shop.distribution.create_withdrawal(shop.users[1], withdrawal_input)).id == withdrawal.id
    approved = await shop.admin_distribution.approve_withdrawal(
        withdrawal.id, WithdrawalReview(revision=1, note="已核验")
    )
    assert approved.status == "approved" and approved.channel_reference is None
    review = await shop.lifecycle.create_review(
        shop.users[0], order.items[0].id, ProductReviewCreate(rating=5, content="测试评价")
    )
    assert (await shop.lifecycle.public_reviews(product.id, 1, 20)).items[0].id == review.id
    await shop.session.commit()
    refund_input = RefundRequestCreate(
        request_id=new_uuid7(), reason="测试售后", items=[dict(order_item_id=order.items[0].id, quantity=1)]
    )
    refund = await shop.lifecycle.create_refund(shop.users[0], order.id, refund_input)
    assert refund.amount == Decimal("100.00")
    assert (await shop.lifecycle.create_refund(shop.users[0], order.id, refund_input)).id == refund.id
    await shop.admin_lifecycle.approve_refund(refund.id, RefundReview(revision=1, note="同意退款"))
    refund_confirmation = VerifiedRefundConfirmation(
        refund_request_id=refund.id,
        channel="wechat",
        payment_transaction_id=confirmation.channel_transaction_id,
        amount=refund.amount,
        currency="CNY",
        channel_refund_id=f"REFUND-{refund.id}",
        confirmed_at=datetime.now(UTC),
        payload_hash="c" * 64,
    )
    assert (await shop.lifecycle.confirm_verified_refund(refund_confirmation)).status == "succeeded"
    assert (await shop.lifecycle.confirm_verified_refund(refund_confirmation)).id == refund.id
    wallet = next(w for w in await shop.distribution.wallets_for_user(shop.users[1]) if w.wallet_type == "commission")
    assert (wallet.available_amount, wallet.frozen_amount, wallet.debt_amount) == (
        Decimal("0.00"),
        Decimal("15.00"),
        Decimal("5.00"),
    )
    await shop.session.commit()
    reconciliation = await shop.admin_lifecycle.reconcile(
        ReconciliationRecordCreate(
            channel="wechat",
            channel_transaction_id=confirmation.channel_transaction_id,
            source_reference="测试账单",
            source_hash="d" * 64,
            amount=order.total_amount,
            currency="CNY",
            occurred_at=confirmation.confirmed_at,
        )
    )
    assert reconciliation.status == "matched"
    for resource, (_, schema) in _RESOURCES.items():
        result = await shop.reporting.page(resource, schema, CommerceFilters(page_size=100))
        assert result.items, resource
        key = "user_id" if resource == "members" else "id"
        selected = getattr(result.items[0], key)
        exported = await shop.reporting.export(resource, SelectedCommerceIds(ids=[selected]))
        assert len(exported.rows) == 1 and key in exported.columns
        assert "request_hash" not in exported.columns and "password_hash" not in exported.columns
    wallets_page = await shop.reporting.page(
        "wallets", AdminWalletRead, CommerceFilters(user_id=shop.users[1], wallet_type="commission")
    )
    ledger = await shop.reporting.ledgers(wallets_page.items[0].id, 1, 20)
    assert {row.entry_type for row in ledger.items} == {
        "commission_settlement",
        "withdrawal_freeze",
        "commission_recovery",
    }
    assert sum(row.amount for row in ledger.items) == Decimal("0.00")
    assert (await shop.distribution.withdrawals_for_user(shop.users[1], 1, 20)).total == 1
    assert (await shop.lifecycle.refunds_for_user(shop.users[0], order.id))[0].status == "succeeded"


@pytest.mark.integration
async def test_cart_cancel_and_rejected_reviews_release_resources(shop):
    product, _, _, _ = await prepare_product(shop)
    user = shop.users[0]
    item = await shop.cart.add(user, CartItemInput(sku_id=product.skus[0].id, quantity=1))
    item = await shop.cart.add(user, CartItemInput(sku_id=product.skus[0].id, quantity=2))
    assert item.quantity == 3
    item = await shop.cart.update(user, item.id, CartItemUpdate(revision=item.revision, quantity=2, selected=False))
    assert (await shop.cart.list(user))[0].selected is False
    await shop.cart.remove(user, item.id)
    assert await shop.cart.list(user) == []
    request = CheckoutRequest(request_id=new_uuid7(), items=[CheckoutLine(sku_id=product.skus[0].id, quantity=2)])
    quote = await shop.orders.preview(user, request)
    request = request.model_copy(update={"quote_fingerprint": quote.fingerprint})
    order = await shop.orders.create(user, request)
    assert (await shop.orders.create(user, request)).id == order.id
    assert (await shop.orders.cancel(user, order.id)).status == "cancelled"
    assert (await shop.orders.cancel(user, order.id)).status == "cancelled"
    assert (await shop.commerce.inventory_read(product.skus[0].id)).available == 50


@pytest.mark.integration
async def test_reporting_rejects_unsupported_filters_and_stale_selection(shop):
    with pytest.raises(AppException) as missing:
        await shop.reporting.export("orders", SelectedCommerceIds(ids=[new_uuid7()]))
    assert missing.value.status_code == 409
    with pytest.raises(AppException) as invalid:
        await shop.reporting.page("wallets", AdminWalletRead, CommerceFilters(order_id=new_uuid7()))
    assert invalid.value.status_code == 422
    with pytest.raises(AppException) as absent:
        await shop.reporting.ledgers(new_uuid7(), 1, 20)
    assert absent.value.status_code == 404
    duplicate = new_uuid7()
    with pytest.raises(ValidationError):
        SelectedCommerceIds(ids=[duplicate, duplicate])
    with pytest.raises(ValidationError):
        ActiveStatusBatch(targets=[VersionedTarget(id=duplicate, revision=1)] * 2, is_active=True)


@pytest.mark.integration
async def test_rejected_withdrawal_and_refund_preserve_money_and_idempotency(shop):
    order, _, confirmation = await prepare_paid_order(shop)
    await shop.admin_lifecycle.deliver_virtual(order.id, VirtualDeliveryCreate(revision=1, delivery_reference="交付"))
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(CommissionRecord)
            .where(CommissionRecord.order_id == order.id)
            .values(settle_after=datetime.now(UTC) - timedelta(days=1))
        )
    await shop.distribution.settle_due()
    user = shop.users[1]
    before = await shop.distribution.profile_for_user(user)
    assert (await shop.distribution.activate_profile(user)).invitation_code == before.invitation_code
    request = WithdrawalCreate(request_id=new_uuid7(), amount="10.00", destination_reference="测试引用")
    withdrawal = await shop.distribution.create_withdrawal(user, request)
    with pytest.raises(AppException) as reused:
        await shop.distribution.create_withdrawal(user, request.model_copy(update={"amount": Decimal("11.00")}))
    assert reused.value.code == "WITHDRAWAL_REQUEST_CONFLICT"
    with pytest.raises(AppException):
        await shop.admin_distribution.approve_withdrawal(withdrawal.id, WithdrawalReview(revision=99, note="旧版本"))
    assert (await shop.distribution.pending_withdrawals(1, 100)).total >= 1
    await shop.session.commit()
    rejected = await shop.admin_distribution.reject_withdrawal(withdrawal.id, WithdrawalReview(revision=1, note="驳回"))
    assert rejected.status == "rejected"
    wallet = next(w for w in await shop.distribution.wallets_for_user(user) if w.wallet_type == "commission")
    assert (wallet.available_amount, wallet.frozen_amount) == (Decimal("20.00"), Decimal("0.00"))
    await shop.session.commit()
    with pytest.raises(AppException):
        await shop.distribution.create_withdrawal(
            user, request.model_copy(update={"request_id": new_uuid7(), "amount": Decimal("21.00")})
        )
    refund_input = RefundRequestCreate(
        request_id=new_uuid7(), reason="售后测试", items=[dict(order_item_id=order.items[0].id, quantity=2)]
    )
    refund = await shop.lifecycle.create_refund(shop.users[0], order.id, refund_input)
    with pytest.raises(AppException):
        await shop.admin_lifecycle.approve_refund(refund.id, RefundReview(revision=99, note="过期决定"))
    rejected_refund = await shop.admin_lifecycle.reject_refund(refund.id, RefundReview(revision=1, note="资料不全"))
    assert rejected_refund.status == "rejected"
    # 拒绝后数量占用释放，可重新申请全部商品金额。
    next_refund = await shop.lifecycle.create_refund(
        shop.users[0], order.id, refund_input.model_copy(update={"request_id": new_uuid7()})
    )
    assert next_refund.amount == order.items_amount
    with pytest.raises(AppException):
        await shop.lifecycle.create_refund(
            shop.users[0], order.id, refund_input.model_copy(update={"request_id": new_uuid7()})
        )
    recon_input = ReconciliationRecordCreate(
        channel="wechat",
        channel_transaction_id=confirmation.channel_transaction_id,
        source_reference="账单",
        source_hash="a" * 64,
        amount=order.total_amount,
        currency="CNY",
        occurred_at=confirmation.confirmed_at,
    )
    recon = await shop.admin_lifecycle.reconcile(recon_input)
    assert (await shop.admin_lifecycle.reconcile(recon_input)).id == recon.id
    with pytest.raises(AppException):
        await shop.admin_lifecycle.reconcile(recon_input.model_copy(update={"amount": Decimal("1.00")}))
    mismatch = await shop.admin_lifecycle.reconcile(
        recon_input.model_copy(update={"channel_transaction_id": f"missing-{new_uuid7()}"})
    )
    assert mismatch.status == "discrepancy" and mismatch.payment_attempt_id is None
    # 退款与对账操作不能改写订单支付事实。
    assert (await shop.orders.admin_read(order.id)).status == "paid"


@pytest.mark.integration
async def test_expiration_auto_delivery_and_missing_resource_boundaries(shop):
    order, product, _ = await prepare_paid_order(shop, physical=True)
    await shop.admin_lifecycle.ship(order.id, ShipmentCreate(carrier="测试", tracking_number="TEST", revision=1))
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(Fulfillment)
            .where(Fulfillment.order_id == order.id)
            .values(auto_confirm_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await shop.lifecycle.auto_confirm_due() == 1
    assert await shop.lifecycle.auto_confirm_due() == 0
    assert (await shop.lifecycle.admin_fulfillment(order.id)).status == "delivered"
    await shop.session.commit()
    address = (await shop.addresses.list_addresses())[0]
    request = CheckoutRequest(
        request_id=new_uuid7(), items=[CheckoutLine(sku_id=product.skus[0].id, quantity=1)], address_id=address.id
    )
    quote = await shop.orders.preview(shop.users[0], request)
    unpaid = await shop.orders.create(
        shop.users[0], request.model_copy(update={"quote_fingerprint": quote.fingerprint})
    )
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(Order).where(Order.id == unpaid.id).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await shop.orders.expire_due() == 1
    assert (await shop.orders.read(shop.users[0], unpaid.id)).status == "cancelled"
    assert (await shop.orders.admin_page(1, 100)).total >= 2
    assert (await shop.lifecycle.admin_refunds(1, 100)).items == []
    await shop.session.commit()
    for operation in [
        lambda: shop.orders.admin_read(new_uuid7()),
        lambda: shop.lifecycle.admin_fulfillment(new_uuid7()),
        lambda: shop.distribution.profile_for_user(new_uuid7()),
        lambda: shop.distribution.wallets_for_user(new_uuid7()),
        lambda: shop.commerce.product_read(new_uuid7()),
        lambda: shop.commerce.shipping_read(new_uuid7()),
        lambda: shop.lifecycle.fulfillment_for_user(shop.users[1], order.id),
        lambda: shop.lifecycle.refunds_for_user(shop.users[1], order.id),
    ]:
        with pytest.raises(AppException) as absent:
            await operation()
        assert absent.value.status_code == 404


@pytest.mark.integration
async def test_real_reporting_routes_export_filters_and_wallet_ledger(shop):
    from httpx import ASGITransport, AsyncClient

    from app.api.commerce_reporting_router import get_commerce_reporting_service
    from app.api.dependencies import get_current_admin, require_admin_csrf
    from app.domains.admin.permissions import PERMISSION_CODES
    from app.main import create_app

    order, _, _ = await prepare_paid_order(shop)
    app = create_app(Settings.model_construct(log_file_enabled=False))
    app.dependency_overrides[get_commerce_reporting_service] = lambda: shop.reporting
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(permissions=PERMISSION_CODES)
    app.dependency_overrides[require_admin_csrf] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        for resource in _RESOURCES:
            response = await client.get(f"/api/v1/admin/{resource}")
            assert response.status_code == 200
            rows = response.json()["data"]["items"]
            if not rows:
                response = await client.post(f"/api/v1/admin/{resource}/export", json={"ids": [str(new_uuid7())]})
                assert response.status_code == 409
                continue
            key = "user_id" if resource == "members" else "id"
            response = await client.post(f"/api/v1/admin/{resource}/export", json={"ids": [rows[0][key]]})
            assert response.status_code == 200 and len(response.json()["data"]["rows"]) == 1
        response = await client.get(
            "/api/v1/admin/orders",
            params={
                "record_id": str(order.id),
                "user_id": str(shop.users[0]),
                "status": "paid",
                "product_type": "virtual",
            },
        )
        assert response.json()["data"]["total"] == 1
        assert (await client.get("/api/v1/admin/orders", params={"user_id": str(shop.users[1])})).json()["data"][
            "total"
        ] == 0
        assert (await client.get("/api/v1/admin/payments", params={"channel": "invalid"})).status_code == 422
        assert (await client.get("/api/v1/admin/orders", params={"record_id": "invalid"})).status_code == 422
        response = await client.get("/api/v1/admin/wallets", params={"user_id": str(shop.users[0])})
        wallet_id = response.json()["data"]["items"][0]["id"]
        assert (await client.get(f"/api/v1/admin/wallets/{wallet_id}/ledgers")).json()["data"]["items"] == []
        app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(permissions=frozenset({"orders:read"}))
        assert (await client.post("/api/v1/admin/orders/export", json={"ids": [str(order.id)]})).status_code == 403


@pytest.mark.integration
async def test_catalog_batch_routes_validate_permissions_versions_and_csrf(shop):
    from httpx import ASGITransport, AsyncClient

    from app.api.commerce_dependencies import get_admin_commerce
    from app.api.dependencies import get_current_admin, require_admin_csrf
    from app.domains.admin.permissions import PERMISSION_CODES
    from app.main import create_app

    product, category, shipping, _ = await prepare_product(shop)
    app = create_app(Settings.model_construct(log_file_enabled=False, admin_origins=["http://testserver"]))
    app.dependency_overrides[get_admin_commerce] = lambda: shop.commerce
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(permissions=PERMISSION_CODES)
    app.dependency_overrides[require_admin_csrf] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        for route in [
            "product-categories",
            "products",
            f"products/{product.id}",
            "shipping-templates",
            f"shipping-templates/{shipping.id}",
            f"inventory/{product.skus[0].id}",
            f"inventory/{product.skus[0].id}/movements",
        ]:
            assert (await client.get(f"/api/v1/admin/{route}")).status_code == 200
        await shop.session.commit()
        for route, target, version, field in [
            ("product-categories", category.id, category.revision, {"is_active": False}),
            ("shipping-templates", shipping.id, shipping.revision, {"is_active": False}),
            ("products", product.id, product.revision, {"status": "off_sale"}),
        ]:
            payload = {"targets": [{"id": str(target), "revision": version}], **field}
            response = await client.patch(f"/api/v1/admin/{route}/status/batch", json=payload)
            assert response.status_code == 200 and response.json()["data"]["completed_count"] == 1
            assert (await client.patch(f"/api/v1/admin/{route}/status/batch", json=payload)).status_code == 409
            assert (
                await client.patch(
                    f"/api/v1/admin/{route}/status/batch", json={**payload, "targets": payload["targets"] * 2}
                )
            ).status_code == 422
        response = await client.patch(
            f"/api/v1/admin/products/{product.id}/skus/status/batch",
            json={"sku_ids": [str(product.skus[0].id)], "revision": product.revision + 1, "is_active": False},
        )
        assert response.status_code == 200 and response.json()["data"]["skus"][0]["is_active"] is False
        app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(permissions=frozenset({"products:read"}))
        assert (
            await client.patch(
                "/api/v1/admin/products/status/batch",
                json={"targets": [{"id": str(product.id), "revision": 1}], "status": "on_sale"},
            )
        ).status_code == 403
        app.dependency_overrides.pop(require_admin_csrf)
        response = await client.patch(
            "/api/v1/admin/products/status/batch",
            json={"targets": [{"id": str(product.id), "revision": 1}], "status": "on_sale"},
        )
        assert response.status_code == 403 and response.json()["code"] == "CSRF_REJECTED"
