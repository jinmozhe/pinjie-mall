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
