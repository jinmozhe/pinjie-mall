"""商城基础规则和库存幂等的回归资产；执行遵循专项测试授权。"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.db.models.address import UserAddress
from app.db.models.identity import Admin, Permission, Role
from app.db.models.inventory import InventoryAccount, InventoryMovement
from app.db.models.reservation import InventoryReservation
from app.domains.addresses.schemas import AddressInput, AddressUpdate
from app.domains.addresses.service import AddressService
from app.domains.inventory.schemas import InventoryAdjustment, adjusted_available
from app.domains.inventory.service import InventoryService
from app.domains.products.catalog_schemas import (
    AdoptionInput,
    AttributeValidation,
    CandidateInput,
    NewSkuInput,
    SpecificationSet,
    WholesalePrice,
)
from app.domains.products.schemas import CategoryInput, ProductCreate, PublicSkuRead, validate_category_tree
from app.domains.shipping.schemas import FreightQuoteInput, ShippingRegion, ShippingTemplateInput, calculate_freight
from app.services.commerce import CommerceService


def template() -> ShippingTemplateInput:
    return ShippingTemplateInput(
        name="标准运费",
        pricing_method="weight",
        regions=[
            ShippingRegion(
                provinces=[],
                first_unit=1000,
                first_price=Decimal("5.00"),
                additional_unit=500,
                additional_price=Decimal("2.00"),
            )
        ],
        free_shipping_threshold=Decimal("100.00"),
        excluded_provinces=["650000"],
    )


@pytest.mark.parametrize(
    ("weight", "expected"), [(1, "5.00"), (1000, "5.00"), (1001, "7.00"), (1500, "7.00"), (1501, "9.00")]
)
def test_freight_rounds_up_only_after_full_first_unit(weight: int, expected: str) -> None:
    result = calculate_freight(
        template(),
        FreightQuoteInput(province_code="110000", pieces=1, weight_grams=weight, items_amount=Decimal("20.00")),
    )
    assert result == Decimal(expected)


def test_free_shipping_respects_excluded_province() -> None:
    quote = FreightQuoteInput(province_code="650000", pieces=1, weight_grams=1000, items_amount=Decimal("100.00"))
    assert calculate_freight(template(), quote) == Decimal("5.00")
    assert calculate_freight(template(), quote.model_copy(update={"province_code": "110000"})) == Decimal("0.00")


def test_regions_must_have_one_default_and_no_duplicate_provinces() -> None:
    data = template().model_dump()
    data["regions"] = []
    with pytest.raises(ValidationError):
        ShippingTemplateInput.model_validate(data)
    data["regions"] = [template().regions[0].model_dump()] * 2
    with pytest.raises(ValidationError):
        ShippingTemplateInput.model_validate(data)
    specified = template().regions[0].model_copy(update={"provinces": ["110000"]})
    data["regions"] = [template().regions[0].model_dump(), specified.model_dump(), specified.model_dump()]
    with pytest.raises(ValidationError):
        ShippingTemplateInput.model_validate(data)


def test_weight_quote_cannot_omit_weight_even_when_free_shipping_matches() -> None:
    with pytest.raises(ValueError):
        calculate_freight(
            template(),
            FreightQuoteInput(province_code="110000", pieces=1, weight_grams=0, items_amount=Decimal("200.00")),
        )


def test_category_move_checks_descendants_and_cycles() -> None:
    root, child, leaf, fourth = (uuid7() for _ in range(4))
    validate_category_tree({root: None, child: root, leaf: child})
    with pytest.raises(ValueError, match="三级"):
        validate_category_tree({root: None, child: root, leaf: child, fourth: leaf})
    with pytest.raises(ValueError, match="循环"):
        validate_category_tree({root: child, child: root})
    with pytest.raises(ValueError, match="不存在"):
        validate_category_tree({child: root})


def test_default_sku_set_rejects_duplicate_default() -> None:
    first = NewSkuInput(code="DEFAULT-1", price=Decimal("1.00"), weight_grams=100)
    with pytest.raises(ValidationError, match="规格组合"):
        SpecificationSet(
            category_revision=1,
            skus=[first, first.model_copy(update={"code": "DEFAULT-2"})],
        )


def test_sku_combination_uses_candidate_identity_and_rejects_duplicates() -> None:
    color = AdoptionInput(
        key="color",
        name="颜色",
        value_type="select",
        validation=AttributeValidation(),
        is_variant=True,
        candidates=[CandidateInput(key="red", display_value="红色")],
    )
    sku = NewSkuInput(code="RED-1", price=Decimal("1.00"), selections={"color": "red"})
    with pytest.raises(ValidationError, match="规格组合"):
        SpecificationSet(category_revision=1, attributes=[color], skus=[sku, sku.model_copy(update={"code": "RED-2"})])


def test_product_rejects_legacy_shipping_template_and_public_sku_hides_cost() -> None:
    sku = NewSkuInput(code="DEFAULT-1", price=Decimal("10.00"), cost_price=Decimal("2.00"))
    with pytest.raises(ValidationError):
        ProductCreate(
            name="商品",
            product_type="physical",
            category_id=uuid7(),
            category_revision=1,
            skus=[sku],
            shipping_template_id=uuid7(),
        )
    public = PublicSkuRead.model_validate(
        {
            "id": uuid7(),
            "code": sku.code,
            "sku_no": 0,
            "specifications": {},
            "price": sku.price,
            "market_price": sku.market_price,
            "wholesale_prices": [WholesalePrice(min_quantity=2, unit_price=Decimal("9.00"))],
            "weight_grams": None,
            "is_active": True,
        }
    )
    assert "cost_price" not in public.model_dump()


@pytest.mark.parametrize(("available", "delta"), [(0, -1), (10, -11), (2147483647, 1)])
def test_stock_rejects_negative_and_database_overflow(available: int, delta: int) -> None:
    with pytest.raises(ValueError):
        adjusted_available(available, delta)


class MemoryInventory:
    def __init__(self) -> None:
        self.sku_id = uuid7()
        self.account = InventoryAccount(sku_id=self.sku_id, available=10, reserved=2, revision=1)
        self.movements: dict[object, InventoryMovement] = {}

    async def get(self, sku_id: object, *, lock: bool = False) -> InventoryAccount:
        assert sku_id == self.sku_id
        return self.account

    async def movement(self, sku_id: object, request_id: object) -> InventoryMovement | None:
        return self.movements.get(request_id)

    async def save(self, value: InventoryAccount | InventoryMovement) -> None:
        if isinstance(value, InventoryMovement):
            value.id = uuid7()
            value.created_at = datetime.now(UTC)
            self.movements[value.request_id] = value


class ArchiveInventory(MemoryInventory):
    def __init__(self) -> None:
        super().__init__()
        self.account.available, self.account.reserved = 90, 10
        self.reservation = InventoryReservation(
            id=uuid7(), order_id=uuid7(), sku_id=self.sku_id, quantity=10, status="reserved", revision=1
        )

    async def reservations(self, order_id: UUID) -> list[InventoryReservation]:
        assert order_id == self.reservation.order_id
        return [self.reservation]

    async def accounts(self, sku_ids: list[UUID]) -> list[InventoryAccount]:
        assert sku_ids == [self.sku_id]
        return [self.account]


@pytest.mark.asyncio
async def test_stock_adjustment_replays_original_result_without_second_write() -> None:
    repository = MemoryInventory()
    service = InventoryService(repository)
    actor = uuid7()
    request = InventoryAdjustment(request_id=uuid7(), revision=1, quantity_delta=-3, reason="盘点")
    first = await service.adjust(repository.sku_id, request, actor)
    repeated = await service.adjust(repository.sku_id, request, actor)
    assert first.id == repeated.id
    assert repository.account.available == 7
    assert repository.account.reserved == 2
    assert repository.account.revision == 2
    assert len(repository.movements) == 1
    with pytest.raises(AppException) as conflict:
        await service.adjust(repository.sku_id, request.model_copy(update={"quantity_delta": -2}), actor)
    assert conflict.value.code == "INVENTORY_IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_stock_rejects_stale_revision_and_insufficient_quantity_before_mutation() -> None:
    repository = MemoryInventory()
    service = InventoryService(repository)
    actor = uuid7()
    stale = InventoryAdjustment(request_id=uuid7(), revision=2, quantity_delta=1, reason="盘点")
    with pytest.raises(AppException) as conflict:
        await service.adjust(repository.sku_id, stale, actor)
    assert conflict.value.code == "INVENTORY_REVISION_CONFLICT"
    with pytest.raises(AppException) as insufficient:
        await service.adjust(repository.sku_id, stale.model_copy(update={"revision": 1, "quantity_delta": -11}), actor)
    assert insufficient.value.code == "INVENTORY_QUANTITY_REJECTED"
    assert repository.account.available == 10
    assert not repository.movements


@pytest.mark.asyncio
async def test_archived_sku_clears_available_then_released_reservation() -> None:
    repository = ArchiveInventory()
    service = InventoryService(repository)
    await service.archive_available(repository.sku_id, repository.reservation.id)
    assert (repository.account.available, repository.account.reserved) == (0, 10)
    await service.transition_reservations(
        repository.reservation.order_id,
        {repository.sku_id: 10},
        "released",
        archived_sku_ids={repository.sku_id},
    )
    assert (repository.account.available, repository.account.reserved) == (0, 0)
    assert repository.reservation.status == "released"
    assert len(repository.movements) == 2


def test_freight_overflow_is_rejected_before_response_serialization() -> None:
    data = template().model_dump()
    data["regions"][0]["additional_price"] = Decimal("9999999999999.99")
    data["free_shipping_threshold"] = None
    with pytest.raises(ValueError, match="金额上限"):
        calculate_freight(
            ShippingTemplateInput.model_validate(data),
            FreightQuoteInput(province_code="110000", pieces=1, weight_grams=2000, items_amount=Decimal("1")),
        )


class MemoryAddresses:
    def __init__(self) -> None:
        self.rows: list[UserAddress] = []

    async def lock_owner(self, user_id: UUID) -> None:
        pass

    async def list_for_user(self, user_id: UUID) -> list[UserAddress]:
        return sorted(
            (row for row in self.rows if row.user_id == user_id),
            key=lambda row: (row.created_at, row.id),
        )

    async def get(self, user_id: UUID, address_id: UUID) -> UserAddress | None:
        return next((row for row in self.rows if row.id == address_id and row.user_id == user_id), None)

    async def save(self, row: UserAddress) -> None:
        if row.id is None:
            row.id = uuid7()
            row.created_at = datetime.now(UTC)
            self.rows.append(row)

    async def delete(self, row: UserAddress) -> None:
        self.rows.remove(row)

    async def flush(self) -> None:
        pass


def address_data(*, default: bool = False) -> AddressInput:
    return AddressInput(
        receiver_name="收件人",
        mobile="13800138000",
        province_code="110000",
        city_code="110100",
        district_code="110101",
        province="北京市",
        city="北京市",
        district="东城区",
        street_address="测试路一号",
        is_default=default,
    )


@pytest.mark.asyncio
async def test_address_ownership_default_replacement_and_stale_revision() -> None:
    repository = MemoryAddresses()
    service = AddressService(repository)
    owner, other = uuid7(), uuid7()
    first = await service.create(owner, address_data())
    second = await service.create(owner, address_data())
    assert first.is_default and not second.is_default
    with pytest.raises(AppException) as hidden:
        await service.snapshot(other, first.id)
    assert hidden.value.status_code == 404
    await service.update(
        owner, second.id, AddressUpdate(**address_data(default=True).model_dump(), revision=second.revision)
    )
    current_first = await service.snapshot(owner, first.id)
    assert not current_first.is_default and current_first.revision > first.revision
    with pytest.raises(AppException) as stale:
        await service.delete(owner, first.id, first.revision)
    assert stale.value.code == "ADDRESS_REVISION_CONFLICT"
    await service.delete(owner, second.id, second.revision + 1)
    replacement = await service.snapshot(owner, first.id)
    assert replacement.is_default
    assert await service.list_for_user(other) == []


@pytest.mark.asyncio
async def test_address_limit_is_per_user() -> None:
    repository = MemoryAddresses()
    service = AddressService(repository)
    owner = uuid7()
    for _ in range(20):
        await service.create(owner, address_data())
    with pytest.raises(AppException) as limit:
        await service.create(owner, address_data())
    assert limit.value.code == "ADDRESS_LIMIT"
    assert (await service.create(uuid7(), address_data())).is_default


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["missing", "disabled", "revoked", "disabled_role", "disabled_permission"])
async def test_management_write_rechecks_authoritative_permissions(denial: str) -> None:
    permission = Permission(code="product-categories:create", is_active=denial != "disabled_permission")
    role = Role(is_active=denial != "disabled_role", permissions=[permission])
    admin = Admin(
        is_active=denial != "disabled",
        is_superuser=False,
        roles=[] if denial == "revoked" else [role],
    )
    access = MagicMock()
    access.get_admin_for_update = AsyncMock(return_value=None if denial == "missing" else admin)
    products = MagicMock()
    products.save_category = AsyncMock()
    audit = MagicMock()

    async def execute(**kwargs: object) -> object:
        return await kwargs["operation"]()

    audit.execute = execute
    service = CommerceService(
        products=products,
        inventory=MagicMock(),
        shipping=MagicMock(),
        access=access,
        audit=audit,
        actor_id=uuid7(),
    )
    with pytest.raises(AppException) as denied:
        await service.create_category(CategoryInput(name="分类"))
    assert denied.value.status_code == 403
    products.save_category.assert_not_awaited()
