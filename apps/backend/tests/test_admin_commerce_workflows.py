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
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.batch import ActiveStatusBatch, VersionedTarget
from app.core.config import Settings
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.request_metadata import RequestMetadata
from app.db.models import Admin, AdminSession, Asset, AuditEvent, User
from app.db.models.commerce_lifecycle import Fulfillment, PaymentAttempt, RefundAttempt, RefundEvent, RefundRequest
from app.db.models.distribution import (
    CommissionRecord,
    DurableTask,
    MemberLevel,
    MemberProfile,
    MembershipQualificationEvent,
)
from app.db.models.inventory import InventoryAccount, InventoryMovement
from app.db.models.order import Order
from app.db.models.purchase import ProductPurchaseRecord
from app.db.repositories.commerce_access import CommerceAccessRepository
from app.db.transaction import transaction_scope
from app.domains.addresses import AddressInput, AddressService
from app.domains.addresses.repository import AddressRepository
from app.domains.cart.schemas import CartItemInput, CartItemUpdate
from app.domains.commissioning import CommissionPolicyService
from app.domains.commissioning.schemas import (
    CommissionAmountRuleCreate,
    CommissionControlUpdate,
    CommissionDistributionRuleCreate,
    CommissionPolicyCreate,
    CommissionPolicyPublish,
)
from app.domains.distribution import (
    DistributionService,
    ReferralBindIn,
    WithdrawalCreate,
    WithdrawalManualCompletion,
    WithdrawalReview,
)
from app.domains.inventory import InventoryAdjustment, InventoryService
from app.domains.inventory.repository import InventoryRepository
from app.domains.lifecycle.schemas import (
    PaymentAttemptCreate,
    ProductReviewCreate,
    ReconciliationRecordCreate,
    ReconciliationResolve,
    RefundRequestCreate,
    RefundReview,
    ShipmentCreate,
    VerifiedPaymentConfirmation,
    VerifiedRefundConfirmation,
    VirtualDeliveryCreate,
)
from app.domains.orders import CheckoutLine, CheckoutRequest, OrderAcceptance
from app.domains.products import (
    CategoryInput,
    CategoryUpdate,
    ProductCreate,
    ProductService,
    ProductStatusUpdate,
    ProductUpdate,
    SkuUpdate,
)
from app.domains.products.catalog_schemas import NewSkuInput
from app.domains.products.repository import ProductRepository
from app.domains.products.schemas import ProductStatusBatch, SkuStatusBatch
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
from app.services.distribution import AdminDistributionApplicationService, UserDistributionApplicationService
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
            actor_session_id = new_uuid7()
            users = [new_uuid7() for _ in range(3)]
            image = new_uuid7()
            now = datetime.now(UTC)
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
                    AdminSession(
                        id=actor_session_id,
                        admin_id=actor,
                        family_id=new_uuid7(),
                        credential_profile="browser_cookie",
                        client_id="pinjie-admin",
                        csrf_digest="a" * 64,
                        last_seen_at=now,
                        idle_expires_at=now + timedelta(days=7),
                        absolute_expires_at=now + timedelta(days=30),
                    )
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
                        scene="product",
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
                actor_session_id=actor_session_id,
            )
            lifecycle = LifecycleService(session)
            distribution = DistributionService(session)
            context = SimpleNamespace(
                session=session,
                factory=factory,
                settings=settings,
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
                user_distribution=UserDistributionApplicationService(
                    distribution=distribution,
                    audit=AuditCoordinator(
                        session=session,
                        session_factory=factory,
                        actor_id=users[1],
                        metadata=RequestMetadata(str(new_uuid7()), str(new_uuid7()), "127.0.0.1", "pytest", "test"),
                    ),
                    actor_id=users[1],
                ),
                reporting=CommerceReportingService(session, audit),
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
        category_revision=category.revision,
        image_asset_ids=[shop.image],
        skus=[NewSkuInput(code=f"SKU-{new_uuid7().hex}", price="100.00", weight_grams=100 if physical else None)],
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
    if not hasattr(shop, "commission_level"):
        level = MemberLevel(
            id=new_uuid7(),
            code=f"commerce_{new_uuid7().hex[:16]}",
            name="交易测试等级",
            discount_factor=Decimal("1.000000"),
            level_rank=1,
            sort_order=0,
            is_active=True,
            revision=1,
        )
        async with transaction_scope(shop.session):
            shop.session.add(level)
            await shop.session.flush()
            await shop.session.execute(
                update(MemberProfile).where(MemberProfile.user_id.in_(shop.users)).values(level_id=level.id)
            )
        policies = CommissionPolicyService(session=shop.session, actor_id=shop.actor, audit=shop.commerce.audit)
        policy = await policies.create_policy(
            CommissionPolicyCreate(
                name="交易测试分佣政策",
                default_mode="fixed_amount",
                default_amount_per_unit="10.00",
                max_depth=1,
            )
        )
        await policies.add_amount_rule(
            policy.id,
            CommissionAmountRuleCreate(sku_id=product.skus[0].id, rule_mode="fixed_amount", amount_per_unit="10.00"),
        )
        await policies.add_distribution_rule(
            policy.id,
            CommissionDistributionRuleCreate(
                buyer_level_id=level.id,
                ancestor_depth=1,
                beneficiary_level_id=level.id,
                allocation_mode="percentage",
                rate="1.000000",
            ),
        )
        await policies.publish_policy(policy.id, CommissionPolicyPublish(revision=policy.revision))
        control = await policies.commission_control()
        await policies.update_commission_control(
            CommissionControlUpdate(revision=control.revision, commissions_enabled=True)
        )
        shop.commission_level = level
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
    await shop.lifecycle.confirm_order_scheduled(attempt.id)
    return order, product, confirmation


@pytest.mark.integration
async def test_product_detail_order_public_projection_and_revision(shop, tmp_path):
    product, category, shipping, data = await prepare_product(shop)
    ids = [new_uuid7(), new_uuid7()]
    async with transaction_scope(shop.session):
        for index, asset_id in enumerate(ids):
            shop.session.add(
                Asset(
                    id=asset_id,
                    uploader_type="admin",
                    uploader_id=shop.actor,
                    storage_driver="local",
                    file_key=f"product/{asset_id}.png",
                    original_name=f"detail-{index}.png",
                    mime_type="image/png",
                    file_size=100,
                    file_hash=str(index + 1) * 64,
                    url=f"/static/uploads/product/{asset_id}.png",
                    scene="product",
                    width=750,
                    height=1000,
                    frame_count=1,
                )
            )
    payload = ProductUpdate(
        **data.model_dump(exclude={"skus", "attributes", "category_revision", "detail_image_asset_ids"}),
        detail_image_asset_ids=list(reversed(ids)),
        revision=product.revision,
    )
    updated = await shop.commerce.update_product(product.id, payload)
    detail = await shop.commerce.product_read(product.id)
    assert detail.detail_image_asset_ids == list(reversed(ids))
    assert detail.image_asset_ids == [shop.image]
    assert [item.asset_id for item in detail.detail_images] == list(reversed(ids))
    public = await shop.commerce.public_product_read(product.id)
    assert [item.url for item in public.detail_images] == [item.url for item in detail.detail_images]
    assert all(set(item.model_dump()) == {"url", "width", "height"} for item in public.detail_images)
    assert "detail_images" not in (await shop.commerce.product_page(1, 20)).items[0].model_dump()
    await shop.session.commit()
    with pytest.raises(AppException) as conflict:
        await shop.commerce.update_product(product.id, payload.model_copy(update={"detail_image_asset_ids": []}))
    assert conflict.value.code == "PRODUCT_REVISION_CONFLICT"
    assert (await shop.commerce.product_read(product.id)).detail_image_asset_ids == list(reversed(ids))
    await shop.session.commit()

    # Real AssetService checks all references before touching any file in a bulk request.
    from app.services.assets import AssetService
    from app.services.storage import LocalStorageProvider

    storage = LocalStorageProvider(tmp_path / "uploads", io_concurrency=1)
    service = AssetService(
        session=shop.session,
        session_factory=shop.factory,
        settings=shop.settings,
        storage=storage,
        metadata=RequestMetadata(str(new_uuid7()), str(new_uuid7()), "127.0.0.1", "pytest", "test"),
    )
    for bulk in (False, True):
        with pytest.raises(AppException) as referenced:
            if bulk:
                await service.delete_bulk(asset_ids=ids, actor_id=shop.actor)
            else:
                await service.delete(asset_id=ids[0], actor_id=shop.actor)
        assert referenced.value.status_code == 409
        assert not (tmp_path / ".uploads-trash").exists()
    cleared = payload.model_copy(update={"detail_image_asset_ids": [], "revision": updated.revision})
    await shop.commerce.update_product(product.id, cleared)
    assert (await shop.commerce.product_read(product.id)).detail_images == []
    assert await shop.session.get(Asset, ids[0]) is not None


@pytest.mark.integration
async def test_product_detail_invalid_metadata_rolls_back_other_fields(shop):
    product, category, shipping, data = await prepare_product(shop)
    payload = ProductUpdate(
        **data.model_dump(exclude={"name", "skus", "attributes", "category_revision", "detail_image_asset_ids"}),
        name="不得写入",
        detail_image_asset_ids=[shop.image],
        revision=product.revision,
    )
    with pytest.raises(AppException) as rejected:
        await shop.commerce.update_product(product.id, payload)
    assert rejected.value.code == "PRODUCT_IMAGE_REJECTED"
    actual = await shop.commerce.product_read(product.id)
    assert actual.name == product.name and actual.revision == product.revision
    assert actual.detail_images == []


@pytest.mark.integration
async def test_backfill_check_apply_and_corruption(shop, tmp_path):
    import hashlib
    import io

    from PIL import Image

    from app.services.asset_image_backfill import AssetImageBackfill
    from app.services.storage import LocalStorageProvider

    output = io.BytesIO()
    Image.new("RGB", (750, 1000), "red").save(output, format="PNG")
    payload = output.getvalue()
    storage = LocalStorageProvider(tmp_path / "uploads", io_concurrency=1)
    staged = await storage.stage(io.BytesIO(payload), extension="png", max_bytes=len(payload))
    key = f"product/{shop.image}.png"
    await storage.commit(staged, file_key=key)
    async with transaction_scope(shop.session):
        asset = await shop.session.get(Asset, shop.image)
        asset.file_key, asset.file_size, asset.file_hash = key, len(payload), hashlib.sha256(payload).hexdigest()
    backfill = AssetImageBackfill(shop.factory, storage)
    assert (await backfill.run_one(shop.image, apply=False)).status == "ready"
    await shop.session.refresh(asset)
    assert asset.width is None
    await shop.session.commit()
    assert (await backfill.run_one(shop.image, apply=True)).status == "updated"
    await shop.session.refresh(asset)
    assert (asset.width, asset.height, asset.frame_count) == (750, 1000, 1)
    await shop.session.commit()
    assert (await backfill.run_one(shop.image, apply=True)).status == "already_complete"
    async with transaction_scope(shop.session):
        asset.width = asset.height = asset.frame_count = None
        asset.file_hash = "0" * 64
    assert (await backfill.run_one(shop.image, apply=True)).status == "invalid_image_or_hash"
    await shop.session.refresh(asset)
    assert asset.width is None


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
            **data.model_dump(exclude={"skus", "description", "attributes", "category_revision"}),
            revision=product.revision,
            description="新版说明",
        ),
    )
    assert product.description == "新版说明"
    sku = product.skus[0]
    product = await shop.commerce.write_sku(
        product.id,
        SkuUpdate(
            **sku.model_dump(exclude={"id", "sku_no", "specifications", "specification_key", "archived_at"}),
            revision=product.revision,
        ),
        sku.id,
    )
    assert (await shop.commerce.inventory_read(sku.id)).available == 50
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
    with pytest.raises(AppException) as unavailable:
        await shop.commerce.shipping_quote(
            shipping.id, FreightQuoteInput(province_code="110000", pieces=3, weight_grams=0, items_amount="300.00")
        )
    assert unavailable.value.code == "COMMERCE_UPGRADE_REQUIRED"
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
    consumption_event = await shop.session.scalar(
        select(MembershipQualificationEvent).where(
            MembershipQualificationEvent.user_id == shop.users[0],
            MembershipQualificationEvent.metric == "consumption",
            MembershipQualificationEvent.source_type == "order_confirm",
            MembershipQualificationEvent.source_id == order.id,
        )
    )
    assert consumption_event is not None
    assert (consumption_event.order_id, consumption_event.amount_delta, consumption_event.reverses_event_id) == (
        order.id,
        order.items_amount,
        None,
    )
    await shop.admin_lifecycle.accept_order(
        order.id, OrderAcceptance(revision=(await shop.orders.admin_read(order.id)).revision)
    )
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
    assert await shop.distribution.settle_due() == 1
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
    refund_order, _, refund_payment = await prepare_paid_order(shop, physical)
    refund_input = RefundRequestCreate(request_id=new_uuid7(), reason="测试售后")
    refund = await shop.lifecycle.create_refund(shop.users[0], refund_order.id, refund_input)
    assert refund.amount == refund_order.total_amount
    assert (await shop.lifecycle.create_refund(shop.users[0], refund_order.id, refund_input)).id == refund.id
    assert refund.status == "approved" and refund.revision == 2
    refund_attempt = await shop.session.scalar(
        select(RefundAttempt).where(RefundAttempt.refund_request_id == refund.id)
    )
    assert refund_attempt is not None
    refund_confirmation = VerifiedRefundConfirmation(
        refund_attempt_id=refund_attempt.id,
        channel="wechat",
        payment_transaction_id=refund_payment.channel_transaction_id,
        amount=refund.amount,
        currency="CNY",
        channel_refund_id=f"REFUND-{refund.id}",
        confirmed_at=datetime.now(UTC),
        payload_hash="c" * 64,
    )
    confirmed_refund = await shop.lifecycle.confirm_verified_refund(refund_confirmation)
    assert confirmed_refund.status == "succeeded"
    assert (await shop.lifecycle.confirm_verified_refund(refund_confirmation)).id == refund_attempt.id
    await shop.lifecycle.complete_refund_scheduled(refund_attempt.id)
    assert (await shop.lifecycle.refunds_for_user(shop.users[0], refund_order.id))[0].status == "completed"
    refund_consumption = await shop.session.scalar(
        select(MembershipQualificationEvent).where(
            MembershipQualificationEvent.user_id == shop.users[0],
            MembershipQualificationEvent.metric == "consumption",
            MembershipQualificationEvent.source_type == "refund",
            MembershipQualificationEvent.source_id == refund.id,
        )
    )
    original_refund_consumption = await shop.session.scalar(
        select(MembershipQualificationEvent).where(
            MembershipQualificationEvent.user_id == shop.users[0],
            MembershipQualificationEvent.metric == "consumption",
            MembershipQualificationEvent.source_type == "order_confirm",
            MembershipQualificationEvent.source_id == refund_order.id,
        )
    )
    assert refund_consumption is not None and original_refund_consumption is not None
    assert (refund_consumption.order_id, refund_consumption.amount_delta, refund_consumption.reverses_event_id) == (
        refund_order.id,
        -refund_order.items_amount,
        original_refund_consumption.id,
    )
    completed = await shop.admin_distribution.complete_withdrawal_manually(
        withdrawal.id,
        WithdrawalManualCompletion(revision=approved.revision, note="已线下转账", payment_reference="OFFLINE-TEST-001"),
    )
    assert completed.status == "succeeded" and completed.channel_reference == "OFFLINE-TEST-001"
    withdrawal_audits = list(
        await shop.session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.action == "withdrawal.state_changed",
                AuditEvent.target_id == withdrawal.id,
                AuditEvent.result == "succeeded",
            )
            .order_by(AuditEvent.target_revision)
        )
    )
    assert [(event.actor_type, event.target_revision) for event in withdrawal_audits] == [("admin", 2), ("admin", 3)]
    with pytest.raises(AppException):
        await shop.admin_distribution.complete_withdrawal_manually(
            withdrawal.id,
            WithdrawalManualCompletion(
                revision=completed.revision, note="重复确认", payment_reference="OFFLINE-TEST-001"
            ),
        )
    wallet = next(w for w in await shop.distribution.wallets_for_user(shop.users[1]) if w.wallet_type == "commission")
    assert (wallet.available_amount, wallet.frozen_amount, wallet.debt_amount) == (
        Decimal("5.00"),
        Decimal("0.00"),
        Decimal("0.00"),
    )
    await shop.session.commit()
    reconciliation = await shop.admin_lifecycle.reconcile(
        ReconciliationRecordCreate(
            channel="wechat",
            record_type="payment",
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
        "withdrawal_paid",
    }
    assert sum(row.amount for row in ledger.items) == Decimal("5.00")
    assert (await shop.distribution.withdrawals_for_user(shop.users[1], 1, 20)).total == 1
    assert (await shop.lifecycle.refunds_for_user(shop.users[0], refund_order.id))[0].status == "completed"


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
    await shop.admin_lifecycle.accept_order(
        order.id, OrderAcceptance(revision=(await shop.orders.admin_read(order.id)).revision)
    )
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
    withdrawal = await shop.user_distribution.create_withdrawal(request)
    replayed = await shop.user_distribution.create_withdrawal(request)
    assert replayed.id == withdrawal.id
    withdrawal_audits = list(
        (
            await shop.session.scalars(
                select(AuditEvent).where(AuditEvent.target_id == withdrawal.id).order_by(AuditEvent.occurred_at)
            )
        ).all()
    )
    assert [(event.actor_type, event.action, event.target_revision, event.result) for event in withdrawal_audits] == [
        ("user", "withdrawal.state_changed", 1, "succeeded"),
        ("user", "withdrawal.request_replayed", 1, "succeeded"),
    ]
    with pytest.raises(AppException) as reused:
        await shop.user_distribution.create_withdrawal(request.model_copy(update={"amount": Decimal("11.00")}))
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
    refund_order, _, _ = await prepare_paid_order(shop)
    accepted = await shop.admin_lifecycle.accept_order(
        refund_order.id, OrderAcceptance(revision=(await shop.orders.admin_read(refund_order.id)).revision)
    )
    assert accepted.acceptance_status == "accepted"
    refund_input = RefundRequestCreate(request_id=new_uuid7(), reason="售后测试")
    refund = await shop.lifecycle.create_refund(shop.users[0], refund_order.id, refund_input)
    with pytest.raises(AppException):
        await shop.admin_lifecycle.approve_refund(refund.id, RefundReview(revision=99, note="过期决定"))
    rejected_refund = await shop.admin_lifecycle.reject_refund(refund.id, RefundReview(revision=1, note="资料不全"))
    assert rejected_refund.status == "rejected"
    # 整单申请被拒绝后可重新提交。
    next_refund = await shop.lifecycle.create_refund(
        shop.users[0], refund_order.id, refund_input.model_copy(update={"request_id": new_uuid7()})
    )
    assert next_refund.amount == refund_order.items_amount
    with pytest.raises(AppException):
        await shop.lifecycle.create_refund(
            shop.users[0], refund_order.id, refund_input.model_copy(update={"request_id": new_uuid7()})
        )
    recon_input = ReconciliationRecordCreate(
        channel="wechat",
        record_type="payment",
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
    await shop.admin_lifecycle.accept_order(
        order.id, OrderAcceptance(revision=(await shop.orders.admin_read(order.id)).revision)
    )
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


@pytest.mark.integration
async def test_trusted_payment_confirmation_rejects_conflicting_replay(shop):
    order, _, confirmation = await prepare_paid_order(shop)
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_verified_payment(
            confirmation.model_copy(update={"channel_transaction_id": f"CONFLICT-{order.id}"})
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"


@pytest.mark.integration
async def test_fulfillment_rejects_wrong_type_and_stale_versions(shop):
    virtual_order, _, _ = await prepare_paid_order(shop)
    await shop.admin_lifecycle.accept_order(
        virtual_order.id, OrderAcceptance(revision=(await shop.orders.admin_read(virtual_order.id)).revision)
    )
    with pytest.raises(AppException) as error:
        await shop.admin_lifecycle.ship(
            virtual_order.id, ShipmentCreate(carrier="测试物流", tracking_number="VIRTUAL", revision=1)
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"
    with pytest.raises(AppException) as error:
        await shop.admin_lifecycle.deliver_virtual(
            virtual_order.id, VirtualDeliveryCreate(delivery_reference="虚拟交付", revision=99)
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_receipt(shop.users[0], virtual_order.id, revision=1)
    assert error.value.code == "ORDER_STATE_CONFLICT"
    delivered = await shop.admin_lifecycle.deliver_virtual(
        virtual_order.id, VirtualDeliveryCreate(delivery_reference="虚拟交付", revision=1)
    )
    assert delivered.status == "delivered"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.create_refund(
            shop.users[0], virtual_order.id, RefundRequestCreate(request_id=new_uuid7(), reason="交付后退款")
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"

    physical_order, _, _ = await prepare_paid_order(shop, physical=True)
    await shop.admin_lifecycle.accept_order(
        physical_order.id, OrderAcceptance(revision=(await shop.orders.admin_read(physical_order.id)).revision)
    )
    with pytest.raises(AppException) as error:
        await shop.admin_lifecycle.deliver_virtual(
            physical_order.id, VirtualDeliveryCreate(delivery_reference="错误交付", revision=1)
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_receipt(shop.users[0], physical_order.id, revision=1)
    assert error.value.code == "ORDER_STATE_CONFLICT"
    with pytest.raises(AppException) as error:
        await shop.admin_lifecycle.ship(
            physical_order.id, ShipmentCreate(carrier="测试物流", tracking_number="STALE", revision=99)
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"
    shipped = await shop.admin_lifecycle.ship(
        physical_order.id, ShipmentCreate(carrier="测试物流", tracking_number="PHYSICAL", revision=1)
    )
    delivered = await shop.lifecycle.confirm_receipt(shop.users[0], physical_order.id, shipped.revision)
    assert delivered.status == "delivered"
    assert (await shop.lifecycle.confirm_receipt(shop.users[0], physical_order.id, revision=1)).status == "delivered"


@pytest.mark.integration
async def test_payment_and_refund_confirmation_reject_invalid_channel_amount_and_replay(shop):
    paid_order, _, payment_confirmation = await prepare_paid_order(shop)
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_verified_payment(payment_confirmation.model_copy(update={"channel": "alipay"}))
    assert error.value.code == "ORDER_STATE_CONFLICT"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_verified_payment(
            payment_confirmation.model_copy(update={"amount": payment_confirmation.amount + Decimal("0.01")})
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"

    refund_order, _, refund_payment = await prepare_paid_order(shop)
    refund = await shop.lifecycle.create_refund(
        shop.users[0], refund_order.id, RefundRequestCreate(request_id=new_uuid7(), reason="退款确认边界")
    )
    refund_attempt = await shop.session.scalar(
        select(RefundAttempt).where(RefundAttempt.refund_request_id == refund.id)
    )
    assert refund_attempt is not None
    confirmation = VerifiedRefundConfirmation(
        refund_attempt_id=refund_attempt.id,
        channel="wechat",
        payment_transaction_id=refund_payment.channel_transaction_id,
        amount=refund.amount,
        currency="CNY",
        channel_refund_id=f"REFUND-BOUNDARY-{refund.id}",
        confirmed_at=datetime.now(UTC),
        payload_hash="e" * 64,
    )
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_verified_refund(confirmation.model_copy(update={"channel": "alipay"}))
    assert error.value.code == "ORDER_STATE_CONFLICT"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_verified_refund(
            confirmation.model_copy(update={"amount": confirmation.amount + Decimal("0.01")})
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"
    completed = await shop.lifecycle.confirm_verified_refund(confirmation)
    assert completed.status == "succeeded"
    await shop.lifecycle.complete_refund_scheduled(refund_attempt.id)
    assert (await shop.lifecycle.refunds_for_user(shop.users[0], refund_order.id))[0].status == "completed"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.confirm_verified_refund(
            confirmation.model_copy(update={"channel_refund_id": f"CONFLICT-{refund.id}"})
        )
    assert error.value.code == "ORDER_STATE_CONFLICT"


@pytest.mark.integration
@pytest.mark.parametrize("payment_status", ["created", "pending", "unknown"])
async def test_unresolved_payment_blocks_expiry_and_cancellation_without_releasing_stock(shop, payment_status):
    product, _, _, _ = await prepare_product(shop)
    request = CheckoutRequest(request_id=new_uuid7(), items=[CheckoutLine(sku_id=product.skus[0].id, quantity=1)])
    preview = await shop.orders.preview(shop.users[0], request)
    order = await shop.orders.create(
        shop.users[0], request.model_copy(update={"quote_fingerprint": preview.fingerprint})
    )
    attempt = await shop.lifecycle.initiate_payment(
        shop.users[0], order.id, PaymentAttemptCreate(request_id=new_uuid7(), channel="wechat")
    )
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(PaymentAttempt).where(PaymentAttempt.id == attempt.id).values(status=payment_status)
        )
        await shop.session.execute(
            update(Order).where(Order.id == order.id).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert not await shop.orders.expire_scheduled(order.id)
    assert not await shop.orders.expire_scheduled(order.id)
    with pytest.raises(AppException) as blocked:
        await shop.orders.cancel(shop.users[0], order.id)
    assert blocked.value.code == "ORDER_STATE_CONFLICT"
    assert (await shop.orders.read(shop.users[0], order.id)).status == "pending_payment"
    inventory = (
        await shop.session.execute(
            select(InventoryAccount.available, InventoryAccount.reserved).where(
                InventoryAccount.sku_id == product.skus[0].id
            )
        )
    ).one()
    assert tuple(inventory) == (49, 1)
    tasks = list(
        await shop.session.scalars(select(DurableTask).where(DurableTask.business_key == f"payment-query:{attempt.id}"))
    )
    assert len(tasks) == 1 and tasks[0].task_type == "payment_query" and tasks[0].status == "pending"
    assert (
        await shop.session.scalar(select(PaymentAttempt.status).where(PaymentAttempt.id == attempt.id))
        == payment_status
    )


@pytest.mark.integration
@pytest.mark.parametrize("scenario", ["duplicate", "cancelled", "expired"])
async def test_late_and_duplicate_payments_preserve_money_and_refund_only_extra_payment(shop, scenario):
    product, _, _, _ = await prepare_product(shop)
    request = CheckoutRequest(request_id=new_uuid7(), items=[CheckoutLine(sku_id=product.skus[0].id, quantity=1)])
    preview = await shop.orders.preview(shop.users[0], request)
    order = await shop.orders.create(
        shop.users[0], request.model_copy(update={"quote_fingerprint": preview.fingerprint})
    )
    first = await shop.lifecycle.initiate_payment(
        shop.users[0], order.id, PaymentAttemptCreate(request_id=new_uuid7(), channel="wechat")
    )
    extra = await shop.lifecycle.initiate_payment(
        shop.users[0], order.id, PaymentAttemptCreate(request_id=new_uuid7(), channel="wechat")
    )
    confirmed_at = datetime.now(UTC)
    confirmation = VerifiedPaymentConfirmation(
        payment_attempt_id=extra.id,
        channel="wechat",
        channel_transaction_id=f"EXTRA-{extra.id}",
        amount=order.total_amount,
        currency="CNY",
        confirmed_at=confirmed_at,
        payload_hash="d" * 64,
    )
    if scenario == "duplicate":
        await shop.lifecycle.confirm_verified_payment(
            confirmation.model_copy(
                update={"payment_attempt_id": first.id, "channel_transaction_id": f"FIRST-{first.id}"}
            )
        )
        # Money has committed, but the order and reserved stock await the independent follow-up.
        assert (await shop.orders.read(shop.users[0], order.id)).status == "pending_payment"
        with pytest.raises(AppException) as blocked:
            await shop.orders.cancel(shop.users[0], order.id)
        assert blocked.value.code == "ORDER_STATE_CONFLICT"
        await shop.lifecycle.confirm_order_scheduled(first.id)
    elif scenario == "cancelled":
        await shop.orders.cancel(shop.users[0], order.id)
    else:
        async with transaction_scope(shop.session):
            await shop.session.execute(update(Order).where(Order.id == order.id).values(expires_at=confirmed_at))

    # A locally closed or unavailable attempt must still retain a later verified money fact.
    async with transaction_scope(shop.session):
        await shop.session.execute(update(PaymentAttempt).where(PaymentAttempt.id == extra.id).values(status="closed"))
    assert (await shop.lifecycle.confirm_verified_payment(confirmation)).status == "succeeded"
    await shop.lifecycle.confirm_order_scheduled(extra.id)
    await shop.lifecycle.confirm_order_scheduled(extra.id)
    attempts = list(
        await shop.session.scalars(select(RefundAttempt).where(RefundAttempt.payment_attempt_id == extra.id))
    )
    assert len(attempts) == 1
    abnormal = attempts[0]
    assert abnormal.purpose == ("duplicate_payment" if scenario == "duplicate" else "late_payment")
    assert abnormal.refund_request_id is None and abnormal.amount == order.total_amount
    abnormal_id = abnormal.id
    await shop.session.commit()
    refund_confirmation = VerifiedRefundConfirmation(
        refund_attempt_id=abnormal_id,
        channel="wechat",
        payment_transaction_id=confirmation.channel_transaction_id,
        amount=order.total_amount,
        currency="CNY",
        channel_refund_id=f"EXTRA-REFUND-{abnormal_id}",
        confirmed_at=datetime.now(UTC),
        payload_hash="e" * 64,
    )
    assert (await shop.lifecycle.confirm_verified_refund(refund_confirmation)).status == "succeeded"
    await shop.lifecycle.complete_refund_scheduled(abnormal_id)
    stored_order = (await shop.session.execute(select(Order.__table__).where(Order.id == order.id))).mappings().one()
    assert stored_order["status"] == ("paid" if scenario == "duplicate" else "cancelled")
    assert stored_order["accepted_payment_attempt_id"] == (first.id if scenario == "duplicate" else None)
    assert await shop.session.scalar(select(RefundRequest.id).where(RefundRequest.order_id == order.id)) is None
    inventory = await shop.session.scalar(
        select(InventoryAccount.available).where(InventoryAccount.sku_id == product.skus[0].id)
    )
    assert inventory == (49 if scenario == "duplicate" else 50)
    contributions = list(
        await shop.session.scalars(
            select(MembershipQualificationEvent).where(MembershipQualificationEvent.order_id == order.id)
        )
    )
    assert len(contributions) == (1 if scenario == "duplicate" else 0)
    assert all(row.amount_delta == order.items_amount for row in contributions)


@pytest.mark.integration
async def test_refund_followup_rolls_back_and_retries_without_repeating_effects(shop):
    order, product, payment = await prepare_paid_order(shop)
    refund = await shop.lifecycle.create_refund(
        shop.users[0], order.id, RefundRequestCreate(request_id=new_uuid7(), reason="补偿失败恢复")
    )
    attempt_id = await shop.session.scalar(select(RefundAttempt.id).where(RefundAttempt.refund_request_id == refund.id))
    assert attempt_id is not None
    confirmation = VerifiedRefundConfirmation(
        refund_attempt_id=attempt_id,
        channel="wechat",
        payment_transaction_id=payment.channel_transaction_id,
        amount=refund.amount,
        currency="CNY",
        channel_refund_id=f"REFUND-RECOVERY-{refund.id}",
        confirmed_at=datetime.now(UTC),
        payload_hash="f" * 64,
    )
    assert (await shop.lifecycle.confirm_verified_refund(confirmation)).status == "succeeded"

    async def snapshot():
        # Read persisted columns directly so rollback assertions cannot reuse stale ORM instances.
        result = {}
        for model, predicate in (
            (RefundRequest, RefundRequest.id == refund.id),
            (RefundAttempt, RefundAttempt.id == attempt_id),
            (RefundEvent, (RefundEvent.refund_request_id == refund.id) | (RefundEvent.refund_attempt_id == attempt_id)),
            (InventoryAccount, InventoryAccount.sku_id == product.skus[0].id),
            (InventoryMovement, InventoryMovement.sku_id == product.skus[0].id),
            (ProductPurchaseRecord, ProductPurchaseRecord.order_id == order.id),
            (CommissionRecord, CommissionRecord.order_id == order.id),
            (MembershipQualificationEvent, MembershipQualificationEvent.order_id == order.id),
            (Fulfillment, Fulfillment.order_id == order.id),
            (DurableTask, DurableTask.business_key == f"refund-followup:{attempt_id}"),
        ):
            rows = await shop.session.execute(select(model.__table__).where(predicate).order_by(model.id))
            result[model.__tablename__] = [dict(row) for row in rows.mappings()]
        await shop.session.commit()
        return result

    confirmed = await snapshot()
    assert confirmed["refund_requests"][0]["status"] == "approved"
    assert confirmed["refund_requests"][0]["completed_at"] is None
    assert confirmed["refund_attempts"][0]["confirmed_at"] == confirmation.confirmed_at
    assert len(confirmed["durable_tasks"]) == 1
    assert confirmed["durable_tasks"][0]["status"] == "pending"
    assert confirmed["product_purchase_records"][0]["status"] == "confirmed"
    assert len(confirmed["membership_qualification_events"]) == 1

    # Persist a conflicting fulfillment fact in the isolated fixture. The real service rejects it
    # after inventory, purchase, commission and membership writes, exercising the transaction rollback.
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(Fulfillment).where(Fulfillment.order_id == order.id).values(status="cancelled")
        )
    before_failure = await snapshot()
    with pytest.raises(AppException) as error:
        await shop.lifecycle.complete_refund_scheduled(attempt_id)
    assert error.value.code == "ORDER_STATE_CONFLICT"
    assert error.value.message == "退款完成时履约状态异常"
    assert await snapshot() == before_failure

    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(Fulfillment)
            .where(Fulfillment.order_id == order.id)
            .values(status=confirmed["fulfillments"][0]["status"])
        )
    await shop.lifecycle.complete_refund_scheduled(attempt_id)
    completed = await snapshot()
    assert completed["refund_requests"][0]["status"] == "completed"
    assert completed["refund_requests"][0]["completed_at"] == confirmation.confirmed_at
    assert completed["refund_attempts"] == confirmed["refund_attempts"]
    assert completed["inventory_accounts"][0]["available"] == (
        confirmed["inventory_accounts"][0]["available"] + order.items[0].quantity
    )
    assert len(completed["inventory_movements"]) == len(confirmed["inventory_movements"]) + 1
    assert completed["product_purchase_records"][0]["status"] == "refunded"
    assert completed["fulfillments"][0]["status"] == "cancelled"
    qualification = completed["membership_qualification_events"]
    assert len(qualification) == 2
    assert sum(row["amount_delta"] for row in qualification) == Decimal("0.00")
    assert completed["durable_tasks"] == confirmed["durable_tasks"]

    # Simulate redelivery after the business commit but before the worker acknowledges its task.
    await shop.lifecycle.complete_refund_scheduled(attempt_id)
    await shop.lifecycle.confirm_verified_refund(confirmation)
    assert await snapshot() == completed


@pytest.mark.integration
async def test_checkout_request_payment_and_cancellation_conflicts_preserve_order_state(shop):
    product, _, _, _ = await prepare_product(shop)
    request = CheckoutRequest(request_id=new_uuid7(), items=[CheckoutLine(sku_id=product.skus[0].id, quantity=1)])
    preview = await shop.orders.preview(shop.users[0], request)
    with pytest.raises(AppException) as error:
        await shop.orders.create(shop.users[0], request.model_copy(update={"quote_fingerprint": "stale"}))
    assert error.value.code == "CHECKOUT_STALE_QUOTE"
    order = await shop.orders.create(
        shop.users[0], request.model_copy(update={"quote_fingerprint": preview.fingerprint})
    )
    with pytest.raises(AppException) as error:
        await shop.orders.create(
            shop.users[0],
            request.model_copy(
                update={
                    "items": [CheckoutLine(sku_id=product.skus[0].id, quantity=2)],
                    "quote_fingerprint": preview.fingerprint,
                }
            ),
        )
    assert error.value.code == "ORDER_REQUEST_CONFLICT"
    payment = PaymentAttemptCreate(request_id=new_uuid7(), channel="wechat")
    assert (await shop.lifecycle.initiate_payment(shop.users[0], order.id, payment)).status == "unavailable"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.initiate_payment(shop.users[0], order.id, payment.model_copy(update={"channel": "alipay"}))
    assert error.value.code == "ORDER_REQUEST_CONFLICT"
    with pytest.raises(AppException) as error:
        await shop.lifecycle.initiate_payment(
            shop.users[0], new_uuid7(), PaymentAttemptCreate(request_id=new_uuid7(), channel="wechat")
        )
    assert error.value.code == "ORDER_NOT_FOUND"
    cancelled = await shop.orders.cancel(shop.users[0], order.id)
    assert cancelled.status == "cancelled"
    assert (await shop.orders.cancel(shop.users[0], order.id)).status == "cancelled"


@pytest.mark.integration
async def test_manual_money_and_lifecycle_missing_resource_boundaries(shop):
    await shop.distribution.activate_profile(shop.users[1])
    with pytest.raises(AppException) as error:
        await shop.distribution.create_withdrawal(
            shop.users[1], WithdrawalCreate(request_id=new_uuid7(), amount="1.00", destination_reference="余额不足")
        )
    assert error.value.code == "WALLET_INSUFFICIENT_BALANCE"
    assert (
        await shop.distribution.matched_withdrawal_id_in_open_transaction(
            channel="manual", channel_reference="UNKNOWN", amount=Decimal("1.00"), currency="CNY"
        )
        is None
    )
    with pytest.raises(AppException) as error:
        await shop.admin_distribution.approve_withdrawal(new_uuid7(), WithdrawalReview(revision=1, note="不存在"))
    assert error.value.code == "WITHDRAWAL_NOT_FOUND"
    with pytest.raises(AppException) as error:
        await shop.admin_distribution.reject_withdrawal(new_uuid7(), WithdrawalReview(revision=1, note="不存在"))
    assert error.value.code == "WITHDRAWAL_NOT_FOUND"
    with pytest.raises(AppException) as error:
        await shop.admin_distribution.complete_withdrawal_manually(
            new_uuid7(), WithdrawalManualCompletion(revision=1, note="不存在", payment_reference="OFFLINE-MISSING")
        )
    assert error.value.code == "WITHDRAWAL_NOT_FOUND"
    with pytest.raises(AppException):
        await shop.distribution.settle_due_in_open_transaction(limit=0)
    with pytest.raises(AppException):
        await shop.distribution.recover_for_refund_in_open_transaction(
            refund_request_id=new_uuid7(),
            order_id=new_uuid7(),
            cumulative_refunded_amount=Decimal("-0.01"),
            refunded_at=datetime.now(UTC),
        )
    with pytest.raises(AppException):
        await shop.lifecycle.admin_fulfillment(new_uuid7())
    with pytest.raises(AppException):
        await shop.lifecycle.auto_confirm_scheduled(new_uuid7())

    order, product, _ = await prepare_paid_order(shop)
    with pytest.raises(AppException):
        await shop.lifecycle.create_review(
            shop.users[0], order.items[0].id, ProductReviewCreate(rating=5, content="过早评价")
        )
    await shop.admin_lifecycle.accept_order(
        order.id, OrderAcceptance(revision=(await shop.orders.admin_read(order.id)).revision)
    )
    await shop.admin_lifecycle.deliver_virtual(
        order.id, VirtualDeliveryCreate(revision=1, delivery_reference="评价交付")
    )
    review = await shop.lifecycle.create_review(
        shop.users[0], order.items[0].id, ProductReviewCreate(rating=5, content="已交付评价")
    )
    assert (
        await shop.lifecycle.create_review(
            shop.users[0], order.items[0].id, ProductReviewCreate(rating=5, content="已交付评价")
        )
    ).id == review.id
    with pytest.raises(AppException):
        await shop.lifecycle.create_review(
            shop.users[0], order.items[0].id, ProductReviewCreate(rating=4, content="冲突评价")
        )
    assert (await shop.lifecycle.public_reviews(product.id, 1, 20)).total == 1


@pytest.mark.integration
async def test_auto_delivery_manual_refund_and_unmatched_reconciliation_paths(shop):
    physical_order, _, _ = await prepare_paid_order(shop, physical=True)
    await shop.admin_lifecycle.accept_order(
        physical_order.id, OrderAcceptance(revision=(await shop.orders.admin_read(physical_order.id)).revision)
    )
    shipped = await shop.admin_lifecycle.ship(
        physical_order.id, ShipmentCreate(carrier="自动确认", tracking_number="AUTO-CONFIRM", revision=1)
    )
    async with transaction_scope(shop.session):
        await shop.session.execute(
            update(Fulfillment)
            .where(Fulfillment.order_id == physical_order.id)
            .values(auto_confirm_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await shop.lifecycle.auto_confirm_scheduled(shipped.id) is True
    assert await shop.lifecycle.auto_confirm_scheduled(shipped.id) is False

    refund_order, _, _ = await prepare_paid_order(shop)
    accepted = await shop.admin_lifecycle.accept_order(
        refund_order.id, OrderAcceptance(revision=(await shop.orders.admin_read(refund_order.id)).revision)
    )
    assert accepted.acceptance_status == "accepted"
    manual_refund = await shop.lifecycle.create_refund(
        shop.users[0], refund_order.id, RefundRequestCreate(request_id=new_uuid7(), reason="人工审核路径")
    )
    assert manual_refund.status == "requested"
    approved = await shop.admin_lifecycle.approve_refund(
        manual_refund.id, RefundReview(revision=manual_refund.revision, note="人工审核通过")
    )
    assert approved.status == "approved"
    with pytest.raises(AppException):
        await shop.admin_lifecycle.approve_refund(new_uuid7(), RefundReview(revision=1, note="不存在"))
    with pytest.raises(AppException):
        await shop.admin_lifecycle.reject_refund(new_uuid7(), RefundReview(revision=1, note="不存在"))

    occurred_at = datetime.now(UTC)
    refund_reconciliation = await shop.admin_lifecycle.reconcile(
        ReconciliationRecordCreate(
            channel="wechat",
            record_type="refund",
            channel_transaction_id="UNMATCHED-REFUND",
            source_reference="缺失退款账单",
            source_hash="f" * 64,
            amount=Decimal("1.00"),
            currency="CNY",
            occurred_at=occurred_at,
        )
    )
    assert refund_reconciliation.status == "discrepancy"
    resolved_reconciliation = await shop.admin_lifecycle.resolve_reconciliation(
        refund_reconciliation.id,
        ReconciliationResolve(revision=refund_reconciliation.revision, note="已核对渠道差异并完成后续处理"),
    )
    assert (
        resolved_reconciliation.status,
        resolved_reconciliation.resolution_status,
        resolved_reconciliation.resolution_note,
        resolved_reconciliation.resolved_by_id,
        resolved_reconciliation.revision,
        resolved_reconciliation.refund_attempt_id,
    ) == ("discrepancy", "resolved", "已核对渠道差异并完成后续处理", shop.actor, 2, None)
    audit = await shop.session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "reconciliation:resolve",
            AuditEvent.target_id == refund_reconciliation.id,
        )
    )
    assert audit is not None and (audit.actor_type, audit.target_revision, audit.result) == ("admin", 2, "succeeded")
    with pytest.raises(AppException):
        await shop.admin_lifecycle.resolve_reconciliation(
            refund_reconciliation.id,
            ReconciliationResolve(revision=1, note="过期版本不得覆盖"),
        )
    withdrawal_reconciliation = await shop.admin_lifecycle.reconcile(
        ReconciliationRecordCreate(
            channel="wechat",
            record_type="withdrawal",
            channel_transaction_id="UNMATCHED-WITHDRAWAL",
            source_reference="缺失提现账单",
            source_hash="a" * 64,
            amount=Decimal("1.00"),
            currency="CNY",
            occurred_at=occurred_at,
        )
    )
    assert withdrawal_reconciliation.status == "discrepancy"


@pytest.mark.integration
@pytest.mark.parametrize("physical", [False, True])
async def test_unfinished_refund_blocks_fulfillment_after_acceptance(shop, physical):
    order, _, _ = await prepare_paid_order(shop, physical=physical)
    accepted = await shop.admin_lifecycle.accept_order(
        order.id, OrderAcceptance(revision=(await shop.orders.admin_read(order.id)).revision)
    )
    refund = await shop.lifecycle.create_refund(
        shop.users[0], order.id, RefundRequestCreate(request_id=new_uuid7(), reason="履约前售后")
    )
    assert accepted.acceptance_status == "accepted" and refund.status == "requested"

    with pytest.raises(AppException) as rejected:
        if physical:
            await shop.admin_lifecycle.ship(
                order.id, ShipmentCreate(carrier="测试物流", tracking_number="REFUND-BLOCKED", revision=1)
            )
        else:
            await shop.admin_lifecycle.deliver_virtual(
                order.id, VirtualDeliveryCreate(delivery_reference="REFUND-BLOCKED", revision=1)
            )
    assert rejected.value.code == "ORDER_STATE_CONFLICT"
