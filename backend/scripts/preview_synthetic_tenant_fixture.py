"""Invoke the exact Preview synthetic-tenant fixture from a sanctioned runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from app.database.session import AsyncSessionFactory, engine
from app.platform.auth.errors import AuthenticationError
from app.platform.auth.services import access_token_service, authentication_service
from app.platform.onboarding.preview_tenant_fixture import (
    FIXTURE_VERSION,
    PreviewSyntheticTenantCommand,
    preview_synthetic_tenant_fixture_service,
)
from app.platform.onboarding.service import OnboardingError
from app.platform.permissions.authorization import (
    AuthorizationError,
    authorization_service,
)


async def execute(args: argparse.Namespace) -> dict[str, object]:
    token = sys.stdin.read().strip()
    if not token:
        raise AuthenticationError("Authentication required.")
    claims = access_token_service.decode(token)
    async with AsyncSessionFactory() as security_session:
        authenticated = await authentication_service.validate_access_context(
            security_session, claims
        )
    async with AsyncSessionFactory() as session:
        context = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=UUID(args.authorizing_company_id),
            branch_id=UUID(args.authorizing_branch_id),
        )
        result = await preview_synthetic_tenant_fixture_service.create_or_reuse(
            session,
            context=context,
            command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
        )
    await engine.dispose()
    return {
        "classification": "PREVIEW_SYNTHETIC_TENANT_READY",
        "action": result.action,
        "company_id": str(result.company_id),
        "branch_id": str(result.branch_id),
        "audit_record_id": str(result.audit_record_id),
        "fixture_version": FIXTURE_VERSION,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--authorizing-company-id", required=True)
    result.add_argument("--authorizing-branch-id", required=True)
    return result


def main() -> None:
    try:
        print(json.dumps(asyncio.run(execute(parser().parse_args())), sort_keys=True))
    except (
        AuthenticationError,
        AuthorizationError,
        OnboardingError,
        ValueError,
    ) as error:
        print(json.dumps({"classification": "BLOCKED", "reason": str(error)}))
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
