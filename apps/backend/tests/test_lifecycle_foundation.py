"""支付与售后阶段不变量回归资产；实际执行遵循专项测试授权。"""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import AppException
from app.domains.lifecycle.service import LifecycleService


def test_request_hash_is_canonical_for_equivalent_payload() -> None:
    assert LifecycleService._request_hash({"channel": "wechat", "amount": 1}) == LifecycleService._request_hash(
        {"amount": 1, "channel": "wechat"}
    )


def test_confirmation_time_requires_timezone() -> None:
    with pytest.raises(AppException) as error:
        LifecycleService._require_aware(datetime(2026, 9, 17, 0, 0), "支付确认时间")
    assert error.value.code == "ORDER_STATE_CONFLICT"
    assert "时区" in error.value.message


def test_confirmation_time_normalizes_to_utc() -> None:
    value = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
    assert LifecycleService._require_aware(value, "支付确认时间") == value
