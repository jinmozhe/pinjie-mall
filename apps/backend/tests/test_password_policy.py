import pytest
from pydantic import ValidationError

from app.core.password_policy import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, validate_new_password_length
from app.core.response import public_message, success_response
from app.domains.admin.schemas import AdminCreateIn, AdminLoginIn, PasswordResetIn
from app.domains.users.schemas import AccountDeleteIn, PasswordChangeIn


@pytest.mark.parametrize("length", [PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH])
def test_new_password_models_accept_policy_boundaries(length: int) -> None:
    password = "a" * length
    assert PasswordChangeIn(current_password="current", new_password=password).new_password == password
    assert AdminCreateIn(username="policy-admin", initial_password=password).initial_password == password
    assert PasswordResetIn(new_password=password).new_password == password
    assert validate_new_password_length(password) == password


@pytest.mark.parametrize("length", [PASSWORD_MIN_LENGTH - 1, PASSWORD_MAX_LENGTH + 1])
def test_new_password_models_reject_outside_policy(length: int) -> None:
    password = "a" * length
    with pytest.raises(ValidationError):
        PasswordChangeIn(current_password="current", new_password=password)
    with pytest.raises(ValidationError):
        AdminCreateIn(username="policy-admin", initial_password=password)
    with pytest.raises(ValidationError):
        PasswordResetIn(new_password=password)
    with pytest.raises(ValueError, match="6 至 64"):
        validate_new_password_length(password)


@pytest.mark.parametrize("password", ["a", "a" * PASSWORD_MAX_LENGTH])
def test_credential_verification_models_accept_up_to_maximum(password: str) -> None:
    assert AdminLoginIn(username="policy-admin", password=password).password == password
    assert AccountDeleteIn(current_password=password).current_password == password


def test_credential_verification_models_reject_over_maximum() -> None:
    password = "a" * (PASSWORD_MAX_LENGTH + 1)
    with pytest.raises(ValidationError):
        AdminLoginIn(username="policy-admin", password=password)
    with pytest.raises(ValidationError):
        AccountDeleteIn(current_password=password)


def test_public_response_messages_fail_closed_to_chinese() -> None:
    assert public_message("操作成功", fallback="请求处理失败") == "操作成功"
    assert public_message("English message", fallback="请求处理失败") == "请求处理失败"
    assert success_response(data=True, request_id="request-id", message="OK").message == "操作成功"
