import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.health import ReadinessResult


@pytest.mark.asyncio
async def test_liveness_is_dependency_free(client) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_system_status_returns_unavailable_without_resources(client) -> None:
    response = await client.get("/api/v1/system/status")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["message"] == "服务尚未就绪"
    assert response.json()["request_id"]


@pytest.mark.asyncio
async def test_system_status_returns_safe_success_payload(client, fake_resources, monkeypatch) -> None:
    from app.main import app

    # 使用 monkeypatch 确保测试结束后自动恢复 app.state，防止污染后续测试
    monkeypatch.setattr(app.state, "resources", fake_resources)
    monkeypatch.setattr(
        app.state,
        "settings",
        app.state.settings.model_copy(update={"database_url": "postgresql+asyncpg://u:p@localhost:5432/app"}),
    )
    with patch(
        "app.domains.system.router.check_readiness",
        new=AsyncMock(return_value=ReadinessResult(ready=True, checks={"database": "ok"})),
    ):
        response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    assert response.json()["code"] == "OK"
    assert response.json()["message"] == "操作成功"
    assert response.json()["data"] == {"status": "available"}


@pytest.mark.asyncio
async def test_unknown_route_has_stable_error(client) -> None:
    response = await client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["message"] == "请求的资源不存在"


@pytest.mark.asyncio
async def test_validation_error_uses_chinese_top_level_message(client) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:3000"},
        json={"username": "browser-user", "password": "a" * 65},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["message"] == "请求参数校验失败"


def _documentation_texts(node: Any) -> list[str]:
    values: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"summary", "description"} and isinstance(value, str):
                values.append(value)
            values.extend(_documentation_texts(value))
    elif isinstance(node, list):
        for value in node:
            values.extend(_documentation_texts(value))
    return values


def _schema_property_descriptions(schema: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    descriptions: list[tuple[str, str, str | None]] = []
    for schema_name, component in schema.get("components", {}).get("schemas", {}).items():
        if not isinstance(component, dict):
            continue
        for field_name, field_schema in component.get("properties", {}).items():
            description = field_schema.get("description") if isinstance(field_schema, dict) else None
            descriptions.append((schema_name, field_name, description))
    return descriptions


def test_openapi_descriptions_are_chinese_and_identifiers_stay_stable() -> None:
    from app.main import app

    schema = app.openapi()
    texts = _documentation_texts(schema)
    assert texts
    assert all(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", text) for text in texts), texts
    property_descriptions = _schema_property_descriptions(schema)
    assert property_descriptions
    missing = [(schema_name, field_name) for schema_name, field_name, text in property_descriptions if not text]
    assert not missing
    assert all(
        re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", text) for _, _, text in property_descriptions if text is not None
    )
    assert {tag["name"] for tag in schema["tags"]} == {
        "用户认证",
        "用户账户",
        "管理员认证",
        "后台管理",
        "文件资产",
        "系统",
        "系统设置",
        "健康检查",
    }
    login_operation = schema["paths"]["/api/v1/auth/login"]["post"]
    assert login_operation["operationId"] == "login_api_v1_auth_login_post"
    assert login_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/UserLoginIn")
    assert "password" in schema["components"]["schemas"]["UserLoginIn"]["properties"]


def test_admin_confirmation_contract_is_deprecated_during_compatibility_window() -> None:
    from app.main import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/admin/auth/confirm"]["post"]
    assert operation["deprecated"] is True
    assert "2026-09-26" in operation["description"]
    assert operation["operationId"] == "confirm_api_v1_admin_auth_confirm_post"


def test_admin_operations_do_not_require_password_confirmation_header() -> None:
    from app.main import app

    schema = app.openapi()
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            parameters = operation.get("parameters", [])
            header_names = {parameter["name"].lower() for parameter in parameters if parameter["in"] == "header"}
            assert "x-admin-confirmation" not in header_names


@pytest.mark.asyncio
async def test_external_request_id_is_rejected_and_replaced(client) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "contains spaces"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] != "contains spaces"
