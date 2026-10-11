import argparse
import asyncio

from app.core.config import get_settings
from app.core.identifiers import new_uuid7
from app.core.resources import create_resources
from app.db.models import Permission
from app.db.repositories import AdminRepository
from app.db.transaction import transaction_scope
from app.domains.admin.permissions import CATALOG_VERSION, PERMISSION_CATALOG
from scripts._database_target import validate_database_target


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or apply the source-controlled permission catalog")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database", required=True)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    validate_database_target(settings, args.confirm_database)
    resources = create_resources(settings)
    try:
        async with resources.session_factory() as session:
            repository = AdminRepository(session)
            current = {item.code: item for item in await repository.list_permissions()}
            expected = {item.code: item for item in PERMISSION_CATALOG}
            missing = sorted(expected.keys() - current.keys())
            obsolete = sorted(
                code
                for code in current.keys() - expected.keys()
                if current[code].is_active or current[code].catalog_version != CATALOG_VERSION
            )
            changed = sorted(
                code
                for code in expected.keys() & current.keys()
                if current[code].name != expected[code].name
                or current[code].description != expected[code].description
                or not current[code].is_active
                or current[code].catalog_version != CATALOG_VERSION
            )
            print(f"missing={len(missing)} changed={len(changed)} obsolete={len(obsolete)}")
            if not args.apply:
                return 1 if missing or changed or obsolete else 0
            async with transaction_scope(session):
                for code in missing:
                    definition = expected[code]
                    repository.add_permission(
                        Permission(
                            id=new_uuid7(),
                            code=definition.code,
                            name=definition.name,
                            description=definition.description,
                            is_active=True,
                            catalog_version=CATALOG_VERSION,
                        )
                    )
                for code in changed:
                    definition = expected[code]
                    item = current[code]
                    item.name = definition.name
                    item.description = definition.description
                    item.is_active = True
                    item.catalog_version = CATALOG_VERSION
                for code in obsolete:
                    current[code].is_active = False
                    current[code].catalog_version = CATALOG_VERSION
            print("Permission catalog synchronized")
            return 0
    finally:
        await resources.close()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_arguments())))


if __name__ == "__main__":
    main()
