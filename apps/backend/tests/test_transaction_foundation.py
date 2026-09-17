"""交易阶段不变量回归资产；实际执行遵循专项测试授权。"""

from decimal import Decimal
from uuid import uuid7

import pytest

from app.core.exceptions import AppException
from app.domains.orders.schemas import CheckoutLine, CheckoutRequest, QuoteLine, ShippingQuoteGroup
from app.domains.products.schemas import CheckoutSku
from app.services.orders import OrderService


def checkout(*lines: CheckoutLine) -> CheckoutRequest:
    return CheckoutRequest(request_id=uuid7(), items=list(lines))


def test_checkout_merges_identical_skus_and_rejects_overflow() -> None:
    sku_id = uuid7()
    request = checkout(CheckoutLine(sku_id=sku_id, quantity=400), CheckoutLine(sku_id=sku_id, quantity=599))
    assert OrderService._normalize(request) == [(sku_id, 999)]
    with pytest.raises(AppException) as error:
        OrderService._normalize(
            checkout(CheckoutLine(sku_id=sku_id, quantity=999), CheckoutLine(sku_id=sku_id, quantity=1))
        )
    assert error.value.code == "CHECKOUT_INVALID"


def test_quote_fingerprint_changes_with_authoritative_amount_or_address() -> None:
    line = QuoteLine(
        sku_id=uuid7(),
        product_id=uuid7(),
        product_name="商品",
        sku_code="SKU-1",
        specifications={},
        quantity=1,
        unit_price=Decimal("10.00"),
        line_amount=Decimal("10.00"),
        weight_grams=100,
        product_revision=1,
        product_type="physical",
        shipping_template_id=uuid7(),
    )
    shipping = [
        ShippingQuoteGroup(
            template_id=line.shipping_template_id,
            revision=1,
            product_type="physical",
            pieces=1,
            weight_grams=100,
            items_amount=Decimal("10.00"),
            freight=Decimal("5.00"),
        )
    ]
    address = {"province_code": "110000"}
    fingerprint = OrderService._fingerprint([line], shipping, address)
    assert fingerprint != OrderService._fingerprint(
        [line.model_copy(update={"unit_price": Decimal("11.00"), "line_amount": Decimal("11.00")})],
        shipping,
        address,
    )
    assert fingerprint != OrderService._fingerprint([line], shipping, {"province_code": "120000"})


class CatalogProducts:
    def __init__(self, rows):
        self.rows = rows

    async def checkout_skus(self, sku_ids):
        return self.rows


@pytest.mark.asyncio
async def test_quote_rejects_mixed_physical_and_virtual_products() -> None:
    rows = [
        CheckoutSku(
            id=uuid7(),
            product_id=uuid7(),
            code=kind.upper(),
            specifications={},
            price=Decimal("1.00"),
            weight_grams=1 if kind == "physical" else 0,
            product_name=kind,
            product_type=kind,
            product_revision=1,
            shipping_template_id=None,
        )
        for kind in ("physical", "virtual")
    ]
    service = OrderService(session=object(), products=CatalogProducts(rows))
    with pytest.raises(AppException) as error:
        await service.preview(uuid7(), checkout(*(CheckoutLine(sku_id=row.id, quantity=1) for row in rows)))
    assert error.value.code == "CHECKOUT_INVALID"
    assert error.value.message == "实物和虚拟商品必须分开下单"
