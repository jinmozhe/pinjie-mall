from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import UserPrincipal, require_admin_csrf, require_permission
from app.api.lifecycle_dependencies import AdminLifecycle, Lifecycle
from app.api.transaction_dependencies import ConsumerTrade
from app.core.context import current_request_id
from app.core.identifiers import new_uuid7
from app.core.pagination import PageResult
from app.core.response import ResponseModel, success_response
from app.domains.admin.permissions import PermissionCode
from app.domains.lifecycle import (
    FulfillmentRead,
    PaymentAttemptCreate,
    PaymentAttemptRead,
    ProductReviewCreate,
    ProductReviewRead,
    ReceiptConfirm,
    ReconciliationRecordCreate,
    ReconciliationRecordRead,
    ReconciliationResolve,
    RefundRequestCreate,
    RefundRequestRead,
    RefundReview,
    ShipmentCreate,
    VirtualDeliveryCreate,
)
from app.domains.orders import OrderAcceptance, OrderRead
from app.domains.orders.schemas import OperationIntentRead
from app.services.trade_query_schemas import (
    ConsumerRefundLookupRead,
    ConsumerRefundRead,
)

router = APIRouter(tags=["支付与售后"])
Page = Annotated[int, Query(ge=1, description="页码，从一开始")]
PageSize = Annotated[int, Query(ge=1, le=100, description="每页数量")]


@router.get(
    "/admin/orders/{order_id}/fulfillment",
    response_model=ResponseModel[FulfillmentRead],
    summary="查看管理订单履约状态",
    dependencies=[Depends(require_permission(PermissionCode.ORDERS_READ))],
)
async def admin_fulfillment_read(order_id: UUID, service: Lifecycle) -> ResponseModel[FulfillmentRead]:
    return success_response(data=await service.admin_fulfillment(order_id), request_id=current_request_id())


@router.post(
    "/orders/{order_id}/payment-attempts",
    response_model=ResponseModel[PaymentAttemptRead],
    status_code=201,
    summary="创建支付意图",
)
async def initiate_payment(
    order_id: UUID, payload: PaymentAttemptCreate, service: Lifecycle, current: UserPrincipal
) -> ResponseModel[PaymentAttemptRead]:
    return success_response(
        data=await service.initiate_payment(current.user.id, order_id, payload),
        request_id=current_request_id(),
    )


@router.get(
    "/orders/{order_id}/fulfillment",
    response_model=ResponseModel[FulfillmentRead],
    summary="查看本人订单履约",
)
async def fulfillment_read(
    order_id: UUID, service: Lifecycle, current: UserPrincipal
) -> ResponseModel[FulfillmentRead]:
    # 资源归属校验：service.fulfillment_for_user 内部通过 user_order(user_id, order_id)
    # 联合过滤 user_id + order_id，非本人订单返回 404，不存在 IDOR 越权风险。
    return success_response(
        data=await service.fulfillment_for_user(current.user.id, order_id),
        request_id=current_request_id(),
    )


@router.post(
    "/orders/{order_id}/fulfillment/confirm-receipt",
    response_model=ResponseModel[FulfillmentRead],
    summary="确认收货",
)
async def confirm_receipt(
    order_id: UUID, payload: ReceiptConfirm, service: Lifecycle, current: UserPrincipal
) -> ResponseModel[FulfillmentRead]:
    return success_response(
        data=await service.confirm_receipt(current.user.id, order_id, payload.revision),
        request_id=current_request_id(),
    )


@router.post(
    "/orders/{order_id}/refunds",
    response_model=ResponseModel[RefundRequestRead],
    status_code=201,
    summary="申请退款",
)
async def refund_create(
    order_id: UUID, payload: RefundRequestCreate, service: Lifecycle, current: UserPrincipal
) -> ResponseModel[RefundRequestRead]:
    return success_response(
        data=await service.create_refund(current.user.id, order_id, payload),
        request_id=current_request_id(),
    )


@router.post(
    "/order-items/{order_item_id}/review",
    response_model=ResponseModel[ProductReviewRead],
    status_code=201,
    summary="评价已交付订单明细",
)
async def review_create(
    order_item_id: UUID, payload: ProductReviewCreate, service: Lifecycle, current: UserPrincipal
) -> ResponseModel[ProductReviewRead]:
    return success_response(
        data=await service.create_review(current.user.id, order_item_id, payload),
        request_id=current_request_id(),
    )


@router.get(
    "/products/{product_id}/reviews",
    response_model=ResponseModel[PageResult[ProductReviewRead]],
    summary="查看公开商品评价",
)
async def review_page(
    product_id: UUID, service: Lifecycle, page: Page = 1, page_size: PageSize = 20
) -> ResponseModel[PageResult[ProductReviewRead]]:
    return success_response(
        data=await service.public_reviews(product_id, page, page_size), request_id=current_request_id()
    )


@router.post(
    "/admin/orders/{order_id}/acceptance",
    response_model=ResponseModel[OrderRead],
    summary="管理员接单",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.ORDERS_ACCEPT))],
)
async def admin_accept_order(
    order_id: UUID, payload: OrderAcceptance, service: AdminLifecycle
) -> ResponseModel[OrderRead]:
    return success_response(data=await service.accept_order(order_id, payload), request_id=current_request_id())


@router.post(
    "/admin/orders/{order_id}/fulfillment/shipment",
    response_model=ResponseModel[FulfillmentRead],
    summary="管理员发货",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.FULFILLMENTS_SHIP))],
)
async def admin_ship(
    order_id: UUID, payload: ShipmentCreate, service: AdminLifecycle
) -> ResponseModel[FulfillmentRead]:
    return success_response(data=await service.ship(order_id, payload), request_id=current_request_id())


@router.post(
    "/admin/orders/{order_id}/fulfillment/virtual-delivery",
    response_model=ResponseModel[FulfillmentRead],
    summary="管理员完成虚拟交付",
    dependencies=[
        Depends(require_admin_csrf),
        Depends(require_permission(PermissionCode.FULFILLMENTS_DELIVER_VIRTUAL)),
    ],
)
async def admin_deliver_virtual(
    order_id: UUID, payload: VirtualDeliveryCreate, service: AdminLifecycle
) -> ResponseModel[FulfillmentRead]:
    return success_response(data=await service.deliver_virtual(order_id, payload), request_id=current_request_id())


@router.post(
    "/admin/refunds/{refund_id}/approve",
    response_model=ResponseModel[RefundRequestRead],
    summary="审核通过退款申请",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.REFUNDS_REVIEW))],
)
async def admin_approve_refund(
    refund_id: UUID, payload: RefundReview, service: AdminLifecycle
) -> ResponseModel[RefundRequestRead]:
    return success_response(data=await service.approve_refund(refund_id, payload), request_id=current_request_id())


@router.post(
    "/admin/refunds/{refund_id}/reject",
    response_model=ResponseModel[RefundRequestRead],
    summary="驳回退款申请",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.REFUNDS_REVIEW))],
)
async def admin_reject_refund(
    refund_id: UUID, payload: RefundReview, service: AdminLifecycle
) -> ResponseModel[RefundRequestRead]:
    return success_response(data=await service.reject_refund(refund_id, payload), request_id=current_request_id())


@router.post(
    "/admin/reconciliation-records",
    response_model=ResponseModel[ReconciliationRecordRead],
    status_code=201,
    summary="导入渠道对账记录",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.RECONCILIATION_IMPORT))],
)
async def admin_reconcile(
    payload: ReconciliationRecordCreate, service: AdminLifecycle
) -> ResponseModel[ReconciliationRecordRead]:
    return success_response(data=await service.reconcile(payload), request_id=current_request_id())


@router.post(
    "/admin/reconciliation-records/{record_id}/resolve",
    response_model=ResponseModel[ReconciliationRecordRead],
    summary="处置对账差异",
    dependencies=[Depends(require_admin_csrf), Depends(require_permission(PermissionCode.RECONCILIATION_RESOLVE))],
)
async def admin_resolve_reconciliation(
    record_id: UUID, payload: ReconciliationResolve, service: AdminLifecycle
) -> ResponseModel[ReconciliationRecordRead]:
    return success_response(
        data=await service.resolve_reconciliation(record_id, payload), request_id=current_request_id()
    )


@router.get("/refunds/intent", response_model=ResponseModel[OperationIntentRead], summary="取得新的退款请求号")
async def refund_intent(current: UserPrincipal) -> ResponseModel[OperationIntentRead]:
    return success_response(data=OperationIntentRead(request_id=new_uuid7()), request_id=current_request_id())


@router.get(
    "/refunds", response_model=ResponseModel[PageResult[ConsumerRefundRead]], summary="分页读取本人整单售后记录"
)
async def refund_list(
    trade: ConsumerTrade,
    current: UserPrincipal,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    order_id: UUID | None = None,
) -> ResponseModel[PageResult[ConsumerRefundRead]]:
    return success_response(
        data=await trade.refunds(current.user.id, page, page_size, order_id), request_id=current_request_id()
    )


@router.get(
    "/refunds/by-request/{request_id}",
    response_model=ResponseModel[ConsumerRefundLookupRead],
    summary="按原请求号确认本人退款受理事实",
)
async def refund_lookup(
    request_id: UUID, trade: ConsumerTrade, current: UserPrincipal
) -> ResponseModel[ConsumerRefundLookupRead]:
    return success_response(
        data=await trade.refund_by_request(current.user.id, request_id), request_id=current_request_id()
    )


@router.get(
    "/refunds/{refund_id}", response_model=ResponseModel[ConsumerRefundRead], summary="读取本人售后审核与资金事实"
)
async def refund_detail(
    refund_id: UUID, trade: ConsumerTrade, current: UserPrincipal
) -> ResponseModel[ConsumerRefundRead]:
    return success_response(data=await trade.refund(current.user.id, refund_id), request_id=current_request_id())
