from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models import CommissionAmountRule, CommissionDistributionRule, CommissionPolicy, SystemSetting

from .repository import CommissionPolicyRepository
from .schemas import (
    CommissionAmountRuleCreate,
    CommissionAmountRuleRead,
    CommissionControlRead,
    CommissionControlUpdate,
    CommissionControlValue,
    CommissionDecisionContext,
    CommissionDistributionRuleCreate,
    CommissionDistributionRuleRead,
    CommissionPolicyCreate,
    CommissionPolicyPublish,
    CommissionPolicyRead,
    CommissionPolicyUpdate,
)

T = TypeVar("T")


class AuditExecutor(Protocol):
    async def execute(
        self,
        *,
        action: str,
        target_type: str,
        target_id: UUID | None,
        changed_fields: dict[str, object],
        operation: Callable[[], Awaitable[T]],
    ) -> T: ...


class CommissionPolicyService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        actor_id: UUID | None = None,
        audit: AuditExecutor | None = None,
    ) -> None:
        self._session = session
        self._repository = CommissionPolicyRepository(session)
        self._actor_id = actor_id
        self._audit_coordinator = audit

    async def policies(self, page: int, page_size: int) -> PageResult[CommissionPolicyRead]:
        rows, total = await self._repository.policies_page(page, page_size)
        return PageResult[CommissionPolicyRead].create(
            items=[CommissionPolicyRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def policy(self, policy_id: UUID) -> CommissionPolicyRead:
        return CommissionPolicyRead.model_validate(await self._require_policy(policy_id))

    async def amount_rules(self, policy_id: UUID) -> list[CommissionAmountRuleRead]:
        await self._require_policy(policy_id)
        return [
            CommissionAmountRuleRead.model_validate(item) for item in await self._repository.amount_rules(policy_id)
        ]

    async def distribution_rules(self, policy_id: UUID) -> list[CommissionDistributionRuleRead]:
        await self._require_policy(policy_id)
        return [
            CommissionDistributionRuleRead.model_validate(item)
            for item in await self._repository.distribution_rules(policy_id)
        ]

    async def commission_control(self) -> CommissionControlRead:
        row = await self._require_control()
        return self._control_read(row)

    async def commission_control_in_open_transaction(self) -> tuple[UUID, CommissionControlRead]:
        row = await self._require_control(lock=True)
        return row.id, self._control_read(row)

    async def active_decision_context_in_open_transaction(self) -> CommissionDecisionContext:
        control_row = await self._require_control(lock=True)
        control = self._control_read(control_row)
        policy = await self._repository.active_policy(lock=True)
        if policy is None:
            return CommissionDecisionContext(
                control_id=control_row.id,
                control=control,
                policy=None,
                amount_rules=[],
                distribution_rules=[],
            )
        return CommissionDecisionContext(
            control_id=control_row.id,
            control=control,
            policy=CommissionPolicyRead.model_validate(policy),
            amount_rules=[
                CommissionAmountRuleRead.model_validate(item) for item in await self._repository.amount_rules(policy.id)
            ],
            distribution_rules=[
                CommissionDistributionRuleRead.model_validate(item)
                for item in await self._repository.distribution_rules(policy.id)
            ],
        )

    async def create_policy(self, data: CommissionPolicyCreate) -> CommissionPolicyRead:
        async def operation() -> CommissionPolicyRead:
            await self._require_control(lock=True)
            row = CommissionPolicy(
                id=new_uuid7(),
                name=data.name,
                status="draft",
                default_mode=data.default_mode,
                default_amount_per_unit=data.default_amount_per_unit,
                default_percentage_rate=data.default_percentage_rate,
                max_depth=data.max_depth,
                settle_delay_days=data.settle_delay_days,
                content_version=await self._repository.next_content_version(),
                revision=1,
                updated_by_id=self._require_actor(),
            )
            self._session.add(row)
            await self._repository.flush()
            return CommissionPolicyRead.model_validate(row)

        return await self._audit(
            "commission-policies.create", "commission_policies", None, {"operation": "create"}, operation
        )

    async def update_policy(self, policy_id: UUID, data: CommissionPolicyUpdate) -> CommissionPolicyRead:
        async def operation() -> CommissionPolicyRead:
            row = await self._require_policy(policy_id, lock=True)
            self._require_draft(row)
            if row.revision != data.revision:
                raise self._conflict("分佣政策已被其他管理员修改，请重新加载")
            if any(
                rule.ancestor_depth > data.max_depth for rule in await self._repository.distribution_rules(policy_id)
            ):
                raise AppException(
                    status_code=422, code=ErrorCode.VALIDATION_ERROR, message="最大层级不能低于已有矩阵层级"
                )
            row.name = data.name
            row.default_mode = data.default_mode
            row.default_amount_per_unit = data.default_amount_per_unit
            row.default_percentage_rate = data.default_percentage_rate
            row.max_depth = data.max_depth
            row.settle_delay_days = data.settle_delay_days
            row.updated_by_id = self._require_actor()
            row.revision += 1
            row.updated_at = datetime.now(UTC)
            await self._repository.flush()
            return CommissionPolicyRead.model_validate(row)

        return await self._audit(
            "commission-policies.update", "commission_policies", policy_id, {"operation": "update"}, operation
        )

    async def add_amount_rule(self, policy_id: UUID, data: CommissionAmountRuleCreate) -> CommissionAmountRuleRead:
        async def operation() -> CommissionAmountRuleRead:
            policy = await self._require_policy(policy_id, lock=True)
            self._require_draft(policy)
            await self._validate_amount_rule(data)
            row = CommissionAmountRule(id=new_uuid7(), policy_id=policy.id, **data.model_dump())
            self._session.add(row)
            await self._repository.flush()
            return CommissionAmountRuleRead.model_validate(row)

        return await self._audit(
            "commission-policies.update", "commission_policies", policy_id, {"operation": "add_amount_rule"}, operation
        )

    async def update_amount_rule(
        self, policy_id: UUID, rule_id: UUID, data: CommissionAmountRuleCreate
    ) -> CommissionAmountRuleRead:
        async def operation() -> CommissionAmountRuleRead:
            policy = await self._require_policy(policy_id, lock=True)
            self._require_draft(policy)
            row = await self._repository.amount_rule(rule_id, lock=True)
            if row is None or row.policy_id != policy_id:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="佣金来源规则不存在")
            await self._validate_amount_rule(data)
            for field, value in data.model_dump().items():
                setattr(row, field, value)
            row.updated_at = datetime.now(UTC)
            await self._repository.flush()
            return CommissionAmountRuleRead.model_validate(row)

        return await self._audit(
            "commission-policies.update",
            "commission_policies",
            policy_id,
            {"operation": "update_amount_rule"},
            operation,
        )

    async def delete_amount_rule(self, policy_id: UUID, rule_id: UUID) -> None:
        async def operation() -> None:
            policy = await self._require_policy(policy_id, lock=True)
            self._require_draft(policy)
            row = await self._repository.amount_rule(rule_id, lock=True)
            if row is None or row.policy_id != policy_id:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="佣金来源规则不存在")
            await self._session.delete(row)
            await self._repository.flush()

        await self._audit(
            "commission-policies.update",
            "commission_policies",
            policy_id,
            {"operation": "delete_amount_rule"},
            operation,
        )

    async def add_distribution_rule(
        self, policy_id: UUID, data: CommissionDistributionRuleCreate
    ) -> CommissionDistributionRuleRead:
        async def operation() -> CommissionDistributionRuleRead:
            policy = await self._require_policy(policy_id, lock=True)
            self._require_draft(policy)
            if data.ancestor_depth > policy.max_depth:
                raise AppException(
                    status_code=422, code=ErrorCode.VALIDATION_ERROR, message="分配层级不能超过政策最大层级"
                )
            if not await self._repository.level_exists(data.buyer_level_id) or not await self._repository.level_exists(
                data.beneficiary_level_id
            ):
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会员等级不存在")
            row = CommissionDistributionRule(id=new_uuid7(), policy_id=policy.id, **data.model_dump())
            self._session.add(row)
            await self._repository.flush()
            return CommissionDistributionRuleRead.model_validate(row)

        return await self._audit(
            "commission-policies.update",
            "commission_policies",
            policy_id,
            {"operation": "add_distribution_rule"},
            operation,
        )

    async def update_distribution_rule(
        self, policy_id: UUID, rule_id: UUID, data: CommissionDistributionRuleCreate
    ) -> CommissionDistributionRuleRead:
        async def operation() -> CommissionDistributionRuleRead:
            policy = await self._require_policy(policy_id, lock=True)
            self._require_draft(policy)
            if data.ancestor_depth > policy.max_depth:
                raise AppException(
                    status_code=422, code=ErrorCode.VALIDATION_ERROR, message="分配层级不能超过政策最大层级"
                )
            row = await self._repository.distribution_rule(rule_id, lock=True)
            if row is None or row.policy_id != policy_id:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="三级分配矩阵规则不存在")
            if not await self._repository.level_exists(data.buyer_level_id) or not await self._repository.level_exists(
                data.beneficiary_level_id
            ):
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会员等级不存在")
            for field, value in data.model_dump().items():
                setattr(row, field, value)
            row.updated_at = datetime.now(UTC)
            await self._repository.flush()
            return CommissionDistributionRuleRead.model_validate(row)

        return await self._audit(
            "commission-policies.update",
            "commission_policies",
            policy_id,
            {"operation": "update_distribution_rule"},
            operation,
        )

    async def delete_distribution_rule(self, policy_id: UUID, rule_id: UUID) -> None:
        async def operation() -> None:
            policy = await self._require_policy(policy_id, lock=True)
            self._require_draft(policy)
            row = await self._repository.distribution_rule(rule_id, lock=True)
            if row is None or row.policy_id != policy_id:
                raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="三级分配矩阵规则不存在")
            await self._session.delete(row)
            await self._repository.flush()

        await self._audit(
            "commission-policies.update",
            "commission_policies",
            policy_id,
            {"operation": "delete_distribution_rule"},
            operation,
        )

    async def publish_policy(self, policy_id: UUID, data: CommissionPolicyPublish) -> CommissionPolicyRead:
        async def operation() -> CommissionPolicyRead:
            control = await self._require_control(lock=True)
            policy = await self._require_policy(policy_id, lock=True)
            self._require_draft(policy)
            if policy.revision != data.revision:
                raise self._conflict("分佣政策已被其他管理员修改，请重新加载")
            active = await self._repository.active_policy(lock=True)
            if active is not None and active.id != policy.id:
                active.status = "retired"
                active.revision += 1
                active.updated_by_id = self._require_actor()
                active.updated_at = datetime.now(UTC)
            policy.status = "active"
            policy.activated_at = datetime.now(UTC)
            policy.revision += 1
            policy.updated_by_id = self._require_actor()
            policy.updated_at = datetime.now(UTC)
            # control is deliberately locked with policy publication, including the no-active-policy case.
            control.updated_at = control.updated_at
            await self._repository.flush()
            return CommissionPolicyRead.model_validate(policy)

        return await self._audit(
            "commission-policies.publish", "commission_policies", policy_id, {"operation": "publish"}, operation
        )

    async def update_commission_control(self, data: CommissionControlUpdate) -> CommissionControlRead:
        async def operation() -> CommissionControlRead:
            row = await self._require_control(lock=True)
            if row.revision != data.revision:
                raise AppException(
                    status_code=412,
                    code=ErrorCode.SETTINGS_REVISION_MISMATCH,
                    message="分佣总开关已被其他管理员修改，请重新加载",
                )
            row.setting_value = CommissionControlValue(
                schema_version=data.schema_version, commissions_enabled=data.commissions_enabled
            ).model_dump(mode="json")
            row.revision += 1
            row.updated_by_id = self._require_actor()
            row.updated_at = datetime.now(UTC)
            await self._repository.flush()
            return self._control_read(row)

        return await self._audit(
            "settings.commission-control.update", "system_settings", None, {"operation": "update"}, operation
        )

    async def _validate_amount_rule(self, data: CommissionAmountRuleCreate) -> None:
        if data.buyer_level_id is not None and not await self._repository.level_exists(data.buyer_level_id):
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会员等级不存在")
        if data.product_id is not None and not await self._repository.product_exists(data.product_id):
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="商品不存在")
        if data.sku_id is not None and not await self._repository.sku_exists(data.sku_id):
            raise AppException(status_code=404, code=ErrorCode.SKU_NOT_FOUND, message="SKU 不存在")

    async def _require_policy(self, policy_id: UUID, *, lock: bool = False) -> CommissionPolicy:
        row = await self._repository.policy(policy_id, lock=lock)
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.COMMISSION_POLICY_NOT_FOUND, message="分佣政策不存在")
        return row

    async def _require_control(self, *, lock: bool = False) -> SystemSetting:
        row = await self._repository.commission_control(lock=lock)
        if row is None:
            raise AppException(
                status_code=503, code=ErrorCode.COMMISSION_CONTROL_UNAVAILABLE, message="分佣总开关配置不可用"
            )
        try:
            CommissionControlValue.model_validate(row.setting_value)
        except ValueError as exc:
            raise AppException(
                status_code=503, code=ErrorCode.COMMISSION_CONTROL_UNAVAILABLE, message="分佣总开关配置不可用"
            ) from exc
        return row

    @staticmethod
    def _control_read(row: SystemSetting) -> CommissionControlRead:
        value = CommissionControlValue.model_validate(row.setting_value)
        return CommissionControlRead(
            **value.model_dump(), revision=row.revision, updated_at=row.updated_at, updated_by_id=row.updated_by_id
        )

    @staticmethod
    def _require_draft(policy: CommissionPolicy) -> None:
        if policy.status != "draft":
            raise AppException(
                status_code=409, code=ErrorCode.COMMISSION_POLICY_FROZEN, message="已发布或已归档政策不能修改"
            )

    async def _audit(
        self,
        action: str,
        target_type: str,
        target_id: UUID | None,
        changed_fields: dict[str, object],
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        if self._audit_coordinator is None or self._actor_id is None:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="需要管理员权限")
        return await self._audit_coordinator.execute(
            action=action,
            target_type=target_type,
            target_id=target_id,
            changed_fields=changed_fields,
            operation=operation,
        )

    @staticmethod
    def _conflict(message: str) -> AppException:
        return AppException(status_code=409, code=ErrorCode.COMMISSION_POLICY_CONFLICT, message=message)

    def _require_actor(self) -> UUID:
        if self._actor_id is None:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="需要管理员权限")
        return self._actor_id


__all__ = ["CommissionPolicyService"]
