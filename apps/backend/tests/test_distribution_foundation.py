"""M4 领域不变量回归资产；实际执行遵循专项测试授权。"""

from decimal import Decimal

from app.domains.distribution.schemas import ReferralBindIn, WithdrawalCreate
from app.domains.distribution.service import COMMISSION_RATES, DistributionService


def test_commission_rates_and_rounding_are_fixed_snapshots() -> None:
    assert COMMISSION_RATES == (Decimal("0.1000"), Decimal("0.0500"))
    assert DistributionService._money(Decimal("10.005")) == Decimal("10.01")
    assert DistributionService._money(Decimal("10.004")) == Decimal("10.00")


def test_referral_and_withdrawal_inputs_normalize_only_local_fields() -> None:
    assert ReferralBindIn(invitation_code="  abcd1234  ").invitation_code == "ABCD1234"
    assert (
        WithdrawalCreate(
            request_id="0198a2e2-0267-7000-8000-000000000001",
            amount="1.00",
            destination_reference="  wechat:masked-openid  ",
        ).destination_reference
        == "wechat:masked-openid"
    )
