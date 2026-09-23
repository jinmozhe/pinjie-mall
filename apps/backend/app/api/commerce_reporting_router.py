"""管理运营查询与选中导出，所有路由显式声明精确资源权限。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import (
    CurrentAdmin,
    DatabaseSession,
    get_current_admin,
    get_resources,
    require_admin_csrf,
    require_permission,
)
from app.core.context import current_request_id
from app.core.pagination import PageResult
from app.core.request_metadata import request_metadata
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.distribution import CommissionRead, MemberProfileRead, WithdrawalRead
from app.domains.lifecycle import PaymentAttemptRead, ReconciliationRecordRead, RefundAttemptRead, RefundRequestRead
from app.domains.orders.schemas import AdminOrderSummary
from app.services.commerce_reporting import (
    AdminWalletRead,
    CommerceExportRead,
    CommerceFilters,
    CommerceReportingService,
    SelectedCommerceIds,
    WalletLedgerRead,
)
from app.services.security_events import AuditCoordinator

router = APIRouter(tags=["商城运营查询"])


def get_commerce_reporting_service(
    request: Request,
    session: DatabaseSession,
    current: Annotated[CurrentAdmin, Depends(get_current_admin)],
) -> CommerceReportingService:
    resources = get_resources(request)
    return CommerceReportingService(
        session,
        AuditCoordinator(
            session=session,
            session_factory=resources.session_factory,
            actor_id=current.admin.id,
            metadata=request_metadata(request),
        ),
    )


Reporting = Annotated[CommerceReportingService, Depends(get_commerce_reporting_service)]
Filters = Annotated[CommerceFilters, Query()]


@router.get(
    "/admin/orders",
    response_model=ResponseModel[PageResult[AdminOrderSummary]],
    summary="查询订单列表",
    dependencies=[Depends(require_permission(PermissionCode.ORDERS_READ))],
)
async def orders_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[AdminOrderSummary]]:
    return success_response(
        data=await service.page("orders", AdminOrderSummary, filters), request_id=current_request_id()
    )


@router.post(
    "/admin/orders/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中订单",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.ORDERS_READ)),
        Depends(require_permission(PermissionCode.ORDERS_EXPORT)),
    ],
)
async def orders_export(service: Reporting, payload: SelectedCommerceIds) -> ResponseModel[CommerceExportRead]:
    return success_response(data=await service.export("orders", payload), request_id=current_request_id())


@router.get(
    "/admin/refunds",
    response_model=ResponseModel[PageResult[RefundRequestRead]],
    summary="查询退款列表",
    dependencies=[Depends(require_permission(PermissionCode.REFUNDS_READ))],
)
async def refunds_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[RefundRequestRead]]:
    return success_response(
        data=await service.page("refunds", RefundRequestRead, filters), request_id=current_request_id()
    )


@router.post(
    "/admin/refunds/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中退款",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.REFUNDS_READ)),
        Depends(require_permission(PermissionCode.REFUNDS_EXPORT)),
    ],
)
async def refunds_export(service: Reporting, payload: SelectedCommerceIds) -> ResponseModel[CommerceExportRead]:
    return success_response(data=await service.export("refunds", payload), request_id=current_request_id())


@router.get(
    "/admin/withdrawals",
    response_model=ResponseModel[PageResult[WithdrawalRead]],
    summary="查询提现列表",
    dependencies=[Depends(require_permission(PermissionCode.WITHDRAWALS_READ))],
)
async def withdrawals_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[WithdrawalRead]]:
    return success_response(
        data=await service.page("withdrawals", WithdrawalRead, filters), request_id=current_request_id()
    )


@router.post(
    "/admin/withdrawals/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中提现",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.WITHDRAWALS_READ)),
        Depends(require_permission(PermissionCode.WITHDRAWALS_EXPORT)),
    ],
)
async def withdrawals_export(service: Reporting, payload: SelectedCommerceIds) -> ResponseModel[CommerceExportRead]:
    return success_response(data=await service.export("withdrawals", payload), request_id=current_request_id())


@router.get(
    "/admin/payments",
    response_model=ResponseModel[PageResult[PaymentAttemptRead]],
    summary="查询支付列表",
    dependencies=[Depends(require_permission(PermissionCode.PAYMENTS_READ))],
)
async def payments_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[PaymentAttemptRead]]:
    return success_response(
        data=await service.page("payments", PaymentAttemptRead, filters), request_id=current_request_id()
    )


@router.post(
    "/admin/payments/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中支付",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.PAYMENTS_READ)),
        Depends(require_permission(PermissionCode.PAYMENTS_EXPORT)),
    ],
)
async def payments_export(service: Reporting, payload: SelectedCommerceIds) -> ResponseModel[CommerceExportRead]:
    return success_response(data=await service.export("payments", payload), request_id=current_request_id())


@router.get(
    "/admin/reconciliation-records",
    response_model=ResponseModel[PageResult[ReconciliationRecordRead]],
    summary="查询对账列表",
    dependencies=[Depends(require_permission(PermissionCode.RECONCILIATION_READ))],
)
async def reconciliation_records_page(
    service: Reporting, filters: Filters
) -> ResponseModel[PageResult[ReconciliationRecordRead]]:
    return success_response(
        data=await service.page("reconciliation-records", ReconciliationRecordRead, filters),
        request_id=current_request_id(),
    )


@router.post(
    "/admin/reconciliation-records/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中对账",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.RECONCILIATION_READ)),
        Depends(require_permission(PermissionCode.RECONCILIATION_EXPORT)),
    ],
)
async def reconciliation_records_export(
    service: Reporting, payload: SelectedCommerceIds
) -> ResponseModel[CommerceExportRead]:
    return success_response(
        data=await service.export("reconciliation-records", payload), request_id=current_request_id()
    )


@router.get(
    "/admin/members",
    response_model=ResponseModel[PageResult[MemberProfileRead]],
    summary="查询会员与推荐关系列表",
    dependencies=[Depends(require_permission(PermissionCode.MEMBERS_READ))],
)
async def members_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[MemberProfileRead]]:
    return success_response(
        data=await service.page("members", MemberProfileRead, filters), request_id=current_request_id()
    )


@router.post(
    "/admin/members/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中会员与推荐关系",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.MEMBERS_READ)),
        Depends(require_permission(PermissionCode.MEMBERS_EXPORT)),
    ],
)
async def members_export(service: Reporting, payload: SelectedCommerceIds) -> ResponseModel[CommerceExportRead]:
    return success_response(data=await service.export("members", payload), request_id=current_request_id())


@router.get(
    "/admin/commissions",
    response_model=ResponseModel[PageResult[CommissionRead]],
    summary="查询佣金列表",
    dependencies=[Depends(require_permission(PermissionCode.COMMISSIONS_READ))],
)
async def commissions_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[CommissionRead]]:
    return success_response(
        data=await service.page("commissions", CommissionRead, filters), request_id=current_request_id()
    )


@router.post(
    "/admin/commissions/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中佣金",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.COMMISSIONS_READ)),
        Depends(require_permission(PermissionCode.COMMISSIONS_EXPORT)),
    ],
)
async def commissions_export(service: Reporting, payload: SelectedCommerceIds) -> ResponseModel[CommerceExportRead]:
    return success_response(data=await service.export("commissions", payload), request_id=current_request_id())


@router.get(
    "/admin/wallets",
    response_model=ResponseModel[PageResult[AdminWalletRead]],
    summary="查询钱包列表",
    dependencies=[Depends(require_permission(PermissionCode.WALLETS_READ))],
)
async def wallets_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[AdminWalletRead]]:
    return success_response(
        data=await service.page("wallets", AdminWalletRead, filters), request_id=current_request_id()
    )


@router.post(
    "/admin/wallets/export",
    response_model=ResponseModel[CommerceExportRead],
    summary="导出选中钱包",
    description="仅导出一至一百条选中记录的公开字段，不修改业务状态。",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.WALLETS_READ)),
        Depends(require_permission(PermissionCode.WALLETS_EXPORT)),
    ],
)
async def wallets_export(service: Reporting, payload: SelectedCommerceIds) -> ResponseModel[CommerceExportRead]:
    return success_response(data=await service.export("wallets", payload), request_id=current_request_id())


@router.get(
    "/admin/wallets/{wallet_id}/ledgers",
    response_model=ResponseModel[PageResult[WalletLedgerRead]],
    summary="查询钱包不可变流水",
    dependencies=[Depends(require_permission(PermissionCode.WALLETS_READ))],
)
async def wallet_ledgers(
    service: Reporting,
    wallet_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResponseModel[PageResult[WalletLedgerRead]]:
    return success_response(data=await service.ledgers(wallet_id, page, page_size), request_id=current_request_id())


@router.get(
    "/admin/refund-executions",
    response_model=ResponseModel[PageResult[RefundAttemptRead]],
    summary="查询退款执行列表",
    dependencies=[Depends(require_permission(PermissionCode.REFUNDS_READ))],
)
async def refund_executions_page(service: Reporting, filters: Filters) -> ResponseModel[PageResult[RefundAttemptRead]]:
    return success_response(
        data=await service.page("refund-executions", RefundAttemptRead, filters), request_id=current_request_id()
    )
