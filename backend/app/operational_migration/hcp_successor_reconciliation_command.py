"""Read-only Preview runner for sealed HCP SOURCE.4 successor reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.models import Customer
from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2ExecutionPlanBuilder,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_successor_reconciliation import (
    IdentityBinding,
    PrivateSuccessorManifest,
    SealedIdentity,
    reconcile_successors_v2,
)
from app.operational_migration.hcp_successor_reuse import (
    QualifiedSuccessorManifest,
    SourceKey,
    build_successor_manifest,
)
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    EstimateSourceIdentity,
    InvoiceSourceIdentity,
    JobSourceIdentity,
    PaymentSourceIdentity,
)

COMMAND_VERSION = "hcp-preview-successor-reconciliation-command/v2"


@dataclass(frozen=True)
class SuccessorReadAuthority:
    expected_repository_sha: str
    package_root: Path
    control_csv: Path
    migration1a_root: Path
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    baseline_counts: dict[str, int]
    private_manifest_output: Path
    qualified_manifest_output: Path | None = None

    @classmethod
    def load(cls, path: Path) -> SuccessorReadAuthority:
        try:
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise SafeEvidenceError(
                    "successor_authority_permissions_unsafe", "0" * 64
                )
            value = json.loads(path.read_bytes())
            if not isinstance(value, dict) or value.get("contract") != COMMAND_VERSION:
                raise ValueError
            counts = value["baseline_counts"]
            if not isinstance(counts, dict) or any(
                not isinstance(key, str) or not isinstance(count, int) or count < 0
                for key, count in counts.items()
            ):
                raise ValueError
            return cls(
                expected_repository_sha=str(value["expected_repository_sha"]),
                package_root=Path(value["package_root"]),
                control_csv=Path(value["control_csv"]),
                migration1a_root=Path(value["migration1a_root"]),
                company_id=UUID(value["company_id"]),
                branch_id=UUID(value["branch_id"]),
                actor_id=UUID(value["actor_id"]),
                baseline_counts=dict(counts),
                private_manifest_output=Path(value["private_manifest_output"]),
                qualified_manifest_output=(
                    Path(value["qualified_manifest_output"])
                    if value.get("qualified_manifest_output")
                    else None
                ),
            )
        except SafeEvidenceError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise SafeEvidenceError("successor_authority_invalid", "0" * 64) from error


IDENTITY_MODELS = (
    ("customer", CustomerSourceIdentity, "source_customer_id", "customer_id"),
    (
        "service_location",
        ServiceLocationSourceIdentity,
        "source_location_id",
        "service_location_id",
    ),
    ("job", JobSourceIdentity, "source_job_id", "job_id"),
    (
        "appointment",
        AppointmentSourceIdentity,
        "source_appointment_id",
        "appointment_id",
    ),
    ("estimate", EstimateSourceIdentity, "source_estimate_id", "estimate_id"),
    ("invoice", InvoiceSourceIdentity, "source_invoice_id", "invoice_id"),
    ("payment", PaymentSourceIdentity, "source_payment_id", "payment_id"),
)


async def load_preview_bindings(
    session: AsyncSession, *, company_id: UUID, branch_id: UUID
) -> tuple[IdentityBinding, ...]:
    """Read scoped identity bindings; no domain or audit row is mutated."""

    bindings: list[IdentityBinding] = []
    for domain, model, source_field, target_field in IDENTITY_MODELS:
        branch_column = model.branch_id
        rows = await session.execute(
            select(
                model.source_system,
                getattr(model, source_field),
                getattr(model, target_field),
            ).where(
                model.company_id == company_id,
                branch_column == branch_id,
                model.source_system.in_(("housecall_pro", "housecall_pro_source4")),
            )
        )
        bindings.extend(
            IdentityBinding(domain, source_system, source_id, str(target_id))
            for source_system, source_id, target_id in rows
        )
    contact_rows = await session.execute(
        select(
            CustomerSourceIdentity.source_system,
            CustomerSourceIdentity.source_customer_id,
            Customer.primary_contact_id,
        )
        .join(Customer, Customer.id == CustomerSourceIdentity.customer_id)
        .where(
            CustomerSourceIdentity.company_id == company_id,
            CustomerSourceIdentity.branch_id == branch_id,
            CustomerSourceIdentity.source_system.in_(
                ("housecall_pro", "housecall_pro_source4")
            ),
            Customer.primary_contact_id.is_not(None),
        )
    )
    bindings.extend(
        IdentityBinding("contact", source_system, source_id, str(target_id))
        for source_system, source_id, target_id in contact_rows
    )
    return tuple(bindings)


def sealed_identities(plan: Any) -> tuple[SealedIdentity, ...]:
    """Extract only provider identities from the already verified plan in memory."""

    result = [
        SealedIdentity("customer", row.source_identity)
        for row in plan.customers.reviewed.aggregates
    ]
    result.extend(
        SealedIdentity("contact", row.source_identity)
        for row in plan.customers.reviewed.aggregates
        if getattr(row, "contact", None) is not None
    )
    result.extend(
        SealedIdentity("service_location", source_id)
        for row in plan.customers.reviewed.aggregates
        for source_id in row.service_location_source_identities
    )
    for domain in ("jobs", "appointments", "estimates", "invoices", "payments"):
        result.extend(
            SealedIdentity(domain.removesuffix("s"), row.source_id)
            for row in getattr(plan, domain)
        )
    return tuple(result)


def _require_runtime(authority: SuccessorReadAuthority) -> None:
    if os.getenv("TARGET_ENVIRONMENT") != "preview":
        raise SafeEvidenceError("successor_target_not_preview", "0" * 64)
    if os.getenv("PRODUCTION_ACCESS_ENABLED", "false").lower() != "false":
        raise SafeEvidenceError("successor_production_access_enabled", "0" * 64)
    if os.getenv("PREVIEW_ACCESS_ENABLED", "false").lower() != "true":
        raise SafeEvidenceError("successor_preview_access_disabled", "0" * 64)
    try:
        repository_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SafeEvidenceError(
            "successor_repository_authority_unavailable", "0" * 64
        ) from error
    if repository_sha != authority.expected_repository_sha:
        raise SafeEvidenceError("successor_repository_authority_mismatch", "0" * 64)


def write_private_manifest(path: Path, manifest: PrivateSuccessorManifest) -> None:
    """Atomically retain private mappings; identical output is replay-safe."""

    parent = path.parent
    try:
        if not parent.is_dir() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
            raise SafeEvidenceError("successor_manifest_directory_unsafe", "0" * 64)
        payload = json.dumps(
            {
                "contract": "hcp-preview-successor-private-manifest/v1",
                "digest": manifest.digest,
                "entries": [asdict(item) for item in manifest.entries],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if path.exists():
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise SafeEvidenceError(
                    "successor_manifest_permissions_unsafe", "0" * 64
                )
            if path.read_bytes() != payload:
                raise SafeEvidenceError("successor_manifest_output_conflict", "0" * 64)
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            # Refuse a race rather than replacing an independently created authority.
            if path.exists():
                raise SafeEvidenceError("successor_manifest_output_conflict", "0" * 64)
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    except SafeEvidenceError:
        raise
    except OSError as error:
        raise SafeEvidenceError("successor_manifest_write_failed", "0" * 64) from error


def write_qualified_manifest(path: Path, manifest: QualifiedSuccessorManifest) -> None:
    """Persist new successor authority without replacing historical evidence."""

    parent = path.parent
    try:
        if not parent.is_dir() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
            raise SafeEvidenceError("successor_manifest_directory_unsafe", "0" * 64)
        payload = json.dumps(
            manifest.private_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        if path.exists():
            if stat.S_IMODE(path.stat().st_mode) != 0o600 or path.read_bytes() != payload:
                raise SafeEvidenceError("successor_manifest_output_conflict", "0" * 64)
            return
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            if path.exists():
                raise SafeEvidenceError("successor_manifest_output_conflict", "0" * 64)
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    except SafeEvidenceError:
        raise
    except OSError as error:
        raise SafeEvidenceError("successor_manifest_write_failed", "0" * 64) from error


async def run(authority: SuccessorReadAuthority) -> dict[str, object]:
    _require_runtime(authority)
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=authority.package_root,
        control_csv=authority.control_csv,
        migration1a_root=authority.migration1a_root,
    )
    plan, plan_summary = builder.build(
        baseline_counts=authority.baseline_counts,
        company_id=authority.company_id,
        branch_id=authority.branch_id,
        actor_id=authority.actor_id,
    )
    async with AsyncSessionFactory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        bindings = await load_preview_bindings(
            session, company_id=authority.company_id, branch_id=authority.branch_id
        )
        result = reconcile_successors_v2(
            current_bindings=bindings, sealed_source4=sealed_identities(plan)
        )
        await session.rollback()
    write_private_manifest(authority.private_manifest_output, result.private_manifest)
    qualified: QualifiedSuccessorManifest | None = None
    if authority.qualified_manifest_output is not None:
        parents: dict[SourceKey, SourceKey] = {}
        for aggregate in plan.customers.reviewed.aggregates:
            for location_id in aggregate.service_location_source_identities:
                parents[SourceKey("service_location", location_id)] = SourceKey(
                    "customer", aggregate.source_identity
                )
        for job_record in plan.jobs:
            parents[SourceKey("job", job_record.source_id)] = SourceKey(
                "customer", job_record.source_customer_id
            )
        for appointment_record in plan.appointments:
            parents[SourceKey("appointment", appointment_record.source_id)] = SourceKey(
                "job", appointment_record.source_job_id
            )
        for domain in ("estimate", "invoice"):
            for financial_record in getattr(plan, f"{domain}s"):
                parents[SourceKey(domain, financial_record.source_id)] = SourceKey(
                    "job", financial_record.source_job_id
                )
        for payment_record in plan.payments:
            parents[SourceKey("payment", payment_record.source_id)] = SourceKey(
                "invoice", payment_record.source_invoice_id
            )
        qualified = build_successor_manifest(
            company_id=str(authority.company_id),
            branch_id=str(authority.branch_id),
            current_bindings=bindings,
            sealed_source4=sealed_identities(plan),
            parents=parents,
        )
        write_qualified_manifest(authority.qualified_manifest_output, qualified)
    return {
        "command": COMMAND_VERSION,
        "plan_digest": plan_summary.plan_digest,
        "report": asdict(result.report),
        "private_manifest": {
            "digest": result.private_manifest.digest,
            "entry_count": len(result.private_manifest.entries),
        },
        "qualified_manifest": (
            {
                "digest": qualified.digest,
                "entry_count": len(qualified.entries),
            }
            if qualified is not None
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = asyncio.run(run(SuccessorReadAuthority.load(args.authority_file)))
    except SafeEvidenceError as error:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "code": error.code,
                    "digest": error.evidence_digest,
                }
            )
        )
        return 2
    except Exception:  # noqa: BLE001 - CLI must never emit protected exception payloads
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "code": "successor_reconciliation_failed",
                    "digest": "0" * 64,
                }
            )
        )
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
