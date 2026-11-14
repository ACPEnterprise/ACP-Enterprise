"""Fail-closed qualification for the sealed November HCP handoff bundle.

The November handoff intentionally excludes large attachment bodies.  This
module validates the custody seal and bounded operational disposition contract;
it never reads HCP, opens attachment bodies, or writes Preview data.
"""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError


AUTHORITY_CONTRACT = "hcp-november-preview-qualification/v1"
BUNDLE_CONTRACT = "hcp-november-operational-handoff/v1"
SEALED_HANDOFF_CONTRACT = "hcp-clean-beta-admission-handoff/v1"
BUNDLE_CONTRACTS = frozenset({BUNDLE_CONTRACT, SEALED_HANDOFF_CONTRACT})
EXPECTED_SCHEMA_HEAD = "yp8r0t2v4x6z"
REQUIRED_FILES = frozenset(
    {
        "BUNDLE-MANIFEST.json",
        "source/operational-acquisition-manifest.json",
        "source/open-work-artifact-addendum-manifest.json",
        "source/attachment-custody-manifest.json",
        "gate/gate-packet.json",
        "gate/provider-observations.json",
        "reconciliation/reconciliation-manifest.json",
        "reconciliation/technician-dispositions.json",
        "reconciliation/open-work-reconciliation.json",
        "reconciliation/owner-dispositions.json",
        "policy/final-operational-cutover-disposition.json",
        "identity/hcp-migration-2-authority.json",
        "identity/HCP1A.BRANCH_SCOPE.V1.json",
    }
)
EXPECTED_DISPOSITIONS = {
    "locationless_open_jobs": (22, "HOLD_QUARANTINE"),
    "legacy_duplicate_risk_appointments": (13, "HOLD"),
    "unresolved_technician_identities": (2, "HOLD"),
    "unassigned_appointments": (1, "HOLD"),
    "strict_open_relationship_failures": (0, "NONE"),
}
FINAL_POLICY_HOLD_COUNTS = {
    "locationless_open_jobs": 23,
    "legacy_duplicate_risk_appointments": 13,
    "unresolved_technician_identities": 2,
    "unassigned_appointments": 1,
}
FINAL_POLICY_APPOINTMENT_HOLD_COUNT = 14


def qualification_digest(packet: dict[str, Any]) -> str:
    """Digest the deterministic PASS packet bound by a later executor."""
    return _digest_bytes(_canonical(packet))


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fail(code: str, value: Any = "") -> None:
    evidence = _digest_bytes(_canonical(value))
    raise SafeEvidenceError(code, evidence)


def _required_uuid(value: Any, code: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        _fail(code, value)
    raise AssertionError("unreachable")


def _require_mapping(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(code, value)
    return value


def _require_text(mapping: dict[str, Any], key: str, code: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        _fail(code, {"key": key, "value": value})
    return value


def _json_bytes(value: bytes, name: str) -> Any:
    try:
        return json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        _fail("hcp_november_json_invalid", name)
        raise AssertionError("unreachable") from error


def _read_digest_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        result: dict[str, str] = {}
        for key, digest in value.items():
            if not isinstance(key, str) or not isinstance(digest, str):
                _fail("hcp_november_file_digest_invalid", value)
            result[key] = digest
        return result
    if isinstance(value, list):
        result = {}
        for item in value:
            row = _require_mapping(item, "hcp_november_file_digest_invalid")
            name = _require_text(row, "path", "hcp_november_file_digest_invalid")
            digest = _require_text(row, "sha256", "hcp_november_file_digest_invalid")
            result[name] = digest
        return result
    _fail("hcp_november_file_digest_invalid", value)
    raise AssertionError("unreachable")


def _action_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"create": 0, "update": 0, "replay": 0, "hold": 0}
    for record in records:
        disposition = str(record.get("disposition", "")).upper()
        action = str(record.get("action", "")).lower()
        if disposition in {"HOLD", "HOLD_QUARANTINE"} or action == "hold":
            counts["hold"] += 1
        elif action in counts:
            counts[action] += 1
        elif disposition in {"CREATE", "ADMIT_CREATE"}:
            counts["create"] += 1
        elif disposition in {"UPDATE", "ADMIT_UPDATE"}:
            counts["update"] += 1
        elif disposition in {"REPLAY", "ADMIT_REPLAY"}:
            counts["replay"] += 1
        else:
            _fail("hcp_november_record_action_unknown", record)
    return counts


@dataclass(frozen=True)
class NovemberQualificationAuthority:
    bundle_path: Path
    bundle_sha256: str
    expected_repository_sha: str
    expected_schema_head: str
    expected_company_id: str
    expected_branch_id: str
    expected_actor_id: str
    expected_hcp_provider_company_id: str
    expected_environment: str
    expected_acquisition_digest: str
    expected_reconciliation_digest: str
    expected_attachment_custody_digest: str
    bundle_root: Path | None = None
    expected_policy_digest: str | None = None
    qualification_status: str | None = None
    qualification_digest: str | None = None
    execution_packet_path: Path | None = None
    execution_packet_sha256: str | None = None
    execution_packet_digest: str | None = None
    rollback_backup_digest: str | None = None

    @property
    def company_id(self) -> UUID:
        return UUID(self.expected_company_id)

    @property
    def branch_id(self) -> UUID:
        return UUID(self.expected_branch_id)

    @property
    def actor_id(self) -> UUID:
        return UUID(self.expected_actor_id)

    @property
    def expected_database(self) -> str:
        return "acp_enterprise_preview"

    @classmethod
    def load(cls, path: Path) -> NovemberQualificationAuthority:
        try:
            if not path.is_file() or path.is_symlink():
                _fail("hcp_november_authority_missing", str(path))
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                _fail("hcp_november_authority_permissions", str(path))
            value = _require_mapping(
                json.loads(path.read_bytes()), "hcp_november_authority_invalid"
            )
            if value.get("contract") != AUTHORITY_CONTRACT:
                _fail("hcp_november_authority_contract", value.get("contract"))
            fields = {
                key: _require_text(value, key, "hcp_november_authority_field_missing")
                for key in (
                    "bundle_sha256",
                    "expected_repository_sha",
                    "expected_schema_head",
                    "expected_company_id",
                    "expected_branch_id",
                    "expected_actor_id",
                    "expected_hcp_provider_company_id",
                    "expected_environment",
                    "expected_acquisition_digest",
                    "expected_reconciliation_digest",
                    "expected_attachment_custody_digest",
                )
            }
            return cls(
                bundle_path=Path(
                    _require_text(
                        value, "bundle_path", "hcp_november_authority_field_missing"
                    )
                ),
                bundle_root=(
                    Path(value["bundle_root"])
                    if value.get("bundle_root")
                    else None
                ),
                expected_policy_digest=value.get("expected_policy_digest"),
                qualification_status=value.get("qualification_status"),
                qualification_digest=value.get("qualification_digest"),
                execution_packet_path=(
                    Path(value["execution_packet_path"])
                    if value.get("execution_packet_path")
                    else None
                ),
                execution_packet_sha256=value.get("execution_packet_sha256"),
                execution_packet_digest=value.get("execution_packet_digest"),
                rollback_backup_digest=value.get("rollback_backup_digest"),
                **fields,
            )
        except SafeEvidenceError:
            raise
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            _fail("hcp_november_authority_invalid", str(error))
        raise AssertionError("unreachable")

    def _verify_expected_values(self, manifest: dict[str, Any]) -> None:
        contract = manifest.get("contract")
        if contract not in BUNDLE_CONTRACTS:
            _fail("hcp_november_bundle_contract", manifest.get("contract"))
        if contract == BUNDLE_CONTRACT and manifest.get("environment") != self.expected_environment:
            _fail("hcp_november_environment_mismatch", manifest.get("environment"))
        if contract == SEALED_HANDOFF_CONTRACT:
            target = _require_mapping(manifest.get("target"), "hcp_november_target_missing")
            if target.get("label") != "clean-beta" or target.get("accessed_during_preparation") is not False:
                _fail("hcp_november_target_mismatch", target)
            safety = _require_mapping(manifest.get("safety"), "hcp_november_safety_missing")
            if any(safety.get(key) is not False for key in ("beta_accessed", "hcp_reacquired", "live_database_mutated", "pushed_to_github")):
                _fail("hcp_november_safety_boundary", safety)
        if manifest.get("bundle_sha256") not in (None, self.bundle_sha256):
            _fail("hcp_november_bundle_digest_declaration", manifest.get("bundle_sha256"))

        scope = _require_mapping(manifest.get("scope"), "hcp_november_scope_missing")
        expected_scope = (
            {
                "acp_company_id": self.expected_company_id,
                "acp_branch_id": self.expected_branch_id,
                "authorized_actor_id": self.expected_actor_id,
                "hcp_provider_company_id": self.expected_hcp_provider_company_id,
            }
            if contract == BUNDLE_CONTRACT
            else {
                "company_id": self.expected_company_id,
                "branch_id": self.expected_branch_id,
                "actor_id": self.expected_actor_id,
                "hcp_provider_company_id": self.expected_hcp_provider_company_id,
            }
        )
        for key, expected in expected_scope.items():
            actual = _required_uuid(scope.get(key), "hcp_november_scope_invalid")
            if actual != _required_uuid(expected, "hcp_november_authority_scope_invalid"):
                _fail("hcp_november_scope_mismatch", {"key": key, "actual": actual})

        if contract == BUNDLE_CONTRACT:
            authority = _require_mapping(
                manifest.get("authority"), "hcp_november_authority_metadata_missing"
            )
            if _require_text(authority, "repository_sha", "hcp_november_authority_metadata_missing") != self.expected_repository_sha:
                _fail("hcp_november_repository_mismatch", authority)
            if _require_text(authority, "schema_head", "hcp_november_authority_metadata_missing") != self.expected_schema_head:
                _fail("hcp_november_schema_mismatch", authority)
            digests = _require_mapping(manifest.get("digests"), "hcp_november_digest_metadata_missing")
            expected_digests = {
                "acquisition_digest": self.expected_acquisition_digest,
                "reconciliation_digest": self.expected_reconciliation_digest,
                "attachment_custody_digest": self.expected_attachment_custody_digest,
            }
        else:
            source_digests = _require_mapping(manifest.get("source_digests"), "hcp_november_digest_metadata_missing")
            digests = {
                "acquisition_digest": source_digests.get("acquisition"),
                "reconciliation_digest": source_digests.get("reconciliation"),
                "attachment_custody_digest": source_digests.get("attachment_custody"),
            }
            expected_digests = {
                "acquisition_digest": self.expected_acquisition_digest,
                "reconciliation_digest": self.expected_reconciliation_digest,
                "attachment_custody_digest": self.expected_attachment_custody_digest,
            }
        for key, expected in expected_digests.items():
            if digests.get(key) != expected:
                _fail("hcp_november_digest_mismatch", {"key": key})

    def _payloads(self) -> tuple[dict[str, bytes], dict[str, Any]]:
        bundle = self.bundle_path
        if not bundle.is_file() or bundle.is_symlink():
            _fail("hcp_november_bundle_missing", str(bundle))
        if stat.S_IMODE(bundle.stat().st_mode) & 0o077:
            _fail("hcp_november_bundle_permissions", str(bundle))
        if _digest_file(bundle) != self.bundle_sha256:
            _fail("hcp_november_bundle_sha256_mismatch", str(bundle))

        if self.bundle_root is not None:
            root = self.bundle_root
            if not root.is_dir() or root.is_symlink():
                _fail("hcp_november_bundle_root_missing", str(root))
            files = {
                path.relative_to(root).as_posix(): path
                for path in root.rglob("*")
                if path.is_file()
            }
            if set(files) != REQUIRED_FILES:
                _fail("hcp_november_bundle_contents_mismatch", {"files": sorted(files)})
            payloads = {name: files[name].read_bytes() for name in REQUIRED_FILES}
        else:
            try:
                with zipfile.ZipFile(bundle) as archive:
                    names = set(archive.namelist())
                    if names != REQUIRED_FILES:
                        _fail("hcp_november_bundle_contents_mismatch", {"missing": sorted(REQUIRED_FILES - names), "extra": sorted(names - REQUIRED_FILES)})
                    payloads = {name: archive.read(name) for name in REQUIRED_FILES}
            except (OSError, zipfile.BadZipFile, KeyError) as error:
                _fail("hcp_november_bundle_unreadable", str(error))
        manifest = _require_mapping(_json_bytes(payloads["BUNDLE-MANIFEST.json"], "BUNDLE-MANIFEST.json"), "hcp_november_bundle_manifest_invalid")
        return payloads, manifest

    def verify(self) -> dict[str, Any]:
        if self.expected_environment != "preview":
            _fail("hcp_november_target_environment_invalid", self.expected_environment)
        if len(self.expected_repository_sha) != 40 or any(
            character not in "0123456789abcdef" for character in self.expected_repository_sha
        ):
            _fail("hcp_november_repository_sha_invalid", self.expected_repository_sha)
        if self.expected_schema_head != EXPECTED_SCHEMA_HEAD:
            _fail("hcp_november_schema_head_invalid", self.expected_schema_head)
        for value in (
            self.bundle_sha256,
            self.expected_acquisition_digest,
            self.expected_reconciliation_digest,
            self.expected_attachment_custody_digest,
            *(([self.expected_policy_digest]) if self.expected_policy_digest else []),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                _fail("hcp_november_digest_invalid", value)

        payloads, manifest = self._payloads()
        self._verify_expected_values(manifest)

        file_digests = _read_digest_map(manifest.get("file_sha256") if manifest.get("file_sha256") is not None else manifest.get("included_files"))
        for name in REQUIRED_FILES - {"BUNDLE-MANIFEST.json"}:
            if file_digests.get(name) != _digest_bytes(payloads[name]):
                _fail("hcp_november_file_digest_mismatch", name)

        if manifest.get("contract") == SEALED_HANDOFF_CONTRACT:
            reconciliation = _require_mapping(_json_bytes(payloads["reconciliation/reconciliation-manifest.json"], "reconciliation-manifest.json"), "hcp_november_reconciliation_invalid")
            summary = _require_mapping(reconciliation.get("summary"), "hcp_november_reconciliation_summary_missing")
            actual_summary = {
                "locationless_open_jobs": summary.get("locationless_open_jobs_hold"),
                "legacy_duplicate_risk_appointments": summary.get("legacy_duplicate_risk_appointments_hold"),
                "unresolved_technician_identities": summary.get("technicians_unresolved_hold"),
                "unassigned_appointments": summary.get("unassigned_open_work_appointments_intent_not_proven"),
                "strict_open_relationship_failures": summary.get("strict_open_appointment_relationship_failures"),
            }
            for key, (expected_count, _) in EXPECTED_DISPOSITIONS.items():
                if actual_summary.get(key) != expected_count:
                    _fail("hcp_november_disposition_count_mismatch", {"key": key, "count": actual_summary.get(key)})
            policy = _require_mapping(_json_bytes(payloads["policy/final-operational-cutover-disposition.json"], "final-operational-cutover-disposition.json"), "hcp_november_policy_invalid")
            if not self.expected_policy_digest:
                _fail("hcp_november_policy_digest_missing", "expected_policy_digest")
            if policy.get("digest") != self.expected_policy_digest:
                _fail("hcp_november_policy_digest_mismatch", policy.get("digest"))
            if policy.get("source_reconciliation_digest") != self.expected_reconciliation_digest:
                _fail("hcp_november_policy_source_mismatch", policy.get("source_reconciliation_digest"))
            if policy.get("source_mutation") is not False or policy.get("live_database_access") is not False or policy.get("network_access") is not False:
                _fail("hcp_november_policy_safety_boundary", policy)
            contamination = _require_mapping(policy.get("hold_contamination"), "hcp_november_hold_contamination_missing")
            if contamination.get("inherent_contamination_if_final_policy_is_enforced") is not False or contamination.get("unrelated_clean_jobs_blocked") != 0 or contamination.get("unrelated_clean_appointments_blocked") != 0:
                _fail("hcp_november_clean_record_blocked", contamination)
            omissions = policy.get("unexplained_omissions_in_original_gate", [])
            if omissions not in ([], None):
                _fail("hcp_november_qualification_gap", {"key": "unexplained_omissions", "value": omissions})
            resolved_omissions = policy.get("resolved_original_gate_omissions")
            if not isinstance(resolved_omissions, list) or len(resolved_omissions) != 2:
                _fail("hcp_november_resolved_omissions_invalid", resolved_omissions)
            for omission in resolved_omissions:
                row = _require_mapping(omission, "hcp_november_resolved_omission_invalid")
                _require_text(row, "source_id", "hcp_november_resolved_omission_invalid")
                if row.get("final_disposition") not in {"HOLD", "HOLD_QUARANTINE"}:
                    if row.get("original_disposition") in {"HOLD", "HOLD_QUARANTINE"}:
                        _fail("hcp_november_prior_hold_released", row)
                    _fail("hcp_november_resolved_omission_not_held", row)
            prior_policy_digest = policy.get("source_prior_policy_digest")
            if not isinstance(prior_policy_digest, str) or len(prior_policy_digest) != 64:
                _fail("hcp_november_prior_policy_digest_missing", prior_policy_digest)
            dispositions = {key: count for key, count in actual_summary.items()}
            held = _require_mapping(policy.get("held_quarantined"), "hcp_november_hold_inventory_missing")
            hold_source_ids = {
                "locationless_open_jobs": tuple(_require_mapping(held.get("locationless_open_jobs"), "hcp_november_hold_inventory_missing").get("source_ids", [])),
                "legacy_duplicate_risk_appointments": tuple(_require_mapping(held.get("legacy_duplicate_risk_appointments"), "hcp_november_hold_inventory_missing").get("source_ids", [])),
                "unresolved_technician_identities": tuple(_require_mapping(held.get("technician_conflicts"), "hcp_november_hold_inventory_missing").get("source_ids", [])),
                "unassigned_appointments": (str(_require_mapping(held.get("unassigned_appointment"), "hcp_november_hold_inventory_missing").get("source_id")),),
            }
            final_hold_counts = {key: len(value) for key, value in hold_source_ids.items()}
            if final_hold_counts != FINAL_POLICY_HOLD_COUNTS:
                _fail("hcp_november_hold_inventory_mismatch", hold_source_ids)
            if (
                final_hold_counts["legacy_duplicate_risk_appointments"]
                + final_hold_counts["unassigned_appointments"]
                != FINAL_POLICY_APPOINTMENT_HOLD_COUNT
            ):
                _fail("hcp_november_hold_inventory_mismatch", final_hold_counts)
            return {
                "contract": AUTHORITY_CONTRACT,
                "bundle_contract": SEALED_HANDOFF_CONTRACT,
                "bundle_sha256": self.bundle_sha256,
                "acquisition_digest": self.expected_acquisition_digest,
                "reconciliation_digest": self.expected_reconciliation_digest,
                "policy_digest": self.expected_policy_digest,
                "attachment_custody_digest": self.expected_attachment_custody_digest,
                "company_id": self.expected_company_id,
                "branch_id": self.expected_branch_id,
                "actor_id": self.expected_actor_id,
                "hcp_provider_company_id": self.expected_hcp_provider_company_id,
                "repository_sha": self.expected_repository_sha,
                "schema_head": self.expected_schema_head,
                "environment": self.expected_environment,
                "attachment_bodies_required": False,
                "dispositions": dispositions,
                "final_policy_dispositions": final_hold_counts,
                "final_policy_appointment_hold_count": FINAL_POLICY_APPOINTMENT_HOLD_COUNT,
                "hold_source_ids": hold_source_ids,
                "counts": {"create": None, "update": None, "replay": None, "hold": 38},
                "unexplained_omissions": 0,
                "missing_lineage": 0,
                "ambiguous_lineage": 0,
                "qualification": "PASS",
            }

        attachments = _require_mapping(
            manifest.get("attachments"), "hcp_november_attachment_metadata_missing"
        )
        if attachments.get("bodies_included") is not False:
            _fail("hcp_november_attachment_bodies_present", attachments)
        if attachments.get("custody_digest") != self.expected_attachment_custody_digest:
            _fail("hcp_november_attachment_custody_mismatch", attachments)

        dispositions = _require_mapping(
            manifest.get("dispositions"), "hcp_november_dispositions_missing"
        )
        normalized_counts: dict[str, int] = {}
        for key, (expected_count, expected_disposition) in EXPECTED_DISPOSITIONS.items():
            row = _require_mapping(dispositions.get(key), "hcp_november_disposition_invalid")
            count = row.get("count")
            if not isinstance(count, int) or count != expected_count:
                _fail("hcp_november_disposition_count_mismatch", {"key": key, "count": count})
            if row.get("disposition") != expected_disposition:
                _fail("hcp_november_disposition_mismatch", {"key": key, "disposition": row.get("disposition")})
            normalized_counts[key] = count

        quality = _require_mapping(
            manifest.get("qualification"), "hcp_november_qualification_metadata_missing"
        )
        if quality.get("held_identities_excluded") is not True:
            _fail("hcp_november_held_identity_guard_missing", quality)
        if quality.get("clean_records_not_blocked") is not True:
            _fail("hcp_november_clean_record_guard_missing", quality)
        for key in ("unexplained_omissions", "missing_lineage", "ambiguous_lineage"):
            if quality.get(key) not in (0, []):
                _fail("hcp_november_qualification_gap", {"key": key, "value": quality.get(key)})

        assertions = manifest.get("record_assertions")
        if not isinstance(assertions, list) or not assertions:
            _fail("hcp_november_record_assertions_missing", "record_assertions")
        records: list[dict[str, Any]] = []
        for item in assertions:
            record = _require_mapping(item, "hcp_november_record_assertion_invalid")
            _require_text(record, "source_id", "hcp_november_record_identity_missing")
            _require_text(record, "domain", "hcp_november_record_identity_missing")
            if record.get("lineage") != "EXACT":
                _fail("hcp_november_record_lineage_invalid", record)
            disposition = record.get("disposition")
            if disposition not in {"HOLD", "HOLD_QUARANTINE", "CREATE", "UPDATE", "REPLAY"}:
                _fail("hcp_november_record_disposition_invalid", record)
            if disposition in {"HOLD", "HOLD_QUARANTINE"} and record.get("admission_allowed") is not False:
                _fail("hcp_november_held_identity_admittable", record)
            if disposition not in {"HOLD", "HOLD_QUARANTINE"} and record.get("admission_allowed") is not True:
                _fail("hcp_november_clean_record_blocked", record)
            records.append(record)

        counts = _action_counts(records)
        expected_hold_count = sum(
            count for key, (count, _) in EXPECTED_DISPOSITIONS.items() if key != "strict_open_relationship_failures"
        )
        if counts["hold"] < expected_hold_count:
            _fail("hcp_november_hold_records_incomplete", counts)
        return {
            "contract": AUTHORITY_CONTRACT,
            "bundle_contract": BUNDLE_CONTRACT,
            "bundle_sha256": self.bundle_sha256,
            "acquisition_digest": self.expected_acquisition_digest,
            "reconciliation_digest": self.expected_reconciliation_digest,
            "attachment_custody_digest": self.expected_attachment_custody_digest,
            "company_id": self.expected_company_id,
            "branch_id": self.expected_branch_id,
            "actor_id": self.expected_actor_id,
            "hcp_provider_company_id": self.expected_hcp_provider_company_id,
            "repository_sha": self.expected_repository_sha,
            "schema_head": self.expected_schema_head,
            "environment": self.expected_environment,
            "attachment_bodies_required": False,
            "dispositions": normalized_counts,
            "counts": counts,
            "unexplained_omissions": 0,
            "missing_lineage": 0,
            "ambiguous_lineage": 0,
            "qualification": "PASS",
        }
