from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import UserPrincipal, require_admin_csrf, require_permission
from app.api.distribution_dependencies import AdminDistribution, ConsumerEngagement, ConsumerFinance
from app.core.context import current_request_id
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.distribution import (
    ReferralBindIn,
    WithdrawalManualCompletion,
    WithdrawalRead,
    WithdrawalReview,
)
from app.services.engagement_schemas import (
    ConsumerReferralRead,
)
from app.services.finance_query_schemas import (
    ConsumerCommissionRead,
    ConsumerMemberRead,
    ConsumerWalletLedgerRead,
    ConsumerWalletRead,
    ConsumerWithdrawalRead,
    WalletType,
)

router = APIRouter(tags=["会员分销"])
Page = Annotated[int, Query(ge=1, description="页码，从一开始")]
PageSize = Annotated[int, Query(ge=1, le=100, description="每页数量")]


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


@router.get(
    "/distribution/me/referrer", response_model=ResponseModel[ConsumerReferralRead], summary="查询本人推荐码及绑定事实"
)
async def referral(
    service: ConsumerEngagement,
    current: UserPrincipal,
    invitation_code: str | None = Query(default=None, min_length=8, max_length=16, pattern=r"^[A-Z0-9]+$"),
) -> ResponseModel[ConsumerReferralRead]:
    return success_response(
        data=await service.referral(current.user.id, invitation_code), request_id=current_request_id()
    )


@router.post(
    "/distribution/me/referrer",
    response_model=ResponseModel[ConsumerReferralRead],
    summary="主动首次绑定本人推荐关系",
    description="服务端校验首次绑定、自邀与循环；同码幂等。未知结果查询本人关系与原码是否匹配，不自动换码重试。",
)
async def referral_bind(
    payload: ReferralBindIn, service: ConsumerEngagement, current: UserPrincipal
) -> ResponseModel[ConsumerReferralRead]:
    return success_response(data=await service.bind(current.user.id, payload), request_id=current_request_id())


@router.get(
    "/distribution/me/profile",
    response_model=ResponseModel[ConsumerMemberRead],
    summary="读取本人档案和会员等级有效状态",
)
async def membership(service: ConsumerFinance, current: UserPrincipal) -> ResponseModel[ConsumerMemberRead]:
    return success_response(data=await service.member(current.user.id), request_id=current_request_id())


@router.post(
    "/distribution/me/profile", response_model=ResponseModel[ConsumerMemberRead], summary="主动幂等开通本人会员分销档案"
)
async def membership_activate(service: ConsumerFinance, current: UserPrincipal) -> ResponseModel[ConsumerMemberRead]:
    return success_response(data=await service.activate(current.user.id), request_id=current_request_id())


@router.get(
    "/distribution/me/wallets", response_model=ResponseModel[list[ConsumerWalletRead]], summary="查询本人双轨钱包"
)
async def wallets(service: ConsumerFinance, current: UserPrincipal) -> ResponseModel[list[ConsumerWalletRead]]:
    return success_response(data=await service.wallets(current.user.id), request_id=current_request_id())


@router.get(
    "/distribution/me/wallets/{wallet_type}/ledgers",
    response_model=ResponseModel[PageResult[ConsumerWalletLedgerRead]],
    summary="分页查询本人指定轨道钱包流水",
)
async def wallet_ledgers(
    wallet_type: WalletType,
    service: ConsumerFinance,
    current: UserPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel[PageResult[ConsumerWalletLedgerRead]]:
    return success_response(
        data=await service.ledgers(current.user.id, wallet_type, page, page_size), request_id=current_request_id()
    )


@router.get(
    "/distribution/me/commissions",
    response_model=ResponseModel[PageResult[ConsumerCommissionRead]],
    summary="分页查询本人安全佣金记录",
)
async def commissions(
    service: ConsumerFinance,
    current: UserPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel[PageResult[ConsumerCommissionRead]]:
    return success_response(
        data=await service.commissions(current.user.id, page, page_size), request_id=current_request_id()
    )


@router.get(
    "/distribution/me/withdrawals",
    response_model=ResponseModel[PageResult[ConsumerWithdrawalRead]],
    summary="分页查询本人历史提现审核和确认事实",
)
async def withdrawals(
    service: ConsumerFinance,
    current: UserPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel[PageResult[ConsumerWithdrawalRead]]:
    return success_response(
        data=await service.withdrawals(current.user.id, page, page_size), request_id=current_request_id()
    )
