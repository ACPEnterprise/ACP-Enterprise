"""Provision or rotate the Beta-only Release actor into a protected token file."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.database.session import AsyncSessionFactory, engine
from app.platform.service_principals.release_actor import release_actor_service


async def run(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.token_output).resolve()
    if str(output) != "/run/secrets/release_actor_token":
        raise ValueError("Release actor token must use canonical secret custody path.")
    async with AsyncSessionFactory() as session, session.begin():
        issued = await release_actor_service.provision_and_rotate(
            session,
            company_id=args.company_id,
            lifetime=timedelta(minutes=args.minutes),
        )
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output.parent, 0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, issued.access_token.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(output, 0o600)
    return {
        "principal_id": str(issued.principal_id),
        "session_id": str(issued.session_id),
        "expires_at": issued.expires_at.isoformat(),
        "token_reference": str(output),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--company-id", required=True, type=UUID)
    result.add_argument("--minutes", type=int, default=60, choices=range(5, 61))
    result.add_argument(
        "--token-output", default="/run/secrets/release_actor_token"
    )
    return result


async def main() -> None:
    try:
        print(json.dumps(await run(parser().parse_args()), sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
