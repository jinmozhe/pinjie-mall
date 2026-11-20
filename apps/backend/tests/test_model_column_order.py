"""Column-order contract for every registered business model."""

import pytest

from app.db.models import Base


@pytest.mark.parametrize("table_name", sorted(Base.metadata.tables))
def test_common_columns_surround_business_columns(table_name: str) -> None:
    columns = list(Base.metadata.tables[table_name].c.keys())
    if "id" in columns:
        assert columns[0] == "id"
    timestamps = [name for name in ("created_at", "updated_at") if name in columns]
    if timestamps:
        assert columns[-len(timestamps) :] == timestamps
    soft_delete = ["deleted_at", "deleted_by_id", "deleted_by_type", "deletion_reason"]
    if "deleted_at" in columns:
        assert all(name in columns for name in soft_delete)
        assert columns[-len(soft_delete + timestamps) :] == soft_delete + timestamps


def test_relationship_tables_keep_their_business_primary_keys() -> None:
    expected = {
        "admin_roles": ["admin_id", "role_id"],
        "role_permissions": ["role_id", "permission_id"],
        "category_spec_attributes": ["category_id", "attribute_id"],
        "product_sku_spec_values": ["sku_id", "adoption_id"],
        "product_attribute_values": ["adoption_id"],
        "product_detail_images": ["product_id", "asset_id"],
        "product_images": ["product_id", "asset_id"],
    }
    for name, primary_key in expected.items():
        table = Base.metadata.tables[name]
        assert "id" not in table.c
        assert list(table.primary_key.columns.keys()) == primary_key
