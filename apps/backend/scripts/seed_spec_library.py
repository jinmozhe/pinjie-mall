"""仅供空商品本机开发库使用的公共规格库重建入口。"""

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import CheckConstraint, Connection, UniqueConstraint, delete, inspect, select, text, update
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings
from app.core.identifiers import new_uuid7
from app.db.models import Base
from app.db.models.catalog import SpecAttribute, SpecAttributeValue
from app.db.models.product import Category
from app.domains.products.catalog_schemas import AttributeInput
from scripts._database_target import validate_database_target

TABLES = (
    "product_sku_spec_values",
    "product_attribute_values",
    "product_spec_values",
    "product_spec_attributes",
    "category_spec_attributes",
    "spec_attribute_values",
    "spec_attributes",
)
BACKUP_TABLES = TABLES + ("product_categories",)
EMPTY_TABLES = TABLES[:4] + ("products", "product_skus")
LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LOCAL_SERVER_ADDRESSES = frozenset({"127.0.0.1", "::1"})
SUPPORTED_REVISION = "20260923_02"


class CommittedVerificationError(RuntimeError):
    """The import transaction committed, but its independent verification did not finish."""


class CommittedReceiptError(RuntimeError):
    """The import transaction committed and verified, but writing its receipt failed."""


SEED_PATH = Path(__file__).parent / "data" / "spec_library.v1.json"
WORKSPACE = Path(__file__).resolve().parents[3]


class SeedValue(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: Literal[True] = True


class SeedAttribute(AttributeInput):
    values: list[SeedValue] = Field(max_length=100)

    @model_validator(mode="after")
    def candidate_rules(self) -> "SeedAttribute":
        if self.value_type not in {"select", "multi_select"} and self.values:
            raise ValueError("非枚举属性不能包含标准值")
        if self.value_type in {"select", "multi_select"} and not self.values:
            raise ValueError("枚举种子必须有候选值")
        if len({row.code for row in self.values}) != len(self.values) or len({row.name for row in self.values}) != len(
            self.values
        ):
            raise ValueError("候选编码或名称重复")
        if not self.is_active:
            raise ValueError("种子属性必须启用")
        return self


class SeedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute_code: str
    value_code: str | None


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_row: int
    category_code: str
    category_name: str
    attribute_code: str
    attribute_name: str
    value_code: str
    value: str
    suggested_variant: bool
    disposition: Literal["保留", "合并", "拆分", "自由录入", "排除"]
    reason: str = Field(min_length=1)
    targets: list[SeedTarget]


class SeedLibrary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    dataset_version: str
    source_file: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sheet: str
    source_rows: Literal[1036]
    retail_rows: Literal[963]
    excluded_local_life_rows: Literal[73]
    attributes: list[SeedAttribute] = Field(min_length=1, max_length=500)
    provenance: list[SourceRecord]

    @model_validator(mode="after")
    def source_coverage(self) -> "SeedLibrary":
        attrs = {row.code: row for row in self.attributes}
        if len(attrs) != len(self.attributes):
            raise ValueError("公共属性编码重复")
        if sorted(row.source_row for row in self.provenance) != list(range(2, self.source_rows + 2)):
            raise ValueError("源行映射缺失或重复")
        local_life = [row for row in self.provenance if row.category_code == "LIF"]
        if len(local_life) != self.excluded_local_life_rows or any(
            row.targets or row.disposition != "排除" for row in local_life
        ):
            raise ValueError("本地生活数据不得导入")
        referenced: set[tuple[str, str | None]] = set()
        for row in self.provenance:
            if row.disposition == "排除":
                if row.targets:
                    raise ValueError("排除的源记录不能保留导入目标")
                continue
            if not row.targets:
                raise ValueError("源记录缺少处理去向")
            for target in row.targets:
                attr = attrs.get(target.attribute_code)
                if attr is None or (
                    target.value_code is not None and target.value_code not in {v.code for v in attr.values}
                ):
                    raise ValueError("来源映射目标不存在")
                referenced.add((target.attribute_code, target.value_code))
        for attr in self.attributes:
            expected = {(attr.code, value.code) for value in attr.values} if attr.values else {(attr.code, None)}
            if not expected <= referenced:
                raise ValueError("种子存在无来源的数据")
        return self


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def canonical_sql(value: object | None, connection: Connection, *, model_expression: bool = False) -> str | None:
    if value is None:
        return None
    rendered = (
        str(value.compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True}))
        if hasattr(value, "compile")
        else str(value)
    )
    # PostgreSQL reflection inserts implicit casts and expands IN into ANY(ARRAY[...]).
    rendered = re.sub(r"::(?:character\s+varying|text|numeric)(?:\[\])?", "", rendered.lower().replace('"', ""))
    rendered = re.sub(r"\s+", "", rendered)
    rendered = re.sub(r"([a-z_][a-z0-9_]*)=any\(array\[(.*?)\]\)", r"\1in(\2)", rendered)
    rendered = re.sub(r"\(([a-z_][a-z0-9_]*is(?:not)?null)\)", r"\1", rendered)
    if model_expression:
        rendered = re.sub(r"\(([^()]*and[^()]*)\)", r"\1", rendered)
    while rendered.startswith("(") and rendered.endswith(")"):
        depth = 0
        wraps_entire_expression = True
        for index, character in enumerate(rendered):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            if depth == 0 and index != len(rendered) - 1:
                wraps_entire_expression = False
                break
        if not wraps_entire_expression:
            break
        rendered = rendered[1:-1]
    return rendered


def validate_structure(connection: Connection) -> None:
    inspector = inspect(connection)
    actual_tables = set(inspector.get_table_names(schema="public"))
    if not set(TABLES + ("products", "product_skus", "product_categories", "alembic_version")) <= actual_tables:
        raise ValueError("缺少必要数据表，请先通过项目迁移建立结构")
    for name in TABLES + ("products", "product_skus", "product_categories"):
        expected = Base.metadata.tables[name]
        columns = inspector.get_columns(name, schema="public")
        actual = {
            row["name"]: (str(row["type"].compile(dialect=connection.dialect)), row["nullable"]) for row in columns
        }
        wanted = {
            column.name: (str(column.type.compile(dialect=connection.dialect)), column.nullable)
            for column in expected.columns
        }
        if actual != wanted:
            raise ValueError(f"表字段或类型不兼容：{name}")
        if inspector.get_pk_constraint(name, schema="public")["constrained_columns"] != [
            column.name for column in expected.primary_key.columns
        ]:
            raise ValueError(f"主键不兼容：{name}")
        actual_fk = {
            (
                tuple(row["constrained_columns"]),
                row.get("referred_schema") or "public",
                row["referred_table"],
                tuple(row["referred_columns"]),
                row["options"].get("ondelete"),
            )
            for row in inspector.get_foreign_keys(name, schema="public")
        }
        wanted_fk = {
            (
                tuple(element.parent.name for element in fk.elements),
                fk.referred_table.schema or "public",
                fk.referred_table.name,
                tuple(element.column.name for element in fk.elements),
                fk.ondelete,
            )
            for fk in expected.foreign_key_constraints
        }
        if actual_fk != wanted_fk:
            raise ValueError(f"外键结构不兼容：{name}")
        expected_unique = {
            (
                tuple(column.name for column in constraint.columns),
                bool(constraint.dialect_options["postgresql"].get("nulls_not_distinct", False)),
            )
            for constraint in expected.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        actual_unique_rows = inspector.get_unique_constraints(name, schema="public")
        actual_unique = {
            (
                tuple(row["column_names"] or ()),
                bool(row.get("dialect_options", {}).get("postgresql_nulls_not_distinct", False)),
            )
            for row in actual_unique_rows
        }
        if actual_unique != expected_unique or len(actual_unique_rows) != len(expected_unique):
            raise ValueError(f"唯一约束不兼容：{name}")
        expected_checks = {
            constraint.name: canonical_sql(constraint.sqltext, connection, model_expression=True)
            for constraint in expected.constraints
            if isinstance(constraint, CheckConstraint)
        }
        if None in expected_checks:
            raise ValueError(f"模型检查约束缺少稳定名称：{name}")
        actual_checks = {
            row["name"]: canonical_sql(row.get("sqltext"), connection)
            for row in inspector.get_check_constraints(name, schema="public")
        }
        if set(actual_checks) != set(expected_checks):
            raise ValueError(f"检查约束不兼容：{name}")
        for constraint_name, expected_sql in expected_checks.items():
            if actual_checks.get(constraint_name) != expected_sql:
                raise ValueError(f"检查约束不兼容：{name}.{constraint_name}")
        actual_indexes = {
            row["name"]: row
            for row in inspector.get_indexes(name, schema="public")
            if row.get("name") and not row.get("duplicates_constraint")
        }
        expected_indexes = {index.name for index in expected.indexes}
        if set(actual_indexes) != expected_indexes:
            raise ValueError(f"索引不兼容：{name}")
        for expected_index in expected.indexes:
            actual_index = actual_indexes.get(expected_index.name)
            expected_where = canonical_sql(expected_index.dialect_options["postgresql"].get("where"), connection)
            actual_where = canonical_sql(
                (actual_index or {}).get("dialect_options", {}).get("postgresql_where"), connection
            )
            if (
                actual_index is None
                or actual_index.get("unique") != bool(expected_index.unique)
                or tuple(actual_index.get("column_names") or ())
                != tuple(column.name for column in expected_index.columns)
                or actual_where != expected_where
            ):
                raise ValueError(f"索引不兼容：{name}.{expected_index.name}")
    external_reference = connection.execute(
        text(
            """
            SELECT 1
            FROM pg_catalog.pg_constraint AS fk
            JOIN pg_catalog.pg_class AS source_table ON source_table.oid = fk.conrelid
            JOIN pg_catalog.pg_namespace AS source_schema ON source_schema.oid = source_table.relnamespace
            JOIN pg_catalog.pg_class AS target_table ON target_table.oid = fk.confrelid
            JOIN pg_catalog.pg_namespace AS target_schema ON target_schema.oid = target_table.relnamespace
            WHERE fk.contype = 'f'
              AND target_schema.nspname = 'public'
              AND target_table.relname = ANY(CAST(:tables AS text[]))
              AND NOT (
                source_schema.nspname = 'public'
                AND source_table.relname = ANY(CAST(:tables AS text[]))
              )
            LIMIT 1
            """
        ),
        {"tables": list(TABLES)},
    ).first()
    if external_reference is not None:
        raise ValueError("发现清空范围外引用")


async def snapshot(connection: AsyncConnection) -> dict[str, list[dict[str, object]]]:
    result = {}
    for name in TABLES + ("product_categories",):
        table = Base.metadata.tables[name]
        rows = await connection.execute(select(table).order_by(*table.primary_key.columns))
        result[name] = [dict(row) for row in rows.mappings()]
    return result


def category_content(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{key: value for key, value in row.items() if key != "updated_at"} for row in rows]


async def verify_categories(
    connection: AsyncConnection, before: dict[str, list[dict[str, object]]], affected_categories: set[object]
) -> None:
    categories_after = (await snapshot(connection))["product_categories"]
    categories_expected = [
        dict(row, revision=int(str(row["revision"])) + (1 if row["id"] in affected_categories else 0))
        for row in before["product_categories"]
    ]
    if digest(category_content(categories_after)) != digest(category_content(categories_expected)):
        raise ValueError("分类范围外字段变化")


async def verify_connected_target(connection: AsyncConnection, url: URL) -> None:
    target = (
        (
            await connection.execute(
                text(
                    "SELECT current_database() AS database_name, "
                    "host(inet_server_addr()) AS server_address, inet_server_port() AS server_port"
                )
            )
        )
        .mappings()
        .one()
    )
    if (
        target["database_name"] != url.database
        or target["server_address"] not in LOCAL_SERVER_ADDRESSES
        or target["server_port"] != (url.port or 5432)
    ):
        raise ValueError("实际连接目标与已确认本机开发库不一致")


async def preflight(connection: AsyncConnection) -> None:
    revisions = list((await connection.execute(text("SELECT version_num FROM public.alembic_version"))).scalars())
    if revisions != [SUPPORTED_REVISION]:
        raise ValueError("数据库迁移版本不在脚本明确支持范围")
    await connection.run_sync(validate_structure)
    for name in EMPTY_TABLES:
        if (await connection.execute(select(Base.metadata.tables[name]).limit(1))).first() is not None:
            raise ValueError(f"拒绝清空：{name} 中存在商品或历史引用")


def backup_database(url: URL, directory: Path, metadata: dict[str, object]) -> Path:
    dump_tool, restore_tool = shutil.which("pg_dump"), shutil.which("pg_restore")
    if not dump_tool or not restore_tool:
        raise ValueError("需要 PostgreSQL pg_dump 和 pg_restore 工具")
    directory = directory.resolve()
    if directory.is_relative_to(WORKSPACE):
        raise ValueError("备份目录必须位于仓库之外")
    directory.mkdir(parents=True, exist_ok=True)
    run_dir = directory / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + str(new_uuid7()))
    run_dir.mkdir()
    dump_path = run_dir / "spec-library.dump"
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("PG")}
    environment.update(PGPASSWORD=url.password or "", PGCONNECT_TIMEOUT="10")
    command = [
        dump_tool,
        "--format=custom",
        "--data-only",
        "--no-owner",
        "--no-acl",
        "--no-password",
        "--host",
        url.host or "",
        "--port",
        str(url.port or 5432),
        "--dbname",
        url.database or "",
        "--file",
        str(dump_path),
    ]
    if url.username:
        command.extend(["--username", url.username])
    command.extend(f"--table=public.{name}" for name in BACKUP_TABLES)
    # Catalog and table write locks remain held by the caller; pg_dump only needs read locks.
    for args in (command, [restore_tool, "--list", str(dump_path)]):
        completed = subprocess.run(args, env=environment, capture_output=True, timeout=60, check=False)
        if completed.returncode != 0:
            raise ValueError("PostgreSQL 备份或备份目录检查失败，未清空数据")
    if not dump_path.stat().st_size:
        raise ValueError("备份文件为空")
    metadata["backup_tables"] = list(BACKUP_TABLES)
    metadata["dump_sha256"] = hashlib.sha256(dump_path.read_bytes()).hexdigest()
    manifest = run_dir / "manifest.json"
    manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if (
        json.loads(manifest.read_text(encoding="utf-8"))["dump_sha256"]
        != hashlib.sha256(dump_path.read_bytes()).hexdigest()
    ):
        raise ValueError("备份复读校验失败")
    return run_dir


def write_receipt(backup: Path, receipt: dict[str, object]) -> None:
    (backup / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def verify_content(connection: AsyncConnection, seed: SeedLibrary) -> str:
    attributes = list(
        (await connection.execute(select(SpecAttribute.__table__).order_by(SpecAttribute.code))).mappings()
    )
    values = list((await connection.execute(select(SpecAttributeValue.__table__))).mappings())
    actual = []
    for row in attributes:
        item = {key: row[key] for key in AttributeInput.model_fields}
        item["values"] = sorted(
            [
                {key: value[key] for key in SeedValue.model_fields}
                for value in values
                if value["attribute_id"] == row["id"]
            ],
            key=lambda value: str(value["code"]),
        )
        if row["revision"] != 1 or any(
            value["revision"] != 1 for value in values if value["attribute_id"] == row["id"]
        ):
            raise ValueError("初始版本核验失败")
        actual.append(item)
    expected = []
    for attribute in sorted(seed.attributes, key=lambda row: row.code):
        item = attribute.model_dump(mode="json", exclude_none=False)
        item["validation"] = attribute.validation.model_dump(mode="json", exclude_none=True)
        item["values"] = sorted(item["values"], key=lambda value: value["code"])
        expected.append(item)
    if len(values) != sum(len(row.values) for row in seed.attributes) or digest(actual) != digest(expected):
        raise ValueError("实际入库内容与种子不一致")
    for name in TABLES[:5]:
        if (await connection.execute(select(Base.metadata.tables[name]).limit(1))).first() is not None:
            raise ValueError("不应预造分类或商品关联")
    return digest(actual)


async def run(args: argparse.Namespace) -> None:
    seed_bytes = SEED_PATH.read_bytes()
    seed = SeedLibrary.model_validate_json(seed_bytes)
    settings = get_settings()
    if settings.database_url is None:
        raise ValueError("缺少数据库配置")
    url = make_url(settings.database_url)
    if url.query:
        raise ValueError("DATABASE_URL 不允许查询参数")
    database_name = validate_database_target(settings, args.confirm_database)
    if url.database is None or url.database != database_name:
        raise ValueError("DATABASE_URL 数据库名称无法与确认目标一致")
    if (
        settings.environment != "local"
        or url.host not in LOCAL_DATABASE_HOSTS
        or url.drivername != "postgresql+asyncpg"
    ):
        raise ValueError("仅允许本机 local PostgreSQL 开发库")
    if url.database.endswith("_test"):
        raise ValueError("本脚本不允许操作测试库")
    if args.apply and (not args.backup_dir or not Path(args.backup_dir).is_absolute()):
        raise ValueError("apply 必须指定仓库外绝对备份目录")
    engine = create_async_engine(
        url,
        connect_args={
            "server_settings": {
                "search_path": "public",
                "lock_timeout": "10000",
                "statement_timeout": "30000",
            }
        },
    )
    backup = None
    try:
        async with engine.begin() as connection:
            if not args.apply:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(text("SET LOCAL search_path TO public"))
            await verify_connected_target(connection, url)
            if args.apply:
                await connection.execute(text("SELECT pg_advisory_xact_lock(722341901)"))
                # Fixed whitelist. These locks block concurrent writes, including bypassing application services.
                await connection.execute(
                    text(
                        "LOCK TABLE public.product_sku_spec_values, public.product_attribute_values, public.product_spec_values, public.product_spec_attributes, public.category_spec_attributes, public.spec_attribute_values, public.spec_attributes, public.products, public.product_skus, public.product_categories IN SHARE ROW EXCLUSIVE MODE"
                    )
                )
            await preflight(connection)
            before = await snapshot(connection)
            expected_counts = {
                "attributes": len(seed.attributes),
                "values": sum(len(row.values) for row in seed.attributes),
            }
            print(
                json.dumps(
                    {
                        "mode": "apply" if args.apply else "check",
                        "database": url.database,
                        "before": {key: len(value) for key, value in before.items()},
                        "expected": expected_counts,
                    },
                    ensure_ascii=False,
                )
            )
            if not args.apply:
                return
            metadata = {
                "format_version": 1,
                "operator": getpass.getuser(),
                "database": url.database,
                "database_revision": SUPPORTED_REVISION,
                "dataset_version": seed.dataset_version,
                "seed_sha256": hashlib.sha256(seed_bytes).hexdigest(),
                "before_sha256": digest(before),
                "tables_sha256": digest({name: before[name] for name in TABLES}),
                "categories_sha256": digest(before["product_categories"]),
                "before": before,
                "created_at": datetime.now(UTC).isoformat(),
            }
            backup = await asyncio.to_thread(backup_database, url, Path(args.backup_dir), metadata)
            if digest(await snapshot(connection)) != digest(before):
                raise ValueError("备份后数据发生变化，拒绝清空")
            affected_categories = {row["category_id"] for row in before["category_spec_attributes"]}
            for name in TABLES:
                await connection.execute(delete(Base.metadata.tables[name]))
            if affected_categories:
                await connection.execute(
                    update(Category).where(Category.id.in_(affected_categories)).values(revision=Category.revision + 1)
                )
            for attribute in seed.attributes:
                attribute_id = new_uuid7()
                payload = attribute.model_dump(mode="json", exclude={"values"})
                payload["validation"] = attribute.validation.model_dump(mode="json", exclude_none=True)
                await connection.execute(
                    SpecAttribute.__table__.insert().values(id=attribute_id, revision=1, **payload)
                )
                if attribute.values:
                    await connection.execute(
                        SpecAttributeValue.__table__.insert(),
                        [
                            dict(id=new_uuid7(), attribute_id=attribute_id, revision=1, **value.model_dump())
                            for value in attribute.values
                        ],
                    )
            checksum = await verify_content(connection, seed)
            await verify_categories(connection, before, affected_categories)
        # A new physical connection verifies the committed state independently.
        try:
            await engine.dispose()
            async with engine.connect() as connection:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                await connection.execute(text("SET LOCAL search_path TO public"))
                await verify_connected_target(connection, url)
                if await verify_content(connection, seed) != checksum:
                    raise ValueError("提交后核验失败")
                await verify_categories(connection, before, affected_categories)
        except Exception as exc:
            if backup is not None:
                failure_receipt = dict(
                    status="committed_unverified",
                    **expected_counts,
                    business_sha256=checksum,
                    backup=str(backup),
                    verification_failed_at=datetime.now(UTC).isoformat(),
                )
                try:
                    write_receipt(backup, failure_receipt)
                except OSError:
                    pass
            raise CommittedVerificationError from exc
        receipt = dict(
            status="committed_verified",
            **expected_counts,
            business_sha256=checksum,
            backup=str(backup),
            verified_at=datetime.now(UTC).isoformat(),
        )
        if backup is not None:
            try:
                write_receipt(backup, receipt)
            except OSError as exc:
                raise CommittedReceiptError from exc
        print(json.dumps(receipt, ensure_ascii=False))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except CommittedVerificationError:
        parser.exit(1, "规格库操作已提交，但独立核验失败。请停止重试并依据备份目录中的回执受控处理。\n")
    except CommittedReceiptError:
        parser.exit(1, "规格库操作已提交且独立核验通过，但回执写入失败。请停止重试并核对备份目录。\n")
    except ValueError as exc:
        parser.exit(1, f"规格库操作拒绝：{exc}\n")
    except Exception as exc:
        # Database/driver errors can contain connection details. Do not print their payload.
        parser.exit(1, f"规格库操作失败：{type(exc).__name__}。请核对数据库状态和备份回执，勿盲目重试。\n")


if __name__ == "__main__":
    main()
