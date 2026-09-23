from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_admin_csrf, require_permission, require_web_csrf
from app.api.distribution_dependencies import AdminDistribution, Distribution, UserDistribution
from app.api.transaction_dependencies import UserPrincipal
from app.core.context import current_request_id
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.distribution import (
    CommissionPage,
    MemberProfileRead,
    ReferralBindIn,
    WalletAccountRead,
    WithdrawalCreate,
    WithdrawalManualCompletion,
    WithdrawalPage,
    WithdrawalRead,
    WithdrawalReview,
)

router = APIRouter(tags=["会员分销"])
Page = Annotated[int, Query(ge=1, description="页码，从一开始")]
PageSize = Annotated[int, Query(ge=1, le=100, description="每页数量")]


@router.post(
    "/distribution/me/profile",
    response_model=ResponseModel[MemberProfileRead],
    status_code=201,
    summary="开通本人会员分销档案",
    dependencies=[Depends(require_web_csrf)],
)
async def activate_profile(service: Distribution, current: UserPrincipal) -> ResponseModel[MemberProfileRead]:
    return success_response(
        data=await service.activate_profile(current.user.id),
        request_id=current_request_id(),
        message="会员分销档案已开通",
    )


@router.get("/distribution/me/profile", response_model=ResponseModel[MemberProfileRead], summary="查看本人会员分销档案")
async def profile_read(service: Distribution, current: UserPrincipal) -> ResponseModel[MemberProfileRead]:
    return success_response(data=await service.profile_for_user(current.user.id), request_id=current_request_id())


@router.post(
    "/distribution/me/referrer",
    response_model=ResponseModel[MemberProfileRead],
    summary="首次绑定推荐人",
    dependencies=[Depends(require_web_csrf)],
)
async def bind_referrer(
    payload: ReferralBindIn, service: Distribution, current: UserPrincipal
) -> ResponseModel[MemberProfileRead]:
    return success_response(
        data=await service.bind_referrer(current.user.id, payload),
        request_id=current_request_id(),
        message="推荐关系已绑定",
    )


@router.get(
    "/distribution/me/wallets", response_model=ResponseModel[list[WalletAccountRead]], summary="查看本人双轨钱包"
)
async def wallets_read(service: Distribution, current: UserPrincipal) -> ResponseModel[list[WalletAccountRead]]:
    return success_response(data=await service.wallets_for_user(current.user.id), request_id=current_request_id())


@router.get("/distribution/me/commissions", response_model=ResponseModel[CommissionPage], summary="查看本人佣金记录")
async def commissions_read(
    service: Distribution, current: UserPrincipal, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[CommissionPage]:
    return success_response(
        data=await service.commissions_for_user(current.user.id, page, page_size), request_id=current_request_id()
    )


@router.post(
    "/distribution/me/withdrawals",
    response_model=ResponseModel[WithdrawalRead],
    status_code=201,
    summary="申请佣金钱包提现",
    dependencies=[Depends(require_web_csrf)],
)
async def withdrawal_create(payload: WithdrawalCreate, service: UserDistribution) -> ResponseModel[WithdrawalRead]:
    return success_response(
        data=await service.create_withdrawal(payload),
        request_id=current_request_id(),
        message="提现申请已提交",
    )


@router.get("/distribution/me/withdrawals", response_model=ResponseModel[WithdrawalPage], summary="查看本人提现申请")
async def withdrawals_read(
    service: Distribution, current: UserPrincipal, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[WithdrawalPage]:
    return success_response(
        data=await service.withdrawals_for_user(current.user.id, page, page_size), request_id=current_request_id()
    )


@router.post(
    "/admin/withdrawals/{withdrawal_id}/approve",
    response_model=ResponseModel[WithdrawalRead],
    summary="审核通过提现申请",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.WITHDRAWALS_REVIEW))],
)
async def admin_approve_withdrawal(
    withdrawal_id: UUID, payload: WithdrawalReview, service: AdminDistribution
) -> ResponseModel[WithdrawalRead]:
    return success_response(
        data=await service.approve_withdrawal(withdrawal_id, payload),
        request_id=current_request_id(),
        message="提现申请已审核通过",
    )


@router.post(
    "/admin/withdrawals/{withdrawal_id}/reject",
    response_model=ResponseModel[WithdrawalRead],
    summary="驳回提现申请",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.WITHDRAWALS_REVIEW))],
)
async def admin_reject_withdrawal(
    withdrawal_id: UUID, payload: WithdrawalReview, service: AdminDistribution
) -> ResponseModel[WithdrawalRead]:
    return success_response(
        data=await service.reject_withdrawal(withdrawal_id, payload),
        request_id=current_request_id(),
        message="提现申请已驳回",
    )


@router.post(
    "/admin/withdrawals/{withdrawal_id}/complete-manually",
    response_model=ResponseModel[WithdrawalRead],
    summary="确认线下转账完成",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.WITHDRAWALS_COMPLETE_MANUAL)),
    ],
)
async def admin_complete_withdrawal_manually(
    withdrawal_id: UUID, payload: WithdrawalManualCompletion, service: AdminDistribution
) -> ResponseModel[WithdrawalRead]:
    return success_response(
        data=await service.complete_withdrawal_manually(withdrawal_id, payload),
        request_id=current_request_id(),
        message="线下转账已确认",
    )
