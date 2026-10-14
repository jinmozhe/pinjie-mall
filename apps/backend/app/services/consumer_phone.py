from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.rate_limit import enforce_rate_limit
from app.core.security import token_digest
from app.db.repositories import SecurityRepository
from app.db.transaction import transaction_scope
from app.domains.auth.schemas import ConsumerUserRead
from app.services.consumer_auth import ConsumerAuthService, bearer_error
from app.services.security_events import login_event
from app.services.wechat_phone import WechatPhoneClient


class ConsumerPhoneService:
    def __init__(self, auth: ConsumerAuthService) -> None:
        self.auth = auth

    async def bind(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        credential_version: int,
        code: str,
    ) -> ConsumerUserRead:
        """Complete this account only. Network exchange never holds a database transaction."""
        auth = self.auth
        _, hmac_key = auth.settings.miniapp_secrets()
        app_id = auth.settings.wechat_app_id
        if not auth.settings.miniapp_login_enabled or app_id is None:
            raise AppException(status_code=503, code=ErrorCode.SERVICE_UNAVAILABLE, message="微信登录尚未开放")
        await enforce_rate_limit(
            auth.redis,
            key=auth.keys.miniapp("phone-user", token_digest(str(user_id), hmac_key)),
            limit=10,
            window_seconds=300,
        )
        binding = await auth.identities.for_user(user_id, app_id)
        if binding is None:
            raise bearer_error()
        openid = binding.subject_id
        # Dependency authentication opened a read transaction. Release it before external I/O.
        await auth.session.rollback()
        phone = await WechatPhoneClient(auth.settings, auth.redis, auth.http).exchange(code, openid)
        try:
            async with transaction_scope(auth.session):
                await auth.users.lock_phone(phone)
                user = await auth.users.get(user_id, for_update=True)
                current = await auth.sessions.get_web(session_id, for_update=True)
                now = datetime.now(UTC)
                if (
                    user is None
                    or current is None
                    or current.user_id != user_id
                    or current.credential_profile != "miniapp_bearer"
                    or current.client_id != "pinjie-miniapp"
                    or current.csrf_digest is not None
                    or current.revoked_at is not None
                    or current.idle_expires_at <= now
                    or current.absolute_expires_at <= now
                    or user.credential_version != credential_version
                ):
                    raise bearer_error()
                if not user.is_active or user.deleted_at is not None:
                    raise AppException(status_code=403, code=ErrorCode.AUTH_ACCOUNT_DISABLED, message="账户已停用")
                if user.phone_e164 is not None and user.phone_e164 != phone:
                    raise AppException(
                        status_code=409,
                        code=ErrorCode.PHONE_BINDING_CONFLICT,
                        message="账户已绑定手机号，本入口不支持换绑",
                    )
                owner = await auth.users.get_by_phone(phone)
                if owner is not None and owner.id != user_id:
                    raise AppException(
                        status_code=409, code=ErrorCode.PHONE_BINDING_CONFLICT, message="手机号绑定冲突，请联系运营核实"
                    )
                if not user.phone_bound:
                    user.phone_e164, user.phone_verified_at = phone, now
                    user.phone_verification_source = "wechat_phone_quick"
                SecurityRepository(auth.session).add_login_event(
                    login_event(
                        principal_type="user",
                        principal_id=user_id,
                        identifier_digest=None,
                        event_type="miniapp_phone_bound",
                        succeeded=True,
                        reason_code="PHONE_VERIFIED",
                        metadata=auth.metadata,
                    )
                )
                result = ConsumerUserRead.model_validate(user)
            return result
        except IntegrityError:
            raise AppException(
                status_code=409, code=ErrorCode.PHONE_BINDING_CONFLICT, message="手机号绑定冲突，请查询当前状态"
            ) from None
