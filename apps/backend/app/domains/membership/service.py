from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.db.models import (
    MemberLevel,
    MemberLevelCondition,
    MemberLevelEvent,
    MemberPriceRule,
    MemberProfile,
    MembershipQualificationEvent,
)
from app.db.models.product import Category, Product, ProductSku

from .repository import MembershipRepository
from .schemas import (
    CommerceQuoteRead,
    CommerceQuoteRequest,
    MemberLevelConditionCreate,
    MemberLevelConditionRead,
    MemberLevelConditionUpdate,
    MemberLevelCreate,
    MemberLevelEventRead,
    MemberLevelRead,
    MemberLevelUpdate,
    MemberPriceRuleCreate,
    MemberPriceRuleRead,
    MemberPriceRuleUpdate,
    MembershipQualificationEventRead,
    OrderShippingSettingRead,
    OrderShippingSettingUpdate,
    OrderShippingSettingValue,
    QuoteLineRead,
)

T = TypeVar("T")
_CENT = Decimal("0.01")


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


class MembershipService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        actor_id: UUID | None = None,
        audit: AuditExecutor | None = None,
    ) -> None:
        self._session = session
        self._repository = MembershipRepository(session)
        self._actor_id = actor_id
        self._audit_coordinator = audit

    async def levels(self, page: int, page_size: int) -> PageResult[MemberLevelRead]:
        rows, total = await self._repository.levels_page(page, page_size)
        return PageResult[MemberLevelRead].create(
            items=[MemberLevelRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def save_level(self, data: MemberLevelCreate, level_id: UUID | None = None) -> MemberLevelRead:
        async def operation() -> MemberLevelRead:
            if level_id is None:
                row = MemberLevel(id=new_uuid7(), revision=1)
            else:
                row = await self._require_level(level_id, for_update=True)
                if not isinstance(data, MemberLevelUpdate) or row.revision != data.revision:
                    raise self._conflict("会员等级版本已变更")
                row.revision += 1
            row.code = data.code
            row.name = data.name
            row.discount_factor = data.discount_factor
            row.level_rank = data.level_rank
            row.sort_order = data.sort_order
            row.is_active = data.is_active
            self._session.add(row)
            await self._repository.flush()
            return MemberLevelRead.model_validate(row)

        return await self._audit("member-levels.write", "member_level", level_id, {"operation": "save"}, operation)

    async def conditions(self, page: int, page_size: int) -> PageResult[MemberLevelConditionRead]:
        rows, total = await self._repository.conditions_page(page, page_size)
        return PageResult[MemberLevelConditionRead].create(
            items=[MemberLevelConditionRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def save_condition(
        self, data: MemberLevelConditionCreate, condition_id: UUID | None = None
    ) -> MemberLevelConditionRead:
        actor_id = self._require_actor()

        async def operation() -> MemberLevelConditionRead:
            await self._require_level(data.level_id, for_update=True)
            if condition_id is None:
                row = MemberLevelCondition(id=new_uuid7(), revision=1)
            else:
                existing = await self._repository.condition(condition_id, for_update=True)
                if existing is None:
                    raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会员等级条件不存在")
                row = existing
                if not isinstance(data, MemberLevelConditionUpdate) or row.revision != data.revision:
                    raise self._conflict("会员等级条件版本已变更")
                row.revision += 1
            row.level_id = data.level_id
            row.metric = data.metric
            row.aggregation = data.aggregation
            row.amount_threshold = data.amount_threshold
            row.count_threshold = data.count_threshold
            row.is_active = data.is_active
            row.effective_at = data.effective_at
            row.updated_by_id = actor_id
            self._session.add(row)
            await self._repository.flush()
            return MemberLevelConditionRead.model_validate(row)

        return await self._audit(
            "member-level-conditions.write", "member_level_condition", condition_id, {"operation": "save"}, operation
        )

    async def qualification_events(
        self, user_id: UUID, page: int, page_size: int
    ) -> PageResult[MembershipQualificationEventRead]:
        rows, total = await self._repository.qualification_events_page(user_id, page, page_size)
        return PageResult[MembershipQualificationEventRead].create(
            items=[MembershipQualificationEventRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def qualification_event_for_source(
        self, *, user_id: UUID, metric: str, source_type: str, source_id: UUID
    ) -> MembershipQualificationEvent | None:
        return await self._repository.qualification_by_source(
            user_id=user_id, metric=metric, source_type=source_type, source_id=source_id, for_update=True
        )

    async def level_events(self, user_id: UUID, page: int, page_size: int) -> PageResult[MemberLevelEventRead]:
        rows, total = await self._repository.level_events_page(user_id, page, page_size)
        return PageResult[MemberLevelEventRead].create(
            items=[MemberLevelEventRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def record_qualification_event(
        self,
        *,
        user_id: UUID,
        metric: Literal["consumption", "invite_count", "points"],
        source_type: str,
        source_id: UUID,
        idempotency_key: str,
        amount_delta: Decimal | None = None,
        count_delta: int | None = None,
        order_id: UUID | None = None,
        reverses_event_id: UUID | None = None,
        trigger_type: Literal["order", "refund", "invite", "points", "policy_reassessment"] = "policy_reassessment",
    ) -> MembershipQualificationEvent:
        if (
            (amount_delta is None) == (count_delta is None)
            or (amount_delta is not None and amount_delta == 0)
            or (count_delta is not None and count_delta == 0)
        ):
            raise AppException(
                status_code=422, code=ErrorCode.VALIDATION_ERROR, message="资格事件必须且只能提供一个非零增量"
            )
        if (metric == "consumption" and amount_delta is None) or (metric != "consumption" and count_delta is None):
            raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="资格指标与增量类型不匹配")
        existing = await self._repository.qualification_by_key(idempotency_key, for_update=True)
        if existing is not None:
            if (
                existing.user_id != user_id
                or existing.metric != metric
                or existing.source_type != source_type
                or existing.source_id != source_id
                or existing.amount_delta != amount_delta
                or existing.count_delta != count_delta
                or existing.reverses_event_id != reverses_event_id
            ):
                raise self._conflict("资格事件幂等键已用于不同请求")
            return existing
        profile = await self._repository.profile(user_id, for_update=True)
        if profile is None:
            raise AppException(
                status_code=409, code=ErrorCode.STATE_CONFLICT, message="用户尚无会员档案，不能写入资格事件"
            )
        if reverses_event_id is None:
            if (amount_delta is not None and amount_delta < 0) or (count_delta is not None and count_delta < 0):
                raise AppException(
                    status_code=422, code=ErrorCode.VALIDATION_ERROR, message="负资格贡献必须关联原事件冲销"
                )
        else:
            original = await self._repository.qualification_event(reverses_event_id, for_update=True)
            if (
                original is None
                or original.reverses_event_id is not None
                or original.user_id != user_id
                or original.metric != metric
            ):
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="资格冲销原事件不匹配")
            if (amount_delta is not None and amount_delta >= 0) or (count_delta is not None and count_delta >= 0):
                raise AppException(status_code=422, code=ErrorCode.VALIDATION_ERROR, message="资格冲销必须使用负增量")
            reversals = [
                event
                for event in await self._repository.qualification_events(user_id, metric)
                if event.reverses_event_id == original.id
            ]
            if (
                amount_delta is not None
                and original.amount_delta is not None
                and -amount_delta
                > original.amount_delta + sum((event.amount_delta or Decimal("0")) for event in reversals)
            ):
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="资格冲销超过原贡献")
            if (
                count_delta is not None
                and original.count_delta is not None
                and -count_delta > original.count_delta + sum(event.count_delta or 0 for event in reversals)
            ):
                raise AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message="资格冲销超过原贡献")
        event = MembershipQualificationEvent(
            id=new_uuid7(),
            user_id=user_id,
            metric=metric,
            source_type=source_type,
            source_id=source_id,
            order_id=order_id,
            amount_delta=amount_delta,
            count_delta=count_delta,
            reverses_event_id=reverses_event_id,
            occurred_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
        )
        self._session.add(event)
        await self._repository.flush()
        await self._reassess_profile(profile, trigger_type=trigger_type, trigger_id=event.id)
        return event

    async def _reassess_profile(
        self,
        profile: MemberProfile,
        *,
        trigger_type: Literal["order", "refund", "invite", "points", "policy_reassessment"],
        trigger_id: UUID,
    ) -> None:
        user_id = profile.user_id
        levels = await self._repository.active_levels()
        conditions = await self._repository.conditions_for_levels([level.id for level in levels], datetime.now(UTC))
        values = await self._qualification_values(user_id)
        by_level: dict[UUID, list[MemberLevelCondition]] = defaultdict(list)
        for condition in conditions:
            by_level[condition.level_id].append(condition)
        selected: MemberLevel | None = None
        level_snapshot: list[dict[str, object]] = []
        snapshot: dict[str, object] = {
            "schema_version": 1,
            "condition_ids": [str(condition.id) for condition in conditions],
            "condition_revisions": {str(condition.id): condition.revision for condition in conditions},
            "metrics": values,
            "evaluated_at": datetime.now(UTC).isoformat(),
            "reason": trigger_type,
            "levels": level_snapshot,
        }
        for level in levels:
            level_conditions = by_level.get(level.id, [])
            if not level_conditions:
                continue
            matched = all(self._matches_condition(condition, values) for condition in level_conditions)
            level_snapshot.append({"level_id": str(level.id), "matched": matched})
            if matched and selected is None:
                selected = level
        if profile.level_id == (selected.id if selected else None):
            return
        previous_level_id = profile.level_id
        profile.level_id = selected.id if selected else None
        profile.level_changed_at = datetime.now(UTC)
        profile.revision += 1
        self._session.add(
            MemberLevelEvent(
                id=new_uuid7(),
                user_id=user_id,
                from_level_id=previous_level_id,
                to_level_id=profile.level_id,
                trigger_type=trigger_type,
                trigger_id=trigger_id,
                qualification_snapshot=snapshot,
                profile_revision=profile.revision,
                operator_id=None,
                idempotency_key=f"qualification:{trigger_id}",
            )
        )
        await self._repository.flush()

    async def _qualification_values(self, user_id: UUID) -> dict[str, dict[str, str | int]]:
        values: dict[str, dict[str, str | int]] = {}
        for metric in ("consumption", "invite_count", "points"):
            events = await self._repository.qualification_events(user_id, metric)
            if metric == "consumption":
                cumulative = sum((event.amount_delta or Decimal("0")) for event in events)
                singles = self._single_amount_values(events)
                values[metric] = {"cumulative": str(cumulative), "single": str(max(singles, default=Decimal("0")))}
            else:
                cumulative_count = sum(event.count_delta or 0 for event in events)
                singles_count = self._single_count_values(events)
                values[metric] = {"cumulative": cumulative_count, "single": max(singles_count, default=0)}
        return values

    @staticmethod
    def _single_amount_values(events: list[MembershipQualificationEvent]) -> list[Decimal]:
        reversals: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
        originals: list[MembershipQualificationEvent] = []
        for event in events:
            if event.reverses_event_id is None:
                originals.append(event)
            else:
                reversals[event.reverses_event_id] += event.amount_delta or Decimal("0")
        return [max(Decimal("0"), (event.amount_delta or Decimal("0")) + reversals[event.id]) for event in originals]

    @staticmethod
    def _single_count_values(events: list[MembershipQualificationEvent]) -> list[int]:
        reversals: dict[UUID, int] = defaultdict(int)
        originals: list[MembershipQualificationEvent] = []
        for event in events:
            if event.reverses_event_id is None:
                originals.append(event)
            else:
                reversals[event.reverses_event_id] += event.count_delta or 0
        return [max(0, (event.count_delta or 0) + reversals[event.id]) for event in originals]

    @staticmethod
    def _matches_condition(condition: MemberLevelCondition, values: dict[str, dict[str, str | int]]) -> bool:
        value = values[condition.metric][condition.aggregation]
        if condition.metric == "consumption":
            return Decimal(str(value)) >= (condition.amount_threshold or Decimal("0"))
        return int(value) >= (condition.count_threshold or 0)

    async def price_rules(self, page: int, page_size: int) -> PageResult[MemberPriceRuleRead]:
        rows, total = await self._repository.price_rules_page(page, page_size)
        return PageResult[MemberPriceRuleRead].create(
            items=[MemberPriceRuleRead.model_validate(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def save_price_rule(self, data: MemberPriceRuleCreate, rule_id: UUID | None = None) -> MemberPriceRuleRead:
        actor_id = self._require_actor()

        async def operation() -> MemberPriceRuleRead:
            await self._require_level(data.member_level_id, for_update=True)
            if rule_id is None:
                row = MemberPriceRule(id=new_uuid7(), revision=1)
            else:
                row = await self._require_rule(rule_id, for_update=True)
                if not isinstance(data, MemberPriceRuleUpdate) or row.revision != data.revision:
                    raise self._conflict("会员价格规则版本已变更")
                row.revision += 1
            row.member_level_id = data.member_level_id
            row.scope_type = data.scope_type
            row.sku_id, row.product_id, row.category_id = data.sku_id, data.product_id, data.category_id
            row.price_mode = data.price_mode
            row.fixed_price, row.discount_factor = data.fixed_price, data.discount_factor
            row.is_active, row.updated_by_id = data.is_active, actor_id
            self._session.add(row)
            await self._repository.flush()
            return MemberPriceRuleRead.model_validate(row)

        return await self._audit(
            "member-price-rules.write", "member_price_rule", rule_id, {"operation": "save"}, operation
        )

    async def order_shipping(self) -> OrderShippingSettingRead:
        setting = await self._repository.setting("order_shipping")
        if setting is None:
            raise self._configuration_error()
        try:
            value = OrderShippingSettingValue.model_validate(setting.setting_value)
        except ValueError as exc:
            raise self._configuration_error() from exc
        return OrderShippingSettingRead(
            **value.model_dump(),
            revision=setting.revision,
            updated_at=setting.updated_at,
            updated_by_id=setting.updated_by_id,
        )

    async def update_order_shipping(self, data: OrderShippingSettingUpdate) -> OrderShippingSettingRead:
        actor_id = self._require_actor()

        async def operation() -> OrderShippingSettingRead:
            setting = await self._repository.setting("order_shipping", for_update=True)
            if setting is None:
                raise self._configuration_error()
            if setting.revision != data.revision:
                raise AppException(
                    status_code=412,
                    code=ErrorCode.SETTINGS_REVISION_MISMATCH,
                    message="平台运费设置已被其他管理员修改，请重新加载",
                )
            value = OrderShippingSettingValue.model_validate(data.model_dump(exclude={"revision"}))
            setting.setting_value = value.model_dump(mode="json")
            setting.revision += 1
            setting.updated_by_id = actor_id
            setting.updated_at = datetime.now(UTC)
            await self._repository.flush()
            return OrderShippingSettingRead(
                **value.model_dump(),
                revision=setting.revision,
                updated_at=setting.updated_at,
                updated_by_id=setting.updated_by_id,
            )

        return await self._audit(
            "settings.order-shipping.update", "system_setting", None, {"operation": "update_order_shipping"}, operation
        )

    async def quote(self, user_id: UUID, data: CommerceQuoteRequest) -> CommerceQuoteRead:
        quantities: dict[UUID, int] = defaultdict(int)
        for item in data.items:
            quantities[item.sku_id] += item.quantity
        if any(quantity > 999 for quantity in quantities.values()):
            raise AppException(status_code=422, code=ErrorCode.CHECKOUT_INVALID, message="单个 SKU 数量不能超过 999")
        catalog = await self._repository.sku_catalog(list(quantities))
        if len(catalog) != len(quantities):
            raise AppException(status_code=404, code=ErrorCode.SKU_NOT_FOUND, message="SKU 不存在")
        categories = {item.id: item for item in await self._repository.categories()}
        profile = await self._repository.profile(user_id)
        level, state = await self._quote_level(profile.level_id if profile else None)
        rules = await self._repository.active_rules(level.id) if level is not None else []
        by_sku = {rule.sku_id: rule for rule in rules if rule.scope_type == "sku"}
        by_product = {rule.product_id: rule for rule in rules if rule.scope_type == "product"}
        by_category = {rule.category_id: rule for rule in rules if rule.scope_type == "category"}
        product_types = {product.product_type for _, product in catalog}
        if len(product_types) != 1:
            raise AppException(status_code=422, code=ErrorCode.CHECKOUT_INVALID, message="实物和虚拟商品不能混合报价")
        lines: list[QuoteLineRead] = []
        for sku, product in catalog:
            self._assert_sellable(sku, product, categories)
            quantity = quantities[sku.id]
            base = self._wholesale_price(sku, quantity)
            unit_price, source = self._member_price(
                sku, product, categories, base, level, by_sku, by_product, by_category
            )
            line_amount = self._money(unit_price * quantity)
            lines.append(
                QuoteLineRead(
                    sku_id=sku.id,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=quantity,
                    base_unit_price=base,
                    unit_price=unit_price,
                    line_amount=line_amount,
                    price_source=source,
                )
            )
        lines.sort(key=lambda line: str(line.sku_id))
        items_amount = self._money(sum((line.line_amount for line in lines), Decimal("0.00")))
        freight, rule_id = await self._freight(product_types.pop(), items_amount, data.province_code)
        total = self._money(items_amount + freight)
        fingerprint = self._fingerprint(user_id, lines, level.id if level else None, state, freight, rule_id)
        return CommerceQuoteRead(
            items=lines,
            items_amount=items_amount,
            freight_amount=freight,
            total_amount=total,
            buyer_level_id=level.id if level else None,
            buyer_level_state=state,
            shipping_rule_id=rule_id,
            fingerprint=fingerprint,
        )

    async def _quote_level(
        self, level_id: UUID | None
    ) -> tuple[MemberLevel | None, Literal["none", "active", "disabled"]]:
        if level_id is None:
            return None, "none"
        level = await self._repository.level(level_id)
        if level is None or not level.is_active:
            return None, "disabled"
        return level, "active"

    async def _freight(
        self, product_type: str, items_amount: Decimal, province_code: str | None
    ) -> tuple[Decimal, UUID | None]:
        if product_type == "virtual":
            return Decimal("0.00"), None
        if province_code is None:
            raise AppException(status_code=422, code=ErrorCode.CHECKOUT_INVALID, message="实物商品报价需要省级行政编码")
        setting = await self._repository.setting("order_shipping")
        if setting is None:
            raise self._configuration_error()
        try:
            value = OrderShippingSettingValue.model_validate(setting.setting_value)
        except ValueError as exc:
            raise self._configuration_error() from exc
        selected = next((rule for rule in value.region_rules if province_code in rule.province_codes), None)
        rule = selected or value.default_rule
        if rule.free_shipping_threshold is not None and items_amount >= rule.free_shipping_threshold:
            return Decimal("0.00"), selected.id if selected else None
        return self._money(rule.fixed_fee), selected.id if selected else None

    @staticmethod
    def _wholesale_price(sku: ProductSku, quantity: int) -> Decimal:
        price = sku.price
        for tier in sku.wholesale_prices:
            if int(str(tier["min_quantity"])) <= quantity:
                price = Decimal(str(tier["unit_price"]))
        return MembershipService._money(price)

    @staticmethod
    def _member_price(
        sku: ProductSku,
        product: Product,
        categories: dict[UUID, Category],
        base: Decimal,
        level: MemberLevel | None,
        by_sku: dict[UUID | None, MemberPriceRule],
        by_product: dict[UUID | None, MemberPriceRule],
        by_category: dict[UUID | None, MemberPriceRule],
    ) -> tuple[Decimal, str]:
        if level is None:
            return base, "wholesale_or_base"
        for source, rule in (("sku_fixed", by_sku.get(sku.id)), ("product_fixed", by_product.get(product.id))):
            if rule is not None and rule.price_mode == "fixed":
                return MembershipService._money(rule.fixed_price or Decimal("0.00")), source
        candidates = [by_sku.get(sku.id), by_product.get(product.id)]
        current_id: UUID | None = product.category_id
        while current_id is not None:
            candidates.append(by_category.get(current_id))
            current = categories.get(current_id)
            current_id = current.parent_id if current else None
        for rule in candidates:
            if rule is None:
                continue
            if rule.price_mode == "exclude":
                return base, "member_excluded"
            if rule.price_mode == "discount":
                if rule.discount_factor is None:
                    raise AppException(
                        status_code=503, code=ErrorCode.CONFIGURATION_ERROR, message="会员折扣规则缺少折扣因子"
                    )
                return MembershipService._money(base * rule.discount_factor), f"{rule.scope_type}_discount"
        return MembershipService._money(base * level.discount_factor), "level_discount"

    @staticmethod
    def _assert_sellable(sku: ProductSku, product: Product, categories: dict[UUID, Category]) -> None:
        if product.status != "on_sale" or not sku.is_active or sku.archived_at is not None:
            raise AppException(status_code=409, code=ErrorCode.CHECKOUT_INVALID, message="SKU 当前不可销售")
        category_id: UUID | None = product.category_id
        while category_id is not None:
            category = categories.get(category_id)
            if category is None or not category.is_active:
                raise AppException(status_code=409, code=ErrorCode.CATEGORY_UNAVAILABLE, message="商品分类当前不可用")
            category_id = category.parent_id

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _fingerprint(
        user_id: UUID,
        lines: list[QuoteLineRead],
        level_id: UUID | None,
        state: str,
        freight: Decimal,
        shipping_rule_id: UUID | None,
    ) -> str:
        payload = {
            "user_id": str(user_id),
            "lines": [line.model_dump(mode="json") for line in lines],
            "level_id": str(level_id) if level_id else None,
            "level_state": state,
            "freight": str(freight),
            "shipping_rule_id": str(shipping_rule_id) if shipping_rule_id else None,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def _require_level(self, level_id: UUID, *, for_update: bool = False) -> MemberLevel:
        row = await self._repository.level(level_id, for_update=for_update)
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会员等级不存在")
        return row

    async def _require_rule(self, rule_id: UUID, *, for_update: bool = False) -> MemberPriceRule:
        row = await self._repository.price_rule(rule_id, for_update=for_update)
        if row is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="会员价格规则不存在")
        return row

    async def _audit(
        self,
        action: str,
        target_type: str,
        target_id: UUID | None,
        changed_fields: dict[str, object],
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        if self._audit_coordinator is None:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="需要管理员权限")
        return await self._audit_coordinator.execute(
            action=action,
            target_type=target_type,
            target_id=target_id,
            changed_fields=changed_fields,
            operation=operation,
        )

    def _require_actor(self) -> UUID:
        if self._actor_id is None:
            raise AppException(status_code=403, code=ErrorCode.PERMISSION_DENIED, message="需要管理员权限")
        return self._actor_id

    @staticmethod
    def _conflict(message: str) -> AppException:
        return AppException(status_code=409, code=ErrorCode.STATE_CONFLICT, message=message)

    @staticmethod
    def _configuration_error() -> AppException:
        return AppException(status_code=503, code=ErrorCode.CONFIGURATION_ERROR, message="平台运费配置不可用")


__all__ = ["MembershipService"]
