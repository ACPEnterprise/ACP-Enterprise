from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from app.accounting_migration import (
    ARTIFACT_KINDS,
    ControlTie,
    InMemoryCheckpointStore,
    JournalLine,
    ManifestValidationError,
    OpeningMigrationRuntime,
    OpeningPackage,
    OpeningPackageValidator,
    OpeningStatePlan,
    RejectionEvidence,
    RollbackOnlyTarget,
    RowAccounting,
    RuntimeValidationError,
)
from app.accounting_migration.manifest import (
    CONDITIONAL_ARTIFACT_KINDS,
    canonical_manifest_sha256,
)

TRANSFORMATION_VERSION = "acc-mig-synthetic-v1"
COMPANY_ID = "00000000-0000-4000-8000-000000000101"
BRANCH_ID = "00000000-0000-4000-8000-000000000102"


def _artifact(kind: str, content: bytes, *, rejected: int = 0) -> dict[str, object]:
    artifact_id = f"synthetic-{kind}"
    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "role": "primary_source",
        "requirement": (
            "conditional" if kind in CONDITIONAL_ARTIFACT_KINDS else "required"
        ),
        "state": "accepted",
        "source_authority": "SYNTHETIC ONLY; SOURCE EVIDENCE REQUIRED",
        "path": f"source/{kind}.synthetic",
        "original_filename": f"{kind}.synthetic",
        "media_type": "application/x-acp-synthetic",
        "byte_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "exported_at": "2030-01-01T00:05:00-05:00",
        "report_definition": "SYNTHETIC ONLY; SOURCE EVIDENCE REQUIRED",
        "source_layout_evidence": "SYNTHETIC ONLY; SOURCE EVIDENCE REQUIRED",
        "source_row_count": 1,
        "accepted_row_count": 1 - rejected,
        "rejected_row_count": rejected,
        "pending_disposition_row_count": 0,
    }


def _manifest(root: Path, *, rejected_kind: str | None = None) -> Path:
    artifacts = []
    for kind in sorted(ARTIFACT_KINDS):
        content = f"synthetic:{kind}\n".encode()
        path = root / "source" / f"{kind}.synthetic"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        artifacts.append(_artifact(kind, content, rejected=int(kind == rejected_kind)))
    document: dict[str, object] = {
        "schema_version": "1.0.0",
        "contract_version": "ACC.DATA.1",
        "transformation_version": TRANSFORMATION_VERSION,
        "package_id": "00000000-0000-4000-8000-000000000099",
        "synthetic": True,
        "source_company": {
            "stable_id": "synthetic-source-company",
            "product": "QuickBooks",
            "edition": "SOURCE EVIDENCE REQUIRED",
            "version": "SOURCE EVIDENCE REQUIRED",
            "currency": "USD",
            "timezone": "America/New_York",
            "locale": "en-US",
            "accounting_basis": "accrual",
        },
        "target_binding": {
            "company_id": COMPANY_ID,
            "branch_policy": "synthetic-explicit-mapping",
            "branch_ids": [BRANCH_ID],
        },
        "cutoff": "2030-01-01T00:00:00-05:00",
        "generated_at": "2026-08-13T00:00:00-04:00",
        "artifacts": artifacts,
        "control_totals": [
            {
                "control_id": "opening-control",
                "equation": "QuickBooks closing balance = ACP opening balance",
                "currency": "USD",
                "source_amount": "100.00",
                "target_amount": "100.00",
                "variance": "0.00",
                "state": "passed",
                "evidence_sha256": "a" * 64,
            }
        ],
    }
    document["manifest_sha256"] = canonical_manifest_sha256(document)
    path = root / "manifest.json"
    path.write_text(json.dumps(document, indent=2) + "\n")
    return path


def _validator(
    *,
    version: str = TRANSFORMATION_VERSION,
    company_id: str = COMPANY_ID,
    branches: tuple[str, ...] = (BRANCH_ID,),
) -> OpeningPackageValidator:
    return OpeningPackageValidator(
        expected_transformation_version=version,
        expected_company_id=company_id,
        expected_branch_ids=branches,
    )


def _plan(package: OpeningPackage, *, rejected_kind: str | None = None) -> OpeningStatePlan:
    trial_balance = next(
        item for item in package.artifacts if item.kind == "trial_balance"
    )
    rows = tuple(
        RowAccounting(
            artifact_id=item.artifact_id,
            source=item.source_rows,
            accepted=item.accepted_rows,
            rejected=item.rejected_rows,
            pending_disposition=item.pending_rows,
        )
        for item in package.artifacts
        if item.role == "primary_source" and item.state == "accepted"
    )
    rejections: tuple[RejectionEvidence, ...] = ()
    if rejected_kind is not None:
        rejected = next(item for item in package.artifacts if item.kind == rejected_kind)
        rejections = (
            RejectionEvidence(
                artifact_id=rejected.artifact_id,
                source_row=1,
                reason_code="synthetic_invalid_row",
                source_identity_sha256="b" * 64,
            ),
        )
    return OpeningStatePlan(
        package_id=package.package_id,
        manifest_sha256=package.manifest_sha256,
        transformation_version=package.transformation_version,
        target_company_id=package.binding.target_company_id,
        target_branch_ids=package.binding.branch_ids,
        journal_lines=(
            JournalLine(
                line_id="opening-debit",
                account_source_id="synthetic-cash",
                branch_id=BRANCH_ID,
                debit=Decimal("100.00"),
                source_artifact_id=trial_balance.artifact_id,
                source_row=1,
            ),
            JournalLine(
                line_id="opening-credit",
                account_source_id="synthetic-equity",
                branch_id=BRANCH_ID,
                credit=Decimal("100.00"),
                source_artifact_id=trial_balance.artifact_id,
                source_row=1,
            ),
        ),
        controls=(
            ControlTie(
                control_id="opening-control",
                source_amount=Decimal("100.00"),
                opening_amount=Decimal("100.00"),
                source_artifact_id=trial_balance.artifact_id,
            ),
        ),
        row_accounting=rows,
        rejections=rejections,
    )


class OpeningPackageValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_complete_synthetic_manifest_is_accepted(self) -> None:
        package = _validator().validate(_manifest(self.root))

        self.assertEqual(len(package.artifacts), 34)
        self.assertEqual(package.binding.target_company_id, COMPANY_ID)
        self.assertEqual(
            package.archive_artifact_ids, ("synthetic-native_archive",)
        )

    def test_artifact_checksum_mismatch_is_rejected(self) -> None:
        manifest = _manifest(self.root)
        (self.root / "source" / "trial_balance.synthetic").write_bytes(b"changed")

        with self.assertRaisesRegex(
            ManifestValidationError, "artifact_size_mismatch|artifact_checksum_mismatch"
        ):
            _validator().validate(manifest)

    def test_manifest_checksum_mismatch_is_rejected(self) -> None:
        manifest = _manifest(self.root)
        document = json.loads(manifest.read_text())
        document["generated_at"] = "2026-08-13T00:00:01-04:00"
        manifest.write_text(json.dumps(document))

        with self.assertRaisesRegex(
            ManifestValidationError, "manifest_checksum_mismatch"
        ):
            _validator().validate(manifest)

    def test_unknown_artifact_is_rejected(self) -> None:
        manifest = _manifest(self.root)
        document = json.loads(manifest.read_text())
        document["artifacts"][0]["kind"] = "unknown_quickbooks_artifact"
        document["manifest_sha256"] = canonical_manifest_sha256(document)
        manifest.write_text(json.dumps(document))

        with self.assertRaisesRegex(ManifestValidationError, "unknown_artifact_kind"):
            _validator().validate(manifest)

    def test_company_branch_mismatch_is_rejected(self) -> None:
        manifest = _manifest(self.root)

        with self.assertRaisesRegex(ManifestValidationError, "company_branch_mismatch"):
            _validator(company_id="different-company").validate(manifest)

    def test_transformation_version_mismatch_is_rejected(self) -> None:
        manifest = _manifest(self.root)

        with self.assertRaisesRegex(
            ManifestValidationError, "transformation_version_mismatch"
        ):
            _validator(version="different-version").validate(manifest)

    def test_real_input_is_fail_closed_at_type_c_boundary(self) -> None:
        manifest = _manifest(self.root)
        document = json.loads(manifest.read_text())
        document["synthetic"] = False
        document["manifest_sha256"] = canonical_manifest_sha256(document)
        manifest.write_text(json.dumps(document))

        with self.assertRaisesRegex(
            ManifestValidationError, "type_c_real_input_prohibited"
        ):
            _validator().validate(manifest)


class OpeningRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = _validator().validate(_manifest(self.root))
        self.plan = _plan(self.package)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_balanced_opening_state_rolls_back_without_target_mutation(self) -> None:
        target = RollbackOnlyTarget()
        result = OpeningMigrationRuntime().run(self.package, self.plan, target=target)

        self.assertTrue(result.rolled_back)
        self.assertEqual(result.committed_records, 0)
        self.assertEqual(target.committed_records, 0)
        self.assertEqual(target.staged_records, 0)
        self.assertEqual(
            result.archive_artifact_ids, ("synthetic-native_archive",)
        )

    def test_unbalanced_opening_state_is_rejected_before_staging(self) -> None:
        unbalanced = replace(
            self.plan,
            journal_lines=(
                self.plan.journal_lines[0],
                replace(self.plan.journal_lines[1], credit=Decimal("99.99")),
            ),
        )
        target = RollbackOnlyTarget()

        with self.assertRaisesRegex(RuntimeValidationError, "opening_journal_unbalanced"):
            OpeningMigrationRuntime().run(self.package, unbalanced, target=target)
        self.assertEqual(target.staged_records, 0)

    def test_control_account_mismatch_is_rejected(self) -> None:
        mismatch = replace(
            self.plan,
            controls=(
                replace(self.plan.controls[0], opening_amount=Decimal("99.99")),
            ),
        )

        with self.assertRaisesRegex(RuntimeValidationError, "control_account_mismatch"):
            OpeningMigrationRuntime().run(
                self.package, mismatch, target=RollbackOnlyTarget()
            )

    def test_row_totals_must_match_manifest(self) -> None:
        first = self.plan.row_accounting[0]
        mismatch = replace(
            self.plan,
            row_accounting=(replace(first, source=2),) + self.plan.row_accounting[1:],
        )

        with self.assertRaisesRegex(RuntimeValidationError, "row_accounting_mismatch"):
            OpeningMigrationRuntime().run(
                self.package, mismatch, target=RollbackOnlyTarget()
            )

    def test_duplicate_replay_has_zero_delta_and_deterministic_audit(self) -> None:
        checkpoints = InMemoryCheckpointStore()
        runtime = OpeningMigrationRuntime(checkpoints=checkpoints)
        first = runtime.run(self.package, self.plan, target=RollbackOnlyTarget())
        replay = runtime.run(self.package, self.plan, target=RollbackOnlyTarget())

        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.delta_records, 0)
        self.assertEqual(replay.audit_sha256, first.audit_sha256)
        self.assertEqual(replay.idempotency_key, first.idempotency_key)

    def test_contradictory_replay_is_rejected(self) -> None:
        checkpoints = InMemoryCheckpointStore()
        runtime = OpeningMigrationRuntime(checkpoints=checkpoints)
        runtime.run(self.package, self.plan, target=RollbackOnlyTarget())
        changed = replace(
            self.plan,
            journal_lines=(
                replace(self.plan.journal_lines[0], account_source_id="changed"),
                self.plan.journal_lines[1],
            ),
        )

        with self.assertRaisesRegex(RuntimeValidationError, "contradictory_replay"):
            runtime.run(self.package, changed, target=RollbackOnlyTarget())

    def test_failed_attempt_can_retry_deterministically(self) -> None:
        checkpoints = InMemoryCheckpointStore()
        runtime = OpeningMigrationRuntime(checkpoints=checkpoints)
        failing = RollbackOnlyTarget(fail_after_stage=True)

        with self.assertRaisesRegex(RuntimeError, "synthetic_target_failure"):
            runtime.run(self.package, self.plan, target=failing)
        self.assertEqual(failing.staged_records, 0)

        retry = runtime.run(self.package, self.plan, target=RollbackOnlyTarget())
        baseline = OpeningMigrationRuntime().run(
            self.package, self.plan, target=RollbackOnlyTarget()
        )
        self.assertEqual(retry.audit_sha256, baseline.audit_sha256)
        self.assertEqual(retry.idempotency_key, baseline.idempotency_key)
        self.assertIn((retry.idempotency_key, "failed"), checkpoints.attempts)

    def test_rejected_rows_remain_explainable(self) -> None:
        other_root = self.root / "rejected"
        package = _validator().validate(
            _manifest(other_root, rejected_kind="gl_detail")
        )
        plan = _plan(package, rejected_kind="gl_detail")

        result = OpeningMigrationRuntime().run(
            package, plan, target=RollbackOnlyTarget()
        )

        self.assertEqual(result.rejected_rows, 1)
        self.assertNotIn("synthetic_invalid_row", result.audit_sha256)


if __name__ == "__main__":
    unittest.main()
