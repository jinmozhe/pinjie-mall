from typing import Any

from app.core.openapi import localize_openapi_schema


def test_localizer_handles_unknown_shapes_and_preserves_explicit_descriptions() -> None:
    schema: dict[str, Any] = {
        "paths": {
            "/invalid": None,
            "/checks": {
                "invalid": None,
                "missing-responses": {},
                "wrong-responses": {"responses": None},
                "get": {
                    "responses": {
                        "invalid": None,
                        "numeric": {"description": 42},
                        "translated": {"description": "Successful Response"},
                    }
                },
            },
        },
        "components": {
            "schemas": {
                "invalid": None,
                "missing-properties": {},
                "wrong-properties": {"properties": None},
                "sample": {
                    "properties": {
                        "invalid": None,
                        "explicit": {"description": "已有中文说明"},
                        "unknown": {},
                        "status": {},
                    }
                },
            }
        },
    }

    result = localize_openapi_schema(schema)

    assert result is schema
    responses = result["paths"]["/checks"]["get"]["responses"]
    assert responses["translated"]["description"] == "请求成功"
    assert responses["numeric"]["description"] == 42
    properties = result["components"]["schemas"]["sample"]["properties"]
    assert properties["explicit"]["description"] == "已有中文说明"
    assert properties["unknown"]["description"] == "当前业务字段，具体语义由所属请求或响应模型定义"
    assert properties["status"]["description"] == "当前状态代码"


def test_localizer_accepts_missing_or_non_mapping_sections() -> None:
    assert localize_openapi_schema({}) == {}
    schema: dict[str, Any] = {"paths": [], "components": []}
    assert localize_openapi_schema(schema) is schema
