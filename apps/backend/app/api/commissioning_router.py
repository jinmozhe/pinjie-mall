from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.commissioning_dependencies import AdminCommissionPolicies
from app.api.dependencies import require_admin_csrf, require_permission
from app.core.context import current_request_id
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.commissioning.schemas import (
    CommissionAmountRuleCreate,
    CommissionAmountRuleRead,
    CommissionControlRead,
    CommissionControlUpdate,
    CommissionDistributionRuleCreate,
    CommissionDistributionRuleRead,
    CommissionPolicyCreate,
    CommissionPolicyPublish,
    CommissionPolicyRead,
    CommissionPolicyUpdate,
)

router = APIRouter(tags=["分佣政策"])
Page = Annotated[int, Query(ge=1, description="页码，从一开始")]
PageSize = Annotated[int, Query(ge=1, le=100, description="每页数量")]


@router.get(
    "/admin/settings/commission-control",
    response_model=ResponseModel[CommissionControlRead],
    dependencies=[Depends(require_permission(PermissionCode.SETTINGS_COMMISSION_CONTROL_READ))],
    summary="获取分佣总开关",
)
async def commission_control(service: AdminCommissionPolicies) -> ResponseModel[CommissionControlRead]:
    return success_response(data=await service.commission_control(), request_id=current_request_id())


@router.put(
    "/admin/settings/commission-control",
    response_model=ResponseModel[CommissionControlRead],
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.SETTINGS_COMMISSION_CONTROL_UPDATE)),
    ],
    summary="更新分佣总开关",
)
async def update_commission_control(
    payload: CommissionControlUpdate, service: AdminCommissionPolicies
) -> ResponseModel[CommissionControlRead]:
    return success_response(data=await service.update_commission_control(payload), request_id=current_request_id())


@router.get(
    "/admin/commission-policies",
    response_model=ResponseModel[PageResult[CommissionPolicyRead]],
    dependencies=[Depends(require_permission(PermissionCode.COMMISSION_POLICIES_READ))],
    summary="分页查看分佣政策",
)
async def policies(
    service: AdminCommissionPolicies, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[CommissionPolicyRead]]:
    return success_response(data=await service.policies(page, page_size), request_id=current_request_id())


@router.post(
    "/admin/commission-policies",
    response_model=ResponseModel[CommissionPolicyRead],
    status_code=201,
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_CREATE))],
    summary="创建分佣政策草稿",
)
async def create_policy(
    payload: CommissionPolicyCreate, service: AdminCommissionPolicies
) -> ResponseModel[CommissionPolicyRead]:
    return success_response(data=await service.create_policy(payload), request_id=current_request_id())


@router.get(
    "/admin/commission-policies/{policy_id}",
    response_model=ResponseModel[CommissionPolicyRead],
    dependencies=[Depends(require_permission(PermissionCode.COMMISSION_POLICIES_READ))],
    summary="查看分佣政策",
)
async def policy(policy_id: UUID, service: AdminCommissionPolicies) -> ResponseModel[CommissionPolicyRead]:
    return success_response(data=await service.policy(policy_id), request_id=current_request_id())


@router.put(
    "/admin/commission-policies/{policy_id}",
    response_model=ResponseModel[CommissionPolicyRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_UPDATE))],
    summary="修改分佣政策草稿",
)
async def update_policy(
    policy_id: UUID, payload: CommissionPolicyUpdate, service: AdminCommissionPolicies
) -> ResponseModel[CommissionPolicyRead]:
    return success_response(data=await service.update_policy(policy_id, payload), request_id=current_request_id())


@router.post(
    "/admin/commission-policies/{policy_id}/publish",
    response_model=ResponseModel[CommissionPolicyRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_PUBLISH))],
    summary="发布分佣政策",
)
async def publish_policy(
    policy_id: UUID, payload: CommissionPolicyPublish, service: AdminCommissionPolicies
) -> ResponseModel[CommissionPolicyRead]:
    return success_response(data=await service.publish_policy(policy_id, payload), request_id=current_request_id())


@router.get(
    "/admin/commission-policies/{policy_id}/amount-rules",
    response_model=ResponseModel[list[CommissionAmountRuleRead]],
    dependencies=[Depends(require_permission(PermissionCode.COMMISSION_POLICIES_READ))],
    summary="查看佣金来源规则",
)
async def amount_rules(
    policy_id: UUID, service: AdminCommissionPolicies
) -> ResponseModel[list[CommissionAmountRuleRead]]:
    return success_response(data=await service.amount_rules(policy_id), request_id=current_request_id())


@router.post(
    "/admin/commission-policies/{policy_id}/amount-rules",
    response_model=ResponseModel[CommissionAmountRuleRead],
    status_code=201,
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_UPDATE))],
    summary="新增佣金来源规则",
)
async def add_amount_rule(
    policy_id: UUID, payload: CommissionAmountRuleCreate, service: AdminCommissionPolicies
) -> ResponseModel[CommissionAmountRuleRead]:
    return success_response(data=await service.add_amount_rule(policy_id, payload), request_id=current_request_id())


@router.put(
    "/admin/commission-policies/{policy_id}/amount-rules/{rule_id}",
    response_model=ResponseModel[CommissionAmountRuleRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_UPDATE))],
    summary="修改佣金来源规则",
)
async def update_amount_rule(
    policy_id: UUID, rule_id: UUID, payload: CommissionAmountRuleCreate, service: AdminCommissionPolicies
) -> ResponseModel[CommissionAmountRuleRead]:
    return success_response(
        data=await service.update_amount_rule(policy_id, rule_id, payload), request_id=current_request_id()
    )


@router.delete(
    "/admin/commission-policies/{policy_id}/amount-rules/{rule_id}",
    response_model=ResponseModel[None],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_UPDATE))],
    summary="删除佣金来源规则",
)
async def delete_amount_rule(policy_id: UUID, rule_id: UUID, service: AdminCommissionPolicies) -> ResponseModel[None]:
    await service.delete_amount_rule(policy_id, rule_id)
    return success_response(data=None, request_id=current_request_id())


@router.get(
    "/admin/commission-policies/{policy_id}/distribution-rules",
    response_model=ResponseModel[list[CommissionDistributionRuleRead]],
    dependencies=[Depends(require_permission(PermissionCode.COMMISSION_POLICIES_READ))],
    summary="查看三级分配矩阵",
)
async def distribution_rules(
    policy_id: UUID, service: AdminCommissionPolicies
) -> ResponseModel[list[CommissionDistributionRuleRead]]:
    return success_response(data=await service.distribution_rules(policy_id), request_id=current_request_id())


@router.post(
    "/admin/commission-policies/{policy_id}/distribution-rules",
    response_model=ResponseModel[CommissionDistributionRuleRead],
    status_code=201,
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_UPDATE))],
    summary="新增三级分配矩阵规则",
)
async def add_distribution_rule(
    policy_id: UUID, payload: CommissionDistributionRuleCreate, service: AdminCommissionPolicies
) -> ResponseModel[CommissionDistributionRuleRead]:
    return success_response(
        data=await service.add_distribution_rule(policy_id, payload), request_id=current_request_id()
    )


@router.put(
    "/admin/commission-policies/{policy_id}/distribution-rules/{rule_id}",
    response_model=ResponseModel[CommissionDistributionRuleRead],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_UPDATE))],
    summary="修改三级分配矩阵规则",
)
async def update_distribution_rule(
    policy_id: UUID,
    rule_id: UUID,
    payload: CommissionDistributionRuleCreate,
    service: AdminCommissionPolicies,
) -> ResponseModel[CommissionDistributionRuleRead]:
    return success_response(
        data=await service.update_distribution_rule(policy_id, rule_id, payload), request_id=current_request_id()
    )


@router.delete(
    "/admin/commission-policies/{policy_id}/distribution-rules/{rule_id}",
    response_model=ResponseModel[None],
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.COMMISSION_POLICIES_UPDATE))],
    summary="删除三级分配矩阵规则",
)
async def delete_distribution_rule(
    policy_id: UUID, rule_id: UUID, service: AdminCommissionPolicies
) -> ResponseModel[None]:
    await service.delete_distribution_rule(policy_id, rule_id)
    return success_response(data=None, request_id=current_request_id())


__all__ = ["router"]
