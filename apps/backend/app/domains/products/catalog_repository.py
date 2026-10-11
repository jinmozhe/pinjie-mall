from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset
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


@dataclass
class CatalogSnapshot:
    adoptions: dict[UUID, list[ProductSpecAttribute]] = field(default_factory=dict)
    candidates: dict[UUID, list[ProductSpecValue]] = field(default_factory=dict)
    descriptions: dict[UUID, list[ProductAttributeValue]] = field(default_factory=dict)
    selections: dict[UUID, list[ProductSkuSpecValue]] = field(default_factory=dict)
    active_attributes: set[UUID] = field(default_factory=set)
    active_values: set[UUID] = field(default_factory=set)


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_entity(self, row: Base) -> None:
        self.session.add(row)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def catalog_snapshot(self, product_ids: list[UUID]) -> CatalogSnapshot:
        snapshot = CatalogSnapshot()
        if not product_ids:
            return snapshot
        for adoption in await self.session.scalars(
            select(ProductSpecAttribute)
            .where(ProductSpecAttribute.product_id.in_(product_ids))
            .order_by(ProductSpecAttribute.id)
            .execution_options(populate_existing=True)
        ):
            snapshot.adoptions.setdefault(adoption.product_id, []).append(adoption)
        for candidate in await self.session.scalars(
            select(ProductSpecValue)
            .where(ProductSpecValue.product_id.in_(product_ids))
            .order_by(ProductSpecValue.id)
            .execution_options(populate_existing=True)
        ):
            snapshot.candidates.setdefault(candidate.product_id, []).append(candidate)
        for description in await self.session.scalars(
            select(ProductAttributeValue)
            .where(ProductAttributeValue.product_id.in_(product_ids))
            .execution_options(populate_existing=True)
        ):
            snapshot.descriptions.setdefault(description.product_id, []).append(description)
        for selection in await self.session.scalars(
            select(ProductSkuSpecValue)
            .where(ProductSkuSpecValue.product_id.in_(product_ids))
            .order_by(ProductSkuSpecValue.sku_id, ProductSkuSpecValue.adoption_id)
        ):
            snapshot.selections.setdefault(selection.product_id, []).append(selection)
        attribute_ids = {
            row.attribute_id for rows in snapshot.adoptions.values() for row in rows if row.attribute_id is not None
        }
        value_ids = {row.value_id for rows in snapshot.candidates.values() for row in rows if row.value_id is not None}
        if attribute_ids:
            snapshot.active_attributes = set(
                await self.session.scalars(
                    select(SpecAttribute.id).where(
                        SpecAttribute.id.in_(attribute_ids), SpecAttribute.is_active.is_(True)
                    )
                )
            )
        if value_ids:
            snapshot.active_values = set(
                await self.session.scalars(
                    select(SpecAttributeValue.id).where(
                        SpecAttributeValue.id.in_(value_ids), SpecAttributeValue.is_active.is_(True)
                    )
                )
            )
        return snapshot

    async def brand(self, brand_id: UUID) -> Brand | None:
        return (
            await self.session.scalars(
                select(Brand).where(Brand.id == brand_id).execution_options(populate_existing=True)
            )
        ).one_or_none()

    async def asset_url(self, asset_id: UUID | None) -> str | None:
        if asset_id is None:
            return None
        return cast(str | None, await self.session.scalar(select(Asset.url).where(Asset.id == asset_id)))

    async def brand_page(self, page: int, page_size: int) -> tuple[list[tuple[Brand, str | None]], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(Brand)) or 0)
        statement = (
            select(Brand, Asset.url)
            .outerjoin(Asset, Brand.logo_asset_id == Asset.id)
            .order_by(Brand.sort_order.asc().nulls_last(), Brand.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(statement)).all()
        return [(row[0], row[1]) for row in rows], total

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

    async def count_standard_value_adoptions(self, value_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(ProductSpecValue).where(ProductSpecValue.value_id == value_id)
            )
            or 0
        )

    async def delete_standard_value(self, row: SpecAttributeValue) -> None:
        await self.session.delete(row)
        await self.session.flush()

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
