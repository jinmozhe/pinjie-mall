"""Admin 只读查询模型：直接读取已提交商城事实，不参与领域写入。

列表按创建时间与主键稳定排序，刷新时重读 PostgreSQL；分页计数为读已提交隔离。
精确资源权限由 Router 声明；导出另需资源 export 权限并仅返回白名单 Schema。
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import PageResult
from app.db.models.base import Base
from app.db.models.commerce_lifecycle import PaymentAttempt, ReconciliationRecord, RefundRequest
from app.db.models.distribution import CommissionRecord, MemberProfile, WalletAccount, WalletLedger, WithdrawalRequest
from app.db.models.order import Order
from app.domains.distribution import CommissionRead, MemberProfileRead, WalletAccountRead, WithdrawalRead
from app.domains.lifecycle import PaymentAttemptRead, ReconciliationRecordRead, RefundRequestRead
from app.domains.orders.schemas import AdminOrderSummary
from app.services.security_events import AuditCoordinator


class AdminWalletRead(WalletAccountRead):
    id: UUID = Field(description="钱包账户标识")
    user_id: UUID = Field(description="账户所属会员标识")


class WalletLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="流水标识")
    wallet_id: UUID = Field(description="钱包标识")
    entry_type: str = Field(description="资金变动类型")
    amount: Decimal = Field(description="可用余额变化")
    frozen_delta: Decimal = Field(description="冻结余额变化")
    debt_delta: Decimal = Field(description="欠款变化")
    reference_type: str = Field(description="关联业务类型")
    reference_id: UUID = Field(description="关联业务标识")
    wallet_revision: int = Field(description="变动后钱包版本")
    balance_after: dict[str, object] = Field(description="变动后余额快照")
    created_at: datetime = Field(description="入账时间")


class CommerceFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")
    record_id: UUID | None = Field(default=None, description="记录标识，会员列表使用用户标识")
    user_id: UUID | None = Field(default=None, description="用户标识，佣金列表使用受益人标识")
    order_id: UUID | None = Field(default=None, description="订单标识")
    inviter_id: UUID | None = Field(default=None, description="直接推荐人标识")
    status: str | None = Field(default=None, min_length=1, max_length=32, description="状态代码")
    channel: Literal["wechat", "alipay"] | None = Field(default=None, description="支付渠道")
    product_type: Literal["physical", "virtual"] | None = Field(default=None, description="商品类型")
    wallet_type: Literal["commission", "consumption"] | None = Field(default=None, description="钱包轨道")


class SelectedCommerceIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(min_length=1, max_length=100, description="一至一百条选中记录，会员使用用户标识")

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("选中记录不能重复")
        return self


class CommerceExportRead(BaseModel):
    columns: list[str] = Field(description="白名单字段名称")
    rows: list[list[str]] = Field(description="按字段顺序序列化的记录，金额保留精度")


# 显式模型与输出白名单，禁止用户指定任意表、字段或 SQL。
_RESOURCES: dict[str, tuple[type[Base], type[BaseModel]]] = {
    "orders": (Order, AdminOrderSummary),
    "refunds": (RefundRequest, RefundRequestRead),
    "withdrawals": (WithdrawalRequest, WithdrawalRead),
    "payments": (PaymentAttempt, PaymentAttemptRead),
    "reconciliation-records": (ReconciliationRecord, ReconciliationRecordRead),
    "members": (MemberProfile, MemberProfileRead),
    "commissions": (CommissionRecord, CommissionRead),
    "wallets": (WalletAccount, AdminWalletRead),
}
_FILTERS = {
    "orders": {"user_id": "user_id", "status": "status", "product_type": "product_type"},
    "refunds": {"user_id": "user_id", "order_id": "order_id", "status": "status"},
    "withdrawals": {"user_id": "user_id", "status": "status"},
    "payments": {"user_id": "user_id", "order_id": "order_id", "status": "status", "channel": "channel"},
    "reconciliation-records": {"status": "status", "channel": "channel"},
    "members": {"user_id": "user_id", "inviter_id": "inviter_id"},
    "commissions": {"user_id": "beneficiary_user_id", "order_id": "order_id", "status": "status"},
    "wallets": {"user_id": "user_id", "wallet_type": "wallet_type"},
}


class CommerceReportingService:
    def __init__(self, session: AsyncSession, audit: AuditCoordinator) -> None:
        self.session = session
        self.audit = audit

    async def page[T: BaseModel](self, resource: str, schema: type[T], filters: CommerceFilters) -> PageResult[T]:
        if resource not in _RESOURCES:
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="不支持的查询资源类型")
        model, expected_schema = _RESOURCES[resource]
        if schema is not expected_schema:
            raise ValueError("查询输出契约不匹配")
        predicates: list[ColumnElement[bool]] = []
        for name, value in filters.model_dump(exclude_none=True).items():
            if name in {"page", "page_size"}:
                continue
            column = (
                ("user_id" if resource == "members" else "id") if name == "record_id" else _FILTERS[resource].get(name)
            )
            if column is None:
                raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="此列表不支持该筛选条件")
            predicates.append(getattr(model, column) == value)
        total = int(await self.session.scalar(select(func.count()).select_from(model).where(*predicates)) or 0)
        rows = await self.session.scalars(
            select(model)
            .where(*predicates)
            .order_by(getattr(model, "created_at").desc(), getattr(model, "id").desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        return PageResult[T].create(
            items=[schema.model_validate(row) for row in rows],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def export(self, resource: str, selection: SelectedCommerceIds) -> CommerceExportRead:
        async def operation() -> CommerceExportRead:
            model, schema = _RESOURCES[resource]
            key = getattr(model, "user_id" if resource == "members" else "id")
            rows = list(await self.session.scalars(select(model).where(key.in_(selection.ids)).order_by(key)))
            if len(rows) != len(selection.ids):
                raise AppException(
                    status_code=409, code=ErrorCode.STATE_CONFLICT, message="部分选中记录已不存在，请刷新后重新选择"
                )
            columns = list(schema.model_fields)
            values = [schema.model_validate(row).model_dump(mode="json") for row in rows]
            return CommerceExportRead(
                columns=columns, rows=[["" if row[c] is None else str(row[c]) for c in columns] for row in values]
            )

        return await self.audit.execute(
            action=f"commerce.{resource}.export",
            target_type=resource,
            target_id=None,
            changed_fields={"record_ids": [str(item) for item in selection.ids], "record_count": len(selection.ids)},
            operation=operation,
        )

    async def ledgers(self, wallet_id: UUID, page: int, page_size: int) -> PageResult[WalletLedgerRead]:
        if await self.session.get(WalletAccount, wallet_id) is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="钱包不存在")
        predicate = WalletLedger.wallet_id == wallet_id
        total = int(await self.session.scalar(select(func.count()).select_from(WalletLedger).where(predicate)) or 0)
        rows = await self.session.scalars(
            select(WalletLedger)
            .where(predicate)
            .order_by(WalletLedger.created_at.desc(), WalletLedger.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return PageResult[WalletLedgerRead].create(
            items=[WalletLedgerRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )
