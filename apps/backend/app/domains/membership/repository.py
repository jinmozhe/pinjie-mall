from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    MemberLevel,
    MemberLevelCondition,
    MemberLevelEvent,
    MemberPriceRule,
    MemberProfile,
    MembershipQualificationEvent,
    SystemSetting,
)
from app.db.models.product import Category, Product, ProductSku


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def level(self, level_id: UUID, *, for_update: bool = False) -> MemberLevel | None:
        statement = select(MemberLevel).where(MemberLevel.id == level_id).execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def levels_page(self, page: int, page_size: int) -> tuple[list[MemberLevel], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(MemberLevel)) or 0)
        rows = await self.session.scalars(
            select(MemberLevel)
            .order_by(MemberLevel.sort_order.asc().nulls_last(), MemberLevel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def active_levels(self) -> list[MemberLevel]:
        return list(
            await self.session.scalars(
                select(MemberLevel)
                .where(MemberLevel.is_active.is_(True))
                .order_by(MemberLevel.level_rank.desc(), MemberLevel.id)
            )
        )

    async def condition(self, condition_id: UUID, *, for_update: bool = False) -> MemberLevelCondition | None:
        statement = (
            select(MemberLevelCondition)
            .where(MemberLevelCondition.id == condition_id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def conditions_page(self, page: int, page_size: int) -> tuple[list[MemberLevelCondition], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(MemberLevelCondition)) or 0)
        rows = await self.session.scalars(
            select(MemberLevelCondition)
            .order_by(MemberLevelCondition.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def conditions_for_levels(self, level_ids: list[UUID], now: datetime) -> list[MemberLevelCondition]:
        if not level_ids:
            return []
        return list(
            await self.session.scalars(
                select(MemberLevelCondition).where(
                    MemberLevelCondition.level_id.in_(level_ids),
                    MemberLevelCondition.is_active.is_(True),
                    MemberLevelCondition.effective_at <= now,
                )
            )
        )

    async def qualification_event(
        self, event_id: UUID, *, for_update: bool = False
    ) -> MembershipQualificationEvent | None:
        statement = (
            select(MembershipQualificationEvent)
            .where(MembershipQualificationEvent.id == event_id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def qualification_by_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> MembershipQualificationEvent | None:
        statement = (
            select(MembershipQualificationEvent)
            .where(MembershipQualificationEvent.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def qualification_by_source(
        self, *, user_id: UUID, metric: str, source_type: str, source_id: UUID, for_update: bool = False
    ) -> MembershipQualificationEvent | None:
        statement = (
            select(MembershipQualificationEvent)
            .where(
                MembershipQualificationEvent.user_id == user_id,
                MembershipQualificationEvent.metric == metric,
                MembershipQualificationEvent.source_type == source_type,
                MembershipQualificationEvent.source_id == source_id,
            )
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def qualification_events(
        self, user_id: UUID, metric: str | None = None
    ) -> list[MembershipQualificationEvent]:
        statement = select(MembershipQualificationEvent).where(MembershipQualificationEvent.user_id == user_id)
        if metric is not None:
            statement = statement.where(MembershipQualificationEvent.metric == metric)
        return list(await self.session.scalars(statement.order_by(MembershipQualificationEvent.id)))

    async def qualification_events_page(
        self, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[MembershipQualificationEvent], int]:
        predicate = MembershipQualificationEvent.user_id == user_id
        total = int(
            await self.session.scalar(select(func.count()).select_from(MembershipQualificationEvent).where(predicate))
            or 0
        )
        rows = await self.session.scalars(
            select(MembershipQualificationEvent)
            .where(predicate)
            .order_by(MembershipQualificationEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def level_events_page(self, user_id: UUID, page: int, page_size: int) -> tuple[list[MemberLevelEvent], int]:
        predicate = MemberLevelEvent.user_id == user_id
        total = int(await self.session.scalar(select(func.count()).select_from(MemberLevelEvent).where(predicate)) or 0)
        rows = await self.session.scalars(
            select(MemberLevelEvent)
            .where(predicate)
            .order_by(MemberLevelEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def price_rule(self, rule_id: UUID, *, for_update: bool = False) -> MemberPriceRule | None:
        statement = (
            select(MemberPriceRule).where(MemberPriceRule.id == rule_id).execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def price_rules_page(self, page: int, page_size: int) -> tuple[list[MemberPriceRule], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(MemberPriceRule)) or 0)
        rows = await self.session.scalars(
            select(MemberPriceRule).order_by(MemberPriceRule.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), total

    async def profile(self, user_id: UUID, *, for_update: bool = False) -> MemberProfile | None:
        statement = (
            select(MemberProfile).where(MemberProfile.user_id == user_id).execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def sku_catalog(self, sku_ids: list[UUID]) -> list[tuple[ProductSku, Product]]:
        rows = await self.session.execute(
            select(ProductSku, Product)
            .join(Product, Product.id == ProductSku.product_id)
            .where(ProductSku.id.in_(sku_ids))
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def categories(self) -> list[Category]:
        return list(await self.session.scalars(select(Category)))

    async def active_rules(self, level_id: UUID) -> list[MemberPriceRule]:
        return list(
            await self.session.scalars(
                select(MemberPriceRule).where(
                    MemberPriceRule.member_level_id == level_id, MemberPriceRule.is_active.is_(True)
                )
            )
        )

    async def setting(self, group: str, *, for_update: bool = False) -> SystemSetting | None:
        statement = (
            select(SystemSetting).where(SystemSetting.setting_group == group).execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def flush(self) -> None:
        await self.session.flush()


__all__ = ["MembershipRepository"]
