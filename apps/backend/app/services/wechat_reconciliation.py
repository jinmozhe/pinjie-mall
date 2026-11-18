import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.domains.lifecycle import ReconciliationRecordCreate
from app.services.wechat_pay_client import PayProtocolError, payload_hash


def parse_bill(
    content: bytes, *, merchant_id: str, bill_date: str, kind: Literal["SUCCESS", "REFUND"]
) -> tuple[list[ReconciliationRecordCreate], int]:
    """Parse the documented current bill format; reject legacy or partial input."""
    try:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
        header = [value.strip() for value in rows[0]]
        required = {"商户号", "公众账号ID", "微信订单号", "商户订单号", "交易时间", "货币种类", "订单金额", "交易状态"}
        if kind == "REFUND":
            required |= {"微信退款单号", "商户退款单号", "申请退款金额", "退款成功时间", "退款状态"}
        if not required.issubset(header) or len(header) != len(set(header)):
            raise ValueError("unsupported bill format")
        results: list[ReconciliationRecordCreate] = []
        pending = 0
        summary_found = False
        detail_count = 0
        for index, row in enumerate(rows[1:], 1):
            if row and row[0].strip() == "总交易单数":
                summary_found = True
                if index + 1 != len(rows) - 1 or int(rows[index + 1][0].strip().removeprefix("`")) != detail_count:
                    raise ValueError("bill summary mismatch")
                break
            if len(row) != len(header):
                raise ValueError("invalid bill row")
            values = dict(zip(header, (value.removeprefix("`").strip() for value in row), strict=True))
            if values["商户号"] != merchant_id or values["货币种类"] != "CNY":
                raise ValueError("merchant or currency mismatch")
            detail_count += 1
            if kind == "REFUND" and values["退款状态"] != "SUCCESS":
                pending += 1
                continue
            if kind == "SUCCESS" and values["交易状态"] != "SUCCESS":
                raise ValueError("unexpected payment state")
            amount = Decimal(values["订单金额" if kind == "SUCCESS" else "申请退款金额"])
            if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
                raise ValueError("invalid bill amount")
            reference = values["微信订单号" if kind == "SUCCESS" else "微信退款单号"]
            occurred_at = datetime.strptime(
                values["交易时间" if kind == "SUCCESS" else "退款成功时间"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone(timedelta(hours=8)))
            # Refund rows can recur on later bills. Hash immutable funds facts, not changing settlement columns.
            facts = {
                key: values[key]
                for key in (
                    "商户号",
                    "公众账号ID",
                    "微信订单号",
                    "商户订单号",
                    "货币种类",
                    "订单金额",
                )
            }
            facts.update({"reference": reference, "amount": str(amount), "occurred_at": occurred_at.isoformat()})
            results.append(
                ReconciliationRecordCreate(
                    channel="wechat",
                    channel_transaction_id=reference,
                    record_type="payment" if kind == "SUCCESS" else "refund",
                    source_reference=f"wechat:{kind}:{reference}",
                    source_hash=payload_hash(facts),
                    amount=amount,
                    currency="CNY",
                    occurred_at=occurred_at,
                )
            )
        if not summary_found:
            raise ValueError("missing bill summary")
        return results, pending
    except (ValueError, IndexError, KeyError, UnicodeError, InvalidOperation) as exc:
        raise PayProtocolError("账单格式或汇总校验失败，请人工核对") from exc
