from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class QboEvidenceMode(str, Enum):
    LIVE = "live"
    HISTORICAL = "historical"
    BLOCKED = "blocked"


class QboEvidenceCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class QboReportControl:
    report_kind: str
    accounting_basis: str
    report_end_date: str
    generated_at: str | None
    registration_sha256: str

    def __post_init__(self) -> None:
        if self.accounting_basis not in {"cash", "accrual", "operational"}:
            raise ValueError("explicit report basis is required")
        if not _SHA256.fullmatch(self.registration_sha256):
            raise ValueError("immutable report registration is required")


@dataclass(frozen=True)
class QboOm2bEvidencePacket:
    """Secret-free source packet; it is evidence, never an ACP ledger or Customer master."""

    contract_version: str
    mode: QboEvidenceMode
    provider: str
    provider_environment: str
    company_identity_sha256: str | None
    company_info_verified_at: str | None
    api_minor_version: int | None
    source_manifest_sha256: str | None
    acquisition_started_at: str | None
    acquisition_ended_at: str | None
    accounting_date_cutoff: str | None
    cutoff_timezone: str | None
    completeness: QboEvidenceCompleteness
    entity_counts: Mapping[str, int]
    page_counts: Mapping[str, int]
    catalog_dispositions: tuple[Mapping[str, str], ...]
    report_controls: tuple[QboReportControl, ...]
    limitations: tuple[str, ...]
    packet_sha256: str

    def __post_init__(self) -> None:
        if self.contract_version != "qbo-om2b-source-evidence/v1":
            raise ValueError("unsupported OM2-B evidence contract")
        if self.provider != "quickbooks_online":
            raise ValueError("QuickBooks Online provider identity is required")
        if self.mode is QboEvidenceMode.LIVE:
            if self.provider_environment != "production":
                raise ValueError("live evidence must be production evidence")
            if not all(
                (
                    self.company_identity_sha256,
                    self.company_info_verified_at,
                    self.source_manifest_sha256,
                    self.acquisition_started_at,
                    self.acquisition_ended_at,
                )
            ):
                raise ValueError("live evidence requires verified, sealed acquisition")
        if self.completeness is QboEvidenceCompleteness.COMPLETE and not (
            self.source_manifest_sha256 and self.acquisition_ended_at
        ):
            raise ValueError("complete evidence requires a terminal sealed manifest")
        for digest in (self.company_identity_sha256, self.source_manifest_sha256):
            if digest is not None and not _SHA256.fullmatch(digest):
                raise ValueError("evidence digest is invalid")
        if not _SHA256.fullmatch(self.packet_sha256):
            raise ValueError("packet digest is invalid")
        object.__setattr__(
            self, "entity_counts", MappingProxyType(dict(self.entity_counts))
        )
        object.__setattr__(
            self, "page_counts", MappingProxyType(dict(self.page_counts))
        )
        object.__setattr__(
            self,
            "catalog_dispositions",
            tuple(MappingProxyType(dict(item)) for item in self.catalog_dispositions),
        )


def build_om2b_evidence_packet(
    *,
    mode: QboEvidenceMode,
    provider_environment: str,
    connection_marker: Mapping[str, object] | None,
    source_manifest: Mapping[str, object] | None,
    source_manifest_sha256: str | None,
    report_controls: tuple[QboReportControl, ...] = (),
    limitations: tuple[str, ...] = (),
) -> QboOm2bEvidencePacket:
    if provider_environment not in {"production", "historical_control"}:
        raise ValueError("bounded provider environment is required")
    marker = connection_marker or {}
    manifest = source_manifest or {}
    state = str(manifest.get("state", "unavailable"))
    completeness = (
        QboEvidenceCompleteness.COMPLETE
        if state == "complete"
        else QboEvidenceCompleteness.PARTIAL
        if state == "partial"
        else QboEvidenceCompleteness.UNAVAILABLE
    )
    identity = _company_identity(marker)
    entities = _integer_mapping(manifest.get("entity_counts", {}))
    pages = _page_counts(manifest.get("pages", []))
    dispositions = _catalog_dispositions(manifest.get("catalog_dispositions", []))
    snapshot = manifest.get("snapshot")
    api_minor_value = (
        snapshot.get("api_minor_version")
        if isinstance(snapshot, Mapping)
        else marker.get("api_minor_version")
    )
    api_minor_version = (
        int(str(api_minor_value)) if api_minor_value is not None else None
    )
    effective_limitations = set(limitations)
    if mode is not QboEvidenceMode.LIVE:
        effective_limitations.add("not_live_provider_evidence")
    if completeness is not QboEvidenceCompleteness.COMPLETE:
        effective_limitations.add("source_acquisition_incomplete")
    effective_limitations.update(
        {
            "source_reported_not_enterprise_accepted",
            "no_customer_master_authority",
            "no_ledger_posting_authority",
            "no_financial_policy_authority",
        }
    )
    canonical = {
        "contract_version": "qbo-om2b-source-evidence/v1",
        "mode": mode.value,
        "provider": "quickbooks_online",
        "provider_environment": provider_environment,
        "company_identity_sha256": identity,
        "company_info_verified_at": marker.get("company_info_verified_at"),
        "api_minor_version": api_minor_version,
        "source_manifest_sha256": source_manifest_sha256,
        "acquisition_started_at": manifest.get("started_at"),
        "acquisition_ended_at": manifest.get("ended_at"),
        "accounting_date_cutoff": _snapshot_value(manifest, "accounting_date_cutoff"),
        "cutoff_timezone": _snapshot_value(manifest, "cutoff_timezone"),
        "completeness": completeness.value,
        "entity_counts": entities,
        "page_counts": pages,
        "catalog_dispositions": dispositions,
        "report_controls": [control.__dict__ for control in report_controls],
        "limitations": sorted(effective_limitations),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return QboOm2bEvidencePacket(
        contract_version="qbo-om2b-source-evidence/v1",
        mode=mode,
        provider="quickbooks_online",
        provider_environment=provider_environment,
        company_identity_sha256=identity,
        company_info_verified_at=(
            str(marker["company_info_verified_at"])
            if marker.get("company_info_verified_at") is not None
            else None
        ),
        api_minor_version=(api_minor_version),
        source_manifest_sha256=source_manifest_sha256,
        acquisition_started_at=(
            str(manifest["started_at"])
            if manifest.get("started_at") is not None
            else None
        ),
        acquisition_ended_at=(
            str(manifest["ended_at"]) if manifest.get("ended_at") is not None else None
        ),
        accounting_date_cutoff=_snapshot_value(manifest, "accounting_date_cutoff"),
        cutoff_timezone=_snapshot_value(manifest, "cutoff_timezone"),
        completeness=completeness,
        entity_counts=entities,
        page_counts=pages,
        catalog_dispositions=tuple(dispositions),
        report_controls=report_controls,
        limitations=tuple(sorted(effective_limitations)),
        packet_sha256=digest,
    )


def _company_identity(marker: Mapping[str, object]) -> str | None:
    values = tuple(
        marker.get(key)
        for key in ("environment", "realm_id", "company_info_id", "company_name")
    )
    if not all(isinstance(value, str) and value for value in values):
        return None
    return hashlib.sha256(":".join(values).encode()).hexdigest()  # type: ignore[arg-type]


def _snapshot_value(manifest: Mapping[str, object], key: str) -> str | None:
    snapshot = manifest.get("snapshot")
    if not isinstance(snapshot, Mapping):
        return None
    value = snapshot.get(key)
    return str(value) if value is not None else None


def _integer_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError("entity counts are invalid")
    result = {str(key): int(count) for key, count in value.items()}
    if any(count < 0 for count in result.values()):
        raise ValueError("entity counts cannot be negative")
    return dict(sorted(result.items()))


def _page_counts(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        raise TypeError("page evidence is invalid")
    result: dict[str, int] = {}
    for page in value:
        if not isinstance(page, Mapping) or not isinstance(
            page.get("entity_kind"), str
        ):
            raise TypeError("page evidence is invalid")
        kind = str(page["entity_kind"])
        result[kind] = result.get(kind, 0) + 1
    return dict(sorted(result.items()))


def _catalog_dispositions(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise TypeError("catalog dispositions are invalid")
    safe_keys = (
        "entity_kind",
        "requirement",
        "disposition",
        "provider_status_classification",
        "error_classification",
        "observed_at",
    )
    return sorted(
        (
            {key: str(item[key]) for key in safe_keys if key in item}
            for item in value
            if isinstance(item, Mapping)
        ),
        key=lambda item: item.get("entity_kind", ""),
    )
