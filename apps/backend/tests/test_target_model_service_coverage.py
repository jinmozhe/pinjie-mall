"""目标模型新增领域的服务级回归测试。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid7

import pytest

from app.api import (
    catalog_router,
    commerce_router,
    commissioning_router,
    distribution_router,
    lifecycle_router,
    membership_router,
    transaction_router,
)
from app.core.exceptions import AppException
from app.db.models.catalog import CategorySpecAttribute, ProductAttributeValue, ProductSpecAttribute, ProductSpecValue
from app.domains.commissioning.schemas import (
    CommissionAmountRuleCreate,
    CommissionControlUpdate,
    CommissionDistributionRuleCreate,
    CommissionPolicyCreate,
    CommissionPolicyPublish,
    CommissionPolicyUpdate,
)
from app.domains.commissioning.service import CommissionPolicyService
from app.domains.durable_tasks.repository import DurableTaskRepository
from app.domains.durable_tasks.service import DurableTaskService, LeasedTask
from app.domains.lifecycle.repository import LifecycleRepository
from app.domains.lifecycle.schemas import VerifiedPaymentConfirmation, VerifiedRefundConfirmation
from app.domains.membership.repository import MembershipRepository
from app.domains.membership.schemas import (
    CommerceQuoteRequest,
    MemberLevelConditionCreate,
    MemberLevelCreate,
    MemberLevelUpdate,
    MemberPriceRuleCreate,
    MemberPriceRuleUpdate,
    OrderShippingSettingUpdate,
    PointsManualAdjustment,
    QuoteItemInput,
)
from app.domains.membership.service import MembershipService
from app.domains.points.repository import PointsRepository
from app.domains.points.service import PointsService
from app.domains.products.catalog_repository import CatalogRepository
from app.domains.products.catalog_schemas import (
    AdoptionInput,
    AttributeInput,
    AttributeUpdate,
    AttributeValidation,
    BrandInput,
    BrandUpdate,
    DescriptionUpdate,
    NewSkuInput,
    SkuFields,
    SpecificationSet,
    StandardValueInput,
    StandardValueUpdate,
    TemplateItem,
    TemplateUpdate,
)
from app.domains.products.catalog_service import CatalogService, specification_key
from app.domains.products.repository import ProductRepository
from app.domains.products.schemas import CategoryInput, CategoryUpdate, ProductUpdate, SkuStatusBatch, SkuUpdate
from app.domains.products.service import ProductService
from app.domains.products.specification_service import SpecificationService
from app.domains.purchases.service import PurchaseLimitService
from app.domains.wallets.service import WalletLedgerService
from app.services.durable_task_runner import DurableTaskRunner
from app.services.payment_lifecycle import LifecycleService


class MemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        now = datetime.now(UTC)
        if hasattr(value, "created_at") and getattr(value, "created_at", None) is None:
            value.created_at = now
        if hasattr(value, "updated_at") and getattr(value, "updated_at", None) is None:
            value.updated_at = now
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def delete(self, value: object) -> None:
        self.added.append(("deleted", value))


class CatalogStore:
    def __init__(self) -> None:
        self.brands: dict[UUID, object] = {}
        self.attributes: dict[UUID, object] = {}
        self.values_by_attribute: dict[UUID, list[object]] = {}
        self.categories_rows: list[object] = []
        self.templates: dict[UUID, list[CategorySpecAttribute]] = {}
        self.saved: list[object] = []
        self.adoption_rows: list[object] = []
        self.candidate_rows: list[object] = []
        self.description_rows: list[object] = []

    async def lock_catalog(self) -> None:
        return None

    async def brand_page(self, page: int, page_size: int) -> tuple[list[object], int]:
        rows = list(self.brands.values())
        return rows, len(rows)

    async def brand(self, brand_id: UUID) -> object | None:
        return self.brands.get(brand_id)

    async def attribute_page(self, page: int, page_size: int) -> tuple[list[object], int]:
        rows = list(self.attributes.values())
        return rows, len(rows)

    async def attribute(self, attribute_id: UUID) -> object | None:
        return self.attributes.get(attribute_id)

    async def attribute_by_code(self, code: str) -> object | None:
        return next((row for row in self.attributes.values() if row.code == code), None)

    async def standard_values(self, attribute_id: UUID) -> list[object]:
        return self.values_by_attribute.setdefault(attribute_id, [])

    async def standard_value(self, value_id: UUID) -> object | None:
        return next(
            (row for rows in self.values_by_attribute.values() for row in rows if row.id == value_id),
            None,
        )

    async def categories(self) -> list[object]:
        return self.categories_rows

    async def template(self, category_id: UUID) -> list[CategorySpecAttribute]:
        return self.templates.get(category_id, [])

    async def replace_template(self, category_id: UUID, rows: list[CategorySpecAttribute]) -> None:
        self.templates[category_id] = rows

    async def save_entity(self, row: object) -> None:
        self.saved.append(row)
        if hasattr(row, "attribute_id") and hasattr(row, "code") and type(row).__name__ == "SpecAttributeValue":
            self.values_by_attribute.setdefault(row.attribute_id, []).append(row)
        elif type(row).__name__ == "Brand":
            self.brands[row.id] = row
        elif type(row).__name__ == "SpecAttribute":
            self.attributes[row.id] = row
        elif isinstance(row, ProductSpecAttribute):
            self.adoption_rows.append(row)
        elif isinstance(row, ProductSpecValue):
            self.candidate_rows.append(row)
        elif isinstance(row, ProductAttributeValue):
            self.description_rows.append(row)

    async def save(self, row: object) -> None:
        self.saved.append(row)

    async def candidates(self, product_id: UUID) -> list[object]:
        return [row for row in self.candidate_rows if row.product_id == product_id]

    async def descriptions(self, product_id: UUID) -> list[object]:
        return [row for row in self.description_rows if row.product_id == product_id]

    async def adoptions(self, product_id: UUID) -> list[object]:
        return [row for row in self.adoption_rows if row.product_id == product_id]


@pytest.mark.asyncio
async def test_catalog_dictionary_versions_templates_and_description_values() -> None:
    store = CatalogStore()
    service = CatalogService(store)  # type: ignore[arg-type]
    brand = await service.save_brand(BrandInput(name="拼界", description="品牌"))
    assert brand.revision == 1
    updated = await service.save_brand(
        BrandUpdate(name="拼界商城", description="更新", revision=brand.revision), brand.id
    )
    assert updated.revision == 2 and (await service.brands(1, 20)).total == 1
    with pytest.raises(AppException) as stale_brand:
        await service.save_brand(BrandUpdate(name="旧", revision=1), brand.id)
    assert stale_brand.value.status_code == 409

    color = await service.save_attribute(
        AttributeInput(
            code="color",
            name="颜色",
            value_type="select",
            validation=AttributeValidation(),
        )
    )
    attribute = store.attributes[color.id]
    first = await service.save_value(
        color.id,
        StandardValueInput(attribute_revision=attribute.revision, code="red", name="红色"),
    )
    changed = await service.save_value(
        color.id,
        StandardValueUpdate(
            attribute_revision=attribute.revision,
            code="red",
            name="正红",
            revision=first.revision,
        ),
        first.id,
    )
    assert changed.name == "正红" and changed.revision == 2
    with pytest.raises(AppException) as duplicate_value:
        await service.save_value(
            color.id,
            StandardValueInput(attribute_revision=attribute.revision, code="red", name="重复"),
        )
    assert duplicate_value.value.status_code == 409

    category_id = uuid7()
    category = SimpleNamespace(id=category_id, revision=1, is_active=True, parent_id=None)
    store.categories_rows.append(category)
    template = await service.save_template(
        category_id,
        TemplateUpdate(
            revision=1,
            attributes=[TemplateItem(attribute_id=color.id, is_variant=True, is_required=True)],
        ),
    )
    assert template.revision == 2 and template.attributes[0].attribute_id == color.id

    adoption = await service.make_adoption(
        uuid7(),
        category_id,
        category.revision,
        1,
        AdoptionInput(
            key="color",
            attribute_id=color.id,
            source_attribute_revision=attribute.revision,
            is_variant=True,
            is_required=True,
            candidates=[{"key": "red", "value_id": first.id}],
        ),
        store.templates[category_id][0],
    )
    assert adoption.name_snapshot == "颜色" and adoption.source_category_id == category_id

    text_adoption = ProductSpecAttribute(
        id=uuid7(),
        product_id=uuid7(),
        attribute_id=None,
        adoption_version=1,
        name_snapshot="备注",
        value_type_snapshot="text",
        unit_snapshot=None,
        validation_snapshot={"schema_version": 1, "max_length": 4},
        source_category_id=None,
        source_category_revision=None,
        source_attribute_revision=None,
        is_required=True,
        allow_custom_value=True,
        is_variant=False,
        is_current=True,
    )
    assert await service.description_value(text_adoption, "好的") == ("好的", {})
    with pytest.raises(AppException):
        await service.description_value(text_adoption, "超过四个字符")
    number_adoption = ProductSpecAttribute(
        id=uuid7(),
        product_id=uuid7(),
        attribute_id=None,
        adoption_version=1,
        name_snapshot="尺寸",
        value_type_snapshot="number",
        unit_snapshot="cm",
        validation_snapshot={"schema_version": 1, "decimal_places": 1, "min": "1", "max": "10"},
        source_category_id=None,
        source_category_revision=None,
        source_attribute_revision=None,
        is_required=False,
        allow_custom_value=True,
        is_variant=False,
        is_current=True,
    )
    assert await service.description_value(number_adoption, "2.5") == ("2.5", {})
    with pytest.raises(AppException):
        await service.description_value(number_adoption, "2.55")


@pytest.mark.asyncio
async def test_catalog_reads_adoption_snapshots_and_rejects_invalid_dictionary_mutations() -> None:
    store = CatalogStore()
    service = CatalogService(store)  # type: ignore[arg-type]
    color = await service.save_attribute(
        AttributeInput(code="color", name="颜色", value_type="select", validation=AttributeValidation())
    )
    color_row = store.attributes[color.id]
    red = await service.save_value(
        color.id, StandardValueInput(attribute_revision=color_row.revision, code="red", name="红色")
    )
    assert (await service.attributes(1, 20)).total == 1 and (await service.values(color.id))[0].id == red.id
    changed = await service.save_attribute(
        AttributeUpdate(
            code="color",
            name="商品颜色",
            value_type="select",
            validation=AttributeValidation(),
            revision=color_row.revision,
        ),
        color.id,
    )
    assert changed.name == "商品颜色" and (await service.read_attribute(color.id)).id == color.id
    with pytest.raises(AppException):
        await service.read_brand(uuid7())
    with pytest.raises(AppException):
        await service.require_attribute(uuid7())
    text = await service.save_attribute(
        AttributeInput(code="note", name="备注", value_type="text", validation=AttributeValidation(max_length=20))
    )
    with pytest.raises(AppException):
        await service.save_value(text.id, StandardValueInput(attribute_revision=1, code="invalid", name="无效"))
    category_id, product_id = uuid7(), uuid7()
    store.categories_rows.append(SimpleNamespace(id=category_id, revision=1, is_active=True, parent_id=None))
    adoption = ProductSpecAttribute(
        id=uuid7(),
        product_id=product_id,
        attribute_id=color.id,
        adoption_version=1,
        name_snapshot="商品颜色",
        value_type_snapshot="select",
        unit_snapshot=None,
        validation_snapshot={"schema_version": 1},
        source_category_id=category_id,
        source_category_revision=1,
        source_attribute_revision=changed.revision,
        is_required=False,
        is_variant=False,
        is_current=True,
        allow_custom_value=False,
    )
    candidate = ProductSpecValue(
        id=uuid7(),
        adoption_id=adoption.id,
        product_id=product_id,
        attribute_id=color.id,
        value_id=red.id,
        display_value="红色",
        normalized_value="红色",
        is_current=True,
    )
    description = ProductAttributeValue(
        adoption_id=adoption.id,
        product_id=product_id,
        attribute_id=color.id,
        value=str(red.id),
        display_snapshot={str(red.id): "红色"},
        schema_version=1,
    )
    await store.save_entity(adoption)
    await store.save_entity(candidate)
    await store.save_entity(description)
    reads = await service.adoption_reads(product_id, current_only=True)
    assert reads[0].candidates[0].id == candidate.id and reads[0].display_snapshot[str(red.id)] == "红色"
    assert await service.description_value(adoption, str(red.id)) == (str(red.id), {str(red.id): "红色"})
    with pytest.raises(AppException):
        await service.description_value(adoption, "not-a-uuid")
    with pytest.raises(AppException):
        await service.save_template(category_id, TemplateUpdate(revision=99, attributes=[]))
    with pytest.raises(AppException):
        await service.make_adoption(
            product_id,
            category_id,
            1,
            2,
            AdoptionInput(
                key="bad",
                attribute_id=color.id,
                source_attribute_revision=changed.revision,
                is_variant=True,
                candidates=[{"key": "red", "value_id": red.id}],
            ),
            CategorySpecAttribute(category_id=category_id, attribute_id=color.id, is_variant=False, is_required=False),
        )


@pytest.mark.asyncio
async def test_catalog_service_guards_dictionary_reads_templates_and_description_values() -> None:
    store = CatalogStore()
    service = CatalogService(store)  # type: ignore[arg-type]
    brand = await service.save_brand(BrandInput(name="可读取品牌"))
    assert (await service.read_brand(brand.id)).name == "可读取品牌"
    with pytest.raises(AppException):
        await service.save_brand(BrandUpdate(name="缺失品牌", revision=1), uuid7())
    color = await service.save_attribute(
        AttributeInput(code="active-color", name="颜色", value_type="select", validation=AttributeValidation())
    )
    with pytest.raises(AppException):
        await service.save_attribute(
            AttributeInput(code="active-color", name="重复颜色", value_type="select", validation=AttributeValidation())
        )
    with pytest.raises(AppException):
        await service.read_template(uuid7())
    with pytest.raises(AppException):
        await service.save_template(uuid7(), TemplateUpdate(revision=1, attributes=[]))
    category_id = uuid7()
    store.categories_rows.append(SimpleNamespace(id=category_id, revision=1, is_active=True, parent_id=None))
    assert (await service.read_template(category_id)).attributes == []
    store.attributes[color.id].is_active = False
    with pytest.raises(AppException):
        await service.make_adoption(
            uuid7(),
            category_id,
            1,
            1,
            AdoptionInput(key="color", attribute_id=color.id, source_attribute_revision=1),
            None,
        )
    text = ProductSpecAttribute(
        id=uuid7(),
        product_id=uuid7(),
        attribute_id=None,
        adoption_version=1,
        name_snapshot="必填文本",
        value_type_snapshot="text",
        unit_snapshot=None,
        validation_snapshot={"schema_version": 1, "max_length": 4},
        source_category_id=None,
        source_category_revision=None,
        source_attribute_revision=None,
        is_required=True,
        is_variant=False,
        is_current=True,
        allow_custom_value=True,
    )
    with pytest.raises(AppException):
        await service.description_value(text, None)
    number = ProductSpecAttribute(
        id=uuid7(),
        product_id=uuid7(),
        attribute_id=None,
        adoption_version=1,
        name_snapshot="数值",
        value_type_snapshot="number",
        unit_snapshot=None,
        validation_snapshot={"schema_version": 1, "decimal_places": 1, "min": "1", "max": "2"},
        source_category_id=None,
        source_category_revision=None,
        source_attribute_revision=None,
        is_required=False,
        is_variant=False,
        is_current=True,
        allow_custom_value=True,
    )
    with pytest.raises(AppException):
        await service.description_value(number, [uuid7()])
    with pytest.raises(AppException):
        await service.description_value(number, "NaN")


def test_specification_key_keeps_identity_and_rejects_duplicate_dimension() -> None:
    first, second, candidate = uuid7(), uuid7(), uuid7()
    assert specification_key([]) == "default"
    result = specification_key([(second, None, candidate), (first, candidate, uuid7())])
    assert f"{first}=std:{candidate}" in result and f"{second}=custom:{candidate}" in result
    with pytest.raises(AppException):
        specification_key([(first, None, candidate), (first, None, uuid7())])
    with pytest.raises(AppException):
        specification_key([(uuid7(), None, uuid7()) for _ in range(20)])


class DurableStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], object] = {}
        self.now = datetime.now(UTC)
        self.completed = True
        self.retry_status: str | None = "pending"

    async def by_key(self, task_type: str, business_key: str, *, lock: bool = False) -> object | None:
        return self.rows.get((task_type, business_key))

    async def flush(self) -> None:
        return None

    async def database_now(self) -> datetime:
        return self.now

    async def lease_candidates(self, now: datetime, limit: int) -> list[object]:
        return list(self.rows.values())[:limit]

    async def complete_lease(self, task_id: UUID, lease_token: UUID) -> bool:
        return self.completed

    async def retry_lease(
        self, task_id: UUID, lease_token: UUID, error_code: str, error_summary: str, retry_at: datetime
    ) -> str | None:
        return self.retry_status

    async def count_lease_candidates(self, now: datetime) -> int:
        return len(self.rows)


@pytest.mark.asyncio
async def test_durable_task_intent_lease_conflict_and_retry_paths() -> None:
    session = MemorySession()
    store = DurableStore()
    service = DurableTaskService(session)  # type: ignore[arg-type]
    service._repository = store  # type: ignore[assignment]
    order_id = uuid7()
    payload = {"schema_version": 1, "order_id": str(order_id)}
    row = await service.enqueue_in_open_transaction(task_type="expire_order", business_key="order:1", payload=payload)
    store.rows[(row.task_type, row.business_key)] = row
    assert (
        await service.enqueue_in_open_transaction(task_type="expire_order", business_key="order:1", payload=payload)
        is row
    )
    with pytest.raises(AppException):
        await service.enqueue_in_open_transaction(
            task_type="expire_order", business_key="order:1", payload={"schema_version": 1, "order_id": str(uuid7())}
        )
    leased = await service.lease_in_open_transaction(limit=1, lease_seconds=10)
    assert leased[0].id == row.id and row.status == "running" and row.attempt_count == 1
    await service.complete_in_open_transaction(task_id=row.id, lease_token=leased[0].lease_token)
    assert (
        await service.retry_in_open_transaction(
            task_id=row.id,
            lease_token=leased[0].lease_token,
            error_code="UPSTREAM_TIMEOUT",
            error_summary="timeout",
            retry_delay_seconds=3,
        )
        == "pending"
    )
    store.completed = False
    with pytest.raises(AppException):
        await service.complete_in_open_transaction(task_id=row.id, lease_token=leased[0].lease_token)
    with pytest.raises(AppException):
        await service.lease_in_open_transaction(limit=0)
    with pytest.raises(AppException):
        await service.retry_in_open_transaction(
            task_id=row.id,
            lease_token=leased[0].lease_token,
            error_code="INVALID_DELAY",
            error_summary="invalid",
            retry_delay_seconds=0,
        )
    store.retry_status = None
    with pytest.raises(AppException):
        await service.retry_in_open_transaction(
            task_id=row.id,
            lease_token=leased[0].lease_token,
            error_code="LEASE_LOST",
            error_summary="lost",
            retry_delay_seconds=1,
        )
    row.status, row.failure_count = "running", row.max_failures - 1
    assert await service.lease_in_open_transaction(limit=1, lease_seconds=10) == []
    assert row.status == "attention" and row.lease_token is None
    with pytest.raises(AppException):
        await service.enqueue_in_open_transaction(task_type="unknown", business_key="x", payload={"schema_version": 1})
    with pytest.raises(AppException):
        await service.enqueue_in_open_transaction(task_type="", business_key="x", payload={"schema_version": 1})
    with pytest.raises(AppException):
        await service.enqueue_in_open_transaction(task_type="expire_order", business_key="x", payload={})
    with pytest.raises(AppException):
        await service.enqueue_in_open_transaction(
            task_type="expire_order",
            business_key="x",
            payload={"schema_version": 1, "order_id": str(order_id)},
            max_failures=0,
        )
    assert await service.due_count() == 1


class Audit:
    async def execute(self, **kwargs: object) -> object:
        return await kwargs["operation"]()  # type: ignore[index, no-any-return]


class CommissionStore:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.control = SimpleNamespace(
            id=uuid7(),
            setting_value={"schema_version": 1, "commissions_enabled": True},
            revision=1,
            updated_at=now,
            updated_by_id=None,
        )
        self.policies: dict[UUID, object] = {}
        self.amounts: dict[UUID, object] = {}
        self.distributions: dict[UUID, object] = {}
        self.deleted: set[UUID] = set()

    async def policies_page(self, page: int, page_size: int) -> tuple[list[object], int]:
        values = list(self.policies.values())
        return values, len(values)

    async def policy(self, policy_id: UUID, *, lock: bool = False) -> object | None:
        return self.policies.get(policy_id)

    async def active_policy(self, *, lock: bool = False) -> object | None:
        return next((row for row in self.policies.values() if row.status == "active"), None)

    async def next_content_version(self) -> int:
        return len(self.policies) + 1

    async def amount_rules(self, policy_id: UUID) -> list[object]:
        return [row for row in self.amounts.values() if row.policy_id == policy_id and row.id not in self.deleted]

    async def amount_rule(self, rule_id: UUID, *, lock: bool = False) -> object | None:
        return self.amounts.get(rule_id)

    async def distribution_rules(self, policy_id: UUID) -> list[object]:
        return [row for row in self.distributions.values() if row.policy_id == policy_id and row.id not in self.deleted]

    async def distribution_rule(self, rule_id: UUID, *, lock: bool = False) -> object | None:
        return self.distributions.get(rule_id)

    async def commission_control(self, *, lock: bool = False) -> object:
        return self.control

    async def level_exists(self, level_id: UUID) -> bool:
        return True

    async def product_exists(self, product_id: UUID) -> bool:
        return True

    async def sku_exists(self, sku_id: UUID) -> bool:
        return True

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_commission_policy_lifecycle_and_control_are_versioned() -> None:
    session, store, actor = MemorySession(), CommissionStore(), uuid7()
    service = CommissionPolicyService(session=session, actor_id=actor, audit=Audit())  # type: ignore[arg-type]
    service._repository = store  # type: ignore[assignment]
    created = await service.create_policy(CommissionPolicyCreate(name="默认三级政策"))
    policy = session.added[-1]
    store.policies[created.id] = policy
    changed = await service.update_policy(
        created.id, CommissionPolicyUpdate(name="调整后政策", revision=created.revision, max_depth=3)
    )
    assert changed.revision == 2
    amount = await service.add_amount_rule(
        created.id,
        CommissionAmountRuleCreate(product_id=uuid7(), rule_mode="fixed_amount", amount_per_unit=Decimal("1.20")),
    )
    store.amounts[amount.id] = session.added[-1]
    changed_amount = await service.update_amount_rule(
        created.id,
        amount.id,
        CommissionAmountRuleCreate(sku_id=uuid7(), rule_mode="percentage", percentage_rate=Decimal("0.120000")),
    )
    assert changed_amount.sku_id is not None and len(await service.amount_rules(created.id)) == 1
    distribution = await service.add_distribution_rule(
        created.id,
        CommissionDistributionRuleCreate(
            buyer_level_id=uuid7(),
            beneficiary_level_id=uuid7(),
            ancestor_depth=1,
            allocation_mode="percentage",
            rate=Decimal("0.500000"),
        ),
    )
    store.distributions[distribution.id] = session.added[-1]
    changed_distribution = await service.update_distribution_rule(
        created.id,
        distribution.id,
        CommissionDistributionRuleCreate(
            buyer_level_id=distribution.buyer_level_id,
            beneficiary_level_id=distribution.beneficiary_level_id,
            ancestor_depth=2,
            allocation_mode="fixed_amount",
            amount_per_unit=Decimal("2.00"),
        ),
    )
    assert changed_distribution.ancestor_depth == 2 and len(await service.distribution_rules(created.id)) == 1
    await service.delete_amount_rule(created.id, amount.id)
    await service.delete_distribution_rule(created.id, distribution.id)
    store.deleted.update({amount.id, distribution.id})
    assert len([item for item in session.added if isinstance(item, tuple) and item[0] == "deleted"]) == 2
    context = await service.active_decision_context_in_open_transaction()
    assert context.policy is None and context.control.commissions_enabled
    published = await service.publish_policy(created.id, CommissionPolicyPublish(revision=changed.revision))
    assert published.status == "active"
    context = await service.active_decision_context_in_open_transaction()
    assert context.policy is not None and not context.amount_rules and not context.distribution_rules
    successor = await service.create_policy(CommissionPolicyCreate(name="替换政策"))
    store.policies[successor.id] = session.added[-1]
    successor_published = await service.publish_policy(
        successor.id, CommissionPolicyPublish(revision=successor.revision)
    )
    assert successor_published.status == "active" and policy.status == "retired"
    assert (await service.policies(1, 20)).total == 2 and (await service.policy(successor.id)).id == successor.id
    control = await service.update_commission_control(CommissionControlUpdate(revision=1, commissions_enabled=False))
    assert not control.commissions_enabled and control.revision == 2
    with pytest.raises(AppException):
        await service.update_commission_control(CommissionControlUpdate(revision=1, commissions_enabled=True))
    with pytest.raises(AppException):
        await service.update_policy(created.id, CommissionPolicyUpdate(name="冻结", revision=published.revision))


@pytest.mark.asyncio
async def test_membership_price_helpers_preserve_priority_and_sellability() -> None:
    category_id, sku_id, product_id = uuid7(), uuid7(), uuid7()
    category = SimpleNamespace(id=category_id, parent_id=None, is_active=True)
    product = SimpleNamespace(id=product_id, category_id=category_id, product_type="physical", status="on_sale")
    sku = SimpleNamespace(
        id=sku_id,
        price=Decimal("10.00"),
        wholesale_prices=[{"min_quantity": 2, "unit_price": "8.00"}],
        is_active=True,
        archived_at=None,
    )
    level = SimpleNamespace(id=uuid7(), revision=1, is_active=True, discount_factor=Decimal("0.900000"))
    fixed = SimpleNamespace(
        id=uuid7(),
        revision=1,
        sku_id=sku_id,
        product_id=None,
        category_id=None,
        price_mode="fixed",
        fixed_price=Decimal("6.66"),
        discount_factor=None,
        scope_type="sku",
    )
    excluded = SimpleNamespace(
        id=uuid7(),
        revision=1,
        sku_id=None,
        product_id=None,
        category_id=category_id,
        price_mode="exclude",
        fixed_price=None,
        discount_factor=None,
        scope_type="category",
    )
    assert MembershipService._wholesale_price(sku, 2) == (
        Decimal("8.00"),
        {"decision": "wholesale_tier", "matched_tier": {"min_quantity": 2, "unit_price": "8.00"}},
    )
    fixed_price = MembershipService._member_price(
        sku, product, {category_id: category}, Decimal("8.00"), level, {sku_id: fixed}, {}, {}
    )
    assert fixed_price[:2] == (Decimal("6.66"), "sku_fixed")
    assert fixed_price[2]["rule_id"] == str(fixed.id) and fixed_price[2]["rule_revision"] == 1
    excluded_price = MembershipService._member_price(
        sku, product, {category_id: category}, Decimal("8.00"), level, {}, {}, {category_id: excluded}
    )
    assert excluded_price[:2] == (Decimal("8.00"), "member_excluded")
    assert excluded_price[2]["rule_id"] == str(excluded.id)
    assert MembershipService._member_price(
        sku, product, {category_id: category}, Decimal("8.00"), level, {}, {}, {}
    ) == (
        Decimal("7.20"),
        "level_discount",
        {"decision": "level_discount", "level_id": str(level.id), "level_revision": 1, "discount_factor": "0.900000"},
    )
    MembershipService._assert_sellable(sku, product, {category_id: category})
    sku.is_active = False
    with pytest.raises(AppException):
        MembershipService._assert_sellable(sku, product, {category_id: category})
    assert len(MembershipService._fingerprint(uuid7(), [], {"state": "none"}, {"mode": "virtual"})) == 64


@pytest.mark.asyncio
async def test_durable_runner_classifies_success_retry_attention_and_lease_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = DurableTaskRunner(SimpleNamespace())  # type: ignore[arg-type]
    first = LeasedTask(uuid7(), "expire_order", "one", {"schema_version": 1, "order_id": str(uuid7())}, uuid7(), 1)
    second = LeasedTask(
        uuid7(), "payment_submit", "two", {"schema_version": 1, "payment_attempt_id": str(uuid7())}, uuid7(), 1
    )

    async def lease(limit: int, lease_seconds: int) -> list[LeasedTask]:
        return [first, second]

    calls = 0

    async def execute(task: LeasedTask) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppException(status_code=503, code="CHANNEL_UNAVAILABLE", message="渠道不可用")

    async def complete(task: LeasedTask) -> bool:
        return True

    async def retry(task: LeasedTask, code: str, message: str, delay: int) -> str:
        return "attention"

    monkeypatch.setattr(runner, "_lease", lease)
    monkeypatch.setattr(runner, "_execute", execute)
    monkeypatch.setattr(runner, "_complete", complete)
    monkeypatch.setattr(runner, "_retry", retry)
    result = await runner.run_once(limit=2, lease_seconds=10, retry_delay_seconds=3)
    assert (result.leased, result.succeeded, result.attention, result.retried) == (2, 1, 1, 0)
    with pytest.raises(ValueError):
        await runner.run_once(limit=1, lease_seconds=1, retry_delay_seconds=0)
    with pytest.raises(AppException):
        runner._payload_uuid(
            first.__class__(first.id, "expire_order", "x", {"schema_version": 1}, first.lease_token, 1), "order_id"
        )


@pytest.mark.asyncio
async def test_durable_runner_executes_each_internal_handler_and_handles_lease_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, UUID]] = []

    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeTasks:
        complete_conflict = False
        retry_conflict = False

        def __init__(self, session: object) -> None:
            self.session = session

        async def due_count(self) -> int:
            return 4

        async def lease_in_open_transaction(self, *, limit: int, lease_seconds: int) -> list[LeasedTask]:
            return [
                LeasedTask(uuid7(), "expire_order", "one", {"schema_version": 1, "order_id": str(uuid7())}, uuid7(), 1)
            ]

        async def complete_in_open_transaction(self, *, task_id: UUID, lease_token: UUID) -> None:
            if self.complete_conflict:
                raise AppException(status_code=409, code="DURABLE_TASK_LEASE_CONFLICT", message="lost")

        async def retry_in_open_transaction(self, **kwargs: object) -> str:
            if self.retry_conflict:
                raise AppException(status_code=409, code="DURABLE_TASK_LEASE_CONFLICT", message="lost")
            return "pending"

    class FakeOrders:
        def __init__(self, session: object) -> None:
            self.session = session

        async def expire_scheduled(self, order_id: UUID) -> None:
            calls.append(("expire", order_id))

    class FakeLifecycle:
        def __init__(self, session: object) -> None:
            self.session = session

        async def confirm_order_scheduled(self, payment_attempt_id: UUID) -> None:
            calls.append(("confirm_order", payment_attempt_id))

        async def auto_confirm_scheduled(self, fulfillment_id: UUID) -> None:
            calls.append(("confirm", fulfillment_id))

        async def complete_refund_scheduled(self, refund_attempt_id: UUID) -> None:
            calls.append(("refund_followup", refund_attempt_id))

    class FakeDistribution:
        def __init__(self, session: object) -> None:
            self.session = session

        async def settle_order_scheduled(self, order_id: UUID) -> None:
            calls.append(("commission", order_id))

    @asynccontextmanager
    async def transaction(session: object):
        yield

    monkeypatch.setattr("app.services.durable_task_runner.DurableTaskService", FakeTasks)
    monkeypatch.setattr("app.services.durable_task_runner.OrderService", FakeOrders)
    monkeypatch.setattr("app.services.durable_task_runner.LifecycleService", FakeLifecycle)
    monkeypatch.setattr("app.services.durable_task_runner.DistributionService", FakeDistribution)
    monkeypatch.setattr("app.services.durable_task_runner.transaction_scope", transaction)
    runner = DurableTaskRunner(lambda: Session())  # type: ignore[arg-type]
    assert await runner.due_count() == 4
    leased = await runner._lease(1, 30)
    assert leased[0].task_type == "expire_order"
    for task_type, payload_key, action in (
        ("expire_order", "order_id", "expire"),
        ("confirm_order", "payment_attempt_id", "confirm_order"),
        ("auto_confirm_fulfillment", "fulfillment_id", "confirm"),
        ("refund_followup", "refund_attempt_id", "refund_followup"),
        ("commission_settlement", "order_id", "commission"),
    ):
        task_id = uuid7()
        await runner._execute(
            LeasedTask(uuid7(), task_type, task_type, {"schema_version": 1, payload_key: str(task_id)}, uuid7(), 1)
        )
        assert calls[-1] == (action, task_id)
    with pytest.raises(AppException):
        await runner._execute(LeasedTask(uuid7(), "payment_submit", "payment", {"schema_version": 1}, uuid7(), 1))
    assert await runner._complete(leased[0])
    assert await runner._retry(leased[0], "TEMPORARY", "retry", 3) == "pending"
    FakeTasks.complete_conflict = True
    FakeTasks.retry_conflict = True
    assert not await runner._complete(leased[0])
    assert await runner._retry(leased[0], "TEMPORARY", "retry", 3) == "lease_lost"


class PointsStore:
    def __init__(self, account: object) -> None:
        self.account_row = account
        self.ledgers: dict[UUID, object] = {}
        self.keys: dict[str, object] = {}

    async def lock_adjustment(self, idempotency_key: str, user_id: UUID) -> None:
        return None

    async def account(self, user_id: UUID, *, lock: bool = False) -> object:
        return self.account_row

    async def account_by_id(self, account_id: UUID, *, lock: bool = False) -> object | None:
        return self.account_row if self.account_row.id == account_id else None

    async def ledger(self, ledger_id: UUID, *, lock: bool = False) -> object | None:
        return self.ledgers.get(ledger_id)

    async def ledger_by_key(self, key: str, *, lock: bool = False) -> object | None:
        return self.keys.get(key)

    async def reversal_total(self, ledger_id: UUID) -> int:
        return -2


@pytest.mark.asyncio
async def test_points_adjustment_accounts_for_debt_and_reversal_limits() -> None:
    account = SimpleNamespace(
        id=uuid7(), user_id=uuid7(), available_points=3, frozen_points=0, debt_points=4, revision=1
    )
    session, store = MemorySession(), PointsStore(account)
    service = PointsService(session=session, actor_id=uuid7(), audit=Audit())  # type: ignore[arg-type]
    service._repository = store  # type: ignore[assignment]
    grant = PointsManualAdjustment(user_id=account.user_id, points=5, operation="grant", idempotency_key="grant-1")
    assert await service._apply_adjustment(account, grant) == (1, -4)
    original = SimpleNamespace(id=uuid7(), account_id=account.id, entry_type="grant", available_delta=10)
    store.ledgers[original.id] = original
    reverse = PointsManualAdjustment(
        user_id=account.user_id,
        points=5,
        operation="reverse",
        idempotency_key="reverse-1",
        reverses_ledger_id=original.id,
    )
    assert await service._apply_adjustment(account, reverse) == (-3, 2)
    with pytest.raises(AppException):
        await service._apply_adjustment(
            account,
            reverse.model_copy(update={"points": 13, "idempotency_key": "reverse-too-large"}),
        )
    with pytest.raises(AppException):
        await service._apply_adjustment(
            account,
            reverse.model_copy(update={"reverses_ledger_id": uuid7(), "idempotency_key": "reverse-missing"}),
        )


class PurchaseStore:
    def __init__(self) -> None:
        self.accounts: dict[tuple[UUID, UUID], object] = {}
        self.rows: dict[UUID, list[object]] = {}

    async def records(self, order_id: UUID) -> list[object]:
        return self.rows.get(order_id, [])

    async def account(self, user_id: UUID, product_id: UUID) -> object | None:
        return self.accounts.get((user_id, product_id))

    async def save(self, row: object) -> None:
        if hasattr(row, "purchased_quantity"):
            self.accounts[(row.user_id, row.product_id)] = row
        elif hasattr(row, "order_id"):
            self.rows.setdefault(row.order_id, []).append(row)


@pytest.mark.asyncio
async def test_purchase_limit_reserve_confirm_release_and_refund_are_idempotent() -> None:
    store = PurchaseStore()
    service = PurchaseLimitService(store)  # type: ignore[arg-type]
    user, product, order = uuid7(), uuid7(), uuid7()
    await service.reserve(order, user, [(product, 2, 3)])
    account = store.accounts[(user, product)]
    assert account.reserved_quantity == 2
    await service.reserve(order, user, [(product, 2, 3)])
    await service.transition(order, "confirmed", datetime.now(UTC))
    assert (account.purchased_quantity, account.reserved_quantity) == (2, 0)
    await service.transition(order, "confirmed", datetime.now(UTC))
    await service.transition(order, "refunded", datetime.now(UTC))
    assert store.rows[order][0].status == "refunded" and account.purchased_quantity == 2
    second_order = uuid7()
    await service.reserve(second_order, user, [(product, 1, 3)])
    await service.transition(second_order, "released", datetime.now(UTC))
    assert account.reserved_quantity == 0
    with pytest.raises(AppException):
        await service.reserve(uuid7(), user, [(product, 2, 3)])


class RouterSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __getattr__(self, name: str):
        async def method(*args: object, **kwargs: object) -> object:
            self.calls.append((name, args + tuple(kwargs.values())))
            return {"operation": name}

        return method


@pytest.mark.asyncio
async def test_target_model_routers_delegate_every_operation_to_scoped_services() -> None:
    service, points = RouterSpy(), RouterSpy()
    brand_id, attribute_id, value_id, category_id, product_id, adoption_id = (uuid7() for _ in range(6))
    payload = object()
    await catalog_router.brands(service, 1, 20)
    await catalog_router.brand(brand_id, service)
    await catalog_router.create_brand(payload, service)  # type: ignore[arg-type]
    await catalog_router.update_brand(brand_id, payload, service)  # type: ignore[arg-type]
    await catalog_router.attributes(service, 1, 20)
    await catalog_router.attribute(attribute_id, service)
    await catalog_router.create_attribute(payload, service)  # type: ignore[arg-type]
    await catalog_router.update_attribute(attribute_id, payload, service)  # type: ignore[arg-type]
    await catalog_router.values(attribute_id, service)
    await catalog_router.create_value(attribute_id, payload, service)  # type: ignore[arg-type]
    await catalog_router.update_value(attribute_id, value_id, payload, service)  # type: ignore[arg-type]
    await catalog_router.template(category_id, service)
    await catalog_router.update_template(category_id, payload, service)  # type: ignore[arg-type]
    await catalog_router.convert_specifications(product_id, payload, service)  # type: ignore[arg-type]
    await catalog_router.update_description(product_id, adoption_id, payload, service)  # type: ignore[arg-type]

    user_id, level_id, condition_id, rule_id, account_id = (uuid7() for _ in range(5))
    await membership_router.member_levels(service, 1, 20)
    await membership_router.create_member_level(payload, service)  # type: ignore[arg-type]
    await membership_router.update_member_level(level_id, payload, service)  # type: ignore[arg-type]
    await membership_router.member_level_conditions(service, 1, 20)
    await membership_router.create_member_level_condition(payload, service)  # type: ignore[arg-type]
    await membership_router.update_member_level_condition(condition_id, payload, service)  # type: ignore[arg-type]
    await membership_router.qualification_events(user_id, service, 1, 20)
    await membership_router.level_events(user_id, service, 1, 20)
    await membership_router.points_accounts(points, 1, 20)
    await membership_router.points_ledgers(account_id, points, 1, 20)
    await membership_router.adjust_points(payload, points)  # type: ignore[arg-type]
    await membership_router.member_price_rules(service, 1, 20)
    await membership_router.create_member_price_rule(payload, service)  # type: ignore[arg-type]
    await membership_router.update_member_price_rule(rule_id, payload, service)  # type: ignore[arg-type]
    await membership_router.get_order_shipping(service)
    await membership_router.update_order_shipping(payload, service)  # type: ignore[arg-type]
    await membership_router.quote(payload, service, SimpleNamespace(user=SimpleNamespace(id=user_id)))  # type: ignore[arg-type]

    policy_id, amount_id, distribution_id = uuid7(), uuid7(), uuid7()
    await commissioning_router.commission_control(service)
    await commissioning_router.update_commission_control(payload, service)  # type: ignore[arg-type]
    await commissioning_router.policies(service, 1, 20)
    await commissioning_router.policy(policy_id, service)
    await commissioning_router.create_policy(payload, service)  # type: ignore[arg-type]
    await commissioning_router.update_policy(policy_id, payload, service)  # type: ignore[arg-type]
    await commissioning_router.amount_rules(policy_id, service)
    await commissioning_router.add_amount_rule(policy_id, payload, service)  # type: ignore[arg-type]
    await commissioning_router.update_amount_rule(policy_id, amount_id, payload, service)  # type: ignore[arg-type]
    await commissioning_router.delete_amount_rule(policy_id, amount_id, service)
    await commissioning_router.distribution_rules(policy_id, service)
    await commissioning_router.add_distribution_rule(policy_id, payload, service)  # type: ignore[arg-type]
    await commissioning_router.update_distribution_rule(policy_id, distribution_id, payload, service)  # type: ignore[arg-type]
    await commissioning_router.delete_distribution_rule(policy_id, distribution_id, service)
    await commissioning_router.publish_policy(policy_id, payload, service)  # type: ignore[arg-type]
    assert len(service.calls) >= 40 and points.calls


@pytest.mark.asyncio
async def test_existing_commerce_transaction_distribution_and_lifecycle_routers_delegate() -> None:
    service, cart, orders = RouterSpy(), RouterSpy(), RouterSpy()
    user_id, first_id, second_id = uuid7(), uuid7(), uuid7()
    current = SimpleNamespace(user=SimpleNamespace(id=user_id))
    payload = object()
    await commerce_router.admin_categories(service)
    await commerce_router.create_category(payload, service)  # type: ignore[arg-type]
    await commerce_router.update_category(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.admin_products(service, 1, 20)
    await commerce_router.categories_status_batch(payload, service)  # type: ignore[arg-type]
    await commerce_router.products_status_batch(payload, service)  # type: ignore[arg-type]
    await commerce_router.shipping_status_batch(payload, service)  # type: ignore[arg-type]
    await commerce_router.admin_product(first_id, service)
    await commerce_router.create_product(payload, service)  # type: ignore[arg-type]
    await commerce_router.update_product(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.set_product_status(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.create_sku(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.update_sku(first_id, second_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.inventory_read(first_id, service)
    await commerce_router.skus_status_batch(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.inventory_adjust(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.inventory_history(first_id, service, 1, 20)
    await commerce_router.shipping_page(service, 1, 20)
    await commerce_router.shipping_read(first_id, service)
    await commerce_router.shipping_create(payload, service)  # type: ignore[arg-type]
    await commerce_router.shipping_update(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.shipping_quote(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.public_categories(service)
    await commerce_router.public_products(service, 1, 20)
    await commerce_router.public_product(first_id, service)
    await commerce_router.addresses_list(service)
    await commerce_router.address_create(payload, service)  # type: ignore[arg-type]
    await commerce_router.address_update(first_id, payload, service)  # type: ignore[arg-type]
    await commerce_router.address_delete(first_id, 1, service)
    await transaction_router.admin_order_read(first_id, orders)
    await transaction_router.cart_list(cart, current)
    await transaction_router.cart_add(payload, cart, current)  # type: ignore[arg-type]
    await transaction_router.cart_update(first_id, payload, cart, current)  # type: ignore[arg-type]
    await transaction_router.cart_delete(first_id, cart, current)
    await transaction_router.checkout_preview(payload, orders, current)  # type: ignore[arg-type]
    await transaction_router.order_create(payload, orders, current)  # type: ignore[arg-type]
    await transaction_router.order_read(first_id, orders, current)
    await transaction_router.order_cancel(first_id, orders, current)
    await distribution_router.activate_profile(service, current)
    await distribution_router.profile_read(service, current)
    await distribution_router.bind_referrer(payload, service, current)  # type: ignore[arg-type]
    await distribution_router.wallets_read(service, current)
    await distribution_router.commissions_read(service, current, 1, 20)
    await distribution_router.withdrawal_create(payload, service)  # type: ignore[arg-type]
    await distribution_router.withdrawals_read(service, current, 1, 20)
    await distribution_router.admin_approve_withdrawal(first_id, payload, service)  # type: ignore[arg-type]
    await distribution_router.admin_reject_withdrawal(first_id, payload, service)  # type: ignore[arg-type]
    await distribution_router.admin_complete_withdrawal_manually(first_id, payload, service)  # type: ignore[arg-type]
    await lifecycle_router.admin_fulfillment_read(first_id, service)
    await lifecycle_router.initiate_payment(first_id, payload, service, current)  # type: ignore[arg-type]
    await lifecycle_router.fulfillment_read(first_id, service, current)
    await lifecycle_router.confirm_receipt(first_id, SimpleNamespace(revision=1), service, current)  # type: ignore[arg-type]
    await lifecycle_router.refund_create(first_id, payload, service, current)  # type: ignore[arg-type]
    await lifecycle_router.refund_list(first_id, service, current)
    await lifecycle_router.review_create(first_id, payload, service, current)  # type: ignore[arg-type]
    await lifecycle_router.review_page(first_id, service, 1, 20)
    await lifecycle_router.admin_ship(first_id, payload, service)  # type: ignore[arg-type]
    await lifecycle_router.admin_deliver_virtual(first_id, payload, service)  # type: ignore[arg-type]
    await lifecycle_router.admin_approve_refund(first_id, payload, service)  # type: ignore[arg-type]
    await lifecycle_router.admin_reject_refund(first_id, payload, service)  # type: ignore[arg-type]
    await lifecycle_router.admin_reconcile(payload, service)  # type: ignore[arg-type]
    assert len(service.calls) >= 50 and cart.calls and orders.calls


@pytest.mark.asyncio
async def test_wallet_ledger_mutation_is_idempotent_and_preserves_nonnegative_balances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wallet = SimpleNamespace(
        id=uuid7(),
        available_amount=Decimal("10.00"),
        frozen_amount=Decimal("2.00"),
        debt_amount=Decimal("0.00"),
        revision=1,
    )
    existing: dict[str, object] = {}
    session = MemorySession()
    service = WalletLedgerService(session)  # type: ignore[arg-type]

    async def get_wallet(wallet_id: UUID, *, lock: bool) -> object:
        assert wallet_id == wallet.id and lock
        return wallet

    async def get_ledger(key: str, *, lock: bool) -> object | None:
        return existing.get(key)

    monkeypatch.setattr(service, "_wallet", get_wallet)
    monkeypatch.setattr(service, "_ledger_by_key", get_ledger)
    reference = uuid7()
    ledger = await service.apply_in_open_transaction(
        wallet_id=wallet.id,
        entry_type="withdrawal_freeze",
        amount=Decimal("-5.00"),
        frozen_delta=Decimal("5.00"),
        debt_delta=Decimal("0.00"),
        idempotency_key="wallet-1",
        reference_type="withdrawal",
        reference_id=reference,
    )
    assert (wallet.available_amount, wallet.frozen_amount, wallet.revision) == (Decimal("5.00"), Decimal("7.00"), 2)
    existing["wallet-1"] = ledger
    assert (
        await service.apply_in_open_transaction(
            wallet_id=wallet.id,
            entry_type="withdrawal_freeze",
            amount=Decimal("-5.00"),
            frozen_delta=Decimal("5.00"),
            debt_delta=Decimal("0.00"),
            idempotency_key="wallet-1",
            reference_type="withdrawal",
            reference_id=reference,
        )
        is ledger
    )
    with pytest.raises(AppException):
        await service.apply_in_open_transaction(
            wallet_id=wallet.id,
            entry_type="invalid",
            amount=Decimal("-6.00"),
            frozen_delta=Decimal("0.00"),
            debt_delta=Decimal("0.00"),
            idempotency_key="wallet-2",
            reference_type="withdrawal",
            reference_id=reference,
        )


class SpecificationStore:
    def __init__(self) -> None:
        self.product_id, self.adoption_id, self.candidate_id = uuid7(), uuid7(), uuid7()
        self.adoption = SimpleNamespace(
            id=self.adoption_id,
            attribute_id=uuid7(),
            is_current=True,
            is_variant=True,
            name_snapshot="颜色",
        )
        self.candidate = SimpleNamespace(
            id=self.candidate_id,
            adoption_id=self.adoption_id,
            attribute_id=self.adoption.attribute_id,
            value_id=uuid7(),
            display_value="红色",
            is_current=True,
        )
        self.sku = SimpleNamespace(
            id=uuid7(), product_id=self.product_id, archived_at=None, is_active=True, specification_key="default"
        )
        self.attribute_row = SimpleNamespace(is_active=True)
        self.standard_row = SimpleNamespace(is_active=True)
        self.code_conflict = False

    async def adoptions(self, product_id: UUID) -> list[object]:
        return [self.adoption]

    async def candidates(self, product_id: UUID) -> list[object]:
        return [self.candidate]

    async def attribute(self, attribute_id: UUID) -> object:
        return self.attribute_row

    async def standard_value(self, value_id: UUID) -> object:
        return self.standard_row

    async def code_exists(self, code: str) -> bool:
        return self.code_conflict

    async def skus(self, product_id: UUID) -> list[object]:
        return [self.sku]

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_specification_service_uses_adoption_identity_and_archives_atomically() -> None:
    store = SpecificationStore()
    service = SpecificationService(store)  # type: ignore[arg-type]
    key, display, selected = await service.combination(store.product_id, [store.candidate_id])
    assert "std:" in key and display == {"颜色": "红色"} and selected == [store.candidate]
    with pytest.raises(AppException):
        await service.combination(store.product_id, [uuid7()])
    sku = SimpleNamespace()
    SpecificationService.set_sku_fields(sku, SkuFields(code="new-sku", price=Decimal("1.20"), weight_grams=20))
    assert (sku.code, sku.price, sku.weight_grams, sku.is_active) == ("new-sku", Decimal("1.20"), 20, True)
    assert await service.sku_is_available(store.sku, [store.adoption], [])
    store.attribute_row.is_active = False
    assert not await service.sku_is_available(store.sku, [store.adoption], [])
    store.attribute_row.is_active = True
    retired = await service.retire_specifications(store.product_id)
    assert retired == [store.sku.id] and store.sku.archived_at is not None and not store.adoption.is_current
    store.sku.archived_at, store.adoption.is_current, store.candidate.is_current = None, True, True
    selection = SimpleNamespace(sku_id=store.sku.id, spec_value_id=store.candidate.id)
    assert await service.sku_is_available(store.sku, [store.adoption], [selection])
    store.candidate.is_current = False
    assert not await service.sku_is_available(store.sku, [store.adoption], [selection])
    store.candidate.is_current, store.standard_row.is_active = True, False
    assert not await service.sku_is_available(store.sku, [store.adoption], [selection])
    store.standard_row.is_active, store.code_conflict = True, True
    with pytest.raises(AppException):
        await service.insert_sku(
            store.product_id, SkuFields(code="DUPLICATE", price=Decimal("1.00")), [store.candidate_id], 1
        )
    store.code_conflict = False
    key, _, _ = await service.combination(store.product_id, [store.candidate_id])
    store.sku.specification_key = key
    with pytest.raises(AppException):
        await service.insert_sku(
            store.product_id, SkuFields(code="SAME-SPEC", price=Decimal("1.00")), [store.candidate_id], 1
        )
    with pytest.raises(AppException):
        await service.replace_description(
            SimpleNamespace(id=store.product_id), uuid7(), DescriptionUpdate(revision=1, value="不存在")
        )


class SpecificationBuildStore:
    def __init__(self, category_id: UUID) -> None:
        self.category = SimpleNamespace(id=category_id, revision=1)
        self.template_rows: list[object] = []
        self.adoption_rows: list[object] = []
        self.candidate_rows: list[object] = []
        self.saved: list[object] = []

    async def categories(self) -> list[object]:
        return [self.category]

    async def template(self, category_id: UUID) -> list[object]:
        assert category_id == self.category.id
        return self.template_rows

    async def adoptions(self, product_id: UUID) -> list[object]:
        return [row for row in self.adoption_rows if row.product_id == product_id]

    async def candidates(self, product_id: UUID) -> list[object]:
        return [row for row in self.candidate_rows if row.product_id == product_id]

    async def standard_value(self, value_id: UUID) -> object | None:
        return None

    async def code_exists(self, code: str) -> bool:
        return False

    async def skus(self, product_id: UUID) -> list[object]:
        return [row for row in self.saved if getattr(row, "product_id", None) == product_id and hasattr(row, "sku_no")]

    async def save(self, row: object) -> None:
        self.saved.append(row)

    async def save_entity(self, row: object) -> None:
        self.saved.append(row)
        if isinstance(row, ProductSpecAttribute) and row not in self.adoption_rows:
            self.adoption_rows.append(row)
        if isinstance(row, ProductSpecValue) and row not in self.candidate_rows:
            self.candidate_rows.append(row)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_specification_builder_creates_snapshot_sku_and_replaces_descriptions() -> None:
    category_id, product_id = uuid7(), uuid7()
    store = SpecificationBuildStore(category_id)
    service = SpecificationService(store)  # type: ignore[arg-type]
    product = SimpleNamespace(id=product_id, category_id=category_id)
    definitions = SpecificationSet(
        category_revision=1,
        attributes=[
            AdoptionInput(
                key="intro",
                name="简介",
                value_type="text",
                validation=AttributeValidation(max_length=20),
                value="首次说明",
            )
        ],
        skus=[NewSkuInput(code="SNAPSHOT-ONE", price=Decimal("9.90"), selections={})],
    )
    await service.build_specifications(product, definitions)  # type: ignore[arg-type]
    adoption = store.adoption_rows[0]
    sku = next(item for item in store.saved if getattr(item, "code", None) == "SNAPSHOT-ONE")
    assert adoption.is_current and sku.specifications == {} and sku.sku_no == 0
    await service.replace_description(
        product,
        adoption.id,
        DescriptionUpdate(revision=1, value="更新后说明"),  # type: ignore[arg-type]
    )
    current = [row for row in store.adoption_rows if row.is_current]
    assert not adoption.is_current and len(current) == 1 and current[0].adoption_version == 2


@pytest.mark.asyncio
async def test_specification_builder_maps_custom_variant_candidates_to_stable_sku_identity() -> None:
    category_id, product_id = uuid7(), uuid7()
    store = SpecificationBuildStore(category_id)
    service = SpecificationService(store)  # type: ignore[arg-type]
    await service.build_specifications(
        SimpleNamespace(id=product_id, category_id=category_id),
        SpecificationSet(
            category_revision=1,
            attributes=[
                AdoptionInput(
                    key="color",
                    name="颜色",
                    value_type="select",
                    validation=AttributeValidation(),
                    is_variant=True,
                    candidates=[{"key": "red", "display_value": "红色"}],
                )
            ],
            skus=[NewSkuInput(code="CUSTOM-RED", price=Decimal("12.00"), selections={"color": "red"})],
        ),
    )
    sku = next(row for row in store.saved if getattr(row, "code", None) == "CUSTOM-RED")
    selection = next(row for row in store.saved if getattr(row, "sku_id", None) == sku.id)
    assert (
        sku.sku_no == 1
        and "custom:" in sku.specification_key
        and selection.spec_value_id in {value.id for value in store.candidate_rows}
    )


@pytest.mark.asyncio
async def test_specification_builder_rejects_stale_categories_and_missing_required_templates() -> None:
    category_id, product_id = uuid7(), uuid7()
    store = SpecificationBuildStore(category_id)
    service = SpecificationService(store)  # type: ignore[arg-type]
    product = SimpleNamespace(id=product_id, category_id=category_id)
    empty = SpecificationSet(
        category_revision=1, attributes=[], skus=[NewSkuInput(code="DEFAULT-ONE", price=Decimal("1.00"))]
    )
    store.category.revision = 2
    with pytest.raises(AppException):
        await service.build_specifications(product, empty)  # type: ignore[arg-type]
    store.category.revision = 1
    store.template_rows = [SimpleNamespace(attribute_id=uuid7(), is_required=True)]
    with pytest.raises(AppException):
        await service.build_specifications(product, empty)  # type: ignore[arg-type]


class QueryRows:
    def one_or_none(self) -> None:
        return None

    def __iter__(self):
        return iter(())


class QueryResult:
    def scalar_one_or_none(self) -> None:
        return None

    def all(self) -> list[tuple[object, object]]:
        return []

    def tuples(self) -> list[tuple[object, object]]:
        return []

    def __iter__(self):
        return iter(())


class QuerySession:
    def __init__(self) -> None:
        self.scalar_value: object = 0
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    def add_all(self, rows: list[object]) -> None:
        self.added.extend(rows)

    async def flush(self) -> None:
        return None

    async def scalar(self, statement: object) -> object:
        return self.scalar_value

    async def scalars(self, statement: object) -> QueryRows:
        return QueryRows()

    async def execute(self, statement: object, *args: object) -> QueryResult:
        return QueryResult()


@pytest.mark.asyncio
async def test_target_model_repositories_cover_pages_lookups_and_optional_row_locks() -> None:
    session = QuerySession()
    ids = [uuid7() for _ in range(4)]
    catalog = CatalogRepository(session)  # type: ignore[arg-type]
    await catalog.flush()
    await catalog.brand(ids[0])
    await catalog.brand_page(1, 10)
    await catalog.attribute(ids[0])
    await catalog.attribute_by_code("color")
    await catalog.attribute_page(1, 10)
    await catalog.standard_value(ids[0])
    await catalog.standard_values(ids[0])
    await catalog.template(ids[0])
    await catalog.replace_template(ids[0], [])
    await catalog.adoptions(ids[0])
    await catalog.candidates(ids[0])
    await catalog.descriptions(ids[0])
    await catalog.sku_selections(ids[0])
    membership = MembershipRepository(session)  # type: ignore[arg-type]
    await membership.level(ids[0], for_update=True)
    await membership.levels_page(1, 10)
    await membership.active_levels()
    await membership.condition(ids[0], for_update=True)
    await membership.conditions_page(1, 10)
    assert await membership.conditions_for_levels([], datetime.now(UTC)) == []
    await membership.conditions_for_levels([ids[0]], datetime.now(UTC))
    await membership.qualification_event(ids[0], for_update=True)
    await membership.qualification_by_key("key", for_update=True)
    await membership.qualification_by_source(
        user_id=ids[0], metric="points", source_type="manual", source_id=ids[1], for_update=True
    )
    await membership.qualification_events(ids[0])
    await membership.qualification_events(ids[0], "points")
    await membership.qualification_events_page(ids[0], 1, 10)
    await membership.level_events_page(ids[0], 1, 10)
    await membership.price_rule(ids[0], for_update=True)
    await membership.price_rules_page(1, 10)
    await membership.profile(ids[0], for_update=True)
    await membership.sku_catalog(ids)
    await membership.categories()
    await membership.active_rules(ids[0])
    await membership.setting("order_shipping", for_update=True)
    await membership.flush()
    points = PointsRepository(session)  # type: ignore[arg-type]
    await points.account(ids[0], lock=True)
    await points.account_by_id(ids[0], lock=True)
    await points.ledger(ids[0], lock=True)
    await points.ledger_by_key("key", lock=True)
    await points.reversal_total(ids[0])
    await points.account_page(1, 10)
    await points.ledger_page(ids[0], 1, 10)
    await points.flush()
    lifecycle = LifecycleRepository(session)  # type: ignore[arg-type]
    await lifecycle.lock_key("payment", "key")
    await lifecycle.payment_by_request(ids[0], ids[1], lock=True)
    await lifecycle.payment(ids[0], lock=True)
    await lifecycle.payment_by_transaction("wechat", "transaction", lock=True)
    await lifecycle.fulfillment(ids[0], lock=True)
    await lifecycle.fulfillment_by_id(ids[0], lock=True)
    await lifecycle.count_due_fulfillments(datetime.now(UTC))
    await lifecycle.due_fulfillments(datetime.now(UTC), 10)
    await lifecycle.refund_by_request(ids[0], ids[1], lock=True)
    await lifecycle.refund(ids[0], lock=True)
    await lifecycle.refund_attempt(ids[0], lock=True)
    await lifecycle.refund_attempt_for_request(ids[0], lock=True)
    await lifecycle.refund_attempt_by_channel("wechat", "refund", lock=True)
    await lifecycle.refund_attempts_for_payment(ids[0], lock=True)
    await lifecycle.user_refund(ids[0], ids[1])
    await lifecycle.refunds_for_order(ids[0], lock=True)
    assert await lifecycle.refund_items([], lock=True) == []
    await lifecycle.refund_items([ids[0]], lock=True)
    await lifecycle.review_for_item(ids[0], ids[1], lock=True)
    await lifecycle.public_reviews(ids[0], 1, 10)
    await lifecycle.reconciliation("wechat", "payment", "transaction", lock=True)
    await lifecycle.refund_page(1, 10)
    products = ProductRepository(session)  # type: ignore[arg-type]
    await products.lock_catalog()
    await products.categories()
    await products.get(ids[0], lock=True)
    await products.skus(ids[0])
    assert await products.code_exists("SKU", ids[0])
    await products.checkout_skus(ids)
    await products.image_ids(ids[0])
    await products.image_urls(ids[0])
    assert (await products.details([]))[0] == {}
    await products.details(ids[:2])
    await products.replace_images(ids[0], [])
    await products.page(1, 10, public=True, search="SKU", category_id=ids[0], status="on_sale", product_type="physical")
    durable = DurableTaskRepository(session)  # type: ignore[arg-type]
    await durable.by_key("expire_order", "order", lock=True)
    session.scalar_value = datetime.now(UTC)
    assert await durable.database_now()
    session.scalar_value = 0
    await durable.lease_candidates(datetime.now(UTC), 10)
    await durable.count_lease_candidates(datetime.now(UTC))
    await durable.task(ids[0], lock=True)
    assert not await durable.complete_lease(ids[0], ids[1])
    assert await durable.retry_lease(ids[0], ids[1], "ERROR", "summary", datetime.now(UTC)) is None
    await durable.flush()


class MembershipStore:
    def __init__(self, session: MemorySession, profile: object, level: object, condition: object) -> None:
        self.session, self.profile_row, self.level_row, self.condition_row = session, profile, level, condition
        self.level_rows: dict[UUID, object] = {level.id: level}
        self.events: list[object] = []
        self.price_rule_rows: dict[UUID, object] = {}
        self.catalog_rows: list[tuple[object, object]] = []
        self.category_rows: list[object] = []
        self.shipping_setting: object | None = None

    async def flush(self) -> None:
        for value in self.session.added:
            if hasattr(value, "idempotency_key") and hasattr(value, "metric") and value not in self.events:
                self.events.append(value)

    async def levels_page(self, page: int, page_size: int) -> tuple[list[object], int]:
        rows = list(self.level_rows.values())
        return rows, len(rows)

    async def conditions_page(self, page: int, page_size: int) -> tuple[list[object], int]:
        return [self.condition_row], 1

    async def level(self, level_id: UUID, *, for_update: bool = False) -> object | None:
        return self.level_rows.get(level_id)

    async def price_rule(self, rule_id: UUID, *, for_update: bool = False) -> object | None:
        return self.price_rule_rows.get(rule_id)

    async def price_rules_page(self, page: int, page_size: int) -> tuple[list[object], int]:
        rows = list(self.price_rule_rows.values())
        return rows, len(rows)

    async def profile(self, user_id: UUID, *, for_update: bool = False) -> object | None:
        return self.profile_row if user_id == self.profile_row.user_id else None

    async def qualification_by_key(self, key: str, *, for_update: bool = False) -> object | None:
        return next((item for item in self.events if item.idempotency_key == key), None)

    async def qualification_event(self, event_id: UUID, *, for_update: bool = False) -> object | None:
        return next((item for item in self.events if item.id == event_id), None)

    async def qualification_events(self, user_id: UUID, metric: str) -> list[object]:
        return [item for item in self.events if item.user_id == user_id and item.metric == metric]

    async def active_levels(self) -> list[object]:
        return [self.level_row]

    async def conditions_for_levels(self, level_ids: list[UUID], now: datetime) -> list[object]:
        return [self.condition_row]

    async def condition(self, condition_id: UUID, *, for_update: bool = False) -> object | None:
        return self.condition_row if condition_id == self.condition_row.id else None

    async def qualification_events_page(self, user_id: UUID, page: int, page_size: int) -> tuple[list[object], int]:
        rows = [item for item in self.events if item.user_id == user_id]
        return rows, len(rows)

    async def level_events_page(self, user_id: UUID, page: int, page_size: int) -> tuple[list[object], int]:
        rows = [
            item
            for item in self.session.added
            if getattr(item, "user_id", None) == user_id and hasattr(item, "trigger_type")
        ]
        return rows, len(rows)

    async def sku_catalog(self, sku_ids: list[UUID]) -> list[tuple[object, object]]:
        return [(sku, product) for sku, product in self.catalog_rows if sku.id in sku_ids]

    async def categories(self) -> list[object]:
        return self.category_rows

    async def active_rules(self, level_id: UUID) -> list[object]:
        return [row for row in self.price_rule_rows.values() if row.member_level_id == level_id and row.is_active]

    async def setting(self, group: str, *, for_update: bool = False) -> object | None:
        assert group == "order_shipping"
        return self.shipping_setting


@pytest.mark.asyncio
async def test_membership_events_are_idempotent_reversible_and_reassess_level() -> None:
    user, level_id = uuid7(), uuid7()
    now = datetime.now(UTC)
    profile = SimpleNamespace(user_id=user, level_id=None, level_changed_at=None, revision=1)
    level = SimpleNamespace(
        id=level_id,
        code="vip",
        name="VIP",
        discount_factor=Decimal("0.9"),
        level_rank=1,
        sort_order=1,
        is_active=True,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    condition = SimpleNamespace(
        id=uuid7(),
        level_id=level_id,
        metric="consumption",
        aggregation="cumulative",
        amount_threshold=Decimal("10.00"),
        count_threshold=None,
        is_active=True,
        effective_at=now,
        updated_by_id=None,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    session = MemorySession()
    service = MembershipService(session=session, actor_id=uuid7(), audit=Audit())  # type: ignore[arg-type]
    store = MembershipStore(session, profile, level, condition)
    service._repository = store  # type: ignore[assignment]
    created_level = await service.save_level(MemberLevelCreate(code="gold", name="金卡", level_rank=2))
    store.level_rows[created_level.id] = session.added[-1]
    changed_level = await service.save_level(
        MemberLevelUpdate(code="gold", name="金卡会员", level_rank=2, revision=created_level.revision), created_level.id
    )
    assert changed_level.revision == 2
    condition_read = await service.save_condition(
        MemberLevelConditionCreate(
            level_id=level_id,
            metric="consumption",
            aggregation="cumulative",
            amount_threshold=Decimal("10.00"),
            effective_at=now,
        )
    )
    assert condition_read.level_id == level_id
    assert (await service.levels(1, 20)).total >= 1
    event = await service.record_qualification_event(
        user_id=user,
        metric="consumption",
        source_type="order",
        source_id=uuid7(),
        idempotency_key="qualification-1",
        amount_delta=Decimal("12.00"),
        trigger_type="order",
    )
    assert profile.level_id == level_id and profile.revision == 2
    assert (await service.conditions(1, 20)).total == 1
    assert (await service.qualification_events(user, 1, 20)).total == 1
    assert (await service.level_events(user, 1, 20)).total == 1
    assert (
        await service.record_qualification_event(
            user_id=user,
            metric="consumption",
            source_type="order",
            source_id=event.source_id,
            idempotency_key="qualification-1",
            amount_delta=Decimal("12.00"),
            trigger_type="order",
        )
        is event
    )
    reversal = await service.record_qualification_event(
        user_id=user,
        metric="consumption",
        source_type="refund",
        source_id=uuid7(),
        idempotency_key="qualification-2",
        amount_delta=Decimal("-12.00"),
        reverses_event_id=event.id,
        trigger_type="refund",
    )
    assert reversal.reverses_event_id == event.id and profile.level_id is None
    with pytest.raises(AppException):
        await service.record_qualification_event(
            user_id=user,
            metric="consumption",
            source_type="refund",
            source_id=uuid7(),
            idempotency_key="qualification-3",
            amount_delta=Decimal("-1.00"),
            reverses_event_id=event.id,
            trigger_type="refund",
        )


@pytest.mark.asyncio
async def test_membership_prices_shipping_and_quote_cover_customer_pricing_paths() -> None:
    user, level_id, category_id, product_id, sku_id = (uuid7() for _ in range(5))
    now = datetime.now(UTC)
    profile = SimpleNamespace(user_id=user, level_id=level_id, level_changed_at=None, revision=1)
    level = SimpleNamespace(
        id=level_id,
        code="vip",
        name="VIP",
        discount_factor=Decimal("0.90"),
        level_rank=1,
        sort_order=1,
        is_active=True,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    condition = SimpleNamespace(id=uuid7(), level_id=level_id, revision=1)
    session = MemorySession()
    service = MembershipService(session=session, actor_id=uuid7(), audit=Audit())  # type: ignore[arg-type]
    store = MembershipStore(session, profile, level, condition)
    service._repository = store  # type: ignore[assignment]
    category = SimpleNamespace(id=category_id, parent_id=None, is_active=True)
    product = SimpleNamespace(
        id=product_id, name="实物商品", product_type="physical", category_id=category_id, status="on_sale", revision=1
    )
    sku = SimpleNamespace(
        id=sku_id,
        product_id=product_id,
        price=Decimal("100.00"),
        wholesale_prices=[{"min_quantity": 2, "unit_price": "80.00"}],
        is_active=True,
        archived_at=None,
    )
    region_id = uuid7()
    store.catalog_rows = [(sku, product)]
    store.category_rows = [category]
    store.shipping_setting = SimpleNamespace(
        id=uuid7(),
        setting_value={
            "schema_version": 1,
            "region_level": "province",
            "default_rule": {"fixed_fee": "12.00", "free_shipping_threshold": "200.00"},
            "region_rules": [
                {"id": str(region_id), "name": "偏远", "province_codes": ["110000"], "fixed_fee": "20.00"}
            ],
        },
        revision=1,
        updated_at=now,
        updated_by_id=None,
    )
    created = await service.save_price_rule(
        MemberPriceRuleCreate(
            member_level_id=level_id,
            scope_type="sku",
            sku_id=sku_id,
            price_mode="fixed",
            fixed_price=Decimal("66.66"),
        )
    )
    store.price_rule_rows[created.id] = session.added[-1]
    updated = await service.save_price_rule(
        MemberPriceRuleUpdate(
            member_level_id=level_id,
            scope_type="sku",
            sku_id=sku_id,
            price_mode="fixed",
            fixed_price=Decimal("65.55"),
            revision=created.revision,
        ),
        created.id,
    )
    assert updated.fixed_price == Decimal("65.55") and (await service.price_rules(1, 20)).total == 1
    read_shipping = await service.order_shipping()
    assert read_shipping.default_rule.fixed_fee == Decimal("12.00")
    changed_shipping = await service.update_order_shipping(
        OrderShippingSettingUpdate(
            revision=1,
            default_rule={"fixed_fee": "10.00", "free_shipping_threshold": "200.00"},
            region_rules=[],
        )
    )
    assert changed_shipping.revision == 2
    quote = await service.quote(
        user,
        CommerceQuoteRequest(items=[QuoteItemInput(sku_id=sku_id, quantity=2)], province_code="110000"),
    )
    assert quote.items[0].base_unit_price == Decimal("80.00")
    assert quote.items[0].unit_price == Decimal("65.55")
    assert quote.freight_amount == Decimal("10.00") and quote.total_amount == Decimal("141.10")
    product.product_type = "virtual"
    virtual_quote = await service.quote(user, CommerceQuoteRequest(items=[QuoteItemInput(sku_id=sku_id, quantity=1)]))
    assert virtual_quote.freight_amount == Decimal("0.00")
    level.is_active = False
    disabled_quote = await service.quote(user, CommerceQuoteRequest(items=[QuoteItemInput(sku_id=sku_id, quantity=1)]))
    assert (
        disabled_quote.buyer_level_state == "disabled" and disabled_quote.items[0].price_source == "wholesale_or_base"
    )
    product.product_type = "physical"
    with pytest.raises(AppException):
        await service.quote(user, CommerceQuoteRequest(items=[QuoteItemInput(sku_id=sku_id, quantity=1)]))


class PointsAdjustmentStore(PointsStore):
    def __init__(self, session: MemorySession) -> None:
        super().__init__(None)
        self.session = session
        self.accounts: dict[UUID, object] = {}
        self.keys: dict[str, object] = {}

    async def account(self, user_id: UUID, *, lock: bool = False) -> object | None:
        return self.accounts.get(user_id)

    async def account_by_id(self, account_id: UUID, *, lock: bool = False) -> object | None:
        return next((row for row in self.accounts.values() if row.id == account_id), None)

    async def flush(self) -> None:
        for row in self.session.added:
            if type(row).__name__ == "PointsAccount":
                row.available_points = row.available_points or 0
                row.frozen_points = row.frozen_points or 0
                row.debt_points = row.debt_points or 0
                self.accounts[row.user_id] = row
            elif type(row).__name__ == "PointsLedger":
                self.ledgers[row.id] = row
                self.keys[row.idempotency_key] = row
        return None


@pytest.mark.asyncio
async def test_points_manual_adjustment_creates_accounts_and_records_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MembershipSpy:
        calls: list[dict[str, object]] = []

        def __init__(self, *, session: object) -> None:
            self.session = session

        async def record_qualification_event(self, **kwargs: object) -> None:
            self.calls.append(kwargs)

        async def qualification_event_for_source(self, **kwargs: object) -> object | None:
            return SimpleNamespace(id=uuid7())

    monkeypatch.setattr("app.domains.points.service.MembershipService", MembershipSpy)
    session = MemorySession()
    store = PointsAdjustmentStore(session)
    service = PointsService(session=session, actor_id=uuid7(), audit=Audit())  # type: ignore[arg-type]
    service._repository = store  # type: ignore[assignment]
    user = uuid7()
    result = await service.adjust(
        PointsManualAdjustment(user_id=user, points=7, operation="grant", idempotency_key="adjust-1")
    )
    account = session.added[0]
    assert result.available_points == 7 and getattr(account, "user_id") == user
    ledger = session.added[1]
    store.accounts[user] = account
    store.ledgers[ledger.id] = ledger
    reverse = await service.adjust(
        PointsManualAdjustment(
            user_id=user,
            points=3,
            operation="reverse",
            idempotency_key="adjust-2",
            reverses_ledger_id=ledger.id,
        )
    )
    assert reverse.available_points == 4 and len(MembershipSpy.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["sku", "product", "category", "ancestor"])
@pytest.mark.parametrize("factor", [Decimal("0"), Decimal("0.95"), Decimal("1"), None])
async def test_quote_preserves_zero_discount_and_rejects_missing_factor(scope, factor) -> None:
    user, sku_id, product_id, category_id, ancestor_id, level_id, rule_id = (uuid7() for _ in range(7))
    session = MemorySession()
    profile = SimpleNamespace(user_id=user, level_id=level_id)
    level = SimpleNamespace(
        id=level_id, code="vip", name="VIP", revision=1, is_active=True, discount_factor=Decimal("0.8")
    )
    store = MembershipStore(session, profile, level, None)
    store.catalog_rows = [
        (
            SimpleNamespace(
                id=sku_id,
                price=Decimal("100.00"),
                wholesale_prices=[{"min_quantity": 2, "unit_price": "80.00"}],
                is_active=True,
                archived_at=None,
            ),
            SimpleNamespace(
                id=product_id,
                category_id=category_id,
                name="折扣边界",
                product_type="virtual",
                status="on_sale",
                revision=1,
            ),
        )
    ]
    store.category_rows = [
        SimpleNamespace(id=category_id, parent_id=ancestor_id, is_active=True),
        SimpleNamespace(id=ancestor_id, parent_id=None, is_active=True),
    ]
    store.price_rule_rows[rule_id] = SimpleNamespace(
        id=rule_id,
        revision=1,
        fixed_price=None,
        member_level_id=level_id,
        is_active=True,
        scope_type="category" if scope == "ancestor" else scope,
        sku_id=sku_id if scope == "sku" else None,
        product_id=product_id if scope == "product" else None,
        category_id=ancestor_id if scope == "ancestor" else category_id if scope == "category" else None,
        price_mode="discount",
        discount_factor=factor,
    )
    service = MembershipService(session=session)  # type: ignore[arg-type]
    service._repository = store  # type: ignore[assignment]
    request = CommerceQuoteRequest(items=[QuoteItemInput(sku_id=sku_id, quantity=2)])
    if factor is None:
        with pytest.raises(AppException) as rejected:
            await service.quote(user, request)
        assert rejected.value.status_code == 503 and rejected.value.code == "CONFIGURATION_ERROR"
        return
    quote = await service.quote(user, request)
    assert quote.items[0].base_unit_price == Decimal("80.00")
    assert quote.items[0].unit_price == Decimal("80.00") * factor
    assert quote.total_amount == Decimal("160.00") * factor
    assert quote.freight_amount == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "reverse"])
@pytest.mark.parametrize("change", [None, "user", "points", "operation", "original", "note", "actor", "source"])
async def test_points_replay_checks_intent_including_debt_components(operation, change) -> None:
    now = datetime.now(UTC)
    actor, user, account_id, ledger_id, original_id = (uuid7() for _ in range(5))
    account = SimpleNamespace(
        id=account_id,
        user_id=user,
        available_points=1,
        frozen_points=0,
        debt_points=0,
        revision=2,
        created_at=now,
        updated_at=now,
    )
    session, store = MemorySession(), PointsStore(account)
    data = PointsManualAdjustment(
        user_id=user,
        points=5,
        operation=operation,
        idempotency_key="replay-with-debt",
        reverses_ledger_id=original_id if operation == "reverse" else None,
        note="已核实",
    )
    ledger = SimpleNamespace(
        id=ledger_id,
        account_id=account_id,
        entry_type=operation,
        available_delta=1 if operation == "grant" else -3,
        debt_delta=-4 if operation == "grant" else 2,
        frozen_delta=0,
        source_type="manual",
        source_id=actor,
        reverses_ledger_id=data.reverses_ledger_id,
        note=data.note,
    )
    store.keys[data.idempotency_key] = ledger
    if change == "user":
        data = data.model_copy(update={"user_id": uuid7()})
    elif change == "points":
        data = data.model_copy(update={"points": 4})
    elif change == "operation":
        data = data.model_copy(
            update={
                "operation": "reverse" if operation == "grant" else "grant",
                "reverses_ledger_id": original_id if operation == "grant" else None,
            }
        )
    elif change == "original":
        ledger.reverses_ledger_id = uuid7()
    elif change == "note":
        data = data.model_copy(update={"note": "修改说明"})
    elif change == "actor":
        actor = uuid7()
    elif change == "source":
        ledger.source_type = "order"
    service = PointsService(session=session, actor_id=actor, audit=Audit())  # type: ignore[arg-type]
    service._repository = store  # type: ignore[assignment]
    if change is None:
        result = await service.adjust(data)
        assert result.available_points == 1 and result.revision == 2
    else:
        with pytest.raises(AppException) as rejected:
            await service.adjust(data)
        assert rejected.value.status_code == 409 and rejected.value.code == "STATE_CONFLICT"
    assert not session.added
    assert account.available_points == 1 and account.revision == 2


class ProductBoundaryStore:
    def __init__(self) -> None:
        self.category_id = uuid7()
        self.category_rows: list[object] = [
            SimpleNamespace(
                id=self.category_id,
                name="可用分类",
                parent_id=None,
                sort_order=None,
                is_active=True,
                revision=1,
            )
        ]
        self.product = SimpleNamespace(
            id=uuid7(),
            name="测试商品",
            description="",
            product_type="virtual",
            category_id=self.category_id,
            brand_id=None,
            purchase_limit_quantity=0,
            status="on_sale",
            revision=1,
        )
        self.sku = SimpleNamespace(
            id=uuid7(),
            product_id=self.product.id,
            code="BOUNDARY-SKU",
            sku_no=2,
            specification_key="default",
            specifications={},
            price=Decimal("1.00"),
            cost_price=None,
            market_price=None,
            wholesale_prices=[],
            weight_grams=None,
            is_active=False,
            archived_at=None,
        )
        self.rows: list[tuple[object, object]] = [(self.sku, self.product)]

    async def lock_catalog(self) -> None:
        return None

    async def checkout_skus(self, sku_ids: list[UUID]) -> list[tuple[object, object]]:
        return self.rows

    async def categories(self) -> list[object]:
        return self.category_rows

    async def adoptions(self, product_id: UUID) -> list[object]:
        return []

    async def sku_selections(self, product_id: UUID) -> list[object]:
        return []

    async def skus(self, product_id: UUID) -> list[object]:
        return [self.sku]

    async def get(self, product_id: UUID, *, lock: bool = False) -> object | None:
        return self.product if product_id == self.product.id else None

    async def code_exists(self, code: str, sku_id: UUID | None = None) -> bool:
        return True

    async def save(self, row: object) -> None:
        return None

    async def brand(self, brand_id: UUID) -> None:
        return None

    async def template(self, category_id: UUID) -> list[object]:
        return [SimpleNamespace(attribute_id=uuid7(), is_required=True, is_variant=False, allow_custom_value=False)]


@pytest.mark.asyncio
async def test_product_service_rejects_unavailable_catalog_and_invalid_sku_operations() -> None:
    store = ProductBoundaryStore()
    service = ProductService(store)  # type: ignore[arg-type]

    store.rows = []
    with pytest.raises(AppException):
        await service.checkout_skus([store.sku.id])
    store.rows = [(store.sku, store.product)]
    store.product.status = "off_sale"
    with pytest.raises(AppException):
        await service.checkout_skus([store.sku.id])
    store.product.status = "on_sale"
    with pytest.raises(AppException):
        await service.checkout_skus([store.sku.id])

    store.category_rows[0].is_active = False
    assert await service.categories(public=True) == []
    store.category_rows[0].is_active = True
    store.category_rows = [
        SimpleNamespace(id=uuid7(), name="一级", parent_id=None, sort_order=None, is_active=True, revision=1)
        for _ in range(1000)
    ]
    with pytest.raises(AppException):
        await service.save_category(CategoryInput(name="超限分类"))
    store.category_rows = [
        SimpleNamespace(
            id=store.category_id,
            name="可用分类",
            parent_id=None,
            sort_order=None,
            is_active=True,
            revision=1,
        )
    ]
    with pytest.raises(AppException):
        await service.save_category(CategoryUpdate(name="不存在", revision=1), uuid7())
    with pytest.raises(AppException):
        await service.save_category(
            CategoryUpdate(name="循环", parent_id=store.category_id, revision=1), store.category_id
        )
    with pytest.raises(AppException):
        await service.save_category(CategoryUpdate(name="过期版本", revision=99), store.category_id)

    with pytest.raises(AppException):
        await service.write_sku(
            store.product.id,
            SkuUpdate(code="DUPLICATE", price=Decimal("1.00"), revision=1),
            None,
        )
    with pytest.raises(AppException):
        await service.set_skus_active(store.product.id, SkuStatusBatch(sku_ids=[uuid7()], revision=1, is_active=True))
    with pytest.raises(AppException):
        await service.validate_publish(store.product.id)
    store.sku.archived_at = datetime.now(UTC)
    with pytest.raises(AppException):
        await service.require_current_sku(store.sku.id)

    store.sku.archived_at = None
    store.product.status = "off_sale"
    with pytest.raises(AppException):
        await service.public_read(store.product.id)
    store.product.status = "on_sale"
    store.category_rows[0].is_active = False
    with pytest.raises(AppException):
        await service.public_read(store.product.id)
    store.category_rows[0].is_active = True
    with pytest.raises(AppException):
        await service.update(
            store.product.id,
            ProductUpdate(name="类型冲突", product_type="physical", category_id=store.category_id, revision=1),
        )
    with pytest.raises(AppException):
        await service.update(
            store.product.id,
            ProductUpdate(
                name="品牌冲突", product_type="virtual", category_id=store.category_id, brand_id=uuid7(), revision=1
            ),
        )
    next_category_id = uuid7()
    store.category_rows.append(
        SimpleNamespace(id=next_category_id, name="新分类", parent_id=None, sort_order=None, is_active=True, revision=1)
    )
    with pytest.raises(AppException):
        await service.update(
            store.product.id,
            ProductUpdate(name="模板冲突", product_type="virtual", category_id=next_category_id, revision=1),
        )


class LifecycleGuardRepository:
    def __init__(self) -> None:
        self.attempt: object | None = None
        self.payment_row: object | None = None
        self.duplicate: object | None = None
        self.refund_row: object | None = None
        self.refund_attempts: list[object] = []

    async def lock_key(self, scope: str, key: str) -> None:
        return None

    async def payment(self, payment_attempt_id: UUID, *, lock: bool = False) -> object | None:
        return self.attempt

    async def payment_by_transaction(self, channel: str, transaction_id: str, *, lock: bool = False) -> object | None:
        return self.payment_row if self.payment_row is not None else self.duplicate

    async def refund_attempt(self, refund_attempt_id: UUID, *, lock: bool = False) -> object | None:
        return self.attempt

    async def refund_attempt_by_channel(self, channel: str, refund_id: str, *, lock: bool = False) -> object | None:
        return self.duplicate

    async def refund_attempts_for_payment(self, payment_attempt_id: UUID, *, lock: bool = False) -> list[object]:
        return self.refund_attempts

    async def refund(self, refund_id: UUID, *, lock: bool = False) -> object | None:
        return self.refund_row

    async def save(self, row: object) -> None:
        return None


class LifecycleGuardOrders:
    def __init__(self, order: object | None) -> None:
        self.order_row = order

    async def order(self, order_id: UUID, *, lock: bool = False) -> object | None:
        return self.order_row


class LifecycleGuardDistribution:
    async def lock_referral_changes(self) -> None:
        return None


@pytest.mark.asyncio
async def test_lifecycle_confirmation_guards_reject_inconsistent_external_facts() -> None:
    now = datetime.now(UTC)
    order_id, payment_id, refund_id = uuid7(), uuid7(), uuid7()
    order = SimpleNamespace(id=order_id, status="paid", total_amount=Decimal("10.00"), currency="CNY")
    payment = SimpleNamespace(
        id=payment_id,
        order_id=order_id,
        channel="wechat",
        status="succeeded",
        amount=Decimal("10.00"),
        currency="CNY",
    )
    refund_attempt = SimpleNamespace(
        id=uuid7(),
        order_id=order_id,
        payment_attempt_id=payment_id,
        refund_request_id=refund_id,
        channel="wechat",
        status="created",
        amount=Decimal("10.00"),
        currency="CNY",
        created_at=now,
    )
    payment_confirmation = VerifiedPaymentConfirmation(
        payment_attempt_id=uuid7(),
        channel="wechat",
        channel_transaction_id="MISSING-PAYMENT",
        amount=Decimal("10.00"),
        currency="CNY",
        confirmed_at=now,
        payload_hash="a" * 64,
    )
    refund_confirmation = VerifiedRefundConfirmation(
        refund_attempt_id=refund_attempt.id,
        channel="wechat",
        payment_transaction_id="SOURCE-PAYMENT",
        channel_refund_id="MISSING-REFUND",
        amount=Decimal("10.00"),
        currency="CNY",
        confirmed_at=now,
        payload_hash="b" * 64,
    )
    repository = LifecycleGuardRepository()
    service = LifecycleService(
        MemorySession(),  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        orders=LifecycleGuardOrders(order),  # type: ignore[arg-type]
        distribution=LifecycleGuardDistribution(),  # type: ignore[arg-type]
    )
    with pytest.raises(AppException):
        await service.confirm_verified_payment_in_open_transaction(payment_confirmation)
    repository.attempt = SimpleNamespace(
        id=payment_id,
        order_id=order_id,
        channel="wechat",
        status="unavailable",
        amount=Decimal("10.00"),
        currency="CNY",
    )
    service.orders = LifecycleGuardOrders(None)  # type: ignore[assignment]
    with pytest.raises(AppException):
        await service.confirm_verified_payment_in_open_transaction(payment_confirmation)
    service.orders = LifecycleGuardOrders(order)  # type: ignore[assignment]
    with pytest.raises(AppException):
        await service.confirm_verified_payment_in_open_transaction(
            payment_confirmation.model_copy(update={"channel": "alipay"})
        )
    repository.attempt.status = "pending"
    with pytest.raises(AppException):
        await service.confirm_verified_payment_in_open_transaction(
            payment_confirmation.model_copy(update={"amount": Decimal("11.00")})
        )
    repository.duplicate = SimpleNamespace(id=uuid7())
    with pytest.raises(AppException):
        await service.confirm_verified_payment_in_open_transaction(payment_confirmation)
    repository.duplicate = None
    order.total_amount = Decimal("11.00")
    with pytest.raises(AppException):
        await service.confirm_verified_payment_in_open_transaction(payment_confirmation)
    repository.attempt = SimpleNamespace(
        id=payment_id,
        order_id=order_id,
        channel="wechat",
        status="succeeded",
        amount=Decimal("10.00"),
        currency="CNY",
        channel_transaction_id="ORIGINAL",
        confirmed_at=now,
    )
    with pytest.raises(AppException):
        await service.confirm_verified_payment_in_open_transaction(payment_confirmation)

    repository.attempt = None
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(refund_confirmation)
    repository.attempt = refund_attempt
    service.orders = LifecycleGuardOrders(None)  # type: ignore[assignment]
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(refund_confirmation)
    service.orders = LifecycleGuardOrders(order)  # type: ignore[assignment]
    repository.payment_row = payment
    order.total_amount = Decimal("10.00")
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(
            refund_confirmation.model_copy(update={"amount": Decimal("9.00")})
        )
    repository.payment_row = None
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(refund_confirmation)
    repository.payment_row = payment
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(
            refund_confirmation.model_copy(update={"confirmed_at": now - timedelta(seconds=1)})
        )
    refund_attempt.status = "closed"
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(refund_confirmation)
    refund_attempt.status = "created"
    repository.duplicate = SimpleNamespace(id=uuid7())
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(refund_confirmation)
    repository.duplicate = None
    repository.refund_attempts = [SimpleNamespace(status="created", amount=Decimal("11.00"))]
    with pytest.raises(AppException):
        await service.confirm_verified_refund_in_open_transaction(refund_confirmation)
    repository.refund_attempts = []
    repository.attempt = SimpleNamespace(
        id=refund_attempt.id,
        order_id=order_id,
        payment_attempt_id=payment_id,
        refund_request_id=None,
        merchant_refund_reference="ABNORMAL-REFUND",
        channel="wechat",
        channel_refund_id=None,
        confirmed_at=None,
        status="created",
        amount=Decimal("10.00"),
        currency="CNY",
        created_at=now,
        revision=1,
    )
    confirmed_refund = await service.confirm_verified_refund_in_open_transaction(refund_confirmation)
    assert confirmed_refund.status == "succeeded"


class WalletScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def one_or_none(self) -> object | None:
        return self.value


class WalletQuerySession(MemorySession):
    def __init__(self, values: list[object | None]) -> None:
        super().__init__()
        self.values = values

    async def scalars(self, statement: object) -> WalletScalarResult:
        return WalletScalarResult(self.values.pop(0))


@pytest.mark.asyncio
async def test_wallet_ledger_queries_lock_rows_and_reject_missing_wallets() -> None:
    wallet = SimpleNamespace(
        id=uuid7(),
        available_amount=Decimal("5.00"),
        frozen_amount=Decimal("0.00"),
        debt_amount=Decimal("0.00"),
        revision=1,
    )
    session = WalletQuerySession([None, wallet])
    service = WalletLedgerService(session)  # type: ignore[arg-type]
    ledger = await service.apply_in_open_transaction(
        wallet_id=wallet.id,
        entry_type="commission_settlement",
        amount=Decimal("2.00"),
        frozen_delta=Decimal("0.00"),
        debt_delta=Decimal("0.00"),
        idempotency_key="query-wallet-1",
        reference_type="commission",
        reference_id=uuid7(),
    )
    assert ledger.wallet_id == wallet.id and wallet.available_amount == Decimal("7.00")
    missing = WalletLedgerService(WalletQuerySession([None, None]))  # type: ignore[arg-type]
    with pytest.raises(AppException):
        await missing.apply_in_open_transaction(
            wallet_id=uuid7(),
            entry_type="commission_settlement",
            amount=Decimal("1.00"),
            frozen_delta=Decimal("0.00"),
            debt_delta=Decimal("0.00"),
            idempotency_key="query-wallet-missing",
            reference_type="commission",
            reference_id=uuid7(),
        )
