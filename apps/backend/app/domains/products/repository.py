from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models.asset import Asset
from app.db.models.product import Category, Product, ProductImage, ProductSku


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_catalog(self) -> None:
        await self.session.execute(text("SELECT pg_advisory_xact_lock(722341901)"))

    async def categories(self) -> list[Category]:
        return list(
            await self.session.scalars(
                select(Category).order_by(Category.sort_order, Category.id).execution_options(populate_existing=True)
            )
        )

    async def get(self, product_id: UUID, *, lock: bool = False) -> Product | None:
        stmt = select(Product).where(Product.id == product_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(stmt)).one_or_none()

    async def skus(self, product_id: UUID) -> list[ProductSku]:
        return list(
            await self.session.scalars(
                select(ProductSku)
                .where(ProductSku.product_id == product_id)
                .order_by(ProductSku.created_at, ProductSku.id)
                .execution_options(populate_existing=True)
            )
        )

    async def code_exists(self, code: str, exclude_id: UUID | None = None) -> bool:
        stmt = select(ProductSku.id).where(ProductSku.code == code)
        if exclude_id is not None:
            stmt = stmt.where(ProductSku.id != exclude_id)
        return await self.session.scalar(stmt.limit(1)) is not None

    async def checkout_skus(self, sku_ids: list[UUID]) -> list[tuple[ProductSku, Product]]:
        rows = await self.session.execute(
            select(ProductSku, Product)
            .join(Product, Product.id == ProductSku.product_id)
            .where(ProductSku.id.in_(sku_ids))
            .order_by(ProductSku.id)
            .execution_options(populate_existing=True)
        )
        return [(sku, product) for sku, product in rows.tuples()]

    async def image_ids(self, product_id: UUID) -> list[UUID]:
        return list(
            await self.session.scalars(
                select(ProductImage.asset_id)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.position)
            )
        )

    async def image_urls(self, product_id: UUID) -> list[str]:
        """只读展示查询，不把资产对象用于领域写入。"""
        return list(
            await self.session.scalars(
                select(Asset.url)
                .join(ProductImage, ProductImage.asset_id == Asset.id)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.position)
            )
        )

    async def details(
        self, product_ids: list[UUID]
    ) -> tuple[dict[UUID, list[ProductSku]], dict[UUID, list[UUID]], dict[UUID, list[str]]]:
        skus: dict[UUID, list[ProductSku]] = {key: [] for key in product_ids}
        image_ids: dict[UUID, list[UUID]] = {key: [] for key in product_ids}
        urls: dict[UUID, list[str]] = {key: [] for key in product_ids}
        if not product_ids:
            return skus, image_ids, urls
        variants = await self.session.scalars(
            select(ProductSku)
            .where(ProductSku.product_id.in_(product_ids))
            .order_by(ProductSku.product_id, ProductSku.created_at, ProductSku.id)
        )
        for variant in variants:
            skus[variant.product_id].append(variant)
        images = await self.session.execute(
            select(ProductImage.product_id, ProductImage.asset_id, Asset.url)
            .join(Asset, Asset.id == ProductImage.asset_id)
            .where(ProductImage.product_id.in_(product_ids))
            .order_by(ProductImage.product_id, ProductImage.position)
        )
        for product_id, asset_id, url in images:
            image_ids[product_id].append(asset_id)
            urls[product_id].append(url)
        return skus, image_ids, urls

    async def replace_images(self, product_id: UUID, asset_ids: list[UUID]) -> None:
        await self.session.execute(delete(ProductImage).where(ProductImage.product_id == product_id))
        for position, asset_id in enumerate(asset_ids):
            self.session.add(ProductImage(product_id=product_id, asset_id=asset_id, position=position))
        await self.session.flush()

    async def page(self, page: int, page_size: int, *, public: bool = False) -> tuple[list[Product], int]:
        query = select(Product)
        if public:
            parent = aliased(Category)
            grandparent = aliased(Category)
            query = (
                query.join(Category, Category.id == Product.category_id)
                .outerjoin(parent, parent.id == Category.parent_id)
                .outerjoin(grandparent, grandparent.id == parent.parent_id)
                .where(
                    Product.status == "on_sale",
                    Category.is_active.is_(True),
                    (Category.parent_id.is_(None) | parent.is_active.is_(True)),
                    (parent.parent_id.is_(None) | grandparent.is_active.is_(True)),
                )
            )
        total = int(await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = await self.session.scalars(
            query.order_by(Product.created_at.desc(), Product.id).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), total

    async def save(self, value: Category | Product | ProductSku) -> None:
        self.session.add(value)
        await self.session.flush()
