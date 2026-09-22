from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CommissionAmountRule,
    CommissionDistributionRule,
    CommissionPolicy,
    MemberLevel,
    SystemSetting,
)
from app.db.models.product import Product, ProductSku


class CommissionPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def policy(self, policy_id: UUID, *, lock: bool = False) -> CommissionPolicy | None:
        statement = (
            select(CommissionPolicy).where(CommissionPolicy.id == policy_id).execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def policies_page(self, page: int, page_size: int) -> tuple[list[CommissionPolicy], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(CommissionPolicy)) or 0)
        rows = await self.session.scalars(
            select(CommissionPolicy)
            .order_by(CommissionPolicy.content_version.desc(), CommissionPolicy.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows), total

    async def active_policy(self, *, lock: bool = False) -> CommissionPolicy | None:
        statement = (
            select(CommissionPolicy)
            .where(CommissionPolicy.status == "active")
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def next_content_version(self) -> int:
        return (
            int(await self.session.scalar(select(func.coalesce(func.max(CommissionPolicy.content_version), 0))) or 0)
            + 1
        )

    async def amount_rules(self, policy_id: UUID) -> list[CommissionAmountRule]:
        return list(
            await self.session.scalars(
                select(CommissionAmountRule)
                .where(CommissionAmountRule.policy_id == policy_id)
                .order_by(CommissionAmountRule.id)
            )
        )

    async def amount_rule(self, rule_id: UUID, *, lock: bool = False) -> CommissionAmountRule | None:
        statement = (
            select(CommissionAmountRule)
            .where(CommissionAmountRule.id == rule_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def distribution_rules(self, policy_id: UUID) -> list[CommissionDistributionRule]:
        return list(
            await self.session.scalars(
                select(CommissionDistributionRule)
                .where(CommissionDistributionRule.policy_id == policy_id)
                .order_by(CommissionDistributionRule.ancestor_depth, CommissionDistributionRule.id)
            )
        )

    async def distribution_rule(self, rule_id: UUID, *, lock: bool = False) -> CommissionDistributionRule | None:
        statement = (
            select(CommissionDistributionRule)
            .where(CommissionDistributionRule.id == rule_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def commission_control(self, *, lock: bool = False) -> SystemSetting | None:
        statement = (
            select(SystemSetting)
            .where(SystemSetting.setting_group == "commission_control")
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self.session.scalars(statement)).one_or_none()

    async def level_exists(self, level_id: UUID) -> bool:
        return await self.session.get(MemberLevel, level_id) is not None

    async def product_exists(self, product_id: UUID) -> bool:
        return await self.session.get(Product, product_id) is not None

    async def sku_exists(self, sku_id: UUID) -> bool:
        return await self.session.get(ProductSku, sku_id) is not None

    async def flush(self) -> None:
        await self.session.flush()


__all__ = ["CommissionPolicyRepository"]
