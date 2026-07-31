"""Private CLI composition for supervised preview Customer pilot execution."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.core.config import settings
from app.customer_migration.adapter_import import (
    ReviewedCustomerAdapterOutput,
    ReviewedCustomerAggregate,
)
from app.customer_migration.pilot_execution import (
    CustomerPilotApproval,
    CustomerPilotExecutionService,
    PilotExecutionError,
    PreviewBackupEvidence,
    PreviewExecutionRuntime,
)
from app.customer_migration.pilot_selection import CustomerPilotManifest
from app.database.session import AsyncSessionFactory, engine
from app.platform.auth.errors import AuthenticationError
from app.platform.auth.services import access_token_service, authentication_service
from app.platform.permissions.authorization import (
    AuthorizationError,
    authorization_service,
)

ACCESS_TOKEN_ENV = "ACP_CUSTOMER_PILOT_ACCESS_TOKEN"
DEPLOYED_SHA_ENV = "ACP_DEPLOYED_GIT_SHA"


def _restricted_file(path: Path) -> None:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or path.is_symlink():
        raise PilotExecutionError("execution input must be a regular file")
    if details.st_mode & 0o077:
        raise PilotExecutionError(
            "execution input permissions must exclude group/other"
        )


def _load_json(path: Path) -> dict[str, Any]:
    _restricted_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PilotExecutionError("execution input is unreadable") from error
    if not isinstance(payload, dict):
        raise PilotExecutionError("execution input must be a JSON object")
    return payload


def _load_reviewed(path: Path) -> ReviewedCustomerAdapterOutput:
    payload = _load_json(path)
    expected = {
        "review_version",
        "source_system",
        "source_sha256",
        "schema_version",
        "transformation_sha256",
        "source_count",
        "accepted_count",
        "rejected_count",
        "duplicate_count",
        "aggregates",
        "rejected_source_identities",
        "duplicate_source_identities",
        "child_exception_source_identities",
        "review_sha256",
    }
    if set(payload) != expected or not isinstance(payload["aggregates"], list):
        raise PilotExecutionError("reviewed-output contract is invalid")
    try:
        aggregate_values = payload.pop("aggregates")
        rejection_values = tuple(payload.pop("rejected_source_identities"))
        duplicate_values = tuple(payload.pop("duplicate_source_identities"))
        child_values = tuple(payload.pop("child_exception_source_identities"))
        aggregates = tuple(
            ReviewedCustomerAggregate(**item) for item in aggregate_values
        )
        reviewed = ReviewedCustomerAdapterOutput(
            **payload,
            aggregates=aggregates,
            rejected_source_identities=rejection_values,
            duplicate_source_identities=duplicate_values,
            child_exception_source_identities=child_values,
        )
        reviewed.validate_integrity()
    except (TypeError, ValueError) as error:
        raise PilotExecutionError(
            "reviewed-output integrity validation failed"
        ) from error
    return reviewed


def verify_backup(path: Path, expected_sha256: str) -> PreviewBackupEvidence:
    _restricted_file(path)
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        magic = source.read(5)
        digest.update(magic)
        size += len(magic)
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise PilotExecutionError("preview backup digest mismatch")
    if magic != b"PGDMP":
        raise PilotExecutionError("preview backup is not PostgreSQL custom format")
    return PreviewBackupEvidence(
        path_sha256=hashlib.sha256(str(path.resolve()).encode()).hexdigest(),
        backup_sha256=actual_sha256,
        byte_size=size,
        custom_format_verified=True,
    )


async def execute(args: argparse.Namespace) -> int:
    if settings.environment != "preview" or args.target != "preview":
        raise PilotExecutionError("command can execute only inside preview")
    approval = CustomerPilotApproval.model_validate(_load_json(args.approval))
    manifest = CustomerPilotManifest.model_validate(_load_json(args.manifest))
    reviewed = _load_reviewed(args.reviewed_output)
    if approval.mode != args.mode:
        raise PilotExecutionError("command mode does not match owner approval")
    if (
        approval.pilot_manifest_sha256 != manifest.manifest_sha256
        or approval.source_sha256 != manifest.source_sha256
        or approval.schema_version != manifest.export_version
        or approval.pilot_boundary_sha256 != manifest.replay_key
        or approval.ordered_source_identity_allowlist
        != manifest.ordered_customer_identity_sha256
    ):
        raise PilotExecutionError("pilot manifest does not match owner approval")
    deployed_sha = os.environ.get(DEPLOYED_SHA_ENV)
    if not deployed_sha:
        raise PilotExecutionError("deployed Git SHA evidence is required")
    token = os.environ.get(ACCESS_TOKEN_ENV)
    if not token:
        raise PilotExecutionError("authenticated owner access token is required")
    if args.backup is None or args.backup_sha256 is None:
        raise PilotExecutionError("backup path and digest are required")
    backup = verify_backup(args.backup, args.backup_sha256)
    claims = access_token_service.decode(token)
    async with AsyncSessionFactory() as session:
        authenticated = await authentication_service.validate_access_context(
            session, claims
        )
        context = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=UUID(args.company_id),
            branch_id=UUID(args.branch_id),
        )
    repository = CustomerPilotExecutionService().repository
    alembic_head = await repository.alembic_head(AsyncSessionFactory)
    report = await CustomerPilotExecutionService().run(
        AsyncSessionFactory,
        context=context,
        reviewed=reviewed,
        approval=approval,
        runtime=PreviewExecutionRuntime(
            environment=settings.environment,
            deployed_git_sha=deployed_sha,
            alembic_head=alembic_head,
            backup=backup,
        ),
    )
    print(report.model_dump_json())
    return 3 if report.status == "completed_with_discrepancy" else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Execute an owner-approved reviewed Customer pilot in preview."
    )
    result.add_argument("--target", choices=("preview",), required=True)
    result.add_argument("--mode", choices=("validate", "import"), required=True)
    result.add_argument("--approval", type=Path, required=True)
    result.add_argument("--reviewed-output", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--company-id", required=True)
    result.add_argument("--branch-id", required=True)
    result.add_argument("--backup", type=Path)
    result.add_argument("--backup-sha256")
    return result


def main() -> None:
    arguments = parser().parse_args()
    try:
        result = asyncio.run(execute(arguments))
    except (
        AuthenticationError,
        AuthorizationError,
        PilotExecutionError,
        ValidationError,
        ValueError,
    ):
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "reason": "controlled_customer_pilot_precondition_failed",
                },
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        result = 2
    finally:
        asyncio.run(engine.dispose())
    raise SystemExit(result)


if __name__ == "__main__":
    main()
