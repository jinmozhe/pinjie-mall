from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.base import Base
from app.db.models.catalog import (
    Brand,
    CategorySpecAttribute,
    ProductAttributeValue,
    ProductSkuSpecValue,
    ProductSpecAttribute,
    ProductSpecValue,
    SpecAttribute,
    SpecAttributeValue,
)


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_entity(self, row: Base) -> None:
        self.session.add(row)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def brand(self, brand_id: UUID) -> Brand | None:
        return (
            await self.session.scalars(
                select(Brand).where(Brand.id == brand_id).execution_options(populate_existing=True)
            )
        ).one_or_none()

    async def brand_page(self, page: int, page_size: int) -> tuple[list[Brand], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(Brand)) or 0)
        rows = await self.session.scalars(
            select(Brand)
            .order_by(Brand.sort_order.asc().nulls_last(), Brand.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def attribute(self, attribute_id: UUID) -> SpecAttribute | None:
        return (
            await self.session.scalars(
                select(SpecAttribute).where(SpecAttribute.id == attribute_id).execution_options(populate_existing=True)
            )
        ).one_or_none()

    async def attribute_by_code(self, code: str) -> SpecAttribute | None:
        return (await self.session.scalars(select(SpecAttribute).where(SpecAttribute.code == code))).one_or_none()

    async def attribute_page(
        self,
        page: int,
        page_size: int,
        *,
        search: str | None = None,
        value_type: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[SpecAttribute], int]:
        query = select(SpecAttribute)
        if search:
            query = query.where(
                or_(
                    SpecAttribute.name.icontains(search, autoescape=True),
                    SpecAttribute.code.icontains(search, autoescape=True),
                )
            )
        if value_type is not None:
            query = query.where(SpecAttribute.value_type == value_type)
        if is_active is not None:
            query = query.where(SpecAttribute.is_active == is_active)
        total = int(await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = await self.session.scalars(
            query.order_by(SpecAttribute.sort_order.asc().nulls_last(), SpecAttribute.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def standard_value(self, value_id: UUID) -> SpecAttributeValue | None:
        return (
            await self.session.scalars(
                select(SpecAttributeValue)
                .where(SpecAttributeValue.id == value_id)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()

    async def standard_values(self, attribute_id: UUID) -> list[SpecAttributeValue]:
        return list(
            await self.session.scalars(
                select(SpecAttributeValue)
                .where(SpecAttributeValue.attribute_id == attribute_id)
                .order_by(SpecAttributeValue.sort_order.asc().nulls_last(), SpecAttributeValue.id.desc())
                .execution_options(populate_existing=True)
            )
        )

    async def template(self, category_id: UUID) -> list[CategorySpecAttribute]:
        return list(
            await self.session.scalars(
                select(CategorySpecAttribute)
                .where(CategorySpecAttribute.category_id == category_id)
                .order_by(CategorySpecAttribute.sort_order.asc().nulls_last(), CategorySpecAttribute.attribute_id)
                .execution_options(populate_existing=True)
            )
        )

    async def replace_template(self, category_id: UUID, rows: list[CategorySpecAttribute]) -> None:
        await self.session.execute(
            delete(CategorySpecAttribute).where(CategorySpecAttribute.category_id == category_id)
        )
        self.session.add_all(rows)
        await self.session.flush()

    async def adoptions(self, product_id: UUID) -> list[ProductSpecAttribute]:
        return list(
            await self.session.scalars(
                select(ProductSpecAttribute)
                .where(ProductSpecAttribute.product_id == product_id)
                .order_by(ProductSpecAttribute.id)
                .execution_options(populate_existing=True)
            )
        )

    async def candidates(self, product_id: UUID) -> list[ProductSpecValue]:
        return list(
            await self.session.scalars(
                select(ProductSpecValue)
                .where(ProductSpecValue.product_id == product_id)
                .order_by(ProductSpecValue.id)
                .execution_options(populate_existing=True)
            )
        )

    async def descriptions(self, product_id: UUID) -> list[ProductAttributeValue]:
        return list(
            await self.session.scalars(
                select(ProductAttributeValue)
                .where(ProductAttributeValue.product_id == product_id)
                .execution_options(populate_existing=True)
            )
        )

    async def sku_selections(self, product_id: UUID) -> list[ProductSkuSpecValue]:
        return list(
            await self.session.scalars(
                select(ProductSkuSpecValue)
                .where(ProductSkuSpecValue.product_id == product_id)
                .order_by(ProductSkuSpecValue.sku_id, ProductSkuSpecValue.adoption_id)
            )
        )
