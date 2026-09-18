"""Reusable provider-acquisition completeness evidence for migrations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "migration-provider-acquisition-completeness/v1"
NEVER_INFER: Final = (
    "identity_from_name",
    "identity_from_email",
    "identity_from_phone",
    "location_identity_from_address_alone",
    "financial_overlap_from_amount_or_date",
    "accounting_authority_from_source_display",
)
QBO_REQUESTED: Final = (
    "profit_and_loss",
    "balance_sheet",
    "trial_balance",
    "general_ledger",
    "ar_aging_detail",
    "ap_aging_detail",
    "customer_balance_detail",
    "vendor_balance_detail",
    "open_invoices",
    "unpaid_bills",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collection(source_root: Path, family: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((source_root / "raw" / family).glob("page-*.json")):
        records.extend(_load(path)[family])
    return records


@dataclass(frozen=True)
class ProviderCompletenessManifest:
    contract: str
    providers: tuple[dict[str, object], ...]
    invariants: dict[str, object]
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        observed = payload.pop("digest")
        if (
            self.contract != CONTRACT
            or observed != hashlib.sha256(_canonical(payload)).hexdigest()
        ):
            raise ValueError("provider completeness digest mismatch")
        for provider in self.providers:
            if not provider.get("provider") or not provider.get("environment"):
                raise ValueError("provider identity/environment missing")
            if "final_completeness_disposition" not in provider:
                raise ValueError("provider final disposition missing")


def build_provider_completeness_manifest(
    *, hcp_source_root: Path, qbo_controls_root: Path
) -> ProviderCompletenessManifest:
    package_path = hcp_source_root / "acquisition-package-manifest.json"
    collection_path = hcp_source_root / "collection-manifest.json"
    package = _load(package_path)
    collection = _load(collection_path)
    if package.get("contract") != "hcp-source-4-acquisition-package/v1":
        raise ValueError("unsupported HCP source package")
    if package.get("request_methods") != ["GET"]:
        raise ValueError("HCP acquisition was not read-only")

    acquired_hcp: dict[str, int] = {
        name: int(evidence["record_count"])
        for name, evidence in sorted(collection["collections"].items())
    }
    customers = _collection(hcp_source_root, "customers")
    jobs = _collection(hcp_source_root, "jobs")
    invoices = _collection(hcp_source_root, "invoices")
    locations = {
        str(address["id"])
        for customer in customers
        for address in customer.get("addresses") or []
        if address.get("id")
    }
    locations.update(
        str(address["id"])
        for job in jobs
        if (address := job.get("address") or {}).get("id")
    )
    appointment_path = hcp_source_root / "relationship-appointments-manifest.json"
    appointments = _load(appointment_path)
    acquired_hcp.update(
        appointments=int(appointments["appointment_record_count"]),
        locations=len(locations),
        payments=sum(len(invoice.get("payments") or []) for invoice in invoices),
        refunds=sum(len(invoice.get("refunds") or []) for invoice in invoices),
    )
    requested_hcp = tuple(sorted((*acquired_hcp, "attachments")))
    unsupported_hcp = ("attachments",)
    appointment_errors = sum(
        int(artifact.get("http_status") or 0) != 200
        for artifact in appointments.get("artifacts") or []
    )
    hcp: dict[str, object] = {
        "provider": "housecall_pro",
        "company_or_realm": "All County Plumbing and Leak",
        "environment": collection.get("source_environment") or "production",
        "scopes": ["read_only_get"],
        "start": collection["acquisition_started_at"],
        "end": collection["acquisition_completed_at"],
        "source_as_of": collection["acquisition_completed_at"],
        "requested_families": requested_hcp,
        "acquired_families": tuple(sorted(acquired_hcp)),
        "counts": acquired_hcp,
        "provider_ids_present": True,
        "versions_or_sync_tokens": "provider updated_at where supplied",
        "unsupported_families": unsupported_hcp,
        "permission_blocked": (),
        "source_missing": (),
        "ambiguous": ("attachment availability",),
        "conflicting": (),
        "owner_input": ("employee native identity certification",),
        "accountant_input": ("HCP/QBO financial overlap",),
        "never_infer": NEVER_INFER,
        "retries_or_errors": (
            {"family": "appointments", "relationship_errors": appointment_errors},
        ),
        "sandbox_production_isolation": "production evidence; no sandbox artifacts",
        "mutation_count": 0,
        "artifact_sha256": {
            "package": _sha(package_path),
            "collection": _sha(collection_path),
            "appointments": _sha(appointment_path),
        },
        "final_completeness_disposition": "PARTIAL_SOURCE_ACQUISITION_NOT_MIGRATION_COMPLETE",
    }

    registrations: list[dict[str, Any]] = []
    registration_shas: dict[str, str] = {}
    for path in sorted(qbo_controls_root.glob("*.json")):
        value = _load(path)
        if value.get("schema_version") == "qbo-control-registration/v1":
            registrations.append(value)
            registration_shas[path.name] = _sha(path)
    kinds = sorted({str(value["kind"]) for value in registrations})
    counts = {
        kind: sum(value.get("kind") == kind for value in registrations)
        for kind in kinds
    }
    missing = tuple(sorted(set(QBO_REQUESTED) - set(kinds)))
    realms = sorted(
        {
            str(value.get("realm_id") or value.get("realm") or "UNAVAILABLE")
            for value in registrations
        }
    )
    qbo: dict[str, object] = {
        "provider": "quickbooks_online",
        "company_or_realm": realms,
        "environment": "production_source_evidence",
        "scopes": ["reports_read_only"],
        "start": None,
        "end": None,
        "source_as_of": "per-report provider metadata",
        "requested_families": QBO_REQUESTED,
        "acquired_families": tuple(kinds),
        "counts": counts,
        "provider_ids_present": "per report; transaction rows vary",
        "versions_or_sync_tokens": "per-report registration metadata",
        "unsupported_families": (),
        "permission_blocked": (),
        "source_missing": missing,
        "ambiguous": (),
        "conflicting": (),
        "owner_input": (),
        "accountant_input": ("credits, unapplied payments, and ledger tie-out",),
        "never_infer": NEVER_INFER,
        "retries_or_errors": (),
        "sandbox_production_isolation": "registered production controls only",
        "mutation_count": 0,
        "artifact_sha256": registration_shas,
        "authority": "QBO_SOURCE_BACKED",
        "accepted_as_acp_accounting": False,
        "final_completeness_disposition": "COMPLETE_REGISTERED_REPORT_SET"
        if not missing
        else "PARTIAL_SOURCE_ACQUISITION_NOT_MIGRATION_COMPLETE",
    }
    invariants: dict[str, object] = {
        "connected_successfully_equals_migration_complete": False,
        "all_requested_families_must_have_disposition": True,
        "fuzzy_matching_permitted": False,
        "provider_mutation_count": 0,
        "production_mutation_count": 0,
        "financial_source_equals_native_accounting": False,
    }
    payload = {"contract": CONTRACT, "providers": (hcp, qbo), "invariants": invariants}
    result = ProviderCompletenessManifest(
        contract=CONTRACT,
        providers=(hcp, qbo),
        invariants=invariants,
        digest=hashlib.sha256(_canonical(payload)).hexdigest(),
    )
    result.verify()
    return result
