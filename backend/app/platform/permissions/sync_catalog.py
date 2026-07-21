import asyncio
import sys

from app.database.session import AsyncSessionFactory, engine
from app.platform.permissions.catalog_sync import permission_catalog_sync_service


async def run() -> int:
    try:
        async with AsyncSessionFactory() as session:
            result = await permission_catalog_sync_service.synchronize(session)
    except Exception:
        print(
            "Permission catalog synchronization failed; no changes were committed.",
            file=sys.stderr,
        )
        return 1
    finally:
        await engine.dispose()

    created = ", ".join(f"{item.code}={item.id}" for item in result.created) or "none"
    existing = ", ".join(f"{item.code}={item.id}" for item in result.existing) or "none"
    print(f"Created canonical permissions: {created}")
    print(f"Existing canonical permissions: {existing}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
