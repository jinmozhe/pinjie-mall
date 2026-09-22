from app.db.models import Base

EXPECTED_MODEL_TABLE_COUNT = 67
TARGET_ADDITION_TABLES = frozenset(
    {
        "brands",
        "category_spec_attributes",
        "commission_amount_rules",
        "commission_distribution_rules",
        "commission_policies",
        "durable_tasks",
        "member_levels",
        "member_level_conditions",
        "member_level_events",
        "member_price_rules",
        "product_attribute_values",
        "product_purchase_limits",
        "product_purchase_records",
        "product_sku_spec_values",
        "product_spec_attributes",
        "product_spec_values",
        "membership_qualification_events",
        "points_accounts",
        "points_ledgers",
        "refund_attempts",
        "spec_attribute_values",
        "spec_attributes",
        "user_external_identities",
    }
)


def verify() -> None:
    table_names = frozenset(Base.metadata.tables)
    missing = TARGET_ADDITION_TABLES - table_names
    if missing:
        raise RuntimeError(f"target model tables are missing: {', '.join(sorted(missing))}")
    if len(table_names) != EXPECTED_MODEL_TABLE_COUNT:
        raise RuntimeError(
            f"model table count is {len(table_names)}, expected {EXPECTED_MODEL_TABLE_COUNT}; update the target audit"
        )
    print(f"model_tables={len(table_names)}; target_addition_tables={len(TARGET_ADDITION_TABLES)}")


def main() -> None:
    verify()


if __name__ == "__main__":
    main()
