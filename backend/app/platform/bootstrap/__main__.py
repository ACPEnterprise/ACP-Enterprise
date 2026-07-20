import asyncio
import sys

from pydantic import ValidationError

from app.core.config import settings
from app.database.session import AsyncSessionFactory, engine
from app.platform.auth.passwords import PasswordService
from app.platform.bootstrap.config import load_bootstrap_configuration
from app.platform.bootstrap.repository import BootstrapRepository
from app.platform.bootstrap.service import BootstrapService


async def run() -> int:
    try:
        configuration = load_bootstrap_configuration()
    except ValidationError as error:
        missing_fields = sorted(
            str(item["loc"][0]) for item in error.errors() if item["type"] == "missing"
        )
        if missing_fields:
            print(
                "Bootstrap configuration is incomplete. Missing: "
                + ", ".join(missing_fields),
                file=sys.stderr,
            )
        else:
            print("Bootstrap configuration is invalid.", file=sys.stderr)
        return 2

    service = BootstrapService(
        repository=BootstrapRepository(),
        password_service=PasswordService(settings),
    )
    try:
        async with AsyncSessionFactory() as session:
            result = await service.initialize(session, configuration)
    except Exception:
        print(
            "ACP Enterprise bootstrap failed; no changes were committed. "
            "Review restricted application and database logs.",
            file=sys.stderr,
        )
        return 1
    finally:
        await engine.dispose()

    if result.initialized:
        print("ACP Enterprise bootstrap completed successfully.")
    else:
        print("ACP Enterprise is already initialized; no changes were made.")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
