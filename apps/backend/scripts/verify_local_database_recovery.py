from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.core.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class DatabaseTarget:
    scheme: str
    hostname: str
    port: int
    netloc: str
    username: str
    password: str
    database: str

    def url_for(self, database: str) -> str:
        return urlunsplit(SplitResult(self.scheme, self.netloc, f"/{database}", "", ""))


def parse_test_database_url(url: str | None) -> DatabaseTarget:
    if not url:
        raise ValueError("TEST_DATABASE_URL is required")
    parsed = urlsplit(url)
    database = parsed.path.removeprefix("/")
    if parsed.scheme != "postgresql+asyncpg":
        raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Local recovery verification only accepts a local PostgreSQL host")
    if not parsed.username or not parsed.password:
        raise ValueError("TEST_DATABASE_URL must include a username and password")
    assert_safe_database_name(database, "TEST_DATABASE_URL database")
    return DatabaseTarget(
        scheme=parsed.scheme,
        hostname=parsed.hostname,
        port=parsed.port or 5432,
        netloc=parsed.netloc,
        username=parsed.username,
        password=parsed.password,
        database=database,
    )


def assert_safe_database_name(database: str, label: str) -> None:
    if re.fullmatch(r"[a-z][a-z0-9_]*_test", database) is None:
        raise ValueError(f"{label} must use letters, digits, underscores, and end with _test")


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required tool is unavailable: {name}")
    return path


def run_checked(command: list[str], *, environment: dict[str, str]) -> None:
    subprocess.run(command, cwd=BACKEND_ROOT, env=environment, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Alembic upgrades and PostgreSQL backup recovery locally")
    parser.add_argument("--migration-database", required=True)
    parser.add_argument("--restore-database", required=True)
    parser.add_argument("--confirm-source-database", required=True)
    parser.add_argument("--confirm-migration-database", required=True)
    parser.add_argument("--confirm-restore-database", required=True)
    args = parser.parse_args()

    target = parse_test_database_url(get_settings().test_database_url)
    assert_safe_database_name(args.migration_database, "migration database")
    assert_safe_database_name(args.restore_database, "restore database")
    names = {target.database, args.migration_database, args.restore_database}
    if len(names) != 3:
        raise ValueError("Source, migration, and restore database names must be different")
    confirmations = {
        target.database: args.confirm_source_database,
        args.migration_database: args.confirm_migration_database,
        args.restore_database: args.confirm_restore_database,
    }
    if any(database != confirmation for database, confirmation in confirmations.items()):
        raise ValueError("Every confirmation value must exactly match its database name")

    createdb = require_tool("createdb")
    dropdb = require_tool("dropdb")
    powershell = require_tool("powershell")
    recovery_script = WORKSPACE_ROOT / "scripts" / "operations" / "test-postgres-backup-restore.ps1"
    # 执行前验证脚本路径，防止 WORKSPACE_ROOT 解析异常时执行非预期脚本
    if not recovery_script.is_file():
        raise RuntimeError(f"Recovery script not found: {recovery_script}")
    environment = os.environ.copy()
    environment["PGPASSWORD"] = target.password
    common_database_args = [
        f"--host={target.hostname}",
        f"--port={target.port}",
        f"--username={target.username}",
    ]
    migration_created = False
    try:
        source_environment = environment | {
            "DATABASE_URL": target.url_for(target.database),
            "TEST_DATABASE_URL": target.url_for(target.database),
            "ENVIRONMENT": "test",
        }
        # 连续执行两次 upgrade head 以验证迁移脚本的幂等性（重复执行应无副作用）
        run_checked([sys.executable, "-m", "alembic", "upgrade", "head"], environment=source_environment)
        run_checked([sys.executable, "-m", "alembic", "upgrade", "head"], environment=source_environment)
        run_checked([sys.executable, "-m", "alembic", "check"], environment=source_environment)

        run_checked(
            [createdb, *common_database_args, f"--owner={target.username}", args.migration_database],
            environment=environment,
        )
        migration_created = True
        migration_environment = environment | {
            "DATABASE_URL": target.url_for(args.migration_database),
            "TEST_DATABASE_URL": target.url_for(args.migration_database),
            "ENVIRONMENT": "test",
        }
        # 同样验证 migration 数据库的迁移幂等性
        run_checked([sys.executable, "-m", "alembic", "upgrade", "head"], environment=migration_environment)
        run_checked([sys.executable, "-m", "alembic", "upgrade", "head"], environment=migration_environment)
        run_checked([sys.executable, "-m", "alembic", "check"], environment=migration_environment)

        run_checked(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(recovery_script),
                "-SourceDatabase",
                target.database,
                "-RestoreDatabase",
                args.restore_database,
                "-Username",
                target.username,
                "-ConfirmSourceDatabase",
                target.database,
                "-ConfirmRestoreDatabase",
                args.restore_database,
                "-DatabaseHost",
                target.hostname,
                "-Port",
                str(target.port),
            ],
            environment=environment,
        )
        print("Local migration and database recovery verification passed.")
    finally:
        if migration_created:
            run_checked(
                [dropdb, "--if-exists", *common_database_args, args.migration_database],
                environment=environment,
            )


if __name__ == "__main__":
    main()
