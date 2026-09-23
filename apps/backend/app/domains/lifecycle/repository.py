from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.commerce_lifecycle import (
    Fulfillment,
    FulfillmentEvent,
    PaymentAttempt,
    PaymentEvent,
    ProductReview,
    ReconciliationRecord,
    RefundAttempt,
    RefundEvent,
    RefundItem,
    RefundRequest,
)


class LifecycleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_key(self, kind: str, value: str) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"pinjie:lifecycle:{kind}:{value}"}
        )

    async def payment_by_request(self, user_id: UUID, request_id: UUID, *, lock: bool = False) -> PaymentAttempt | None:
        statement = select(PaymentAttempt).where(
            PaymentAttempt.user_id == user_id, PaymentAttempt.request_id == request_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def payment(self, payment_attempt_id: UUID, *, lock: bool = False) -> PaymentAttempt | None:
        statement = select(PaymentAttempt).where(PaymentAttempt.id == payment_attempt_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def payment_by_transaction(
        self, channel: str, channel_transaction_id: str, *, lock: bool = False
    ) -> PaymentAttempt | None:
        statement = select(PaymentAttempt).where(
            PaymentAttempt.channel == channel,
            PaymentAttempt.channel_transaction_id == channel_transaction_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def fulfillment(self, order_id: UUID, *, lock: bool = False) -> Fulfillment | None:
        statement = select(Fulfillment).where(Fulfillment.order_id == order_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def fulfillment_by_id(self, fulfillment_id: UUID, *, lock: bool = False) -> Fulfillment | None:
        statement = select(Fulfillment).where(Fulfillment.id == fulfillment_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def count_due_fulfillments(self, now: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Fulfillment)
                .where(Fulfillment.status == "shipped", Fulfillment.auto_confirm_at <= now)
            )
            or 0
        )

    async def due_fulfillments(self, now: datetime, limit: int) -> list[Fulfillment]:
        return list(
            await self.session.scalars(
                select(Fulfillment)
                .where(Fulfillment.status == "shipped", Fulfillment.auto_confirm_at <= now)
                .order_by(Fulfillment.auto_confirm_at, Fulfillment.id)
                .limit(limit)
            )
        )

    async def refund_by_request(self, user_id: UUID, request_id: UUID, *, lock: bool = False) -> RefundRequest | None:
        statement = select(RefundRequest).where(
            RefundRequest.user_id == user_id, RefundRequest.request_id == request_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def refund(self, refund_id: UUID, *, lock: bool = False) -> RefundRequest | None:
        statement = select(RefundRequest).where(RefundRequest.id == refund_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def refund_attempt(self, refund_attempt_id: UUID, *, lock: bool = False) -> RefundAttempt | None:
        statement = select(RefundAttempt).where(RefundAttempt.id == refund_attempt_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def refund_attempt_for_request(self, refund_request_id: UUID, *, lock: bool = False) -> RefundAttempt | None:
        statement = select(RefundAttempt).where(RefundAttempt.refund_request_id == refund_request_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def refund_attempt_by_channel(
        self, channel: str, channel_refund_id: str, *, lock: bool = False
    ) -> RefundAttempt | None:
        statement = select(RefundAttempt).where(
            RefundAttempt.channel == channel, RefundAttempt.channel_refund_id == channel_refund_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def refund_attempts_for_payment(self, payment_attempt_id: UUID, *, lock: bool = False) -> list[RefundAttempt]:
        statement = (
            select(RefundAttempt)
            .where(RefundAttempt.payment_attempt_id == payment_attempt_id)
            .order_by(RefundAttempt.id)
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list(await self.session.scalars(statement))

    async def user_refund(self, user_id: UUID, refund_id: UUID) -> RefundRequest | None:
        return (
            await self.session.scalars(
                select(RefundRequest).where(RefundRequest.user_id == user_id, RefundRequest.id == refund_id)
            )
        ).one_or_none()

    async def refunds_for_order(self, order_id: UUID, *, lock: bool = False) -> list[RefundRequest]:
        statement = select(RefundRequest).where(RefundRequest.order_id == order_id).order_by(RefundRequest.id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list(await self.session.scalars(statement))

    async def refund_items(self, refund_ids: list[UUID], *, lock: bool = False) -> list[RefundItem]:
        if not refund_ids:
            return []
        statement = (
            select(RefundItem).where(RefundItem.refund_request_id.in_(refund_ids)).order_by(RefundItem.order_item_id)
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return list(await self.session.scalars(statement))

    async def review_for_item(self, user_id: UUID, order_item_id: UUID, *, lock: bool = False) -> ProductReview | None:
        statement = select(ProductReview).where(
            ProductReview.user_id == user_id, ProductReview.order_item_id == order_item_id
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def public_reviews(self, product_id: UUID, page: int, page_size: int) -> tuple[list[ProductReview], int]:
        filters = (ProductReview.product_id == product_id, ProductReview.is_published.is_(True))
        total = int(await self.session.scalar(select(func.count()).select_from(ProductReview).where(*filters)) or 0)
        rows = list(
            await self.session.scalars(
                select(ProductReview)
                .where(*filters)
                .order_by(ProductReview.published_at.desc(), ProductReview.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return rows, total

    async def reconciliation(
        self, channel: str, record_type: str, channel_transaction_id: str, *, lock: bool = False
    ) -> ReconciliationRecord | None:
        statement = select(ReconciliationRecord).where(
            ReconciliationRecord.channel == channel,
            ReconciliationRecord.record_type == record_type,
            ReconciliationRecord.channel_transaction_id == channel_transaction_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self.session.scalars(statement)).one_or_none()

    async def refund_page(self, page: int, page_size: int) -> tuple[list[RefundRequest], int]:
        total = int(await self.session.scalar(select(func.count()).select_from(RefundRequest)) or 0)
        rows = await self.session.scalars(
            select(RefundRequest).order_by(RefundRequest.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows), total

    async def save(
        self,
        value: PaymentAttempt
        | PaymentEvent
        | Fulfillment
        | FulfillmentEvent
        | RefundRequest
        | RefundAttempt
        | RefundEvent
        | RefundItem
        | ProductReview
        | ReconciliationRecord,
    ) -> None:
        self.session.add(value)
        await self.session.flush()
