from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal
from uuid import UUID

ArtifactState = Literal[
    "accepted", "rejected", "not_applicable", "finance_disposition_required"
]
ArtifactRole = Literal["primary_source", "control_report", "archive_evidence"]

ARTIFACT_KINDS = frozenset(
    {
        "chart_of_accounts",
        "trial_balance",
        "gl_detail",
        "open_customer_invoices",
        "customer_credits",
        "ar_aging",
        "unapplied_customer_receipts",
        "undeposited_funds",
        "open_vendor_bills",
        "vendor_credits",
        "ap_aging",
        "bank_accounts",
        "cash_accounts",
        "credit_card_balances",
        "loan_balances_and_terms",
        "outstanding_checks",
        "deposits",
        "transfers",
        "reconciling_items",
        "sales_tax_liabilities",
        "inventory_control_balance",
        "payroll_liabilities_accruals",
        "payroll_summary",
        "fixed_assets",
        "accumulated_depreciation",
        "equity",
        "retained_earnings",
        "prepaids",
        "accruals",
        "customer_identities",
        "vendor_identities",
        "accounting_periods",
        "export_metadata",
        "native_archive",
    }
)

CONDITIONAL_ARTIFACT_KINDS = frozenset(
    {
        "credit_card_balances",
        "loan_balances_and_terms",
        "outstanding_checks",
        "deposits",
        "transfers",
        "reconciling_items",
        "fixed_assets",
        "accumulated_depreciation",
        "prepaids",
        "accruals",
    }
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "contract_version",
        "transformation_version",
        "package_id",
        "synthetic",
        "source_company",
        "target_binding",
        "cutoff",
        "generated_at",
        "artifacts",
        "control_totals",
        "manifest_sha256",
    }
)
_SOURCE_COMPANY_KEYS = frozenset(
    {
        "stable_id",
        "product",
        "edition",
        "version",
        "currency",
        "timezone",
        "locale",
        "accounting_basis",
    }
)
_TARGET_BINDING_KEYS = frozenset({"company_id", "branch_policy", "branch_ids"})
_ARTIFACT_KEYS = frozenset(
    {
        "artifact_id",
        "kind",
        "role",
        "requirement",
        "state",
        "source_authority",
        "path",
        "original_filename",
        "media_type",
        "byte_size",
        "sha256",
        "exported_at",
        "report_definition",
        "source_layout_evidence",
        "source_row_count",
        "accepted_row_count",
        "rejected_row_count",
        "pending_disposition_row_count",
        "finance_disposition_id",
    }
)
_CONTROL_KEYS = frozenset(
    {
        "control_id",
        "equation",
        "currency",
        "source_amount",
        "target_amount",
        "variance",
        "state",
        "evidence_sha256",
        "finance_disposition_id",
    }
)


class ManifestValidationError(ValueError):
    """Fail-closed manifest error that never contains source row values."""

    def __init__(self, code: str, *, artifact_id: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.artifact_id = artifact_id


@dataclass(frozen=True)
class CompanyBinding:
    source_company_id: str
    target_company_id: str
    branch_policy: str
    branch_ids: tuple[str, ...]
    currency: str
    timezone: str
    locale: str
    accounting_basis: str


@dataclass(frozen=True)
class ArtifactEvidence:
    artifact_id: str
    kind: str
    role: ArtifactRole
    requirement: str
    state: ArtifactState
    source_authority: str
    path: str
    byte_size: int
    sha256: str
    source_rows: int
    accepted_rows: int
    rejected_rows: int
    pending_rows: int
    finance_disposition_id: str | None


@dataclass(frozen=True)
class ManifestControl:
    control_id: str
    source_amount: str
    target_amount: str
    variance: str
    state: str
    evidence_sha256: str


@dataclass(frozen=True)
class OpeningPackage:
    package_id: str
    manifest_sha256: str
    transformation_version: str
    cutoff: str
    binding: CompanyBinding
    artifacts: tuple[ArtifactEvidence, ...]
    controls: tuple[ManifestControl, ...]
    artifact_paths: Mapping[str, Path]

    @property
    def archive_artifact_ids(self) -> tuple[str, ...]:
        return tuple(
            artifact.artifact_id
            for artifact in self.artifacts
            if artifact.kind == "native_archive" and artifact.state == "accepted"
        )


def canonical_manifest_sha256(document: Mapping[str, object]) -> str:
    """Digest the accepted JSON-domain manifest with its digest omitted.

    ACC.DATA.1 restricts manifests to JSON values used by this serializer. For
    those values, sorted compact UTF-8 JSON is the repository's deterministic
    RFC 8785-compatible representation.
    """

    payload = dict(document)
    payload.pop("manifest_sha256", None)
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class OpeningPackageValidator:
    """Validate an immutable synthetic ACC.DATA.1 package without transforming it."""

    def __init__(
        self,
        *,
        expected_transformation_version: str,
        expected_company_id: str,
        expected_branch_ids: tuple[str, ...],
    ) -> None:
        if not _VERSION.fullmatch(expected_transformation_version):
            raise ValueError("expected_transformation_version is invalid")
        if not expected_company_id or not expected_branch_ids:
            raise ValueError("Company and Branch expectations are required")
        self.expected_transformation_version = expected_transformation_version
        self.expected_company_id = expected_company_id
        self.expected_branch_ids = tuple(sorted(expected_branch_ids))

    @staticmethod
    def _object(value: object, code: str) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ManifestValidationError(code)
        return value

    @staticmethod
    def _string(document: Mapping[str, object], key: str, code: str) -> str:
        value = document.get(key)
        if not isinstance(value, str) or not value:
            raise ManifestValidationError(code)
        return value

    @staticmethod
    def _count(document: Mapping[str, object], key: str, artifact_id: str) -> int:
        value = document.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ManifestValidationError("invalid_row_count", artifact_id=artifact_id)
        return value

    @staticmethod
    def _safe_path(package_root: Path, value: str, artifact_id: str) -> Path:
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ManifestValidationError("unsafe_artifact_path", artifact_id=artifact_id)
        resolved_root = package_root.resolve()
        resolved = (resolved_root / Path(*relative.parts)).resolve()
        if resolved != resolved_root and resolved_root not in resolved.parents:
            raise ManifestValidationError("unsafe_artifact_path", artifact_id=artifact_id)
        return resolved

    @staticmethod
    def _closed_keys(
        document: Mapping[str, object], allowed: frozenset[str], code: str
    ) -> None:
        if not set(document).issubset(allowed):
            raise ManifestValidationError(code)

    @staticmethod
    def _timestamp(value: str, code: str) -> None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ManifestValidationError(code) from error
        if parsed.tzinfo is None:
            raise ManifestValidationError(code)

    def validate(self, manifest_path: Path) -> OpeningPackage:
        try:
            raw = manifest_path.read_bytes()
            document = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ManifestValidationError("invalid_manifest_json") from error
        document = self._object(document, "manifest_must_be_object")
        self._closed_keys(document, _TOP_LEVEL_KEYS, "unknown_manifest_property")
        if document.get("schema_version") != "1.0.0" or document.get(
            "contract_version"
        ) != "ACC.DATA.1":
            raise ManifestValidationError("unsupported_manifest_contract")
        if document.get("synthetic") is not True:
            raise ManifestValidationError("type_c_real_input_prohibited")

        manifest_digest = self._string(
            document, "manifest_sha256", "invalid_manifest_checksum"
        )
        if not _SHA256.fullmatch(manifest_digest) or (
            canonical_manifest_sha256(document) != manifest_digest
        ):
            raise ManifestValidationError("manifest_checksum_mismatch")

        transformation_version = self._string(
            document, "transformation_version", "missing_transformation_version"
        )
        if transformation_version != self.expected_transformation_version:
            raise ManifestValidationError("transformation_version_mismatch")

        source = self._object(
            document.get("source_company"), "missing_source_company"
        )
        target = self._object(document.get("target_binding"), "missing_target_binding")
        self._closed_keys(source, _SOURCE_COMPANY_KEYS, "unknown_source_company_property")
        self._closed_keys(target, _TARGET_BINDING_KEYS, "unknown_target_binding_property")
        if source.get("product") != "QuickBooks":
            raise ManifestValidationError("unsupported_source_product")
        self._string(source, "edition", "missing_source_edition")
        self._string(source, "version", "missing_source_version")
        currency = self._string(source, "currency", "missing_currency")
        if not _CURRENCY.fullmatch(currency):
            raise ManifestValidationError("invalid_currency")
        accounting_basis = self._string(
            source, "accounting_basis", "missing_accounting_basis"
        )
        if accounting_basis not in {"accrual", "cash"}:
            raise ManifestValidationError("invalid_accounting_basis")
        target_company_id = self._string(target, "company_id", "missing_company_id")
        raw_branches = target.get("branch_ids")
        if not isinstance(raw_branches, list) or not raw_branches or not all(
            isinstance(value, str) and value for value in raw_branches
        ):
            raise ManifestValidationError("invalid_branch_binding")
        if len(set(raw_branches)) != len(raw_branches):
            raise ManifestValidationError("invalid_branch_binding")
        if target_company_id != self.expected_company_id or tuple(
            sorted(raw_branches)
        ) != self.expected_branch_ids:
            raise ManifestValidationError("company_branch_mismatch")

        binding = CompanyBinding(
            source_company_id=self._string(
                source, "stable_id", "missing_source_company_identity"
            ),
            target_company_id=target_company_id,
            branch_policy=self._string(
                target, "branch_policy", "missing_branch_policy"
            ),
            branch_ids=tuple(sorted(raw_branches)),
            currency=currency,
            timezone=self._string(source, "timezone", "missing_timezone"),
            locale=self._string(source, "locale", "missing_locale"),
            accounting_basis=accounting_basis,
        )
        package_id = self._string(document, "package_id", "missing_package_id")
        try:
            UUID(package_id)
        except ValueError as error:
            raise ManifestValidationError("invalid_package_id") from error
        cutoff = self._string(document, "cutoff", "missing_cutoff")
        generated_at = self._string(document, "generated_at", "missing_generated_at")
        self._timestamp(cutoff, "invalid_cutoff")
        self._timestamp(generated_at, "invalid_generated_at")

        raw_artifacts = document.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise ManifestValidationError("missing_artifacts")
        artifacts: list[ArtifactEvidence] = []
        artifact_paths: dict[str, Path] = {}
        ids: set[str] = set()
        paths: set[str] = set()
        primary: dict[str, ArtifactEvidence] = {}
        package_root = manifest_path.parent
        for raw_artifact in raw_artifacts:
            value = self._object(raw_artifact, "invalid_artifact")
            self._closed_keys(value, _ARTIFACT_KEYS, "unknown_artifact_property")
            artifact_id = self._string(value, "artifact_id", "missing_artifact_id")
            if artifact_id in ids:
                raise ManifestValidationError("duplicate_artifact_id", artifact_id=artifact_id)
            ids.add(artifact_id)
            kind = self._string(value, "kind", "missing_artifact_kind")
            if kind not in ARTIFACT_KINDS:
                raise ManifestValidationError("unknown_artifact_kind", artifact_id=artifact_id)
            role = self._string(value, "role", "missing_artifact_role")
            if role not in {"primary_source", "control_report", "archive_evidence"}:
                raise ManifestValidationError("unknown_artifact_role", artifact_id=artifact_id)
            state = self._string(value, "state", "missing_artifact_state")
            requirement = self._string(
                value, "requirement", "missing_artifact_requirement"
            )
            if state not in {
                "accepted",
                "rejected",
                "not_applicable",
                "finance_disposition_required",
            }:
                raise ManifestValidationError("unknown_artifact_state", artifact_id=artifact_id)
            if requirement not in {"required", "conditional"}:
                raise ManifestValidationError(
                    "unknown_artifact_requirement", artifact_id=artifact_id
                )
            for key in (
                "source_authority",
                "original_filename",
                "media_type",
                "report_definition",
                "source_layout_evidence",
            ):
                self._string(value, key, f"missing_{key}")
            exported_at = self._string(value, "exported_at", "missing_exported_at")
            self._timestamp(exported_at, "invalid_exported_at")
            path_value = self._string(value, "path", "missing_artifact_path")
            if path_value in paths:
                raise ManifestValidationError("duplicate_artifact_path", artifact_id=artifact_id)
            paths.add(path_value)
            path = self._safe_path(package_root, path_value, artifact_id)
            size = value.get("byte_size")
            digest = self._string(value, "sha256", "invalid_artifact_checksum")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ManifestValidationError("invalid_artifact_size", artifact_id=artifact_id)
            if not _SHA256.fullmatch(digest):
                raise ManifestValidationError("invalid_artifact_checksum", artifact_id=artifact_id)
            if not path.is_file():
                raise ManifestValidationError("artifact_missing", artifact_id=artifact_id)
            raw_bytes = path.read_bytes()
            if len(raw_bytes) != size:
                raise ManifestValidationError("artifact_size_mismatch", artifact_id=artifact_id)
            if hashlib.sha256(raw_bytes).hexdigest() != digest:
                raise ManifestValidationError("artifact_checksum_mismatch", artifact_id=artifact_id)
            source_rows = self._count(value, "source_row_count", artifact_id)
            accepted_rows = self._count(value, "accepted_row_count", artifact_id)
            rejected_rows = self._count(value, "rejected_row_count", artifact_id)
            pending_rows = self._count(
                value, "pending_disposition_row_count", artifact_id
            )
            if source_rows != accepted_rows + rejected_rows + pending_rows:
                raise ManifestValidationError("row_accounting_mismatch", artifact_id=artifact_id)
            raw_disposition_id = value.get("finance_disposition_id")
            finance_disposition_id = (
                raw_disposition_id if isinstance(raw_disposition_id, str) else None
            )
            artifact = ArtifactEvidence(
                artifact_id=artifact_id,
                kind=kind,
                role=role,  # type: ignore[arg-type]
                requirement=requirement,
                state=state,  # type: ignore[arg-type]
                source_authority=self._string(
                    value, "source_authority", "missing_source_authority"
                ),
                path=path_value,
                byte_size=size,
                sha256=digest,
                source_rows=source_rows,
                accepted_rows=accepted_rows,
                rejected_rows=rejected_rows,
                pending_rows=pending_rows,
                finance_disposition_id=finance_disposition_id,
            )
            if role == "primary_source":
                if kind in primary:
                    raise ManifestValidationError(
                        "duplicate_primary_artifact", artifact_id=artifact_id
                    )
                primary[kind] = artifact
            artifacts.append(artifact)
            artifact_paths[artifact_id] = path

        if set(primary) != ARTIFACT_KINDS:
            raise ManifestValidationError("artifact_catalog_incomplete")
        for kind, artifact in primary.items():
            conditional = kind in CONDITIONAL_ARTIFACT_KINDS
            expected_requirement = "conditional" if conditional else "required"
            if artifact.requirement != expected_requirement:
                raise ManifestValidationError(
                    "artifact_requirement_mismatch", artifact_id=artifact.artifact_id
                )
            allowed_states = {"accepted", "not_applicable"} if conditional else {"accepted"}
            if artifact.state not in allowed_states:
                raise ManifestValidationError(
                    "artifact_not_ready", artifact_id=artifact.artifact_id
                )
            if artifact.state == "not_applicable" and (
                artifact.source_rows
                or artifact.accepted_rows
                or artifact.rejected_rows
                or artifact.pending_rows
                or not artifact.finance_disposition_id
            ):
                raise ManifestValidationError(
                    "not_applicable_without_finance_disposition",
                    artifact_id=artifact.artifact_id,
                )
            if artifact.pending_rows:
                raise ManifestValidationError(
                    "pending_finance_disposition", artifact_id=artifact.artifact_id
                )

        raw_controls = document.get("control_totals")
        if not isinstance(raw_controls, list) or not raw_controls:
            raise ManifestValidationError("missing_control_totals")
        controls: list[ManifestControl] = []
        control_ids: set[str] = set()
        for raw_control in raw_controls:
            value = self._object(raw_control, "invalid_control")
            self._closed_keys(value, _CONTROL_KEYS, "unknown_control_property")
            control_id = self._string(value, "control_id", "missing_control_id")
            if control_id in control_ids:
                raise ManifestValidationError("duplicate_control_id")
            control_ids.add(control_id)
            control = ManifestControl(
                control_id=control_id,
                source_amount=self._string(
                    value, "source_amount", "missing_control_amount"
                ),
                target_amount=self._string(
                    value, "target_amount", "missing_control_amount"
                ),
                variance=self._string(value, "variance", "missing_control_variance"),
                state=self._string(value, "state", "missing_control_state"),
                evidence_sha256=self._string(
                    value, "evidence_sha256", "missing_control_evidence"
                ),
            )
            self._string(value, "equation", "missing_control_equation")
            control_currency = self._string(
                value, "currency", "missing_control_currency"
            )
            if not _CURRENCY.fullmatch(control_currency):
                raise ManifestValidationError("invalid_control_currency")
            if not _SHA256.fullmatch(control.evidence_sha256):
                raise ManifestValidationError("invalid_control_evidence")
            try:
                source_amount = Decimal(control.source_amount)
                target_amount = Decimal(control.target_amount)
                variance = Decimal(control.variance)
            except InvalidOperation as error:
                raise ManifestValidationError("invalid_control_amount") from error
            if not all(
                amount.is_finite()
                for amount in (source_amount, target_amount, variance)
            ):
                raise ManifestValidationError("invalid_control_amount")
            if (
                control.state != "passed"
                or variance != 0
                or source_amount != target_amount
            ):
                raise ManifestValidationError("manifest_control_failed")
            controls.append(control)

        return OpeningPackage(
            package_id=package_id,
            manifest_sha256=manifest_digest,
            transformation_version=transformation_version,
            cutoff=cutoff,
            binding=binding,
            artifacts=tuple(artifacts),
            controls=tuple(controls),
            artifact_paths=MappingProxyType(artifact_paths),
        )
