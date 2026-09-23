from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.identifiers import new_uuid7
from app.db.models import WalletAccount, WalletLedger


class WalletLedgerService:
    """Applies a single wallet mutation and its immutable ledger entry in one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply_in_open_transaction(
        self,
        *,
        wallet_id: UUID,
        entry_type: str,
        amount: Decimal,
        frozen_delta: Decimal,
        debt_delta: Decimal,
        idempotency_key: str,
        reference_type: str,
        reference_id: UUID,
    ) -> WalletLedger:
        wallet = await self._wallet(wallet_id, lock=True)
        existing = await self._ledger_by_key(idempotency_key, lock=False)
        if existing is not None:
            if (
                existing.wallet_id != wallet_id
                or existing.entry_type != entry_type
                or existing.amount != amount
                or existing.frozen_delta != frozen_delta
                or existing.debt_delta != debt_delta
                or existing.reference_type != reference_type
                or existing.reference_id != reference_id
            ):
                raise AppException(
                    status_code=409, code=ErrorCode.STATE_CONFLICT, message="钱包幂等键已用于其他记账内容"
                )
            return existing
        available = wallet.available_amount + amount
        frozen = wallet.frozen_amount + frozen_delta
        debt = wallet.debt_amount + debt_delta
        if min(available, frozen, debt) < 0 or amount == 0 and frozen_delta == 0 and debt_delta == 0:
            raise AppException(
                status_code=409, code=ErrorCode.WALLET_INSUFFICIENT_BALANCE, message="钱包余额变动不合法"
            )
        wallet.available_amount = available
        wallet.frozen_amount = frozen
        wallet.debt_amount = debt
        wallet.revision += 1
        balance_after = {
            "schema_version": "1",
            "available_amount": f"{available:.2f}",
            "frozen_amount": f"{frozen:.2f}",
            "debt_amount": f"{debt:.2f}",
        }
        ledger = WalletLedger(
            id=new_uuid7(),
            wallet_id=wallet.id,
            entry_type=entry_type,
            amount=amount,
            frozen_delta=frozen_delta,
            debt_delta=debt_delta,
            idempotency_key=idempotency_key,
            reference_type=reference_type,
            reference_id=reference_id,
            wallet_revision=wallet.revision,
            balance_after=balance_after,
        )
        self._session.add(wallet)
        self._session.add(ledger)
        await self._session.flush()
        return ledger

    async def _wallet(self, wallet_id: UUID, *, lock: bool) -> WalletAccount:
        statement = select(WalletAccount).where(WalletAccount.id == wallet_id).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        wallet = (await self._session.scalars(statement)).one_or_none()
        if wallet is None:
            raise AppException(status_code=404, code=ErrorCode.NOT_FOUND, message="钱包不存在")
        return wallet

    async def _ledger_by_key(self, idempotency_key: str, *, lock: bool) -> WalletLedger | None:
        statement = (
            select(WalletLedger)
            .where(WalletLedger.idempotency_key == idempotency_key)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return (await self._session.scalars(statement)).one_or_none()


__all__ = ["WalletLedgerService"]
