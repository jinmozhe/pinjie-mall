"""Normalize business-table column order without changing data or keys.

Revision ID: 20261120_01
Revises: 20261119_01
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import context, op

revision = "20261120_01"
down_revision = "20261119_01"
branch_labels = None
depends_on = None

# Frozen physical column order at the parent revision, independent of live models.
PREVIOUS_COLUMNS: dict[str, tuple[str, ...]] = {
    "admin_refresh_tokens": tuple(
        "id session_id token_digest issued_at expires_at consumed_at revoked_at revoke_reason replaced_by_id".split()
    ),
    "admin_roles": tuple("admin_id role_id".split()),
    "admin_sessions": tuple(
        "id admin_id family_id credential_profile client_id csrf_digest ip_address user_agent_summary device_name last_seen_at idle_expires_at absolute_expires_at revoked_at revoke_reason created_at updated_at".split()
    ),
    "admins": tuple(
        "id username display_name password_hash is_active is_superuser credential_version created_at updated_at avatar".split()
    ),
    "assets": tuple(
        "uploader_type uploader_id storage_driver file_key original_name mime_type file_size file_hash url scene id created_at updated_at width height frame_count".split()
    ),
    "audit_events": tuple(
        "id actor_id action target_type target_id result changed_fields request_id trace_id release_version ip_address occurred_at completed_at actor_type target_revision".split()
    ),
    "brands": tuple("name logo_asset_id description sort_order is_active revision id created_at updated_at".split()),
    "cart_items": tuple("user_id sku_id quantity selected revision id created_at updated_at".split()),
    "category_spec_attributes": tuple(
        "category_id attribute_id is_variant is_required sort_order allow_custom_value".split()
    ),
    "commission_amount_rules": tuple(
        "policy_id buyer_scope buyer_level_id product_id sku_id rule_mode amount_per_unit percentage_rate id created_at updated_at".split()
    ),
    "commission_distribution_rules": tuple(
        "policy_id buyer_level_id ancestor_depth beneficiary_level_id allocation_mode rate amount_per_unit id created_at updated_at".split()
    ),
    "commission_policies": tuple(
        "name status default_mode default_amount_per_unit default_percentage_rate max_depth settle_delay_days activated_at content_version revision updated_by id created_at updated_at".split()
    ),
    "commission_records": tuple(
        "order_id source_user_id beneficiary_user_id level base_amount rate amount recovered_amount status frozen_at settle_after settled_at recovered_at id created_at updated_at order_item_id policy_id revision rule_snapshot".split()
    ),
    "commission_recoveries": tuple(
        "commission_id refund_request_id amount id created_at updated_at cancelled_frozen_amount wallet_deducted_amount debt_created_amount".split()
    ),
    "durable_tasks": tuple(
        "task_type business_key payload status available_at attempt_count failure_count max_failures lease_token lease_until revision completed_at last_error_code last_error_summary id created_at updated_at".split()
    ),
    "fulfillment_events": tuple(
        "fulfillment_id revision from_status to_status actor_type actor_id reason id created_at updated_at".split()
    ),
    "fulfillments": tuple(
        "order_id product_type status carrier tracking_number delivery_reference shipped_at delivered_at auto_confirm_at updated_by_id revision id created_at updated_at cancelled_at".split()
    ),
    "inventory_accounts": tuple("sku_id available reserved revision id created_at updated_at".split()),
    "inventory_movements": tuple(
        "sku_id request_id actor_id quantity_delta before_available after_available expected_revision resulting_revision reason id created_at updated_at actor_type source_type source_id request_hash".split()
    ),
    "inventory_reservation_events": tuple(
        "id created_at updated_at reservation_id revision to_status before_available after_available before_reserved after_reserved resulting_inventory_revision".split()
    ),
    "inventory_reservations": tuple(
        "order_id sku_id quantity status revision released_at id created_at updated_at".split()
    ),
    "member_level_conditions": tuple(
        "id level_id metric aggregation amount_threshold count_threshold is_active effective_at updated_by revision created_at updated_at".split()
    ),
    "member_level_events": tuple(
        "id user_id from_level_id to_level_id trigger_type trigger_id qualification_snapshot profile_revision operator_id idempotency_key created_at updated_at".split()
    ),
    "member_levels": tuple(
        "code name discount_factor level_rank sort_order revision is_active id created_at updated_at".split()
    ),
    "member_price_rules": tuple(
        "member_level_id scope_type sku_id product_id category_id price_mode fixed_price discount_factor is_active updated_by revision id created_at updated_at".split()
    ),
    "member_profiles": tuple(
        "user_id invitation_code inviter_id bound_at id created_at updated_at level_id level_changed_at revision".split()
    ),
    "membership_qualification_events": tuple(
        "id user_id metric source_type source_id order_id amount_delta count_delta reverses_event_id occurred_at idempotency_key created_at updated_at".split()
    ),
    "order_events": tuple(
        "order_id revision from_status to_status actor_type actor_id reason id created_at updated_at event_type".split()
    ),
    "order_items": tuple(
        "order_id product_id sku_id product_name sku_code specifications quantity unit_price line_amount weight_grams product_revision id created_at updated_at price_snapshot commission_snapshot category_snapshot brand_snapshot".split()
    ),
    "orders": tuple(
        "user_id request_id request_hash quote_fingerprint product_type status currency items_amount freight_amount total_amount address_snapshot shipping_snapshot pricing_version expires_at paid_at cancelled_at cancel_reason revision id created_at updated_at buyer_level_id buyer_level_snapshot commission_policy_id commission_result_snapshot accepted_payment_attempt_id settlement_kind zero_confirmation_id acceptance_status accepted_at accepted_by_id".split()
    ),
    "payment_attempts": tuple(
        "order_id user_id request_id request_hash channel merchant_reference status amount currency channel_transaction_id unavailable_reason confirmed_at revision id created_at updated_at channel_paid_at channel_context prepay_id channel_expires_at submission_started_at close_requested".split()
    ),
    "payment_events": tuple(
        "payment_attempt_id revision from_status to_status reason payload_hash id created_at updated_at".split()
    ),
    "permissions": tuple("id code name description is_active catalog_version created_at updated_at".split()),
    "points_accounts": tuple(
        "id user_id available_points frozen_points debt_points revision created_at updated_at".split()
    ),
    "points_ledgers": tuple(
        "id account_id entry_type available_delta frozen_delta debt_delta source_type source_id reverses_ledger_id idempotency_key note created_at updated_at".split()
    ),
    "product_attribute_values": tuple(
        "adoption_id product_id attribute_id value schema_version display_snapshot created_at updated_at".split()
    ),
    "product_categories": tuple(
        "name parent_id sort_order is_active revision id created_at updated_at icon_asset_id description".split()
    ),
    "product_detail_images": tuple("product_id asset_id position".split()),
    "product_images": tuple("product_id asset_id position".split()),
    "product_purchase_limits": tuple(
        "user_id product_id purchased_quantity reserved_quantity revision id created_at updated_at".split()
    ),
    "product_purchase_records": tuple(
        "order_id user_id product_id quantity status revision limit_snapshot confirmed_at released_at refunded_at id created_at updated_at".split()
    ),
    "product_reviews": tuple(
        "user_id order_item_id product_id rating content is_published published_at id created_at updated_at".split()
    ),
    "product_sku_spec_values": tuple("product_id sku_id adoption_id attribute_id spec_value_id".split()),
    "product_skus": tuple(
        "product_id code specifications price weight_grams is_active id created_at updated_at sku_no specification_key cost_price market_price wholesale_prices archived_at".split()
    ),
    "product_spec_attributes": tuple(
        "product_id attribute_id adoption_version name_snapshot value_type_snapshot unit_snapshot validation_snapshot source_category_id source_category_revision source_attribute_revision is_required allow_custom_value is_variant is_current created_at id".split()
    ),
    "product_spec_values": tuple(
        "adoption_id product_id attribute_id value_id display_value normalized_value is_current created_at id".split()
    ),
    "products": tuple(
        "name description product_type category_id status revision id created_at updated_at brand_id purchase_limit_quantity description_version is_home_recommended home_recommend_sort".split()
    ),
    "reconciliation_records": tuple(
        "channel channel_transaction_id source_reference source_hash amount currency occurred_at status payment_attempt_id note id created_at updated_at record_type refund_attempt_id withdrawal_request_id resolution_status resolution_note resolved_by_id resolved_at revision".split()
    ),
    "refund_attempts": tuple(
        "order_id payment_attempt_id refund_request_id purpose attempt_no merchant_refund_reference request_hash channel currency channel_refund_id amount status channel_refunded_at closed_at revision confirmed_at id created_at updated_at".split()
    ),
    "refund_events": tuple(
        "refund_request_id revision from_status to_status actor_type actor_id reason id created_at updated_at payload_hash refund_attempt_id event_scope event_type".split()
    ),
    "refund_items": tuple("refund_request_id order_item_id quantity amount id created_at updated_at".split()),
    "refund_requests": tuple(
        "order_id user_id request_id request_hash status amount currency reason review_note reviewed_by_id reviewed_at revision id created_at updated_at review_mode items_amount freight_amount fulfillment_status_snapshot completed_at".split()
    ),
    "request_logs": tuple(
        "id request_id trace_id method route_template status_code duration_ms principal_type principal_digest release_version occurred_at request_body".split()
    ),
    "role_permissions": tuple("role_id permission_id".split()),
    "roles": tuple("id code name description is_active created_at updated_at".split()),
    "security_login_events": tuple(
        "id principal_type principal_id identifier_digest event_type succeeded reason_code ip_address user_agent_summary request_id trace_id release_version occurred_at".split()
    ),
    "shipping_templates": tuple(
        "name pricing_method regions free_shipping_threshold excluded_provinces is_active revision updated_by_id id created_at updated_at".split()
    ),
    "spec_attribute_values": tuple(
        "attribute_id code name revision sort_order is_active id created_at updated_at".split()
    ),
    "spec_attributes": tuple(
        "code name value_type unit validation revision sort_order is_active id created_at updated_at".split()
    ),
    "system_settings": tuple("setting_group setting_value revision updated_by id created_at updated_at".split()),
    "user_addresses": tuple(
        "user_id receiver_name mobile province_code city_code district_code province city district street_address is_default revision id created_at updated_at".split()
    ),
    "user_external_identities": tuple(
        "user_id provider app_id subject_id union_id id created_at updated_at union_scope_id".split()
    ),
    "user_refresh_tokens": tuple(
        "id session_id token_digest issued_at expires_at consumed_at revoked_at revoke_reason replaced_by_id".split()
    ),
    "user_sessions": tuple(
        "id user_id family_id credential_profile client_id csrf_digest ip_address user_agent_summary device_name last_seen_at idle_expires_at absolute_expires_at revoked_at revoke_reason created_at updated_at".split()
    ),
    "users": tuple(
        "id username email display_name password_hash is_active credential_version deleted_at created_at updated_at deletion_reason deleted_by_id deleted_by_type avatar phone_e164 phone_verified_at phone_verification_source".split()
    ),
    "wallet_accounts": tuple(
        "user_id wallet_type available_amount frozen_amount debt_amount revision id created_at updated_at".split()
    ),
    "wallet_ledgers": tuple(
        "wallet_id entry_type amount frozen_delta debt_delta idempotency_key reference_type reference_id id created_at updated_at wallet_revision balance_after".split()
    ),
    "wechat_pay_notifications": tuple(
        "id created_at updated_at merchant_id notification_id event_type payload_hash config_version verified_payload status".split()
    ),
    "withdrawal_requests": tuple(
        "user_id wallet_id request_id request_hash amount currency destination_reference status review_note reviewed_by_id reviewed_at channel_reference confirmed_at revision id created_at updated_at merchant_reference channel channel_context channel_paid_at payload_hash".split()
    ),
}

SOFT_DELETE_COLUMNS = ("deleted_at", "deleted_by_id", "deleted_by_type", "deletion_reason")
TIMESTAMP_COLUMNS = ("created_at", "updated_at")


def ordered_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    first = tuple(name for name in ("id",) if name in columns)
    last = tuple(name for name in (*SOFT_DELETE_COLUMNS, *TIMESTAMP_COLUMNS) if name in columns)
    middle = tuple(name for name in columns if name not in first and name not in last)
    return first + middle + last


def _quote(connection: Connection, name: str) -> str:
    return connection.dialect.identifier_preparer.quote_identifier(name)


def _table(connection: Connection, name: str) -> str:
    return f'"public".{_quote(connection, name)}'


def _rows(connection: Connection, sql: str) -> list[tuple[object, ...]]:
    return [tuple(row) for row in connection.exec_driver_sql(sql)]


def schema_snapshot(connection: Connection) -> dict[str, list[tuple[object, ...]]]:
    """Compare semantic definitions, excluding OIDs and physical column positions."""
    return {
        "tables": _rows(
            connection,
            """
            SELECT c.relname, c.relkind::text, c.relowner, c.relacl::text,
                   c.reloptions::text, c.relrowsecurity, c.relforcerowsecurity,
                   c.relreplident::text, c.relpersistence::text, c.reltablespace,
                   c.relam, obj_description(c.oid, 'pg_class')
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            ORDER BY c.relname
            """,
        ),
        "columns": _rows(
            connection,
            """
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
                   a.attnotnull, a.attcollation, a.attidentity::text, a.attgenerated::text,
                   a.attstorage::text, a.attcompression::text, a.attstattarget,
                   a.attacl::text, a.attoptions::text, a.attfdwoptions::text,
                   pg_get_expr(d.adbin, d.adrelid), col_description(c.oid, a.attnum)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
            WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY c.relname, a.attname
            """,
        ),
        "constraints": _rows(
            connection,
            """
            SELECT c.relname, con.conname, con.contype::text, pg_get_constraintdef(con.oid),
                   con.condeferrable, con.condeferred, con.convalidated, con.connoinherit,
                   obj_description(con.oid, 'pg_constraint')
            FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
            ORDER BY c.relname, con.conname
            """,
        ),
        "indexes": _rows(
            connection,
            """
            SELECT t.relname, i.relname, pg_get_indexdef(i.oid),
                   x.indisvalid, x.indisready, x.indisclustered, x.indisreplident,
                   i.reloptions::text, i.reltablespace, obj_description(i.oid, 'pg_class')
            FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
            JOIN pg_class t ON t.oid = x.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
            ORDER BY t.relname, i.relname
            """,
        ),
    }


def data_snapshot(connection: Connection) -> dict[str, tuple[int, str]]:
    """Hash every complete row without exposing business values in diagnostics."""
    result = {}
    for name in sorted(PREVIOUS_COLUMNS):
        digest = hashlib.sha256()
        count = 0
        query = (
            "SELECT encode(sha256(convert_to(to_jsonb(t)::text, 'UTF8')), 'hex') AS row_hash "
            f"FROM {_table(connection, name)} t ORDER BY row_hash"
        )
        # Explicit CLOSE releases PostgreSQL's relation references before DDL.
        # asyncpg streaming portals can otherwise outlive CursorResult.close().
        connection.exec_driver_sql(f"DECLARE column_order_hash NO SCROLL CURSOR FOR {query}")
        try:
            while rows := connection.exec_driver_sql("FETCH FORWARD 1000 FROM column_order_hash").all():
                for row in rows:
                    digest.update(row[0].encode("ascii"))
                    count += 1
        finally:
            connection.exec_driver_sql("CLOSE column_order_hash")
        result[name] = (count, digest.hexdigest())
    return result


def _preflight(connection: Connection) -> dict[str, tuple[str, ...]]:
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Column reordering requires PostgreSQL")
    inspector = sa.inspect(connection)
    names = set(inspector.get_table_names(schema="public"))
    if names != set(PREVIOUS_COLUMNS) | {"alembic_version"}:
        raise RuntimeError("Unexpected public table set; review schema before reordering")
    columns = {
        name: tuple(column["name"] for column in inspector.get_columns(name, schema="public"))
        for name in PREVIOUS_COLUMNS
    }
    for name, expected in PREVIOUS_COLUMNS.items():
        if set(columns[name]) != set(expected):
            raise RuntimeError(f"Unexpected column set: {name}")
    # Reflection cannot guarantee preservation of these custom objects/settings.
    # Reject before any DDL instead of silently losing them during table recreation.
    checks = {
        "custom relations, views, sequences or schemas": """
            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname NOT IN ('information_schema') AND n.nspname NOT LIKE 'pg_%'
              AND (n.nspname <> 'public' OR c.relkind NOT IN ('r', 'i'))
        """,
        "table ownership, grants, options, partitioning or RLS": """
            SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND (c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
                   OR c.relacl IS NOT NULL OR c.reloptions IS NOT NULL OR c.relispartition
                   OR c.relrowsecurity OR c.relforcerowsecurity OR c.relreplident <> 'd'
                   OR c.relpersistence <> 'p' OR c.reltablespace <> 0
                   OR c.relam <> (SELECT oid FROM pg_am WHERE amname = 'heap'))
        """,
        "triggers or rules": """
            SELECT (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal)
                 + (SELECT count(*) FROM pg_rewrite r
                    JOIN pg_class c ON c.oid = r.ev_class
                    WHERE c.relnamespace = 'public'::regnamespace)
        """,
        "inheritance, publications, extended statistics or default grants": """
            SELECT (SELECT count(*) FROM pg_inherits)
                 + (SELECT count(*) FROM pg_publication)
                 + (SELECT count(*) FROM pg_statistic_ext)
                 + (SELECT count(*) FROM pg_default_acl)
        """,
        "unsupported columns": """
            SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
              AND a.attnum > 0 AND NOT a.attisdropped
              AND (a.attidentity <> '' OR a.attgenerated <> '' OR a.attacl IS NOT NULL
                   OR a.attoptions IS NOT NULL OR a.attfdwoptions IS NOT NULL)
        """,
        "unsupported or unvalidated constraints": """
            SELECT count(*) FROM pg_constraint
            WHERE connamespace = 'public'::regnamespace
              AND (contype NOT IN ('p','u','f','c','n') OR NOT convalidated)
        """,
        "external foreign keys": """
            SELECT count(*) FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_class dst ON dst.oid = con.confrelid
            WHERE con.contype = 'f'
              AND dst.relnamespace = 'public'::regnamespace
              AND src.relnamespace <> 'public'::regnamespace
        """,
        "invalid or specially configured indexes": """
            SELECT count(*) FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
            WHERE i.relnamespace = 'public'::regnamespace
              AND (NOT x.indisvalid OR NOT x.indisready OR x.indisclustered
                   OR x.indisreplident OR i.reloptions IS NOT NULL OR i.reltablespace <> 0)
        """,
    }
    for label, query in checks.items():
        if connection.exec_driver_sql(query).scalar():
            raise RuntimeError(f"Column reordering refuses {label}; review migration scope")
    return columns


def _restore_constraint_metadata(connection: Connection, original: list[tuple[object, ...]], changed: set[str]) -> None:
    # PostgreSQL 18 names NOT NULL constraints after the temporary table. Restore
    # original names by semantic definition, without touching their enforcement.
    current = {(row[0], row[3]): row[1] for row in schema_snapshot(connection)["constraints"] if row[2] == "n"}
    for table, name, kind, definition, *_flags, comment in original:
        if table not in changed:
            continue
        table_sql = _table(connection, str(table))
        name_sql = _quote(connection, str(name))
        if kind == "n":
            actual = current.get((table, definition))
            if actual is None:
                raise RuntimeError(f"Missing NOT NULL constraint on {table}")
            if actual != name:
                connection.exec_driver_sql(
                    f"ALTER TABLE {table_sql} RENAME CONSTRAINT {_quote(connection, str(actual))} TO {name_sql}"
                )
        if comment is not None:
            value = sa.literal(comment).compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True})
            connection.exec_driver_sql(f"COMMENT ON CONSTRAINT {name_sql} ON {table_sql} IS {value}")


def canonical_constraints(
    connection: Connection, constraints: list[tuple[object, ...]], changed: set[str]
) -> list[tuple[object, ...]]:
    """Parse original CHECK DDL with PostgreSQL, never with regex substitutions.

    PostgreSQL can rewrite ARRAY casts while reparsing its own deparsed CHECK
    expressions. Use empty temporary tables with identical column types to obtain
    the server's canonical definitions. All other constraint attributes stay exact.
    """
    canonical = {}
    for table in sorted(changed):
        checks = [row for row in constraints if row[0] == table and row[2] == "c"]
        if not checks:
            continue
        connection.exec_driver_sql(
            f'CREATE TEMPORARY TABLE "_column_order_check" (LIKE {_table(connection, table)}) ON COMMIT DROP'
        )
        for _, name, _, definition, *_ in checks:
            connection.exec_driver_sql(
                f'ALTER TABLE pg_temp."_column_order_check" ADD CONSTRAINT {_quote(connection, str(name))} {definition}'
            )
        for name, definition in connection.exec_driver_sql(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'pg_temp._column_order_check'::regclass AND contype = 'c'"
        ):
            canonical[table, name] = definition
        connection.exec_driver_sql('DROP TABLE pg_temp."_column_order_check"')
    return [(*row[:3], canonical.get((row[0], row[1]), row[3]), *row[4:]) for row in constraints]


def canonical_indexes(
    connection: Connection, indexes: list[tuple[object, ...]], changed: set[str]
) -> list[tuple[object, ...]]:
    """Canonicalize original index expressions/predicates with the same parser."""
    canonical = {}
    for table in sorted(changed):
        originals = [row for row in indexes if row[0] == table]
        if not originals:
            continue
        connection.exec_driver_sql(
            f'CREATE TEMPORARY TABLE "_column_order_index" (LIKE {_table(connection, table)}) ON COMMIT DROP'
        )
        for _, name, definition, *_ in originals:
            prefix, separator, expression = str(definition).partition(" USING ")
            source = f" ON public.{connection.dialect.identifier_preparer.quote(table)}"
            if not separator or not prefix.endswith(source):
                raise RuntimeError(f"Unexpected index DDL for {table}.{name}")
            # Retain the original index name/uniqueness and change only the
            # relation for parsing; never modify the expression or predicate.
            temporary = prefix.removesuffix(source) + ' ON pg_temp."_column_order_index"'
            connection.exec_driver_sql(f"{temporary} USING {expression}")
            name_value = sa.literal(name).compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True})
            parsed = connection.exec_driver_sql(
                "SELECT pg_get_indexdef(oid) FROM pg_class "
                f"WHERE relnamespace = pg_my_temp_schema() AND relname = {name_value} AND relkind = 'i'"
            ).scalar()
            if not isinstance(parsed, str) or " USING " not in parsed:
                raise RuntimeError(f"Could not canonicalize index {table}.{name}")
            canonical[table, name] = prefix + " USING " + parsed.partition(" USING ")[2]
        connection.exec_driver_sql('DROP TABLE pg_temp."_column_order_index"')
    return [(*row[:2], canonical.get((row[0], row[1]), row[2]), *row[3:]) for row in indexes]


def _reorder(*, restore_previous: bool) -> None:
    if context.is_offline_mode():
        raise RuntimeError("Column reorder requires online catalog checks and data verification")
    connection = op.get_bind()
    connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
    connection.exec_driver_sql("SET LOCAL statement_timeout = '120s'")
    connection.exec_driver_sql("SET LOCAL search_path = public, pg_catalog")
    actual = _preflight(connection)
    targets = {
        name: previous if restore_previous else ordered_columns(previous) for name, previous in PREVIOUS_COLUMNS.items()
    }
    changed = {name for name in targets if targets[name] != actual[name]}
    if not changed:
        return
    # Lock every application table in a fixed order before hashing and removing
    # FKs. Concurrent writes cannot race the before/after integrity checks.
    names_sql = ", ".join(_table(connection, name) for name in sorted(PREVIOUS_COLUMNS))
    connection.exec_driver_sql(f"LOCK TABLE {names_sql} IN ACCESS EXCLUSIVE MODE")
    actual = _preflight(connection)
    changed = {name for name in targets if targets[name] != actual[name]}
    before_schema = schema_snapshot(connection)
    before_schema["constraints"] = canonical_constraints(connection, before_schema["constraints"], changed)
    before_schema["indexes"] = canonical_indexes(connection, before_schema["indexes"], changed)
    before_data = data_snapshot(connection)
    foreign_keys = [row for row in before_schema["constraints"] if row[2] == "f"]
    for table, name, *_ in foreign_keys:
        connection.exec_driver_sql(
            f"ALTER TABLE {_table(connection, str(table))} DROP CONSTRAINT {_quote(connection, str(name))}"
        )
    for name in sorted(changed):
        reflected = sa.Table(name, sa.MetaData(), schema="public", autoload_with=connection)
        with op.batch_alter_table(
            name,
            schema="public",
            recreate="always",
            copy_from=reflected,
            partial_reordering=[targets[name]],
            table_kwargs={"comment": reflected.comment},
        ):
            pass
    for table, name, _kind, definition, *_flags, comment in foreign_keys:
        table_sql = _table(connection, str(table))
        name_sql = _quote(connection, str(name))
        connection.exec_driver_sql(f"ALTER TABLE {table_sql} ADD CONSTRAINT {name_sql} {definition}")
        if comment is not None:
            value = sa.literal(comment).compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True})
            connection.exec_driver_sql(f"COMMENT ON CONSTRAINT {name_sql} ON {table_sql} IS {value}")
    _restore_constraint_metadata(connection, before_schema["constraints"], changed)
    for table, index, _definition, *_flags, comment in before_schema["indexes"]:
        if table in changed and comment is not None:
            value = sa.literal(comment).compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True})
            connection.exec_driver_sql(f"COMMENT ON INDEX {_table(connection, str(index))} IS {value}")
    after_schema = schema_snapshot(connection)
    for section in before_schema:
        if before_schema[section] != after_schema[section]:
            before_only = [row[:8] for row in before_schema[section] if row not in after_schema[section]]
            after_only = [row[:8] for row in after_schema[section] if row not in before_schema[section]]
            raise RuntimeError(
                f"Column reorder changed {section}; transaction must roll back. "
                f"Before: {before_only[:3]!r}; after: {after_only[:3]!r}"
            )
    if before_data != data_snapshot(connection):
        raise RuntimeError("Column reorder changed row counts or data hashes; transaction must roll back")
    inspector = sa.inspect(connection)
    for name, target in targets.items():
        found = tuple(column["name"] for column in inspector.get_columns(name, schema="public"))
        if found != target:
            raise RuntimeError(f"Column order verification failed: {name}")


def upgrade() -> None:
    _reorder(restore_previous=False)


def downgrade() -> None:
    _reorder(restore_previous=True)
