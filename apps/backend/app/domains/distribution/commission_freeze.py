from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Sequence, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models.distribution import CommissionRecord, MemberLevel, MemberProfile
from app.db.models.identity import User
from app.db.models.order import Order, OrderItem
from app.domains.commissioning import CommissionAmountRuleRead, CommissionPolicyService

_CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _source_rule(
    rules: Sequence[CommissionAmountRuleRead], item: OrderItem, buyer_level_id: UUID | None
) -> CommissionAmountRuleRead | None:
    for sku_id, product_id, level_id in (
        (item.sku_id, None, buyer_level_id),
        (item.sku_id, None, None),
        (None, item.product_id, buyer_level_id),
        (None, item.product_id, None),
    ):
        for rule in rules:
            if rule.sku_id == sku_id and rule.product_id == product_id and rule.buyer_level_id == level_id:
                return rule
    return None


async def freeze_order_commission_sources(session: AsyncSession, order_id: UUID) -> None:
    order = await session.get(Order, order_id, with_for_update=True)
    if order is None:
        raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
    decision = await CommissionPolicyService(session=session).active_decision_context_in_open_transaction()
    policy = decision.policy
    items = list(
        await session.scalars(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id).with_for_update()
        )
    )
    if policy is None:
        for item in items:
            item.commission_snapshot = {
                "schema_version": 1,
                "reason": "policy_unavailable",
                "source_mode": None,
                "source_amount": "0.00",
            }
        await session.flush()
        return
    order.commission_policy_id = policy.id
    raw_level_id = (
        order.buyer_level_snapshot.get("level_id") if order.buyer_level_snapshot.get("state") == "active" else None
    )
    buyer_level_id = UUID(str(raw_level_id)) if raw_level_id else None
    distribution_rules = [rule.model_dump(mode="json") for rule in decision.distribution_rules]
    for item in items:
        source = _source_rule(decision.amount_rules, item, buyer_level_id)
        mode = source.rule_mode if source else policy.default_mode
        amount_per_unit = source.amount_per_unit if source else policy.default_amount_per_unit
        percentage_rate = source.percentage_rate if source else policy.default_percentage_rate
        if mode == "fixed_amount":
            source_amount = _money((amount_per_unit or Decimal("0.00")) * item.quantity)
        elif mode == "percentage":
            source_amount = _money(item.line_amount * (percentage_rate or Decimal("0.00")))
        else:
            source_amount = Decimal("0.00")
        item.commission_snapshot = {
            "schema_version": 1,
            "policy": policy.model_dump(mode="json"),
            "buyer_level": order.buyer_level_snapshot,
            "source_rule": source.model_dump(mode="json") if source else None,
            "source_mode": mode,
            "source_amount": str(source_amount),
            "quantity": item.quantity,
            "line_amount": str(item.line_amount),
            "distribution_rules": distribution_rules,
            "rounding": "half_up_2dp",
        }
    await session.flush()


async def _beneficiary(
    session: AsyncSession, user_id: UUID
) -> tuple[MemberProfile | None, User | None, MemberLevel | None]:
    profile = (
        await session.scalars(
            select(MemberProfile)
            .where(MemberProfile.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    user = (
        await session.scalars(
            select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
        )
    ).one_or_none()
    level = None
    if profile is not None and profile.level_id is not None:
        level = (
            await session.scalars(
                select(MemberLevel)
                .where(MemberLevel.id == profile.level_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
    return profile, user, level


async def freeze_paid_commissions(
    session: AsyncSession, *, order_id: UUID, source_user_id: UUID, paid_at: datetime
) -> None:
    order = await session.get(Order, order_id, with_for_update=True)
    if order is None:
        raise AppException(status_code=404, code=ErrorCode.ORDER_NOT_FOUND, message="订单不存在")
    if order.commission_result_snapshot is not None:
        return
    control_id, control = await CommissionPolicyService(session=session).commission_control_in_open_transaction()
    items = list(
        await session.scalars(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id).with_for_update()
        )
    )
    policy: dict[str, Any] | None = next(
        (
            cast(dict[str, Any], item.commission_snapshot["policy"])
            for item in items
            if item.commission_snapshot.get("policy")
        ),
        None,
    )
    results: list[dict[str, object]] = []
    if not control.commissions_enabled or policy is None:
        order.commission_result_snapshot = {
            "schema_version": 1,
            "calculation_version": "commission_budget_v1",
            "confirmed_at": paid_at.isoformat(),
            "control": {
                "setting_id": str(control_id),
                "revision": control.revision,
                "commissions_enabled": control.commissions_enabled,
            },
            "policy_id": str(order.commission_policy_id) if order.commission_policy_id else None,
            "policy_content_version": policy.get("content_version") if policy else None,
            "results": results,
        }
        await session.flush()
        return
    buyer_profile, _, _ = await _beneficiary(session, source_user_id)
    buyer_level_id = policy_item_level_id(items)
    policy_id = UUID(str(policy["id"]))
    max_depth = int(policy["max_depth"])
    for item in items:
        snapshot = item.commission_snapshot
        source_amount = Decimal(str(snapshot.get("source_amount", "0.00")))
        budget = source_amount
        ancestor_id = (
            buyer_profile.inviter_id
            if buyer_profile and buyer_profile.bound_at and buyer_profile.bound_at <= paid_at
            else None
        )
        rules = cast(list[dict[str, Any]], snapshot.get("distribution_rules", []))
        for depth in range(1, max_depth + 1):
            if ancestor_id is None:
                break
            beneficiary, user, level = await _beneficiary(session, ancestor_id)
            if beneficiary is None:
                break
            eligible = (
                user is not None and user.is_active and user.deleted_at is None and (level is None or level.is_active)
            )
            rule = next(
                (
                    value
                    for value in rules
                    if value["buyer_level_id"] == str(buyer_level_id)
                    and value["beneficiary_level_id"] == (str(beneficiary.level_id) if beneficiary.level_id else None)
                    and value["ancestor_depth"] == depth
                ),
                None,
            )
            zero_reason: str | None = None
            beneficiary_state = {
                "user_active": user.is_active if user is not None else False,
                "user_deleted": user.deleted_at is not None if user is not None else False,
                "level_active": level.is_active if level is not None else None,
            }
            if source_amount == 0:
                candidate_amount = Decimal("0.00")
                zero_reason = "source_disabled"
            elif not eligible:
                candidate_amount = Decimal("0.00")
                zero_reason = "beneficiary_ineligible"
            elif rule is None and depth == 1:
                candidate_amount = source_amount
                zero_reason = None
            elif rule is None:
                candidate_amount = Decimal("0.00")
                zero_reason = "no_matrix_at_depth"
            elif rule["allocation_mode"] == "percentage":
                candidate_amount = _money(source_amount * Decimal(str(rule["rate"])))
            else:
                candidate_amount = _money(Decimal(str(rule["amount_per_unit"])) * item.quantity)
            amount = min(candidate_amount, budget)
            if amount == 0 and zero_reason is None:
                zero_reason = "matrix_explicit_zero" if rule is not None else "source_disabled"
            result = {
                "order_item_id": str(item.id),
                "ancestor_depth": depth,
                "beneficiary_user_id": str(beneficiary.user_id),
                "beneficiary_eligible": eligible,
                "source_amount": str(source_amount),
                "beneficiary_state": beneficiary_state,
                "candidate_amount": str(candidate_amount),
                "budget_before": str(budget),
                "amount": str(amount),
                "budget_after": str(budget - amount),
                "zero_reason": zero_reason,
                "distribution_rule": rule,
            }
            results.append(result)
            if amount > 0:
                session.add(
                    CommissionRecord(
                        id=new_uuid7(),
                        order_id=order.id,
                        order_item_id=item.id,
                        source_user_id=source_user_id,
                        beneficiary_user_id=beneficiary.user_id,
                        level=depth,
                        base_amount=source_amount,
                        policy_id=policy_id,
                        rate=Decimal(str(rule["rate"])) if rule and rule["rate"] is not None else None,
                        amount=amount,
                        recovered_amount=Decimal("0.00"),
                        status="frozen",
                        frozen_at=paid_at,
                        settle_after=None,
                        settled_at=None,
                        recovered_at=None,
                        revision=1,
                        rule_snapshot={"schema_version": 1, "settle_delay_days": policy["settle_delay_days"], **result},
                    )
                )
            budget -= amount
            ancestor_id = beneficiary.inviter_id if beneficiary.bound_at and beneficiary.bound_at <= paid_at else None
    order.commission_result_snapshot = {
        "schema_version": 1,
        "calculation_version": "commission_budget_v1",
        "confirmed_at": paid_at.isoformat(),
        "control": {"setting_id": str(control_id), "revision": control.revision, "commissions_enabled": True},
        "policy_id": str(policy_id),
        "policy_content_version": policy["content_version"],
        "results": results,
    }
    await session.flush()


def policy_item_level_id(items: list[OrderItem]) -> UUID | None:
    snapshot = next((cast(dict[str, Any], item.commission_snapshot.get("buyer_level", {})) for item in items), {})
    raw = snapshot.get("level_id") if snapshot.get("state") == "active" else None
    return UUID(str(raw)) if raw else None
