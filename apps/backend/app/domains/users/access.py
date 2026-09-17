from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.repositories.commerce_access import CommerceAccessRepository


class UserAccessService:
    """用户写用例的权威状态校验；调用方拥有事务，用户行锁持有至事务结束。"""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = CommerceAccessRepository(session)

    async def require_active_user(self, user_id: UUID) -> None:
        user = await self.repository.get_user_for_update(user_id)
        if user is None or not user.is_active or user.deleted_at is not None:
            raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="用户已停用")
