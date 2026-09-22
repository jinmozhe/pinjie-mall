from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_admin_csrf, require_permission
from app.api.membership_dependencies import AdminMembership, AdminPoints, Membership, UserMembership
from app.core.context import current_request_id
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.membership.schemas import (
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
    PointsAccountRead,
    PointsLedgerRead,
    PointsManualAdjustment,
)

router = APIRouter(tags=["会员价格与运费"])
Page = Annotated[int, Query(ge=1, description="页码，从一开始")]
PageSize = Annotated[int, Query(ge=1, le=100, description="每页数量")]


@router.get(
    "/admin/member-levels",
    response_model=ResponseModel[PageResult[MemberLevelRead]],
    dependencies=[Depends(require_permission(PermissionCode.MEMBER_LEVELS_READ))],
    summary="分页查看会员等级",
)
async def member_levels(
    service: AdminMembership, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[MemberLevelRead]]:
    return success_response(data=await service.levels(page, page_size), request_id=current_request_id())


@router.post(
    "/admin/member-levels",
    response_model=ResponseModel[MemberLevelRead],
    status_code=201,
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.MEMBER_LEVELS_CREATE))],
    summary="创建会员等级",
)
async def create_member_level(payload: MemberLevelCreate, service: AdminMembership) -> ResponseModel[MemberLevelRead]:
    return success_response(data=await service.save_level(payload), request_id=current_request_id())


@router.put(
    "/admin/member-levels/{level_id}",
    response_model=ResponseModel[MemberLevelRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.MEMBER_LEVELS_UPDATE))],
    summary="修改会员等级",
)
async def update_member_level(
    level_id: UUID, payload: MemberLevelUpdate, service: AdminMembership
) -> ResponseModel[MemberLevelRead]:
    return success_response(data=await service.save_level(payload, level_id), request_id=current_request_id())


@router.get(
    "/admin/member-level-conditions",
    response_model=ResponseModel[PageResult[MemberLevelConditionRead]],
    dependencies=[Depends(require_permission(PermissionCode.MEMBER_LEVEL_CONDITIONS_READ))],
    summary="分页查看会员资格条件",
)
async def member_level_conditions(
    service: AdminMembership, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[MemberLevelConditionRead]]:
    return success_response(data=await service.conditions(page, page_size), request_id=current_request_id())


@router.post(
    "/admin/member-level-conditions",
    response_model=ResponseModel[MemberLevelConditionRead],
    status_code=201,
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.MEMBER_LEVEL_CONDITIONS_CREATE)),
    ],
    summary="创建会员资格条件",
)
async def create_member_level_condition(
    payload: MemberLevelConditionCreate, service: AdminMembership
) -> ResponseModel[MemberLevelConditionRead]:
    return success_response(data=await service.save_condition(payload), request_id=current_request_id())


@router.put(
    "/admin/member-level-conditions/{condition_id}",
    response_model=ResponseModel[MemberLevelConditionRead],
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.MEMBER_LEVEL_CONDITIONS_UPDATE)),
    ],
    summary="修改会员资格条件",
)
async def update_member_level_condition(
    condition_id: UUID, payload: MemberLevelConditionUpdate, service: AdminMembership
) -> ResponseModel[MemberLevelConditionRead]:
    return success_response(data=await service.save_condition(payload, condition_id), request_id=current_request_id())


@router.get(
    "/admin/members/{user_id}/qualification-events",
    response_model=ResponseModel[PageResult[MembershipQualificationEventRead]],
    dependencies=[Depends(require_permission(PermissionCode.MEMBERS_READ))],
    summary="查看会员资格贡献历史",
)
async def qualification_events(
    user_id: UUID, service: AdminMembership, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[MembershipQualificationEventRead]]:
    return success_response(
        data=await service.qualification_events(user_id, page, page_size), request_id=current_request_id()
    )


@router.get(
    "/admin/members/{user_id}/level-events",
    response_model=ResponseModel[PageResult[MemberLevelEventRead]],
    dependencies=[Depends(require_permission(PermissionCode.MEMBERS_READ))],
    summary="查看会员等级变更历史",
)
async def level_events(
    user_id: UUID, service: AdminMembership, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[MemberLevelEventRead]]:
    return success_response(data=await service.level_events(user_id, page, page_size), request_id=current_request_id())


@router.get(
    "/admin/points-accounts",
    response_model=ResponseModel[PageResult[PointsAccountRead]],
    dependencies=[Depends(require_permission(PermissionCode.POINTS_READ))],
    summary="分页查看积分账户",
)
async def points_accounts(
    service: AdminPoints, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[PointsAccountRead]]:
    return success_response(data=await service.accounts(page, page_size), request_id=current_request_id())


@router.get(
    "/admin/points-accounts/{account_id}/ledgers",
    response_model=ResponseModel[PageResult[PointsLedgerRead]],
    dependencies=[Depends(require_permission(PermissionCode.POINTS_READ))],
    summary="查看积分账户流水",
)
async def points_ledgers(
    account_id: UUID, service: AdminPoints, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[PointsLedgerRead]]:
    return success_response(data=await service.ledgers(account_id, page, page_size), request_id=current_request_id())


@router.post(
    "/admin/points-adjustments",
    response_model=ResponseModel[PointsAccountRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.POINTS_ADJUST))],
    summary="人工授予或冲销积分",
)
async def adjust_points(payload: PointsManualAdjustment, service: AdminPoints) -> ResponseModel[PointsAccountRead]:
    return success_response(data=await service.adjust(payload), request_id=current_request_id())


@router.get(
    "/admin/member-price-rules",
    response_model=ResponseModel[PageResult[MemberPriceRuleRead]],
    dependencies=[Depends(require_permission(PermissionCode.MEMBER_PRICE_RULES_READ))],
    summary="分页查看会员价格规则",
)
async def member_price_rules(
    service: AdminMembership, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[MemberPriceRuleRead]]:
    return success_response(data=await service.price_rules(page, page_size), request_id=current_request_id())


@router.post(
    "/admin/member-price-rules",
    response_model=ResponseModel[MemberPriceRuleRead],
    status_code=201,
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.MEMBER_PRICE_RULES_CREATE))],
    summary="创建会员价格规则",
)
async def create_member_price_rule(
    payload: MemberPriceRuleCreate, service: AdminMembership
) -> ResponseModel[MemberPriceRuleRead]:
    return success_response(data=await service.save_price_rule(payload), request_id=current_request_id())


@router.put(
    "/admin/member-price-rules/{rule_id}",
    response_model=ResponseModel[MemberPriceRuleRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.MEMBER_PRICE_RULES_UPDATE))],
    summary="修改会员价格规则",
)
async def update_member_price_rule(
    rule_id: UUID, payload: MemberPriceRuleUpdate, service: AdminMembership
) -> ResponseModel[MemberPriceRuleRead]:
    return success_response(data=await service.save_price_rule(payload, rule_id), request_id=current_request_id())


@router.get(
    "/admin/settings/order-shipping",
    response_model=ResponseModel[OrderShippingSettingRead],
    dependencies=[Depends(require_permission(PermissionCode.SETTINGS_ORDER_SHIPPING_READ))],
    summary="获取平台运费配置",
)
async def get_order_shipping(service: AdminMembership) -> ResponseModel[OrderShippingSettingRead]:
    return success_response(data=await service.order_shipping(), request_id=current_request_id())


@router.put(
    "/admin/settings/order-shipping",
    response_model=ResponseModel[OrderShippingSettingRead],
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.SETTINGS_ORDER_SHIPPING_UPDATE)),
    ],
    summary="更新平台运费配置",
)
async def update_order_shipping(
    payload: OrderShippingSettingUpdate, service: AdminMembership
) -> ResponseModel[OrderShippingSettingRead]:
    return success_response(data=await service.update_order_shipping(payload), request_id=current_request_id())


@router.post(
    "/commerce/quotes",
    response_model=ResponseModel[CommerceQuoteRead],
    summary="按当前会员身份预览统一报价",
)
async def quote(
    payload: CommerceQuoteRequest, service: Membership, current: UserMembership
) -> ResponseModel[CommerceQuoteRead]:
    return success_response(data=await service.quote(current.user.id, payload), request_id=current_request_id())


__all__ = ["router"]
