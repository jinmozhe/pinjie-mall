"""商城基础账户初始化；只在已授权建号或登录事务内调用，无手机号前置。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.distribution import DistributionService
from app.domains.points import PointsService


class CustomerAccountsService:
    def __init__(self, session: AsyncSession) -> None:
        self.points = PointsService(session=session)
        self.distribution = DistributionService(session)

    async def initialize_in_open_transaction(self, user_id: UUID) -> None:
        # 与积分调整的 points -> member_profile 锁顺序一致，防止登录与积分入账互锁。
        await self.points.initialize_account_in_open_transaction(user_id)
        await self.distribution.initialize_accounts_in_open_transaction(user_id)
