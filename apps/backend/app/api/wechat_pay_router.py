import asyncio
from typing import Annotated, cast
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.dependencies import DatabaseSession, PhoneUserPrincipal, get_request_settings, get_resources
from app.core.context import current_request_id
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.core.response import ResponseModel, success_response
from app.domains.lifecycle import PaymentStatusRead
from app.domains.lifecycle.schemas import WechatReceiptRead
from app.domains.orders.schemas import OperationIntentRead
from app.services.wechat_pay import WechatPaymentService
from app.services.wechat_pay_client import WechatPayClient
from app.services.wechat_shipping import WechatShippingService

router = APIRouter(tags=["支付与售后"])


def payment_service(request: Request, session: DatabaseSession) -> WechatPaymentService:
    return WechatPaymentService(
        session,
        get_request_settings(request),
        cast(WechatPayClient | None, getattr(request.app.state, "wechat_pay", None)),
    )


WechatPayment = Annotated[WechatPaymentService, Depends(payment_service)]


@router.get(
    "/orders/{order_id}/wechat-receipt",
    response_model=ResponseModel[WechatReceiptRead],
    summary="核对本人微信平台收货状态",
)
async def wechat_receipt(
    order_id: UUID, request: Request, current: PhoneUserPrincipal, session: DatabaseSession
) -> ResponseModel[WechatReceiptRead]:
    resources = get_resources(request)
    service = WechatShippingService(session, get_request_settings(request), resources.wechat_http, resources.redis)
    return success_response(data=await service.receipt(current.user.id, order_id), request_id=current_request_id())


@router.get("/payments/intent", response_model=ResponseModel[OperationIntentRead], summary="生成本人支付请求号")
async def payment_intent(current: PhoneUserPrincipal) -> ResponseModel[OperationIntentRead]:
    del current
    return success_response(data=OperationIntentRead(request_id=new_uuid7()), request_id=current_request_id())


@router.get(
    "/orders/{order_id}/payment-status",
    response_model=ResponseModel[PaymentStatusRead],
    summary="查询本人支付与渠道能力",
)
async def payment_status(
    order_id: UUID, current: PhoneUserPrincipal, service: WechatPayment
) -> ResponseModel[PaymentStatusRead]:
    return success_response(data=await service.status(current.user.id, order_id), request_id=current_request_id())


@router.get(
    "/orders/{order_id}/payment-attempts/by-request/{request_id}",
    response_model=ResponseModel[PaymentStatusRead],
    summary="按本人请求号恢复支付意图",
)
async def payment_by_request(
    order_id: UUID, request_id: UUID, current: PhoneUserPrincipal, service: WechatPayment
) -> ResponseModel[PaymentStatusRead]:
    return success_response(
        data=await service.status(current.user.id, order_id, request_id), request_id=current_request_id()
    )


async def notification(request: Request, service: WechatPayment, *, refund: bool) -> Response:
    try:
        async with asyncio.timeout(4):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse({"code": "FAIL", "message": "通知过大"}, status_code=413)
            await service.receive(httpx.Headers(request.headers), bytes(body), refund=refund)
        return Response(status_code=204)
    except AppException as exc:
        logger.bind(request_id=current_request_id(), code=exc.code).warning("wechat notification rejected")
        return JSONResponse({"code": "FAIL", "message": "通知未接收，请重试"}, status_code=exc.status_code)
    except Exception as exc:
        # No raw body or provider payload in logs, including cryptographic failures.
        logger.bind(request_id=current_request_id(), error_type=type(exc).__name__).error(
            "wechat notification persistence failed"
        )
        return JSONResponse({"code": "FAIL", "message": "通知未接收，请重试"}, status_code=503)


@router.post("/payments/wechat/notify", status_code=204, response_class=Response, summary="接收微信支付可信通知")
async def payment_notify(request: Request, service: WechatPayment) -> Response:
    return await notification(request, service, refund=False)


@router.post("/refunds/wechat/notify", status_code=204, response_class=Response, summary="接收微信退款可信通知")
async def refund_notify(request: Request, service: WechatPayment) -> Response:
    return await notification(request, service, refund=True)
