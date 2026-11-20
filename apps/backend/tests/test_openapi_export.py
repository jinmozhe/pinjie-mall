import json

from scripts.export_openapi import export_openapi


def test_openapi_export_is_independent_from_runtime_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROJECT_NAME", "Local machine override")
    monkeypatch.setenv("RELEASE_VERSION", "local-machine-version")
    output = tmp_path / "openapi.json"

    export_openapi(output)

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["info"]["title"] == "Pinjie Mall Backend"
    assert schema["info"]["version"] == "0.1.0"


def test_public_search_is_optional_bounded_and_composable_with_category(tmp_path) -> None:
    output = tmp_path / "openapi.json"
    export_openapi(output)
    schema = json.loads(output.read_text(encoding="utf-8"))
    parameters = {item["name"]: item for item in schema["paths"]["/api/v1/products"]["get"]["parameters"]}
    assert parameters["search"]["required"] is False
    assert any(part.get("maxLength") == 200 for part in parameters["search"]["schema"]["anyOf"])
    assert "category_id" in parameters and "page" in parameters and "page_size" in parameters


def test_home_recommendations_have_array_contract_without_pagination(tmp_path) -> None:
    output = tmp_path / "openapi.json"
    export_openapi(output)
    schema = json.loads(output.read_text(encoding="utf-8"))
    operation = schema["paths"]["/api/v1/products/recommended"]["get"]
    assert not operation.get("security")
    assert not operation.get("parameters")
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    data = schema["components"]["schemas"][response]["properties"]["data"]
    assert any(item.get("type") == "array" for item in data.get("anyOf", [data]))
    assert "/api/v1/admin/products/recommendations/batch" in schema["paths"]
    assert "/api/v1/admin/products/{product_id}/recommendation" in schema["paths"]
