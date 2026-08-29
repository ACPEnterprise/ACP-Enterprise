"""Restricted Preview command for Operational Migration Phase 1."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.core.config import settings
from app.database.session import AsyncSessionFactory, engine
from app.events.models import BusinessEvent
from app.jobs.models import Job, JobAppointmentLink
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    JobSourceIdentity,
)
from app.operational_migration.phase1 import (
    OperationalPhase1Manifest,
    ReviewedOperationalOutput,
    reviewed_output,
    select_stage,
    stage_records,
    transform_phase1,
)
from app.operational_migration.service import OperationalMigrationService
from app.platform.auth.errors import AuthenticationError
from app.platform.auth.services import access_token_service, authentication_service
from app.platform.permissions.authorization import (
    AuthorizationError,
    authorization_service,
)
from app.scheduling.models import Appointment

ACCESS_TOKEN_ENV = "ACP_OPERATIONAL_MIGRATION_ACCESS_TOKEN"
DEPLOYED_SHA_ENV = "ACP_DEPLOYED_GIT_SHA"


class OperationalExecutionApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_version: Literal["operational-migration-phase1-execution/v1"]
    target: Literal["preview"]
    mode: Literal["validate", "import"]
    manifest_sha256: str
    replay_digest: str
    ordered_job_identity_sha256: tuple[str, ...]
    expected_deployed_git_sha: str
    backup_sha256: str | None
    approval_sha256: str

    def verify(self) -> None:
        payload = self.model_dump(exclude={"approval_sha256"}, mode="json")
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if expected != self.approval_sha256:
            raise ValueError("operational execution approval digest mismatch")


def _restricted(path: Path) -> None:
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or path.is_symlink()
        or details.st_mode & 0o077
    ):
        raise ValueError("migration input must be a restricted regular file")


def _json(path: Path) -> dict[str, Any]:
    _restricted(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("migration input must contain a JSON object")
    return payload


def _write(path: Path, payload: BaseModel | dict[str, object]) -> None:
    value = (
        payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    )
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _backup(path: Path, expected: str) -> dict[str, object]:
    _restricted(path)
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        magic = source.read(5)
        digest.update(magic)
        size += len(magic)
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    actual = digest.hexdigest()
    if actual != expected or magic != b"PGDMP":
        raise ValueError("Preview backup integrity validation failed")
    return {"sha256": actual, "byte_size": size, "custom_format": True}


def prepare(args: argparse.Namespace) -> int:
    for path in (args.source, args.customer_reviewed, args.customer_manifest):
        _restricted(path)
    review = transform_phase1(
        source_bytes=args.source.read_bytes(),
        reviewed_customer_bytes=args.customer_reviewed.read_bytes(),
        customer_manifest_bytes=args.customer_manifest.read_bytes(),
    )
    _write(args.output, reviewed_output(review))
    return 0


def manifest(args: argparse.Namespace) -> int:
    reviewed = ReviewedOperationalOutput.model_validate(_json(args.reviewed_output))
    prior = (
        OperationalPhase1Manifest.model_validate(_json(args.prior_manifest))
        if args.prior_manifest
        else None
    )
    selected = select_stage(
        reviewed,
        stage_identifier=args.stage_identifier,
        limit=args.limit,
        prior=prior,
        generated_at=datetime.now(timezone.utc),
    )
    _write(args.output, selected)
    return 0


def approval(args: argparse.Namespace) -> int:
    selected = OperationalPhase1Manifest.model_validate(_json(args.manifest))
    payload: dict[str, object] = {
        "approval_version": "operational-migration-phase1-execution/v1",
        "target": "preview",
        "mode": args.mode,
        "manifest_sha256": selected.manifest_sha256,
        "replay_digest": selected.replay_digest,
        "ordered_job_identity_sha256": selected.ordered_job_identity_sha256,
        "expected_deployed_git_sha": args.deployed_git_sha,
        "backup_sha256": args.backup_sha256,
    }
    payload["approval_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _write(args.output, payload)
    return 0


async def _counts(company_id: UUID) -> dict[str, int]:
    async with AsyncSessionFactory() as session:
        values: dict[str, int] = {}
        for label, model in (
            ("jobs", Job),
            ("appointments", Appointment),
            ("job_links", JobAppointmentLink),
            ("job_source_identities", JobSourceIdentity),
            ("appointment_source_identities", AppointmentSourceIdentity),
        ):
            values[label] = int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.company_id == company_id)
                )
                or 0
            )
        values["migration_business_events"] = int(
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == company_id,
                    BusinessEvent.event_type.in_(
                        ("job.migrated", "appointment.migrated")
                    ),
                )
            )
            or 0
        )
        return values


async def execute(args: argparse.Namespace) -> int:
    if settings.environment != "preview" or args.target != "preview":
        raise ValueError("operational migration can execute only in Preview")
    reviewed = ReviewedOperationalOutput.model_validate(_json(args.reviewed_output))
    selected = OperationalPhase1Manifest.model_validate(_json(args.manifest))
    authorized = OperationalExecutionApproval.model_validate(_json(args.approval))
    authorized.verify()
    deployed_sha = os.environ.get(DEPLOYED_SHA_ENV)
    if (
        authorized.mode != args.mode
        or authorized.manifest_sha256 != selected.manifest_sha256
        or authorized.replay_digest != selected.replay_digest
        or authorized.ordered_job_identity_sha256
        != selected.ordered_job_identity_sha256
        or authorized.expected_deployed_git_sha != deployed_sha
    ):
        raise ValueError("operational approval does not match execution inputs")
    backup = None
    if args.mode == "import":
        if args.backup is None or authorized.backup_sha256 is None:
            raise ValueError("verified Preview backup is required for import")
        backup = _backup(args.backup, authorized.backup_sha256)
    elif args.backup is not None or authorized.backup_sha256 is not None:
        raise ValueError("validation mode does not accept backup evidence")
    jobs, appointments = stage_records(reviewed, selected)
    token = os.environ.get(ACCESS_TOKEN_ENV)
    if not token:
        raise ValueError("authenticated migration access token is required")
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
    before = await _counts(context.company.id)
    report = await OperationalMigrationService().run(
        AsyncSessionFactory,
        context=context,
        source_system=reviewed.source_system,
        jobs=jobs,
        appointments=appointments,
        dry_run=args.mode == "validate",
    )
    after = await _counts(context.company.id)
    result = {
        "status": "completed",
        "stage_identifier": selected.stage_identifier,
        "manifest_sha256": selected.manifest_sha256,
        "replay_digest": selected.replay_digest,
        "mode": args.mode,
        "run_id": str(report.run_id),
        "source": report.source,
        "accepted": report.accepted,
        "rejected": report.rejected,
        "duplicate": report.duplicate,
        "unresolved": report.unresolved,
        "before": before,
        "after": after,
        "delta": {key: after[key] - before[key] for key in before},
        "backup": backup,
        "deployed_git_sha": deployed_sha,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if report.rejected == 0 and report.unresolved == 0 else 3


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--source", type=Path, required=True)
    prep.add_argument("--customer-reviewed", type=Path, required=True)
    prep.add_argument("--customer-manifest", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    stage = commands.add_parser("manifest")
    stage.add_argument("--reviewed-output", type=Path, required=True)
    stage.add_argument("--stage-identifier", required=True)
    stage.add_argument("--limit", type=int)
    stage.add_argument("--prior-manifest", type=Path)
    stage.add_argument("--output", type=Path, required=True)
    approve = commands.add_parser("approval")
    approve.add_argument("--manifest", type=Path, required=True)
    approve.add_argument("--mode", choices=("validate", "import"), required=True)
    approve.add_argument("--deployed-git-sha", required=True)
    approve.add_argument("--backup-sha256")
    approve.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("execute")
    run.add_argument("--target", choices=("preview",), required=True)
    run.add_argument("--mode", choices=("validate", "import"), required=True)
    run.add_argument("--reviewed-output", type=Path, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--approval", type=Path, required=True)
    run.add_argument("--company-id", required=True)
    run.add_argument("--branch-id", required=True)
    run.add_argument("--backup", type=Path)
    return result


async def _main(args: argparse.Namespace) -> int:
    try:
        if args.command == "prepare":
            return prepare(args)
        if args.command == "manifest":
            return manifest(args)
        if args.command == "approval":
            return approval(args)
        return await execute(args)
    finally:
        await engine.dispose()


def main() -> None:
    try:
        code = asyncio.run(_main(parser().parse_args()))
    except (
        AuthenticationError,
        AuthorizationError,
        ValueError,
        TypeError,
        OSError,
        KeyError,
    ):
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "reason": "controlled_operational_precondition_failed",
                },
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
