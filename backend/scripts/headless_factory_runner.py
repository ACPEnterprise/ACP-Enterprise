"""Run one authenticated, singleton headless factory scheduling cycle."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.database.session import AsyncSessionFactory
from app.engineering_control.scheduler.runner import HeadlessRunner
from app.platform.auth.services import (
    access_token_service,
    authentication_service,
)
from app.platform.permissions.authorization import authorization_service
from app.worker_control.transport.http.dependencies import worker_transport_service


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=UUID, required=True)
    parser.add_argument("--worker-session-id", type=UUID, required=True)
    parser.add_argument("--authority-sha", required=True)
    parser.add_argument("--delegation-id", type=UUID, required=True)
    return parser.parse_args()


def admin_access_token() -> str:
    """Load the scheduler principal without placing its token in argv or logs."""

    token_file = os.environ.get("ACP_HEADLESS_ADMIN_ACCESS_TOKEN_FILE")
    if token_file:
        path = Path(token_file).expanduser().resolve(strict=True)
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise SystemExit(
                "ACP_HEADLESS_ADMIN_ACCESS_TOKEN_FILE must be a mode-0600 file"
            )
        token = path.read_text(encoding="utf-8").strip()
    else:
        token = os.environ.get("ACP_HEADLESS_ADMIN_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "ACP_HEADLESS_ADMIN_ACCESS_TOKEN_FILE or "
            "ACP_HEADLESS_ADMIN_ACCESS_TOKEN is required"
        )
    return token


async def run() -> int:
    options = arguments()
    token = admin_access_token()
    async with AsyncSessionFactory() as session:
        claims = access_token_service.decode(token)
        authenticated = await authentication_service.validate_access_context(
            session, claims
        )
        admin = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=options.company_id,
        )
        worker = await worker_transport_service.authenticate_http_session(
            session, session_id=options.worker_session_id
        )
        if worker.context.company_id != options.company_id:
            raise SystemExit("authenticated worker session belongs to another company")
        applied = await HeadlessRunner().run_once(
            session,
            admin_context=admin,
            worker_context=worker.context,
            expected_authority_sha=options.authority_sha,
            now=datetime.now(timezone.utc),
            delegation_id=options.delegation_id,
        )
    print(json.dumps({"applied_milestone_ids": applied, "count": len(applied)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
