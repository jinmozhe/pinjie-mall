from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from loguru import logger
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.db.transaction import transaction_scope
from app.domains.distribution.service import DistributionService
from app.domains.durable_tasks.service import DurableTaskService, LeasedTask, TaskDeferred
from app.services.orders import OrderService
from app.services.payment_lifecycle import LifecycleService
from app.services.wechat_pay import WechatPaymentService
from app.services.wechat_pay_client import WechatPayClient
from app.services.wechat_shipping import WechatShippingService


@dataclass(frozen=True, slots=True)
class DurableTaskRunResult:
    leased: int
    succeeded: int
    retried: int
    attention: int
    lease_lost: int
    deferred: int = 0


class DurableTaskRunner:
    """Runs one bounded batch without holding a task lease transaction during business work."""

    _INTERNAL_HANDLERS = frozenset(
        {"expire_order", "confirm_order", "auto_confirm_fulfillment", "refund_followup", "commission_settlement"}
    )

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        settings: Settings | None = None,
        wechat_pay: WechatPayClient | None = None,
        wechat_http: httpx.AsyncClient | None = None,
        redis: Redis | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings, self._wechat_pay = settings, wechat_pay
        self._wechat_http, self._redis = wechat_http, redis

    async def due_count(self) -> int:
        async with self._session_factory() as session:
            return await DurableTaskService(session).due_count()

    async def run_once(self, *, limit: int, lease_seconds: int, retry_delay_seconds: int) -> DurableTaskRunResult:
        if not 1 <= retry_delay_seconds <= 900:
            raise ValueError("retry_delay_seconds must be between 1 and 900")
        if not 1 <= limit <= 100 or (self._wechat_pay is not None and lease_seconds < 45):
            raise ValueError("channel workers require limit 1..100 and lease_seconds >= 45")
        succeeded = retried = attention = lease_lost = 0
        leased = deferred = 0
        for _ in range(limit):
            tasks = await self._lease(1, lease_seconds)
            if not tasks:
                break
            task = tasks[0]
            leased += 1
            try:
                await self._execute(task)
            except TaskDeferred as exc:
                try:
                    async with self._session_factory() as session, transaction_scope(session):
                        await DurableTaskService(session).defer_in_open_transaction(
                            task.id, task.lease_token, exc.seconds
                        )
                    deferred += 1
                except AppException as lease_error:
                    if lease_error.code != ErrorCode.DURABLE_TASK_LEASE_CONFLICT.value:
                        raise
                    lease_lost += 1
            except AppException as exc:
                outcome = await self._retry(task, exc.code, exc.message, retry_delay_seconds)
                retried += outcome == "pending"
                attention += outcome == "attention"
                lease_lost += outcome == "lease_lost"
            except Exception as exc:
                logger.bind(task_id=str(task.id), task_type=task.task_type).opt(exception=exc).error(
                    "durable task execution failed"
                )
                outcome = await self._retry(
                    task,
                    ErrorCode.INTERNAL_ERROR.value,
                    f"任务处理抛出未预期异常：{type(exc).__name__}",
                    retry_delay_seconds,
                )
                retried += outcome == "pending"
                attention += outcome == "attention"
                lease_lost += outcome == "lease_lost"
            else:
                if await self._complete(task):
                    succeeded += 1
                else:
                    lease_lost += 1
        return DurableTaskRunResult(
            leased=leased,
            succeeded=succeeded,
            retried=retried,
            attention=attention,
            lease_lost=lease_lost,
            deferred=deferred,
        )

    async def _lease(self, limit: int, lease_seconds: int) -> list[LeasedTask]:
        async with self._session_factory() as session, transaction_scope(session):
            return await DurableTaskService(session).lease_in_open_transaction(limit=limit, lease_seconds=lease_seconds)

    async def _execute(self, task: LeasedTask) -> None:
        if task.task_type == "wechat_shipping" and self._settings is not None:
            async with self._session_factory() as session:
                await WechatShippingService(session, self._settings, self._wechat_http, self._redis).upload(
                    self._payload_uuid(task, "fulfillment_id")
                )
            return
        if (
            task.task_type
            in {
                "payment_submit",
                "payment_query",
                "payment_close",
                "refund_submit",
                "refund_query",
                "wechat_notification",
            }
            and self._settings is not None
        ):
            async with self._session_factory() as session:
                service = WechatPaymentService(session, self._settings, self._wechat_pay)
                if task.task_type == "wechat_notification":
                    await service.process_notification(self._payload_uuid(task, "notification_id"))
                elif task.task_type.startswith("refund_"):
                    await service.refund(
                        self._payload_uuid(task, "refund_attempt_id"), submit=task.task_type == "refund_submit"
                    )
                elif task.task_type == "payment_submit":
                    await service.submit(self._payload_uuid(task, "payment_attempt_id"))
                else:
                    await service.query(
                        self._payload_uuid(task, "payment_attempt_id"), close=task.task_type == "payment_close"
                    )
            return
        if task.task_type not in self._INTERNAL_HANDLERS:
            raise AppException(
                status_code=503,
                code=ErrorCode.SERVICE_UNAVAILABLE,
                message=f"任务 {task.task_type} 需要可信渠道适配器，当前未接入",
            )
        if task.task_type == "expire_order":
            order_id = self._payload_uuid(task, "order_id")
            async with self._session_factory() as session:
                await OrderService(session).expire_scheduled(order_id)
            return
        if task.task_type == "confirm_order":
            payment_attempt_id = self._payload_uuid(task, "payment_attempt_id")
            async with self._session_factory() as session:
                await LifecycleService(session).confirm_order_scheduled(payment_attempt_id)
            return
        if task.task_type == "auto_confirm_fulfillment":
            fulfillment_id = self._payload_uuid(task, "fulfillment_id")
            async with self._session_factory() as session:
                await LifecycleService(session).auto_confirm_scheduled(fulfillment_id)
            return
        if task.task_type == "refund_followup":
            refund_attempt_id = self._payload_uuid(task, "refund_attempt_id")
            async with self._session_factory() as session:
                await LifecycleService(session).complete_refund_scheduled(refund_attempt_id)
            return
        order_id = self._payload_uuid(task, "order_id")
        async with self._session_factory() as session:
            await DistributionService(session).settle_order_scheduled(order_id)

    @staticmethod
    def _payload_uuid(task: LeasedTask, key: str) -> UUID:
        if set(task.payload) != {"schema_version", key} or task.payload.get("schema_version") != 1:
            raise AppException(status_code=409, code=ErrorCode.VALIDATION_ERROR, message="持久任务载荷结构无效")
        value = task.payload.get(key)
        if not isinstance(value, str):
            raise AppException(status_code=409, code=ErrorCode.VALIDATION_ERROR, message="持久任务业务标识无效")
        try:
            return UUID(value)
        except ValueError as exc:
            raise AppException(
                status_code=409, code=ErrorCode.VALIDATION_ERROR, message="持久任务业务标识无效"
            ) from exc

    async def _complete(self, task: LeasedTask) -> bool:
        try:
            async with self._session_factory() as session, transaction_scope(session):
                await DurableTaskService(session).complete_in_open_transaction(
                    task_id=task.id, lease_token=task.lease_token
                )
            return True
        except AppException as exc:
            if exc.code == ErrorCode.DURABLE_TASK_LEASE_CONFLICT.value:
                logger.bind(task_id=str(task.id), task_type=task.task_type).warning(
                    "durable task lease lost before completion"
                )
                return False
            raise

    async def _retry(self, task: LeasedTask, error_code: str, error_summary: str, retry_delay_seconds: int) -> str:
        try:
            async with self._session_factory() as session, transaction_scope(session):
                return await DurableTaskService(session).retry_in_open_transaction(
                    task_id=task.id,
                    lease_token=task.lease_token,
                    error_code=error_code,
                    error_summary=error_summary,
                    retry_delay_seconds=retry_delay_seconds,
                )
        except AppException as exc:
            if exc.code == ErrorCode.DURABLE_TASK_LEASE_CONFLICT.value:
                logger.bind(task_id=str(task.id), task_type=task.task_type).warning(
                    "durable task lease lost before retry"
                )
                return "lease_lost"
            raise


__all__ = ["DurableTaskRunResult", "DurableTaskRunner"]
