import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.pagination import PageResult
from app.core.password_policy import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.domains.auth.schemas import normalize_username

_ROLE_CODE = re.compile(r"^[a-z][a-z0-9_-]{2,99}$")


class ConfirmationAction(StrEnum):
    USER_DISABLE = "users:disable"
    USER_PASSWORD_RESET = "users:credentials:reset"
    USER_SESSION_REVOKE = "users:sessions:revoke"
    ADMIN_CREATE = "admins:create"
    ADMIN_SUPERUSER_CHANGE = "admins:superuser:change"
    ADMIN_STATUS_CHANGE = "admins:status:change"
    ADMIN_PASSWORD_RESET = "admins:credentials:reset"
    ADMIN_ROLES_ASSIGN = "admins:roles:assign"
    ADMIN_SESSIONS_REVOKE = "admins:sessions:revoke"
    ROLE_DELETE = "roles:delete"
    ROLE_PERMISSIONS_ASSIGN = "roles:permissions:assign"
    ASSET_DELETE = "assets:delete"


class AdminLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH, description="登录密码，最多 64 个字符")

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_username(value)


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    code: str
    name: str


class AdminRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    username: str
    display_name: str | None
    avatar: str | None = Field(default=None, description="管理员头像 URL 或站内资源路径")
    is_active: bool
    is_superuser: bool
    roles: list[RoleSummary]
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class AdminAuthSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal: AdminRead
    session_id: uuid.UUID
    access_expires_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime


class AdminConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(
        min_length=1,
        max_length=PASSWORD_MAX_LENGTH,
        description="当前管理员密码，最多 64 个字符",
    )
    action: ConfirmationAction = Field(description="旧客户端声明的敏感操作类型")


class AdminConfirmOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_token: str = Field(description="旧客户端兼容确认回执，不作为后续操作授权凭据")
    action: ConfirmationAction = Field(description="旧客户端声明的敏感操作类型")
    expires_at: datetime = Field(description="兼容确认回执的客户端有效期提示")


class AdminCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    initial_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="初始密码，长度为 6 至 64 个字符",
    )
    display_name: str | None = Field(default=None, max_length=100)
    is_active: bool = True
    is_superuser: bool = False
    role_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_username(value)


class AdminUserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(description="普通用户登录用户名，长度为 3 至 50 个字符")
    initial_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="初始密码，长度为 6 至 64 个字符",
    )
    display_name: str | None = Field(default=None, max_length=100, description="用户显示名称")
    email: str | None = Field(default=None, max_length=320, description="用户邮箱，保存时规范化为小写")
    is_active: bool = Field(default=True, description="是否允许用户登录")

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        normalized = value.strip().lower() if value else None
        return normalized or None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None


class AdminUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=100)
    avatar: str | None = Field(default=None, max_length=500, description="管理员头像 URL 或站内资源路径")

    @model_validator(mode="after")
    def require_explicit_field(self) -> "AdminUpdateIn":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class AdminSuperuserUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_superuser: bool = Field(description="是否授予目标管理员超级管理员身份")


class AdminProfileUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=100)
    avatar: str | None = Field(default=None, max_length=500, description="管理员头像 URL 或站内资源路径")

    @model_validator(mode="after")
    def require_explicit_field(self) -> "AdminProfileUpdateIn":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class StatusUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class AdminBulkStatusUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admin_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=100,
        description="待批量更新状态的管理员唯一标识列表",
    )
    is_active: bool

    @field_validator("admin_ids")
    @classmethod
    def validate_unique_admin_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("admin_ids must be unique")
        return value


class _UserBulkTargetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=100,
        description="待批量操作的用户唯一标识列表",
    )

    @field_validator("user_ids")
    @classmethod
    def validate_unique_user_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("user_ids must be unique")
        return value


class UserBulkDeleteIn(_UserBulkTargetIn):
    deletion_reason: str | None = Field(default=None, max_length=100, description="软删除原因，可为空")

    @field_validator("deletion_reason")
    @classmethod
    def normalize_deletion_reason(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None


class UserBulkStatusUpdateIn(_UserBulkTargetIn):
    is_active: bool = Field(description="批量操作后的用户启用状态")


class UserRestoreBatchIn(_UserBulkTargetIn):
    pass


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    username: str
    display_name: str | None
    email: str | None
    avatar: str | None = Field(default=None, description="用户头像站内资源路径")
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = Field(description="账户进入回收站的时间")
    deleted_by_id: uuid.UUID | None = Field(description="执行软删除的主体唯一标识")
    deleted_by_type: str | None = Field(description="执行软删除的主体类型")
    deletion_reason: str | None = Field(description="账户删除原因代码")
    can_restore: bool = Field(description="当前是否允许恢复")


class RoleBulkDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=100,
        description="待批量操作的角色唯一标识列表",
    )

    @field_validator("role_ids")
    @classmethod
    def validate_unique_role_ids(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) != len(set(value)):
            raise ValueError("role_ids must be unique")
        return value


class RoleBulkStatusUpdateIn(RoleBulkDeleteIn):
    is_active: bool = Field(description="批量操作后的角色启用状态")


class BatchActionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed_count: int = Field(ge=0, description="本次批量操作完成的目标数量")
    target_ids: list[uuid.UUID] = Field(description="本次批量操作处理的目标唯一标识列表")


class PasswordResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="新密码，长度为 6 至 64 个字符",
    )


class AdminRoleAssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_ids: list[uuid.UUID]


class RoleCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _ROLE_CODE.fullmatch(normalized):
            raise ValueError("invalid role code")
        return normalized


class RoleUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_explicit_field(self) -> "RoleUpdateIn":
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        return self


class RolePermissionAssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permission_codes: list[str]


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    catalog_version: str
    assignable_to_roles: bool = Field(description="该权限是否允许分配给普通角色")


class RoleRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class LoginEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    principal_type: str
    principal_id: uuid.UUID | None
    event_type: str
    succeeded: bool
    reason_code: str
    ip_address: str | None
    user_agent_summary: str | None
    request_id: str
    occurred_at: datetime


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_type: str
    action: str
    target_type: str
    target_id: uuid.UUID | None
    target_revision: int | None
    result: str
    changed_fields: dict[str, object]
    request_id: str
    occurred_at: datetime
    completed_at: datetime | None


class RequestLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    request_id: str
    trace_id: str
    method: str
    route_template: str
    status_code: int
    duration_ms: int
    principal_type: str | None
    release_version: str | None
    occurred_at: datetime
    request_body: str | None


AdminPage = PageResult[AdminRead]
RolePage = PageResult[RoleRead]
LoginEventPage = PageResult[LoginEventRead]
AuditEventPage = PageResult[AuditEventRead]
RequestLogPage = PageResult[RequestLogRead]
UserPage = PageResult[AdminUserRead]


class DatabaseHealthRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable", "mismatch", "timeout"] = Field(description="数据库连接和迁移状态")
    latency_ms: float = Field(description="探测往返耗时（毫秒）")
    details: str = Field(description="诊断详情，如 migration_heads_matched 或错误原因")


class RedisHealthRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable", "disabled"] = Field(description="Redis 连接状态")
    latency_ms: float = Field(description="探测往返耗时（毫秒）")
    mode: Literal["required", "disabled"] = Field(description="Redis 运行模式")


class StorageConfigurationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver: Literal["local"] = Field(description="存储驱动名称")
    public_base_url: str = Field(description="文件公开访问根路径")


class SecurityConfigurationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_isolation: Literal["separate_cookie_profiles"] = Field(description="C/B 端会话隔离策略")
    csrf_strategy: Literal["double_submit_hmac"] = Field(description="CSRF 校验策略")
    refresh_rotation: Literal["single_use_rotation"] = Field(description="Refresh Token 轮换策略")


class InfrastructureOverviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database: DatabaseHealthRead = Field(description="PostgreSQL 实时健康探针结果")
    redis: RedisHealthRead = Field(description="Redis 实时健康探针结果")
    storage: StorageConfigurationRead = Field(description="文件存储公开配置摘要")
    security: SecurityConfigurationRead = Field(description="认证与会话安全机制摘要")


class SystemTelemetryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable"] = Field(description="业务遥测采样状态")
    sampled_at: datetime = Field(description="业务遥测数据采样时间")
    source: Literal["database", "redis_cache", "unavailable"] = Field(description="业务遥测数据来源")
    user_count: int | None = Field(description="未进入回收站的普通用户数")
    admin_count: int | None = Field(description="启用管理员数")
    role_count: int | None = Field(description="启用角色数")
    asset_count: int | None = Field(description="现存文件资产记录数")
    audit_event_count: int | None = Field(description="保留期内现存安全审计事件数")
    cached: bool = Field(default=False, description="统计数据是否命中 Redis 缓存")


class SystemOverviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "degraded", "unavailable"] = Field(description="系统综合健康状态")
    started_at: datetime = Field(description="服务启动时间")
    uptime_seconds: int = Field(description="服务已稳定运行时长（秒）")
    environment: Literal["local", "test", "production"] = Field(description="部署运行环境")
    release_version: str = Field(description="系统发行版本号")
    python_version: str = Field(description="当前 CPython 运行时版本")
    fastapi_version: str = Field(description="当前 FastAPI 运行时版本")
    timezone: str = Field(description="服务器基准时区")
    cors_origin_count: int = Field(description="已配置的受信任跨域来源数量")
    infrastructure: InfrastructureOverviewRead = Field(description="基础设施健康与公开配置摘要")
    telemetry: SystemTelemetryRead = Field(description="业务资产统计遥测结果")


__all__ = [
    "AdminAuthSessionOut",
    "AdminBulkStatusUpdateIn",
    "AdminConfirmIn",
    "AdminConfirmOut",
    "AdminCreateIn",
    "AdminLoginIn",
    "AdminPage",
    "AdminProfileUpdateIn",
    "AdminRead",
    "AdminRoleAssignIn",
    "AdminSuperuserUpdateIn",
    "AdminUpdateIn",
    "AdminUserCreateIn",
    "AdminUserRead",
    "AuditEventPage",
    "AuditEventRead",
    "BatchActionResult",
    "ConfirmationAction",
    "DatabaseHealthRead",
    "InfrastructureOverviewRead",
    "LoginEventPage",
    "LoginEventRead",
    "PasswordResetIn",
    "PermissionRead",
    "RedisHealthRead",
    "RoleCreateIn",
    "RoleBulkDeleteIn",
    "RoleBulkStatusUpdateIn",
    "RolePage",
    "RolePermissionAssignIn",
    "RoleRead",
    "RoleSummary",
    "RoleUpdateIn",
    "StatusUpdateIn",
    "SecurityConfigurationRead",
    "StorageConfigurationRead",
    "SystemOverviewRead",
    "SystemTelemetryRead",
    "RequestLogPage",
    "RequestLogRead",
    "UserPage",
    "UserBulkDeleteIn",
    "UserBulkStatusUpdateIn",
    "UserRestoreBatchIn",
]
