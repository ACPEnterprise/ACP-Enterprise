"""Fail-closed Preview runner for legacy HCP projection classification.

This command reads the sealed SOURCE.4 plan and scoped Preview identities, invokes the
authoritative classifier, and writes immutable private classification, qualified
successor-manifest, and Enterprise replay-packet artifacts.  It never admits data.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_legacy_projection_classification import (
    LegacyProjectionDisposition,
    ProjectionCorrelationEvidence,
    classify_correlated_legacy,
)
from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2ExecutionPlanBuilder,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_successor_reconciliation import (
    LEGACY_SOURCE_SYSTEM,
)
from app.operational_migration.hcp_successor_reconciliation_command import (
    SuccessorReadAuthority,
    _require_runtime,
    load_preview_bindings,
    sealed_identities,
)
from app.operational_migration.hcp_successor_reuse import (
    AdmissionDisposition,
    QualifiedSuccessorManifest,
    SuccessorManifestEntry,
)

COMMAND_VERSION = "hcp-legacy-projection-preview-run/v1"
CLASSIFIED_DOMAINS = frozenset(
    {
        "customer",
        "contact",
        "service_location",
        "job",
        "appointment",
        "estimate",
        "invoice",
        "payment",
    }
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class PreviewClassificationAuthority:
    reconciliation: SuccessorReadAuthority
    expected_legacy_projection_count: int
    classification_output: Path
    qualified_manifest_output: Path
    admission_packet_output: Path

    @classmethod
    def load(cls, path: Path) -> PreviewClassificationAuthority:
        try:
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise ValueError
            value = json.loads(path.read_bytes())
            if value.get("contract") != COMMAND_VERSION:
                raise ValueError
            nested_payload = json.dumps(
                value["reconciliation"], sort_keys=True, separators=(",", ":")
            ).encode()
            nested = (
                path.parent
                / f".reconciliation-authority-{hashlib.sha256(nested_payload).hexdigest()}.json"
            )
            _write_once(nested, nested_payload)
            return cls(
                reconciliation=SuccessorReadAuthority.load(nested),
                expected_legacy_projection_count=int(
                    value["expected_legacy_projection_count"]
                ),
                classification_output=Path(value["classification_output"]),
                qualified_manifest_output=Path(value["qualified_manifest_output"]),
                admission_packet_output=Path(value["admission_packet_output"]),
            )
        except SafeEvidenceError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise SafeEvidenceError(
                "preview_classification_authority_invalid", "0" * 64
            ) from error


def _write_once(path: Path, payload: bytes) -> None:
    """Atomically create or replay identical protected evidence."""

    parent = path.parent
    if not parent.is_dir() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise SafeEvidenceError("classification_output_directory_unsafe", "0" * 64)
    if path.exists():
        if stat.S_IMODE(path.stat().st_mode) != 0o600 or path.read_bytes() != payload:
            raise SafeEvidenceError("classification_output_conflict", "0" * 64)
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
            raise SafeEvidenceError("classification_output_conflict", "0" * 64)
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_qualified_manifest(
    *,
    company_id: UUID,
    branch_id: UUID,
    classification: object,
    sealed: tuple[object, ...],
) -> QualifiedSuccessorManifest:
    report = classification.report  # type: ignore[attr-defined]
    exact = {
        item.successor_source_id: item
        for item in classification.records  # type: ignore[attr-defined]
        if item.disposition == LegacyProjectionDisposition.EXACT_SUCCESSOR
        and item.successor_source_id is not None
    }
    entries = []
    for source in sealed:
        match = exact.get(source.source_id)  # type: ignore[attr-defined]
        entries.append(
            SuccessorManifestEntry(
                domain=source.domain,  # type: ignore[attr-defined]
                source_id=source.source_id,  # type: ignore[attr-defined]
                disposition=(
                    AdmissionDisposition.REUSE_EXACT_SUCCESSOR
                    if match
                    else AdmissionDisposition.CREATE_NEW
                ),
                evidence_digest=(
                    match.evidence_digest
                    if match
                    else _digest(
                        {
                            "domain": source.domain,  # type: ignore[attr-defined]
                            "source_id": source.source_id,  # type: ignore[attr-defined]
                            "disposition": "create_new",
                        }
                    )
                ),
                native_id=match.target_id if match else None,
                reason=("exact_legacy_successor" if match else "no_qualified_reuse"),
            )
        )
    return QualifiedSuccessorManifest.build(
        company_id=str(company_id),
        branch_id=str(branch_id),
        entries=entries,
        canonical_reconciliation_digest=report.safe_digest,
        canonical_reconciliation_admission_allowed=report.canonical_admission_allowed,
    )


async def run(authority: PreviewClassificationAuthority) -> dict[str, object]:
    source = authority.reconciliation
    _require_runtime(source)
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=source.package_root,
        control_csv=source.control_csv,
        migration1a_root=source.migration1a_root,
    )
    plan, plan_summary = builder.build(
        baseline_counts=source.baseline_counts,
        company_id=source.company_id,
        branch_id=source.branch_id,
        actor_id=source.actor_id,
    )
    sealed = sealed_identities(plan)
    sealed_evidence = tuple(
        ProjectionCorrelationEvidence(item.domain, item.source_id, None)
        for item in sealed
        if item.domain in CLASSIFIED_DOMAINS
    )
    async with AsyncSessionFactory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        bindings = await load_preview_bindings(
            session, company_id=source.company_id, branch_id=source.branch_id
        )
        await session.rollback()
    legacy_evidence = tuple(
        ProjectionCorrelationEvidence(item.domain, item.source_id, item.target_id)
        for item in bindings
        if item.source_system == LEGACY_SOURCE_SYSTEM
        and item.domain in CLASSIFIED_DOMAINS
    )
    if (
        authority.expected_legacy_projection_count <= 0
        or len(legacy_evidence) != authority.expected_legacy_projection_count
    ):
        raise SafeEvidenceError(
            "legacy_projection_population_mismatch",
            _digest(
                {
                    "expected": authority.expected_legacy_projection_count,
                    "observed": len(legacy_evidence),
                }
            ),
        )
    classification = classify_correlated_legacy(
        legacy=legacy_evidence, sealed=sealed_evidence
    )
    manifest = build_qualified_manifest(
        company_id=source.company_id,
        branch_id=source.branch_id,
        classification=classification,
        sealed=sealed,
    )
    private = {
        "contract": COMMAND_VERSION,
        "plan_digest": plan_summary.plan_digest,
        "report": asdict(classification.report),
        "records": [asdict(item) for item in classification.records],
    }
    private["digest"] = _digest(private)
    _write_once(
        authority.classification_output,
        json.dumps(private, sort_keys=True, separators=(",", ":")).encode(),
    )
    _write_once(
        authority.qualified_manifest_output,
        json.dumps(
            manifest.private_payload(), sort_keys=True, separators=(",", ":")
        ).encode(),
    )
    packet = {
        "contract": "hcp-source4-enterprise-admission-packet/v1",
        "expected_repository_sha": source.expected_repository_sha,
        "plan_digest": plan_summary.plan_digest,
        "classification_digest": private["digest"],
        "classification_report_digest": classification.report.safe_digest,
        "qualified_manifest_digest": manifest.digest,
        "canonical_admission_allowed": classification.report.canonical_admission_allowed,
        "required_executor": "hcp-source4-preview-admission/v1",
        "execution_owner": "OM1-ENTERPRISE",
    }
    packet["digest"] = _digest(packet)
    _write_once(
        authority.admission_packet_output,
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode(),
    )
    return {
        "command": COMMAND_VERSION,
        "plan_digest": plan_summary.plan_digest,
        "report": asdict(classification.report),
        "qualified_manifest": {
            "digest": manifest.digest,
            "entry_count": len(manifest.entries),
        },
        "admission_packet": packet,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output = asyncio.run(
            run(PreviewClassificationAuthority.load(args.authority_file))
        )
    except SafeEvidenceError as error:
        print(json.dumps({"status": "rejected", "code": error.code}))
        return 2
    except Exception:  # noqa: BLE001 - protected data must not enter CLI errors
        print(json.dumps({"status": "rejected", "code": "classification_run_failed"}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
