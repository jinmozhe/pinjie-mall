import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

admin_roles = Table(
    "admin_roles",
    Base.metadata,
    Column("admin_id", ForeignKey("admins.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    comment="管理员与角色关联",
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="RESTRICT"), primary_key=True),
    comment="角色与权限关联",
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("credential_version >= 1", name="ck_users_credential_version_positive"),
        CheckConstraint(
            "(deleted_at IS NULL AND deleted_by_id IS NULL AND deleted_by_type IS NULL) "
            "OR (deleted_at IS NOT NULL AND deleted_by_id IS NOT NULL AND deleted_by_type IS NOT NULL)",
            name="ck_users_soft_delete_actor_consistency",
        ),
        CheckConstraint(
            "deleted_by_type IS NULL OR deleted_by_type IN ('admin', 'user', 'system')",
            name="ck_users_soft_delete_actor_type",
        ),
        Index("ix_users_active_created", "is_active", "created_at"),
        {"comment": "C 端用户账户"},
    )

    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, comment="规范化用户名")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True, comment="未验证可选邮箱")
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="展示名称")
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="用户头像站内资源路径")
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Argon2id 密码摘要；仅外部身份用户可为空"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否允许登录")
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="凭据版本")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("credential_profile = 'browser_cookie'", name="ck_user_sessions_profile"),
        CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_user_sessions_expiry_order"),
        Index("ix_user_sessions_user_active", "user_id", "revoked_at", "absolute_expires_at"),
        {"comment": "C 端登录会话权威记录"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="用户 ID"
    )
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True, comment="Refresh Token 族 ID")
    credential_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="browser_cookie")
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, default="pinjie-web")
    csrf_digest: Mapped[str] = mapped_column(String(64), nullable=False, comment="CSRF Token HMAC")
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True, comment="可信客户端 IP")
    user_agent_summary: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="清理后的 UA 摘要")
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="设备展示名称")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
    refresh_tokens: Mapped[list["UserRefreshToken"]] = relationship(
        back_populates="session", foreign_keys="UserRefreshToken.session_id", cascade="all, delete-orphan"
    )


class UserRefreshToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_refresh_tokens"
    __table_args__ = (
        Index("ix_user_refresh_session_state", "session_id", "consumed_at", "revoked_at"),
        {"comment": "C 端 Refresh Token 单次消费记录"},
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="Token HMAC")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )

    session: Mapped[UserSession] = relationship(back_populates="refresh_tokens", foreign_keys=[session_id])


class UserExternalIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "app_id", "subject_id", name="uq_user_external_identity_subject"),
        UniqueConstraint("user_id", "provider", "app_id", name="uq_user_external_identity_user_provider"),
        Index("ix_user_external_identity_user", "user_id"),
        CheckConstraint("provider = 'wechat'", name="ck_user_external_identity_provider"),
        {"comment": "可信外部身份与商城用户的不可变绑定"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="商城用户"
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="wechat", comment="外部身份提供方")
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="服务端登记的平台应用标识")
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="可信 OpenID")
    union_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="可信返回的 UnionID，仅记录不合并")


class Admin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admins"
    __table_args__ = (
        CheckConstraint("credential_version >= 1", name="ck_admins_credential_version_positive"),
        Index("ix_admins_active_created", "is_active", "created_at"),
        {"comment": "B 端管理员账户"},
    )

    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="管理员头像 URL 或路径")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    roles: Mapped[list["Role"]] = relationship(secondary=admin_roles, back_populates="admins", lazy="selectin")
    sessions: Mapped[list["AdminSession"]] = relationship(back_populates="admin", cascade="all, delete-orphan")


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = ({"comment": "管理员角色"},)

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, comment="稳定角色代码")
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    admins: Mapped[list[Admin]] = relationship(secondary=admin_roles, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = ({"comment": "源码权限目录数据库映射"},)

    code: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)

    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")


class AdminSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        CheckConstraint("credential_profile = 'browser_cookie'", name="ck_admin_sessions_profile"),
        CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_admin_sessions_expiry_order"),
        Index("ix_admin_sessions_admin_active", "admin_id", "revoked_at", "absolute_expires_at"),
        {"comment": "B 端管理员登录会话权威记录"},
    )

    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False, comment="管理员 ID"
    )
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    credential_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="browser_cookie")
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, default="pinjie-admin")
    csrf_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    admin: Mapped[Admin] = relationship(back_populates="sessions")
    refresh_tokens: Mapped[list["AdminRefreshToken"]] = relationship(
        back_populates="session", foreign_keys="AdminRefreshToken.session_id", cascade="all, delete-orphan"
    )


class AdminRefreshToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "admin_refresh_tokens"
    __table_args__ = (
        Index("ix_admin_refresh_session_state", "session_id", "consumed_at", "revoked_at"),
        {"comment": "B 端 Refresh Token 单次消费记录"},
    )

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin_sessions.id", ondelete="CASCADE"), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )

    session: Mapped[AdminSession] = relationship(back_populates="refresh_tokens", foreign_keys=[session_id])


class SecurityLoginEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "security_login_events"
    __table_args__ = (
        CheckConstraint("principal_type IN ('user', 'admin')", name="ck_login_events_principal_type"),
        Index("ix_login_events_occurred", "occurred_at"),
        Index("ix_login_events_principal", "principal_type", "principal_id", "occurred_at"),
        {"comment": "登录、刷新和会话安全事件"},
    )

    principal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    principal_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    identifier_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    release_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("result IN ('started', 'succeeded', 'denied', 'failed')", name="ck_audit_events_result"),
        Index("ix_audit_events_occurred", "occurred_at"),
        Index("ix_audit_events_actor_action", "actor_id", "action", "occurred_at"),
        {"comment": "高风险管理操作审计事件"},
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(150), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    changed_fields: Mapped[dict[str, Any]] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    release_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RequestLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "request_logs"
    __table_args__ = (
        CheckConstraint("duration_ms >= 0", name="ck_request_logs_duration_nonnegative"),
        Index("ix_request_logs_occurred", "occurred_at"),
        {"comment": "可选请求元数据日志，仅保存脱敏后的错误请求入参"},
    )

    request_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    route_template: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    principal_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    principal_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    release_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True, comment="脱敏后的错误请求入参")


__all__ = [
    "Admin",
    "AdminRefreshToken",
    "AdminSession",
    "AuditEvent",
    "Permission",
    "RequestLog",
    "Role",
    "SecurityLoginEvent",
    "User",
    "UserRefreshToken",
    "UserSession",
    "admin_roles",
    "role_permissions",
]
