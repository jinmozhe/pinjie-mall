import argparse
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.identifiers import new_uuid7
from app.db.models import Permission
from app.domains.admin.permissions import CATALOG_VERSION, PERMISSION_CATALOG
from scripts import sync_permissions


@pytest.mark.parametrize(
    ("active", "version", "needs_sync"),
    [(True, CATALOG_VERSION, True), (False, "retired-version", True), (False, CATALOG_VERSION, False)],
)
async def test_permission_sync_converges_without_deleting_retired_records(
    monkeypatch: pytest.MonkeyPatch, active: bool, version: str, needs_sync: bool
) -> None:
    permissions = [
        Permission(
            id=new_uuid7(),
            code=item.code,
            name=item.name,
            description=item.description,
            is_active=True,
            catalog_version=CATALOG_VERSION,
        )
        for item in PERMISSION_CATALOG
    ]
    retired = Permission(
        id=new_uuid7(),
        code="retired:fixture",
        name="历史权限",
        description="保留历史关联",
        is_active=active,
        catalog_version=version,
    )
    permissions.append(retired)
    retired_id = retired.id
    repository = SimpleNamespace(
        list_permissions=AsyncMock(return_value=permissions), add_permission=permissions.append
    )

    @asynccontextmanager
    async def session_factory():
        yield object()

    @asynccontextmanager
    async def transaction_scope(session):
        yield

    resources = SimpleNamespace(session_factory=session_factory, close=AsyncMock())
    validate_target = MagicMock()
    monkeypatch.setattr(sync_permissions, "get_settings", lambda: object())
    monkeypatch.setattr(sync_permissions, "validate_database_target", validate_target)
    monkeypatch.setattr(sync_permissions, "create_resources", lambda settings: resources)
    monkeypatch.setattr(sync_permissions, "AdminRepository", lambda session: repository)
    monkeypatch.setattr(sync_permissions, "transaction_scope", transaction_scope)
    check = argparse.Namespace(apply=False, confirm_database="permission_fixture_test")
    apply = argparse.Namespace(apply=True, confirm_database="permission_fixture_test")

    assert await sync_permissions._run(check) == int(needs_sync)
    assert retired.is_active is active
    assert retired.catalog_version == version
    assert await sync_permissions._run(apply) == 0
    assert await sync_permissions._run(check) == 0
    assert retired in permissions and retired.id == retired_id
    assert retired.description == "保留历史关联"
    assert retired.is_active is False
    assert retired.catalog_version == CATALOG_VERSION

    # Active catalog entries still require their source state, even with a
    # correctly retired row present. Apply repairs changes and missing rows.
    expected = permissions[0]
    expected.is_active = False
    expected.catalog_version = "retired-version"
    expected.name = "过期名称"
    missing = permissions.pop(1)
    assert await sync_permissions._run(check) == 1
    assert await sync_permissions._run(apply) == 0
    assert await sync_permissions._run(check) == 0
    assert {item.code for item in permissions} == {item.code for item in PERMISSION_CATALOG} | {retired.code}
    assert any(item.code == missing.code and item.is_active for item in permissions)
    assert expected.is_active is True and expected.catalog_version == CATALOG_VERSION
    assert expected.name == PERMISSION_CATALOG[0].name
    assert await sync_permissions._run(apply) == 0
    assert await sync_permissions._run(check) == 0
    assert retired in permissions
    validate_target.assert_called()
    resources.close.assert_awaited()
