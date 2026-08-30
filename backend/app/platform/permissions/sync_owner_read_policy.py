import asyncio
import sys

from app.database.session import AsyncSessionFactory, engine
from app.platform.permissions.owner_read_policy import owner_read_policy_service


async def run() -> int:
    try:
        async with AsyncSessionFactory() as session:
            results = await owner_read_policy_service.synchronize(session)
    except Exception:  # noqa: BLE001 - CLI fails closed without exposing DB details
        print(
            "Company Administrator owner-read synchronization failed.", file=sys.stderr
        )
        return 1
    finally:
        await engine.dispose()
    changed = sum(bool(item.added_codes) for item in results)
    print(
        f"Company Administrator owner-read policy synchronized for {len(results)} companies; changed={changed}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
